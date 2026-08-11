# Day 18：Profiling、Benchmark 与性能假设 — 课程方案

> 所属项目：`mini-infer`（可扩展的迷你 LLM 推理流水线框架）
> 前置基础：Day 5 可观测性（耗时字段） / Day 16 CI（benchmark 默认不进 PR 门禁） / Day 17 异步队列
> 学员画像：EDA 工程师，C++/Java 背景（熟悉 perf / VTune / JMH / 百分位延迟）
> 设计依据：`roadmap.md` Day 18「先测量，再优化」

---

## 0. 课程概览与时间分配（总时长 ≈ 2.8 小时）

| 环节 | 内容 | 时长 |
|------|------|------|
| 开场 | 「感觉慢」不是结论；建立测量纪律 | 5 min |
| 3.1 | `perf_counter` / `timeit` / `cProfile` 分层 | 16 min |
| 3.2 | CPU time vs wall time；latency vs throughput | 14 min |
| 3.3 | p50 / p95 / p99；平均值为何不够 | 12 min |
| 3.4 | warm-up、噪声、实验报告六段结构 | 14 min |
| 练习 1 | Benchmark harness + tokenizer 单请求/批量 | 25 min |
| 练习 2 | batch size / prompt 长度扫参 + cold/steady | 22 min |
| 练习 3 | scheduler 测量 + `results.json` / `report.md` | 28 min |
| 收尾 | 课后测验讲解 + 总结与延伸阅读 | 14 min |

> 标注为「可压缩」：3.1 工具演示可缩短；练习 2 与 3 可合并扫参维度。核心不可删：**百分位、warm-up 声明、六段结论、不进默认 PR CI**。

---

## 1. 课程目标

学完今天，学员应当能够：

1. **选对粒度**：用 `time.perf_counter`、`timeit`、`cProfile` 分别做区间计时、微基准与函数级画像。
2. **分清指标**：解释 CPU time vs wall time、latency vs throughput、cold start vs steady state。
3. **报告尾部**：给出 p50 / p95 / p99，而不是只报平均值。
4. **控制噪声**：固定输入、重复实验、记录环境、一次只改一个变量。
5. **产出可复核物**：`benchmarks/results.json` + `benchmarks/report.md`，每条结论含 roadmap 要求的六段字段。
6. **守住 CI 边界**：完整 benchmark 默认放 nightly/手动，不因噪声拖垮 PR fail-fast。

---

## 2. 知识点大纲

```text
Profiling、Benchmark 与性能假设
├── 2.1 测量工具分层
│      ├── time.perf_counter
│      ├── timeit
│      ├── cProfile / py-spy
│      └── 场景级 harness
├── 2.2 时间语义
│      ├── wall time vs CPU time
│      └── 异步等待为何「墙钟慢、CPU 不高」
├── 2.3 系统指标
│      ├── latency（单请求）
│      ├── throughput（req/s、tok/s）
│      └── p50 / p95 / p99
├── 2.4 实验纪律
│      ├── warm-up / cold start / steady state
│      ├── 重复次数与固定输入
│      └── 一次一变量
└── 2.5 报告与门禁
       ├── 六段结论模板
       ├── results.json + report.md
       └── benchmark ≠ 默认 PR 门禁
```

---

## 3. 详细讲解内容

### 3.1 测量工具分层：先问「我要回答什么问题」

**类比**：VTune / perf 看热点，JMH 做微基准，线上监控看百分位——三者不可互相替代。Python 同样如此。

| 工具 | 粒度 | 回答的问题 |
|------|------|------------|
| `time.perf_counter()` | 手动区间 | 这段业务路径耗时多少？ |
| `timeit` | 微基准 | 两个小函数谁更快？（自动重复） |
| `cProfile` / `py-spy` | 函数级 | 时间花在哪个函数？ |
| 自定义 harness | 场景级 | 某 batch size 下 p99 / throughput？ |

```python
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def timed(fn: Callable[..., T], *args: object, **kwargs: object) -> tuple[T, float]:
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, time.perf_counter() - t0
```

> 口诀：**工具服务问题；没有问题的 profiling 只是好看的火焰图。**

---

### 3.2 CPU time vs wall time；latency vs throughput

**CPU time vs wall time**：

- **wall time**：墙上时钟（含等待、调度、I/O、锁竞争）。
- **CPU time**：进程实际占用 CPU 的时间。

在 Day 17 的异步队列里，大量时间可能是**等待**——wall ↑ 但 CPU 不高。此时「优化 matmul」是南辕北辙；应看队列、batch 策略、超时。

**Latency vs Throughput**（推理系统的基本语言）：

| 指标 | 含义 | 典型单位 |
|------|------|----------|
| Latency | 单请求从 submit 到完成 | ms / s |
| Throughput | 单位时间完成量 | req/s、tok/s |

**反直觉事实**：提高 batch size 常使 throughput ↑，同时**单请求 latency ↑**。优化目标必须先声明——服务交互看 latency 尾部，离线灌库看 throughput。

---

### 3.3 百分位：平均值为什么不够

只报平均值会骗人：一条长尾拖死 p99，平均值仍然「好看」。用户体验与 SLA 看的是尾部。

```python
import statistics


def percentiles(samples: list[float]) -> dict[str, float]:
    s = sorted(samples)

    def pct(p: float) -> float:
        if not s:
            return float("nan")
        k = min(len(s) - 1, max(0, int(round((p / 100) * (len(s) - 1)))))
        return s[k]

    return {
        "p50": pct(50),
        "p95": pct(95),
        "p99": pct(99),
        "mean": statistics.fmean(s) if s else float("nan"),
    }
```

教学要求：所有场景级结论至少带 **p50 / p95 / p99**（样本量极小时注明「仅供参考」）。

---

### 3.4 Warm-up、噪声与六段报告纪律

**必须 warm-up**：第一次调用常含 import、缓存分配、磁盘冷启动、分支预测。报告中要区分：

- **cold start**（含首次）
- **steady state**（丢弃前 N 次后的稳态）

**降低噪声的最低要求**：

1. 固定输入（同一组 prompt、同一 batch size）。
2. 重复足够次数（例如 30～100，视耗时而定）。
3. 记录环境：CPU 型号、Python 版本、是否装了 torch、进程亲和、是否省电模式。
4. **一次只改一个变量**（batch size **或** prompt 长度，不要同时改）。
5. 写明**尚未排除的变量**（例如机器上是否有其他负载）。

roadmap 强制六段（每条结论）：

```text
假设：
环境：
输入：
重复次数：
结果：
尚未排除的变量：
```

> 项目落点：没有六段字段的「优化建议」在本课程中**不算交付**。

---

## 4. 练习设计（3 个递进）

> 前置假设：已有 tokenizer（Whitespace 或 Adapter）与 Day 17 的 async engine（可用 fake）。创建 `benchmarks/` 目录。

### 练习 1（基础 · 25 min）：Harness + tokenizer 基础测量

**目标**：可复用的计时与百分位工具。

**任务**：
1. 创建 `benchmarks/`：`bench_tokenizer.py`、公共 `bench_lib.py`（计时、百分位、写 JSON）。
2. 测量单请求 encode latency（steady state）。
3. 测量 batched encode throughput。

**检查点**：运行脚本能打印 p50/p95/p99；结果可写入结构体/JSON。

---

### 练习 2（进阶 · 22 min）：扫参 + cold/steady

**目标**：学会一次一变量。

**任务**：
1. 不同 prompt 长度（短 / 中 / 长）各跑一组。
2. 明确 warm-up 次数；同时记录 cold start 与 steady state。
3. 在报告中用表格对比，不写「感觉差不多」。

**检查点**：报告中能看出长度对 latency 的趋势；cold 与 steady 数值分开列出。

---

### 练习 3（挑战 · 28 min）：scheduler 测量 + 双文件交付

**目标**：满足 roadmap 产出物。

**任务**：
1. `bench_scheduler.py`：不同 batch size 下的 latency 与 throughput；接近满载时的 timeout/拒绝率（稳定性指标）。
2. 写 `benchmarks/results.json`（机器可读）。
3. 写 `benchmarks/report.md`（人可读），**至少 3 条**结论含六段字段。
4. 在文档注明：默认 PR CI 不跑完整 benchmark。

**检查点 / 预期输出**：
```bash
python benchmarks/bench_tokenizer.py --out benchmarks/results.json
# report.md 中至少 3 条带六段字段的结论
```
断言：JSON 含百分位；报告区分 cold/steady；无「感觉变快了」式无数据句子。

---

## 5. 课后测验 / 思考题

### 选择题

1. throughput 上升时，p99 latency 一定下降吗？
   a) 一定
   b) 不一定；例如加大 batch 提高吞吐同时拉高单请求等待
   c) 一定上升
   d) 与 latency 无关故无关系可谈

2. 为什么完整 benchmark 默认不放进每次 PR 的 fail-fast 门禁？
   a) 太容易写
   b) 噪声大、耗时长，易造成不稳定红灯
   c) Python 不能测性能
   d) 覆盖率已足够

3. `cProfile` 显示某函数占 80% CPU，是否足以决定必须重写该函数？
   a) 是
   b) 否；还需确认是否在关键路径、是否 wall 瓶颈、收益与风险
   c) 是，且应立刻上多线程
   d) 否，因为只能用 timeit

4. 把冷启动次数混进 steady state 样本，最可能导致？
   a) 版本号错误
   b) 错误的架构结论（高估或低估稳态成本）
   c) mypy 失败
   d) wheel 无法构建

### 编码思考题

5. 写出一段伪代码：丢弃前 `warmup` 次，对剩余样本算 p50/p95/p99。

6. 设计一个「一次一变量」实验：验证 batch_size 对 async engine 的影响时，哪些因素必须固定？

### 思考题（开放）

7. 对照你们用 JMH/perf 的经验：Python harness 最容易踩的三个陷阱是什么？如何在 `report.md` 里预先披露？

---

## 6. 总结与延伸阅读建议

### 今日一句话总结
**先测量，再优化；用百分位与六段报告让结论可复核、可证伪，而不是用平均值讲故事。**

### 三条今天必须刻进肌肉记忆的规则
1. 声明 cold vs steady，声明环境与重复次数。
2. 至少报告 p50/p95/p99；一次只改一个变量。
3. benchmark 产出 `results.json` + `report.md`；默认不进 PR fail-fast。

### 延伸阅读
- Python 文档：`time.perf_counter`、`timeit`、`profile` / `cProfile`。
- Google Benchmark / JMH「避免常见陷阱」（可迁移到 Python harness）。
- **roadmap 衔接**：Day 19 起进入 PyTorch；Day 30 性能回归实验复用今天的百分位语言。

### 给讲师的复盘提示
- 当场演示「平均值好看、p99 难看」的人造长尾样本，说服力极强。
- 检查报告时只问一句：「六段字段齐了吗？」不齐即未完成。
- 预告明天：测量能力就绪后，用 shape-first 读 PyTorch 执行路径。
