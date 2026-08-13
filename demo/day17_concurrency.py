"""Demonstrate the concurrency concepts behind Day 17's scheduler.

Run it directly:

    python demo/day17_concurrency.py

Each section prints a short, self-explaining result so the behaviour is visible
without reading the source. Everything here is standard-library only — no
mini_infer dependency.
"""

import asyncio
import threading
import time


# ---------------------------------------------------------------------------
# [1] GIL: threads do NOT speed up pure-Python CPU work
# ---------------------------------------------------------------------------

def _cpu_task(n: int = 4_000_000) -> float:
    """A pure-Python CPU-bound loop (no I/O, no C extension)."""
    total = 0.0
    for i in range(n):
        total += i * 0.5
    return total


def demo_gil_blocks_cpu_speedup() -> None:
    """Two threads run the same CPU work as two serial calls — no speedup."""
    print("[1] GIL：双线程不会加速纯 Python 的 CPU 计算")

    start = time.perf_counter()
    _cpu_task()
    _cpu_task()
    serial = time.perf_counter() - start

    start = time.perf_counter()
    t1 = threading.Thread(target=_cpu_task)
    t2 = threading.Thread(target=_cpu_task)
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    threaded = time.perf_counter() - start

    print(f"    串行 2 个任务:   {serial:.3f}s")
    print(f"    双线程 2 个任务: {threaded:.3f}s  <- GIL 下不加速（甚至更慢）")


# ---------------------------------------------------------------------------
# [2] Waiting releases the GIL: threads DO help for I/O-style waits
# ---------------------------------------------------------------------------

def _io_wait(name: str) -> None:
    """Simulate I/O: the call blocks but releases the GIL while waiting."""
    time.sleep(1.0)


def demo_waiting_releases_gil() -> None:
    """Four threads each sleep 1s; total is ~1s, not ~4s."""
    print("\n[2] 等待会释放 GIL：4 个线程各 sleep 1s，总耗时 ~1s 而非 4s")

    start = time.perf_counter()
    threads = [threading.Thread(target=_io_wait, args=(f"t{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - start
    print(f"    4 线程并发等待，总耗时 {elapsed:.2f}s")


# ---------------------------------------------------------------------------
# [3] asyncio: concurrent I/O with a single thread
# ---------------------------------------------------------------------------

async def _fetch(name: str, delay: float) -> str:
    """Simulate a network request; await yields control while waiting."""
    await asyncio.sleep(delay)
    return f"{name} 完成"


async def demo_asyncio_io_speedup() -> None:
    """Three 1s requests: serial takes ~3s, concurrent takes ~1s."""
    print("\n[3] asyncio：单线程并发 I/O，等待不阻塞")

    start = time.perf_counter()
    serial = [await _fetch(n, 1.0) for n in ("A", "B", "C")]
    serial_t = time.perf_counter() - start

    start = time.perf_counter()
    concurrent = await asyncio.gather(
        _fetch("A", 1.0), _fetch("B", 1.0), _fetch("C", 1.0)
    )
    concurrent_t = time.perf_counter() - start

    print(f"    串行: {serial}  耗时 {serial_t:.2f}s")
    print(f"    并发: {concurrent}  耗时 {concurrent_t:.2f}s  <- 等待期间切换协程")


# ---------------------------------------------------------------------------
# [4] Bounded queue: backpressure instead of unbounded growth
# ---------------------------------------------------------------------------

class QueueFullError(Exception):
    """领域异常：队列满载。真实项目里应继承 MiniInferError。"""

    error_code = "E_QUEUE_FULL"


def demo_backpressure() -> None:
    """A maxsize=2 queue rejects the third item with an explicit error."""
    print("\n[4] 有界队列：满了就明确失败（背压），而不是无限堆积")

    q: asyncio.Queue[int] = asyncio.Queue(maxsize=2)
    for i in range(3):
        try:
            q.put_nowait(i)
            print(f"    入队 {i} 成功，当前 {q.qsize()}/{q.maxsize}")
        except asyncio.QueueFull:
            print(
                f"    入队 {i} 失败：队列已满 -> 抛 QueueFullError"
                f" ({QueueFullError.error_code})"
            )


# ---------------------------------------------------------------------------
# [5] Timeout + cancellation: the Future lifecycle state machine
# ---------------------------------------------------------------------------

async def _slow_worker(name: str, fut: asyncio.Future[str]) -> None:
    """Sleep, then write the result back — only if the future is still alive."""
    await asyncio.sleep(3.0)
    if not fut.done():
        fut.set_result(f"{name} 的结果")
    else:
        print("    [worker] future 已结束（超时/取消），跳过写回，避免 InvalidStateError")


async def demo_timeout_and_cancel() -> None:
    """A 1s caller timeout races a 3s worker; the worker must notice the dead future."""
    print("\n[5] timeout + 取消：future 有明确生命周期，写回前必须检查")

    loop = asyncio.get_running_loop()
    fut: asyncio.Future[str] = loop.create_future()
    worker = asyncio.create_task(_slow_worker("任务A", fut))

    try:
        result = await asyncio.wait_for(asyncio.shield(fut), timeout=1.0)
        print(f"    拿到结果: {result}")
    except asyncio.TimeoutError:
        print("    调用方 1s 超时（worker 要 3s）")
        if not fut.done():
            fut.cancel()  # 主动终结 future，向所有等待者广播「请求已死」

    await worker  # 等 worker 收尾，观察它如何跳过写回
    print(f"    future 最终状态: cancelled={fut.cancelled()}, done={fut.done()}")


# ---------------------------------------------------------------------------
# [6] Anti-pattern: nesting an event loop inside a sync-looking API
# ---------------------------------------------------------------------------

async def _inner() -> int:
    return 42


def sync_looking_api() -> int:
    """❌ 反模式：sync 签名内部偷偷 run_until_complete。"""
    coro = _inner()
    try:
        return asyncio.get_event_loop().run_until_complete(coro)
    except RuntimeError:
        coro.close()  # 显式关闭未消费的协程，避免 "never awaited" 警告
        raise


async def demo_nested_loop_anti_pattern() -> None:
    """Calling a run_until_complete API from inside a running loop blows up."""
    print("\n[6] 反模式：sync 接口内部偷偷跑 event loop")

    try:
        sync_looking_api()
        print("    意外成功？")
    except RuntimeError as exc:
        print(f"    ❌ 调用方已在自己 loop 里时，运行报错：{exc}")
    print("    结论：库不要偷偷创建/复用 loop；由应用层决定怎么跑")


def main() -> None:
    demo_gil_blocks_cpu_speedup()
    demo_waiting_releases_gil()
    asyncio.run(demo_asyncio_io_speedup())
    demo_backpressure()
    asyncio.run(demo_timeout_and_cancel())
    asyncio.run(demo_nested_loop_anti_pattern())


if __name__ == "__main__":
    main()
