# mini-infer

`mini-infer` 是一个面向 AI Infra 学习的迷你 LLM 推理流水线。当前版本建立
W1–W2 工程骨架：稳定领域对象、可替换组件、错误边界、生命周期日志和可测试的
naive generation loop。它刻意不伪装成完整推理引擎；PyTorch Transformer、KV
cache、continuous batching、C++/CUDA 后端会沿课程里程碑逐步加入。

## Quick start

要求 Python 3.11 或更高版本。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

mini-infer --version
python -m pytest
python -m ruff check .
python -m mypy
python examples/basic_generation.py
```

## 当前数据流

```text
InferenceRequest
      │
      ▼
InferenceEngine
      ├── Tokenizer.encode(prompt)
      ├── Model.next_token_logits(context)
      ├── Sampler.sample(logits, config)
      ├── repeat until stop/max_tokens
      └── Tokenizer.decode(generated tokens)
                  │
                  ▼
          GenerationResult
```

`InferenceEngine` 通过 `Protocol` 依赖四个边界：`Tokenizer`、`Model`、
`Sampler` 和 `MetricsSink`。核心层不导入 Transformers/PyTorch，第三方接口只能
通过 adapter 进入。`FifoScheduler` 与 `TokenCache` 先固定职责和所有权，后续再演进
为 continuous batching 与逐层 KV cache。

## 目录

```text
mini-infer/
├── src/mini_infer/
│   ├── config.py              # 不可变、运行时校验的配置
│   ├── protocols.py           # 组件间静态契约
│   ├── exceptions.py          # 领域异常层级
│   ├── tokenizer/             # 内置实现与第三方 adapter
│   ├── sampling/              # greedy / top-k strategy
│   ├── engine/                # request、scheduler、orchestration
│   └── model/                 # cache 与后续 Transformer 扩展位
├── tests/unit/
├── tests/integration/
├── benchmarks/
├── examples/
└── docs/
```

更详细的依赖规则见
[`docs/import-boundaries.md`](docs/import-boundaries.md)，演进次序见
[`docs/milestones.md`](docs/milestones.md)。

## 设计边界

- 配置和值对象不可变，运行态由明确的 owner 管理。
- Engine 组合组件，不通过继承扩展 tokenizer/sampler/model。
- Adapter 把第三方异常翻译为 `MiniInferError` 子类。
- 库不配置 root logger，日志只记录 request ID 和指标，不记录完整 prompt。
- 测试验证可观察行为；真实 Transformers/GPU 集成测试后续标为 optional/slow。

## 版本路线

- v0.1 skeleton：Python 工程基线、协议、naive loop（当前）。
- v0.2 model：PyTorch decoder-only Transformer、generation 与 KV cache 一致性。
- v0.3 scheduler：异步队列、dynamic/continuous batching、paged block manager。
- v0.4 native：C++/PyTorch 扩展与 golden tests。
- v0.5 CUDA：softmax/decode attention/paged attention 与 profiling。
- v1.0 portfolio：三后端一致性、benchmark、与 vLLM 受控对照。

## 非目标

当前版本不提供生产 Serving、模型权重加载、GPU kernel 或性能承诺。所有后续优化都
必须先有 golden test，再记录硬件、软件版本、输入形状、重复次数与误差。

