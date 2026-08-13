# Day 17：Python 并发模型 — 课程方案

> 所属项目：`mini-infer`（可扩展的迷你 LLM 推理流水线框架）
> 前置基础：Day 4 领域异常 / Day 10 组合注入（Engine 持有 Scheduler） / Day 14 无全局可变状态 / Day 16 测试分层
> 学员画像：EDA 工程师，C++/Java 背景（熟悉 pthread / `std::thread` / `ExecutorService` / Future / 背压）
> 设计依据：`roadmap.md` Day 17「为 batching 和 inference scheduler 奠定基础」
> 配套演示：`demo/day17_concurrency.py`（标准库实现，可直接运行验证每个概念）

---

## 0. 课程概览与时间分配（总时长 ≈ 2.9 小时）

| 环节 | 内容 | 时长 |
|------|------|------|
| 开场 | 课程目标、为何 scheduler 需要并发心智模型 | 5 min |
| 3.1 | 三种并发原语 + GIL（含演示①GIL 实验、②等待释放 GIL） | 24 min |
| 3.2 | I/O-bound vs compute-bound；模型 forward 放哪（含演示③） | 14 min |
| 3.3 | queue / backpressure / timeout / cancellation（含演示④⑤） | 24 min |
| 3.4 | async API 与 sync API 边界（含演示⑥反模式） | 12 min |
| 3.5 | 与推理系统的映射（Week 4 continuous batching 预习） | 6 min |
| 练习 1 | 异步队列骨架 + batch 取件 | 25 min |
| 练习 2 | 满队列背压 + timeout | 22 min |
| 练习 3 | 取消不泄漏 future + async/sync 边界文档 | 28 min |
| 收尾 | 课后测验讲解 + 总结与延伸阅读 | 14 min |

> 标注为「可压缩」：3.5 可并入 3.3 收尾；练习 3 文档可课后完成。核心不可删：**三种模型选型、有界队列背压、timeout/取消状态机、async/sync 边界**。
>
> **讲法提示**：演示 ①–⑥ 全部在 `demo/day17_concurrency.py` 中，每节先现场运行、看输出，再讲概念——让学员先"看见"再"理解"。

---

## 1. 课程目标

学完今天，学员应当能够：

1. **选型正确**：根据任务是 I/O-bound 还是 compute-bound，在 thread / process / asyncio 中做出可辩护的选择，并说清 GIL 的真实影响。
2. **画清骨架**：描述 `submit → queue → scheduler batch → worker → future` 的最小调度路径。
3. **实现背压**：用有界队列在满载时产生明确错误（领域异常），而不是无限堆积至 OOM。
4. **处理超时与取消**：`await engine.submit(request)` 支持 timeout；取消后不泄漏 future，scheduler 能识别「已死」请求。
5. **守住 API 边界**：库内不偷偷 `run_until_complete`；对外要么清晰 async，要么清晰 sync。
6. **为 Week 4 铺路**：今天的队列是 continuous batching scheduler 的雏形，测试用 fake model，不引入真实 GPU。

---

## 2. 知识点大纲

```text
Python 并发模型
├── 2.1 三种并发原语
│      ├── threading
│      ├── multiprocessing
│      └── asyncio
├── 2.2 GIL 与负载类型
│      ├── GIL 对纯 Python CPU 的影响
│      ├── I/O-bound vs compute-bound
│      └── PyTorch/C 扩展释放 GIL 的含义
├── 2.3 调度工程概念
│      ├── Queue（有界）
│      ├── Backpressure
│      ├── Timeout
│      └── Cancellation / Future 生命周期
├── 2.4 API 边界
│      ├── async Engine vs sync generate
│      └── 禁止库内嵌套 event loop
└── 2.5 与推理系统的映射
       ├── 请求接入与排队 → asyncio
       ├── forward → 同步计算（可 to_thread）
       └── Week 4 continuous batching 的预习
```

一句话概括今天的主线：**并发不是"多线程"一个词，而是"按负载类型选工具 + 用状态机管好每个请求的生死"**。三节内容层层递进：先认识工具（3.1）→ 学会选型（3.2）→ 实现调度（3.3）→ 守住边界（3.4）→ 展望未来（3.5）。

---

## 3. 详细讲解内容

### 3.1 三种并发原语：先看清工具箱里有什么

#### 3.1.1 一张表对齐你已有的并发经验

| Python 模型 | 近似 C++/Java | 擅长 | 不擅长 |
|-------------|---------------|------|--------|
| `threading` | pthread / 线程池 | I/O 等待、释放 GIL 的 C 扩展 | 纯 Python CPU 密集循环 |
| `multiprocessing` | 多进程 | CPU-bound、绕开 GIL | 共享内存复杂、启动成本高 |
| `asyncio` | 单线程事件循环 + Future | 高并发 I/O、调度协程、结构化并发 | 在 event loop 里跑重 CPU |

```text
                    ┌── threading: 多线程共享内存，受 GIL 约束
并发需求 ───────────┼── multiprocessing: 多进程真并行，通信贵
                    └── asyncio: 单线程协作式多任务，适合「大量等待」
```

#### 3.1.2 代码演示①：GIL 实验——双线程不加速纯 Python 计算

> 运行：`python demo/day17_concurrency.py`（第 1 段）

```python
import threading
import time

def _cpu_task(n: int = 4_000_000) -> float:
    """纯 Python 的 CPU 密集循环：没有 I/O，也没有 C 扩展。"""
    total = 0.0
    for i in range(n):
        total += i * 0.5
    return total

# 串行：同一线程连续跑两次
start = time.perf_counter()
_cpu_task(); _cpu_task()
serial = time.perf_counter() - start

# 双线程：两个线程各跑一次
start = time.perf_counter()
t1 = threading.Thread(target=_cpu_task)
t2 = threading.Thread(target=_cpu_task)
t1.start(); t2.start()
t1.join(); t2.join()
threaded = time.perf_counter() - start

print(f"串行 2 个任务:   {serial:.3f}s")
print(f"双线程 2 个任务: {threaded:.3f}s")
```

**预期输出（大致）**：

```text
串行 2 个任务:   0.37s
双线程 2 个任务: 0.23s   ← 没有变快（甚至更慢）
```

#### 3.1.3 代码演示②：等待释放 GIL——线程对 I/O 有效

> 运行：`python demo/day17_concurrency.py`（第 2 段）

```python
def _io_wait(name: str) -> None:
    """模拟 I/O：调用会阻塞，但等待期间会释放 GIL。"""
    time.sleep(1.0)

start = time.perf_counter()
threads = [threading.Thread(target=_io_wait, args=(f"t{i}",)) for i in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print(f"4 线程并发等待，总耗时 {time.perf_counter() - start:.2f}s")
```

**预期输出**：`4 线程并发等待，总耗时 1.01s`（而不是 4s）。

#### 3.1.4 概念解释：GIL 到底限制了什么

把演示①和②放在一起看，GIL 的行为就非常直观了：

**GIL（Global Interpreter Lock，全局解释器锁）**：同一时刻，通常只有一个线程在**执行 Python 字节码**。

- **演示①**：两个线程都在跑纯 Python 循环——它们都在"执行字节码"，所以被 GIL 串行化。开再多线程也不会让 softmax 的 Python 循环变快。
- **演示②**：`time.sleep` 期间线程在"等"，没有执行字节码，**锁被让出来**，其他线程可以继续跑。所以 4 个线程的等待可以重叠。

关键推论（今天必须讲透）：

| 场景 | GIL 影响 | 结论 |
|------|----------|------|
| 纯 Python CPU 循环 | 被串行化 | 多线程无用；用 multiprocessing 或改算法 |
| I/O 等待（网络、磁盘、sleep） | 等待时释放 GIL | 线程 / asyncio 都能并发 |
| PyTorch / C++ 扩展 | 扩展内部计算时释放 GIL | 多线程可能重叠计算与等待 |

> 对 `mini-infer` 的启示：真正的矩阵算力在释放了 GIL 的 PyTorch / C++ 扩展里——**别把并发心智用在错误的层**：请求接入、排队、超时、取消用 asyncio（或线程 + queue）；模型 forward 是同步计算，可丢给 `asyncio.to_thread` / 线程池，避免堵住 event loop。

---

### 3.2 I/O-bound vs compute-bound：把问题分类再选工具

#### 3.2.1 分类表

| 类型 | 例子（推理框架） | 常见选择 |
|------|------------------|----------|
| I/O-bound | 等客户端、等远程 tokenizer、读大词表文件 | asyncio / 线程 |
| compute-bound（Python） | 纯 Python 循环做采样后处理 | multiprocessing 或改算法 / 下沉 |
| compute-bound（原生） | `torch` matmul | 让库跑；外层别堵 loop |

#### 3.2.2 代码演示③：asyncio 并发 I/O vs 串行 I/O

> 运行：`python demo/day17_concurrency.py`（第 3 段）

```python
import asyncio
import time

async def _fetch(name: str, delay: float) -> str:
    """模拟一次网络请求：await 让出控制权，等待时不占 CPU。"""
    await asyncio.sleep(delay)
    return f"{name} 完成"

async def demo() -> None:
    # 串行：一个等完再发下一个
    start = time.perf_counter()
    serial = [await _fetch(n, 1.0) for n in ("A", "B", "C")]
    serial_t = time.perf_counter() - start

    # 并发：三个请求「同时」发出
    start = time.perf_counter()
    concurrent = await asyncio.gather(
        _fetch("A", 1.0), _fetch("B", 1.0), _fetch("C", 1.0)
    )
    concurrent_t = time.perf_counter() - start

    print(f"串行: {serial}  耗时 {serial_t:.2f}s")
    print(f"并发: {concurrent}  耗时 {concurrent_t:.2f}s")

asyncio.run(demo())
```

**预期输出**：

```text
串行: ['A 完成', 'B 完成', 'C 完成']  耗时 3.00s
并发: ['A 完成', 'B 完成', 'C 完成']  耗时 1.00s
```

#### 3.2.3 概念解释：为什么"等待"能并发而"计算"不能

- **I/O 等待的本质**：CPU 在等网络/磁盘时无事可做。asyncio 在这个空档切换到下一个协程，把"等的时间"重叠起来——所以 3 个 1 秒的请求并发只需 1 秒。
- **CPU 计算的本质**：计算是 CPU 真在干活，asyncio 不能"同时"干两份活，线程又受 GIL 限制。想让纯 Python 计算并行，只能上多进程或原生扩展。

**错误示范**：在 `async def submit` 里直接跑长时间纯 Python 循环——整个服务的超时与取消全部卡死。

**正确示范**：scheduler 协程只做「取 batch / 派发 / 写回 future」；重计算丢给线程或同步 worker：

```python
# ✅ 重计算不堵 event loop：交给线程池
import asyncio

async def submit(self, request):
    # ... 入队、等待 future ...
    result = await asyncio.to_thread(self._model.forward, batch)
    # forward 在独立线程里跑，event loop 继续服务其他请求
```

---

### 3.3 调度工程四件套：queue / backpressure / timeout / cancellation

#### 3.3.1 最小调度骨架

推理服务的最小调度路径：

```text
Client --submit--> Queue --scheduler batch--> Worker(s) --set_result--> Future
```

| 概念 | 含义 | 做错的后果 |
|------|------|------------|
| Queue | 请求缓冲 | 无队列则无法 batch |
| 有界队列 | 容量上限 | 无界 = 延迟 OOM |
| Backpressure | 满时拒绝或阻塞 | 静默丢请求更糟 |
| Timeout | 等待过久明确失败 | 永远 pending 耗尽资源 |
| Cancellation | 结束 Future 且不泄漏 | 僵尸 waiter、回调写已死 Future |

#### 3.3.2 代码演示④：有界队列背压

> 运行：`python demo/day17_concurrency.py`（第 4 段）

```python
import asyncio

class QueueFullError(Exception):
    """领域异常：队列满载。真实项目里应继承 MiniInferError。"""
    error_code = "E_QUEUE_FULL"

q: asyncio.Queue[int] = asyncio.Queue(maxsize=2)  # 容量上限 = 2

for i in range(3):
    try:
        q.put_nowait(i)          # 立即放入；队列满了立刻抛异常
        print(f"入队 {i} 成功，当前 {q.qsize()}/{q.maxsize}")
    except asyncio.QueueFull:
        print(f"入队 {i} 失败：队列已满 -> 抛 QueueFullError")
```

**预期输出**：前两个入队成功，第三个抛 `QueueFullError`。

**概念解释（背压）**：`asyncio.Queue(maxsize=N)` 的 `maxsize` 就是背压开关。`put_nowait` 在满时立即失败，调用方拿到一个**明确、可处理的领域异常**，而不是让请求无限堆积直到 OOM。对比无界队列：它只是"看起来没拒绝"，实际上把 OOM 风险推迟到了最坏的时刻。

#### 3.3.3 代码演示⑤：timeout + 取消状态机

> 运行：`python demo/day17_concurrency.py`（第 5 段）

```python
import asyncio

async def _slow_worker(name: str, fut: asyncio.Future[str]) -> None:
    """3 秒后才完成——比调用方的超时阈值（1s）慢得多。"""
    await asyncio.sleep(3.0)
    # 写回前必须检查：future 还活着吗？
    if not fut.done():
        fut.set_result(f"{name} 的结果")
    else:
        print("[worker] future 已结束（超时/取消），跳过写回")

async def demo() -> None:
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[str] = loop.create_future()
    worker = asyncio.create_task(_slow_worker("任务A", fut))

    try:
        # shield：wait_for 超时只取消「等待」，不取消 future 本身
        result = await asyncio.wait_for(asyncio.shield(fut), timeout=1.0)
        print(f"拿到结果: {result}")
    except asyncio.TimeoutError:
        print("调用方 1s 超时（worker 要 3s）")
        if not fut.done():
            fut.cancel()  # 主动终结 future，向所有等待者广播「请求已死」

    await worker  # 等 worker 收尾，观察它如何跳过写回
    print(f"future 最终状态: cancelled={fut.cancelled()}, done={fut.done()}")

asyncio.run(demo())
```

**预期输出**：

```text
调用方 1s 超时（worker 要 3s）
[worker] future 已结束（超时/取消），跳过写回
future 最终状态: cancelled=True, done=True
```

#### 3.3.4 概念解释：Future 生命周期状态机

这个演示藏着今天最核心的工程难点。把 future 想象成一张"请求状态卡"，它只有几种状态，且**只能向前转换**：

```text
pending ──set_result()──► done（有结果）
pending ──cancel()──────► cancelled（被放弃，也是 done）
pending ──异常写回──────► done（带异常）
```

三个细节必须讲透：

1. **`shield` 的作用**：`asyncio.wait_for(fut, t)` 超时后会**取消 `fut` 本身**；而 `wait_for(shield(fut), t)` 超时只取消"这次等待"，future 还活着——这样是否取消由我们自己的状态机决定，而不是被超时机制偷偷代劳。
2. **写回前必须查 `fut.done()`**：worker 算完时，调用方可能已经超时并 `cancel()` 了 future。此时再 `set_result` 会抛 `InvalidStateError`（对已结束的 future 写结果），而且更隐蔽的问题是：结果写给了一个**已放弃的调用方**，资源逻辑却以为请求"还活着"。
3. **取消是广播，不是回收**：`fut.cancel()` 只是把状态改为 cancelled，worker 自己醒来后要检查、要收尾（跳过写回）。**取消不泄漏 future** 的含义是：所有对该 future 的引用都有明确的终结路径。

> **核心难点**：超时后 scheduler 仍可能取出该请求——必须统一状态机：写回前检查 `fut.cancelled()` / `fut.done()`，避免 `InvalidStateError`，也避免把结果写给已放弃的调用方却让资源逻辑以为「还活着」。

#### 3.3.5 项目落点：AsyncInferenceEngine 骨架（练习 1–3 的目标）

把演示④⑤组合进 `mini-infer`，就是今天的工程目标（完整实现是练习任务，注意竞态是难点）：

```python
import asyncio
from dataclasses import dataclass

from mini_infer.exceptions import MiniInferError


class QueueFullError(MiniInferError):
    error_code = "E_QUEUE_FULL"


class RequestTimeoutError(MiniInferError):
    error_code = "E_TIMEOUT"


@dataclass
class InferenceRequest:
    request_id: str
    prompt: str


class AsyncInferenceEngine:
    def __init__(self, max_queue_size: int = 64, batch_size: int = 8) -> None:
        self._queue: asyncio.Queue[tuple[InferenceRequest, asyncio.Future[str]]] = (
            asyncio.Queue(maxsize=max_queue_size)
        )
        self._batch_size = batch_size
        self._scheduler_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._scheduler_task = asyncio.create_task(self._run_scheduler())

    async def submit(self, request: InferenceRequest, *, timeout: float = 5.0) -> str:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[str] = loop.create_future()
        try:
            self._queue.put_nowait((request, fut))
        except asyncio.QueueFull as exc:
            raise QueueFullError("请求队列已满") from exc
        try:
            return await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
        except asyncio.TimeoutError as exc:
            if not fut.done():
                fut.cancel()
            raise RequestTimeoutError(
                f"请求超时：{request.request_id}"
            ) from exc

    async def _run_scheduler(self) -> None:
        while True:
            batch: list[tuple[InferenceRequest, asyncio.Future[str]]] = []
            item = await self._queue.get()
            batch.append(item)
            while len(batch) < self._batch_size and not self._queue.empty():
                batch.append(self._queue.get_nowait())
            # 练习任务：过滤已取消；fake infer；set_result / set_exception
            ...
```

> 对照关系：`submit` 里的 `put_nowait` + `QueueFullError` 就是演示④；`wait_for(shield(...))` + `fut.cancel()` 就是演示⑤。概念演示是"微缩版"，这里是把它们放进真实类型体系（领域异常、`InferenceRequest`）。

---

### 3.4 async API 与 sync API 边界：拒绝"半异步"

#### 3.4.1 代码演示⑥：嵌套 event loop 反模式

> 运行：`python demo/day17_concurrency.py`（第 6 段）

```python
import asyncio

async def _inner() -> int:
    return 42

def sync_looking_api() -> int:
    """❌ 反模式：sync 签名内部偷偷 run_until_complete。"""
    coro = _inner()
    try:
        return asyncio.get_event_loop().run_until_complete(coro)
    except RuntimeError:
        coro.close()
        raise

async def main() -> None:
    # 调用方自己已经在一个 event loop 里
    sync_looking_api()   # 会怎样？

asyncio.run(main())
```

**预期输出**：`RuntimeError: This event loop is already running`。

#### 3.4.2 概念解释：为什么禁止 run_until_complete

事件循环是"一个进程一个"的独占资源。`run_until_complete` 要求"这个 loop 归我管"——但如果调用方（Web 框架、另一段 async 代码）已经在跑同一个 loop，就会冲突报错。更糟的是：即使碰巧能跑，库偷偷创建的 loop 也不会被正确关闭，造成资源泄漏与行为不可预测。

**结论**：**"看起来是 sync、内部跑 loop"的函数，在 async 调用方手里必炸**。这不是风格问题，是正确性问题。

#### 3.4.3 正确边界：应用层决定怎么跑 loop

```text
✅ 清晰
  CLI / Web 层 ── await ──► AsyncInferenceEngine
  脚本 / 笔记本 ── 同步 ──► InferenceEngine.generate

❌ 半异步
  库函数 sync 签名内部偷偷跑 event loop
```

- **对外提供清晰的一层**：要么 `AsyncInferenceEngine.submit`（async），要么同步 `InferenceEngine.generate`。
- 同步世界需要异步能力时，由**应用层**决定如何跑 loop（`asyncio.run` 或线程封装），库不要偷偷创建 / 复用 loop。
- 测试：async 测试用 `pytest-asyncio`；不要在单元测试里手工嵌套 loop。

---

### 3.5 与推理系统的映射：今天的队列是 Week 4 的雏形

| 今天学到的 | 在推理系统里的落点 |
|------------|--------------------|
| `asyncio.Queue` 有界队列 | 请求接入与排队（waiting 队列） |
| scheduler 批量取件 | continuous batching：多请求拼成一个 batch 跑 forward |
| 背压 / timeout / 取消 | 服务端 QoS：满载拒绝、慢请求超时、客户端断开即取消 |
| `asyncio.to_thread` 跑 forward | 不阻塞 event loop，同时让 GPU 计算与请求调度重叠 |
| fake model 验证调度 | 先验证调度语义正确，再上真实 GPU（Day 19+） |

**预习问题（留到 Week 4 回答）**：vLLM / 线上推理服务的 waiting 队列与 running 队列，和今天这个"单队列 + 批量取件"差在哪里？哪些假设在 GPU continuous batching 下会失效？

---

## 4. 练习设计（3 个递进）

> 前置假设：已有 `InferenceRequest`、领域异常层级、组合注入的 Engine 骨架。今天用 **fake model**（`await asyncio.sleep` + 回显）验证调度语义。
> 参考实现思路：概念演示见 `demo/day17_concurrency.py` 第 4、5 段；练习把演示中的机制搬进 `mini_infer` 的类型体系。

### 练习 1（基础 · 25 min）：异步队列骨架 + batch 取件

**目标**：多个 `submit` 能进入同一 batch。

**任务**：
1. 实现 `AsyncInferenceEngine`：`start` / `submit` / 后台 `_run_scheduler`。
2. 有界 `asyncio.Queue`；scheduler 一次最多取 `batch_size` 个。
3. 用 fake worker 证明「同批处理」（例如记录 `batch_id` 或日志）。

**检查点**：
```bash
python -m pytest tests/unit/test_async_engine.py -k batch -q
```
断言：并发提交的 N 个请求在同一调度轮次被取出（在 `batch_size` 允许范围内）。

### 练习 2（进阶 · 22 min）：背压 + timeout

**目标**：满载与超时有明确领域错误。

**任务**：
1. 队列满：`put_nowait` 失败 → `QueueFullError`（继承 `MiniInferError`）。
2. 等待超过 `timeout` → `RequestTimeoutError`。
3. 测试：打满队列断言背压；慢 worker + 短 timeout 断言超时。

**检查点 / 预期输出**：
```python
with pytest.raises(QueueFullError):
    ...
with pytest.raises(RequestTimeoutError):
    ...
```
断言：错误类型稳定；`__cause__` 合理（可选）；日志可带 `request_id`（呼应 Day 5）。

### 练习 3（挑战 · 28 min）：取消不泄漏 + 边界文档

**目标**：取消路径收敛；API 边界写清。

**任务**：
1. 取消 pending 请求后：Future 结束；scheduler 取出已取消请求时跳过，不 `set_result` 到已死 future。
2. `engine.close()` / `aclose()` 时取消 scheduler task，收集未完成任务，断言无泄漏。
3. 写 `docs/async-sync-boundary.md`。

**检查点**：
```bash
python -m pytest tests/unit/test_async_engine.py -q
# 覆盖：多请求入队、batch、timeout、queue full、cancel 无泄漏
```
断言：满队列有明确错误；取消后无悬挂 future；scheduler 停止时任务收敛。

---

## 5. 课后测验 / 思考题

### 选择题

1. 为什么「多线程跑纯 Python 的 token 循环」通常加速有限？
   a) 线程不能共享内存
   b) GIL 限制同一时刻执行 Python 字节码的线程数
   c) asyncio 更快所以线程无用
   d) Python 没有线程

2. 队列满时，推理服务更倾向？
   a) 静默丢请求
   b) 无限扩容
   c) 显式背压错误或阻塞策略（并度量）
   d) 重启进程

3. 请求已 timeout，但 scheduler 随后算完了，应该？
   a) 一定 `set_result`，调用方还能拿到
   b) 检查 future 状态，已结束则跳过写回
   c) 忽略结果并崩溃
   d) 自动重试三次

4. 库的同步公开 API 内部调用 `run_until_complete` 的主要风险是？
   a) 版本号错误
   b) 嵌套 event loop / 与调用方 loop 冲突
   c) 无法 import
   d) 覆盖率下降

### 编码思考题

5. 用伪代码写出 scheduler 取 batch 后过滤 `fut.cancelled()` 的逻辑。

6. 说明 `asyncio.wait_for` 与 `Future.cancel()` 在「已出队正在计算」时各自保证什么、不保证什么。（提示：回到演示⑤，`shield` 与直接 `wait_for` 的差别是什么？）

### 思考题（开放）

7. 对照 vLLM / 线上推理服务：waiting 队列与 running 队列和今天的单队列模型差在哪里？今天的实现哪些假设在 GPU continuous batching 下会失效？

---

## 6. 总结与延伸阅读建议

### 今日一句话总结
**并发模型按负载选型；有界队列给背压，超时与取消靠状态机收敛；async/sync 边界清晰比「到处都能调」更重要。**

### 三条今天必须刻进肌肉记忆的规则
1. GIL 下别指望多线程加速纯 Python CPU；forward 别堵 event loop。
2. 无界队列不是策略，是延迟爆炸。
3. 取消/超时后禁止向已死 Future 写结果。

### 延伸阅读
- Python 官方：`asyncio` 队列、Task 取消、`wait_for`、`to_thread`。
- Real Python / 官方 HOWTO：GIL 与何时用 multiprocessing。
- 本课配套演示：`demo/day17_concurrency.py`（改参数重跑，观察行为变化）。
- **roadmap 衔接**：Day 18 先测量再优化；Day 26 continuous batching 会升级今天的队列语义；Week 4 读 vLLM scheduler 时会反复看到 waiting/running。

### 给讲师的复盘提示
- 用 `BlockingQueue.offer` 失败 = 背压 类比开场。
- **先跑演示、再讲概念**：①GIL 计时对比、④背压报错、⑤worker 跳过写回这三段输出，是学员最可能"哦——原来如此"的时刻。
- 练习 3 的竞态（超时后仍出队）是区分「能跑 demo」与「能上服务」的分水岭——务必让学员写测试钉死。
- 强调今天用 fake model：目标是调度正确性，不是算力。
