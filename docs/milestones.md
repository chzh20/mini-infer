# Milestones

本文件把两份课程文档压缩为项目演进门禁；每个里程碑都要求代码、测试、数据和解释。

| 里程碑 | 核心增量 | 验收证据 |
|---|---|---|
| W1 | src layout、领域对象、异常、日志、CLI | install/test/lint/type 全绿 |
| W2 | Protocol、DI、tokenizer adapter、greedy/top-k | 组件契约测试、无反向依赖 |
| W3 | asyncio 请求队列、benchmark、profiling 基线 | 延迟/吞吐测量可复现 |
| W4–6 | PyTorch 模块、Transformer、naive/KV generation | cache/no-cache 输出一致 |
| W7–8 | continuous batching、paged block manager | 调度与缓存不变量测试 |
| W10–11 | C++ backend、torch.ops/pybind11 | Python/C++ golden test |
| W12–14 | CUDA softmax/decode/paged attention | 随机与边界 golden test、Nsight 数据 |
| W15 | TP=1/2、量化与通信对照 | TTFT/TPOT/QPS/显存表 |
| W22 | v1.0 三后端整合 | 100+ 测试、wheel、完整 benchmark |

## 当前 Definition of Done

- 公共 API 有类型标注，配置输入有运行时校验。
- tokenizer、model、sampler 可以独立替换。
- 错误保留 `__cause__`，日志可以按 request ID 串联且不包含 prompt。
- `pytest` 全绿；安装后的 console script 可运行。
- 未实现模块明确标记里程碑，不放入不可验证的“假实现”。

