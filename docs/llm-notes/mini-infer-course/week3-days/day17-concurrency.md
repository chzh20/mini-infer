# Day 17：Python 并发模型 — 课程方案

> 所属项目：`mini-infer`（可扩展的迷你 LLM 推理流水线框架）
> 前置基础：Day 4 领域异常 / Day 10 组合注入（Engine 持有 Scheduler） / Day 14 无全局可变状态 / Day 16 测试分层
> 学员画像：EDA 工程师，C++/Java 背景（熟悉 pthread / `std::thread` / `ExecutorService` / Future / 背压）
> 设计依据：`roadmap.md` Day 17「为 batching 和 inference scheduler 奠定基础」

---

## 0. 课程概览与时间分配（总时长 ≈ 2.9 小时）

| 环节 | 内容 | 时长 |
|------|------|------|
| 开场 | 课程目标、为何 scheduler 需要并发心智模型 | 5 min |
| 3.1 | thread / process / asyncio 与 GIL（对照线程池） | 20 min |
| 3.2 | I/O-bound vs compute-bound；模型 forward 放哪 | 12 min |
| 3.3 | queue、backpressure、timeout、cancellation | 18 min |
| 3.4 | async API 与 sync API 边界（禁止半异步） | 12 min |
| 练习 1 | 异步队列骨架 + batch 取件 | 25 min |
| 练习 2 | 满队列背压 + timeout | 22 min |
| 练习 3 | 取消不泄漏 future + async/sync 边界文档 | 28 min |
| 收尾 | 课后测验讲解 + 总结与延伸阅读 | 14 min |

> 标注为「可压缩」：3.2 可并入 3.1；练习 3 文档可课后完成。核心不可删：**三种模型选型、有界队列背压、timeout/取消状态机、async/sync 边界**。

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

---

## 3. 详细讲解内容

### 3.1 thread / process / asyncio：对照你已有的并发工具箱

| 模型 | 近似 C++/Java | 擅长 | 不擅长 |
|------|---------------|------|--------|
| `threading` | pthread / 线程池 | I/O 等待、释放 GIL 的 C 扩展 | 纯 Python CPU 密集循环 |
| `multiprocessing` | 多进程 | CPU-bound、绕开 GIL | 共享内存复杂、启动成本高 |
| `asyncio` | 单线程事件循环 + Future | 高并发 I/O、调度协程、结构化并发 | 在 event loop 里跑重 CPU |

```text
                    ┌── threading: 多线程共享内存，受 GIL 约束
并发需求 ───────────┼── multiprocessing: 多进程真并行，通信贵
                    └── asyncio: 单线程协作式多任务，适合「大量等待」
```

**GIL（Global Interpreter Lock）**：同一时刻通常只有一个线程执行 Python 字节码。  
因此：**「开很多线程」不会让纯 Python 的 softmax 循环变快**。真正的矩阵算力往往在释放了 GIL 的 PyTorch / C++ 扩展里——那时多线程才可能重叠计算与等待。

对 `mini-infer` 的启示（今天就要讲透）：

- **请求接入、排队、超时、取消** → asyncio（或线程 + queue）很合适。
- **模型 forward** → 同步计算；可在 `asyncio.to_thread` / 线程池中调用，避免堵住 event loop。
- **真正并行纯 Python CPU** → 多进程或依赖原生扩展；不要幻想「asyncio 加速 matmul」。

---

### 3.2 I/O-bound vs compute-bound：把问题分类再选工具

| 类型 | 例子（推理框架） | 常见选择 |
|------|------------------|----------|
| I/O-bound | 等客户端、等远程 tokenizer、读大词表文件 | asyncio / 线程 |
| compute-bound（Python） | 纯 Python 循环做采样后处理 | multiprocessing 或改算法 / 下沉 |
| compute-bound（原生） | `torch` matmul | 让库跑；外层别堵 loop |

**错误示范**：在 `async def submit` 里直接跑长时间纯 Python 循环——整个服务的超时与取消全部卡死。  
**正确示范**：scheduler 协程只做「取 batch / 派发 / 写回 future」；重计算丢给线程或同步 worker。

---

### 3.3 queue、backpressure、timeout、cancellation

推理服务的最小调度骨架：

```text
Client --submit--> Queue --scheduler batch--> Worker(s) --set_result--> Future
```

关键概念（用 Java `BlockingQueue` / 背压经验对齐）：

| 概念 | 含义 | 做错的后果 |
|------|------|------------|
| Queue | 请求缓冲 | 无队列则无法 batch |
| 有界队列 | 容量上限 | 无界 = 延迟 OOM |
| Backpressure | 满时拒绝或阻塞 | 静默丢请求更糟 |
| Timeout | 等待过久明确失败 | 永远 pending 耗尽资源 |
| Cancellation | 结束 Future 且不泄漏 | 僵尸 waiter、回调写已死 Future |

教学骨架（完整实现见练习；注意竞态是难点）：

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
            # 过滤已取消；fake infer；set_result / set_exception
            ...
```

> **核心难点**：超时后 scheduler 仍可能取出该请求——必须统一状态机：写回前检查 `fut.cancelled()` / `fut.done()`，避免 `InvalidStateError`，也避免把结果写给已放弃的调用方却让资源逻辑以为「还活着」。

---

### 3.4 async API 与 sync API 边界

反模式（库作者最容易犯）：

```python
# ❌ 看起来是 sync，内部却 run_until_complete —— 嵌套 loop 噩梦
def submit(self, request):
    return asyncio.get_event_loop().run_until_complete(self._submit_async(request))
```

推荐边界：

- **对外提供清晰的一层**：要么 `AsyncInferenceEngine.submit`（async），要么同步 `InferenceEngine.generate`。
- 同步世界需要异步能力时，由**应用层**决定如何跑 loop（或用线程封装），库不要偷偷创建 / 复用 loop。
- 测试：async 测试用 `pytest-asyncio`；不要在单元测试里手工嵌套 loop。

```text
✅ 清晰
  CLI / Web 层 ── await ──► AsyncInferenceEngine
  脚本 / 笔记本 ── 同步 ──► InferenceEngine.generate

❌ 半异步
  库函数 sync 签名内部偷偷跑 event loop
```

写一份短文档 `docs/async-sync-boundary.md`（练习 3）：何时用 async 队列、何时保持同步 `generate`，以及禁止 `run_until_complete` 的原因。

---

## 4. 练习设计（3 个递进）

> 前置假设：已有 `InferenceRequest`、领域异常层级、组合注入的 Engine 骨架。今天用 **fake model**（`await asyncio.sleep` + 回显）验证调度语义。

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

---

### 练习 2（进阶 · 22 min）：背压 + timeout

**目标**：满载与超时有明确领域错误。

**任务**：
1. 队列满：`put_nowait` 失败 → `QueueFullError`（继承 `MiniInferError`）。
2. 等待超过 `timeout` → `RequestTimeoutError`。
3. 测试：打满队列断言背压；慢 worker + 短 timeout 断言超时。

**检查点 / 预期输出**：
```python
# 伪断言示意
with pytest.raises(QueueFullError):
    ...
with pytest.raises(RequestTimeoutError):
    ...
```
断言：错误类型稳定；`__cause__` 合理（可选）；日志可带 `request_id`（呼应 Day 5）。

---

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

6. 说明 `asyncio.wait_for` 与 `Future.cancel()` 在「已出队正在计算」时各自保证什么、不保证什么。

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
- **roadmap 衔接**：Day 18 先测量再优化；Day 26 continuous batching 会升级今天的队列语义；Week 4 读 vLLM scheduler 时会反复看到 waiting/running。

### 给讲师的复盘提示
- 用 `BlockingQueue.offer` 失败 = 背压 类比开场。
- 练习 3 的竞态（超时后仍出队）是区分「能跑 demo」与「能上服务」的分水岭——务必让学员写测试钉死。
- 强调今天用 fake model：目标是调度正确性，不是算力。
