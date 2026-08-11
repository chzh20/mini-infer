# Day 21：最小 Decoder-only Transformer — 课程方案

> 所属项目：`mini-infer`（可扩展的迷你 LLM 推理流水线框架）
> 前置基础：Day 19 Module 执行模型 / Day 20 `MiniAttention` / Day 9–10 Model 抽象与组合 / Day 15–16 packaging 与 CI
> 学员画像：EDA 工程师，C++/Java 背景（熟悉分层架构、残差/流水线式数据流）
> 设计依据：`roadmap.md` Day 21「把 attention 放回完整 block」

---

## 0. 课程概览与时间分配（总时长 ≈ 3.0 小时）

| 环节 | 内容 | 时长 |
|------|------|------|
| 开场 | 本周收束：从 packaging 到最小 Transformer | 5 min |
| 3.1 | 端到端数据流：ids → logits | 14 min |
| 3.2 | TransformerBlock：pre-norm、residual、FFN | 16 min |
| 3.3 | Embedding、位置信息、LM Head、权重共享 | 14 min |
| 3.4 | 工程约束：小配置、optional torch、测试分层 | 8 min |
| 练习 1 | 实现 Block + `MiniTransformer.forward` | 30 min |
| 练习 2 | 分层单元测试（Embedding / Block / 全模型） | 22 min |
| 练习 3 | shape-flow 图 + Protocol 接入 + Week 3 自测 | 28 min |
| 收尾 | 课后测验 + Week 3 成果核对 + 预告 Week 4 | 16 min |

> 标注为「可压缩」：权重共享可概念讲解不强制实现；位置编码可进阶。核心不可删：**`[B,T]→[B,T,V]` 契约、pre-norm block、分层测试、shape-flow 图、Week 3 五问自测**。

---

## 1. 课程目标

学完今天，学员应当能够：

1. **组装完整数据流**：`Embedding → N × TransformerBlock → Norm → LM Head → logits`。
2. **说清 Block 内部**：pre-norm vs post-norm（概念）、residual、FFN（`H→4H→H`）、因果 Attention 的位置。
3. **实现可跑模型**：小词表、小 hidden size，CPU 可测的 decoder-only Transformer。
4. **守住契约**：`forward(input_ids)` 输入 `[batch, sequence]`，输出 logits `[batch, sequence, vocab]`。
5. **分层验证**：Embedding / Block / 全模型各有单元测试；交付 shape-flow 图。
6. **完成本周验收**：对照 roadmap Week 3 输出成果与综合自测五问，能口头回答。

---

## 2. 知识点大纲

```text
最小 Decoder-only Transformer
├── 2.1 端到端数据流
│      ├── input_ids [B, T]
│      ├── Embedding / Position
│      ├── N × Block
│      ├── Final Norm
│      └── LM Head → logits [B, T, V]
├── 2.2 TransformerBlock
│      ├── pre-norm（教学默认）
│      ├── Attention + residual
│      └── FFN + residual
├── 2.3 词表投影与位置
│      ├── token embedding
│      ├── 位置信息（加性 / 诚实声明缺失）
│      ├── LM head
│      └── 权重共享概念
├── 2.4 工程约束
│      ├── 小配置 CPU 可测
│      ├── torch 仍为 optional
│      └── 只做 forward，不做训练
└── 2.5 Week 3 收束
       ├── 与 packaging/CI/并发/benchmark 的关系
       └── 综合自测五问
```

---

## 3. 详细讲解内容

### 3.1 端到端数据流：本周模型线的终点，下周生成线的起点

```text
input_ids          [B, T]
  → Token Embedding      [B, T, H]
  → (+ Position)         [B, T, H]
  → N × TransformerBlock [B, T, H]
  → Final Norm           [B, T, H]
  → LM Head              [B, T, V]   # logits
```

这就是 Week 4「naive generation」将反复调用的 `model(input_ids)`：取 `logits[:, -1, :]` 采样 next token。今天必须把 **logits 最后一维是词表 V** 刻进肌肉——与 hidden `H` 混淆是生成循环里最常见的 bug 预告。

---

### 3.2 TransformerBlock 解剖

教学推荐 **pre-norm**（现代 decoder 常见；本课以推理理解为主）：

```text
x
 ├─ LayerNorm → Attention → +  (residual)
 └─ LayerNorm → FFN       → +  (residual)
```

| 结构 | Norm 位置 | 本课态度 |
|------|-----------|----------|
| pre-norm | 子层前 | **默认实现** |
| post-norm | 子层后 | 概念了解即可 |

FFN 典型：

```python
# H → 4H → H
hidden = activation(linear1(x))
out = linear2(hidden)
```

Attention 使用 Day 20 的 `MiniAttention`（causal）。**残差能加的前提是每一支路保形 `[B,T,H]→[B,T,H]`**——先保形，再谈对错。

---

### 3.3 Embedding、位置、LM Head、权重共享

| 组件 | 作用 | 最小实现建议 |
|------|------|----------------|
| Token embedding | `nn.Embedding(V, H)` | 必做 |
| 位置信息 | 加性 `nn.Embedding(max_pos, H)` 或等价 | 建议做；若极简省略须在文档诚实写清后果 |
| Final Norm | 进 LM head 前归一化 | 必做（与 pre-norm 风格一致） |
| LM Head | `Linear(H, V)` → logits | 必做 |
| 权重共享 | embedding 与 LM head 共用矩阵 | 概念必懂；实现可选 |

```python
logits = lm_head(normalized_hidden)  # [B, T, V]
# 下一步（Week 4）：
# next_token = sampler.sample(logits[:, -1, :])
```

**没有位置信息的后果**（若你选择暂不做）：置换 token 顺序后模型难以区分——必须在 `docs/mini-transformer-shape-flow.md` 或 ADR 中写明，禁止假装「不需要位置」。

---

### 3.4 工程约束（呼应前两周与本周前半）

- **小配置示例**：`vocab=128, H=64, layers=2, heads=4, T<=32`，CPU 秒级可测。
- **依赖**：`torch` 仍为 optional extra；测试用 `pytest.importorskip("torch")` 或 CI matrix 的 torch job。
- **边界**：Engine 依赖 `Model` Protocol（Day 9/10）；`MiniTransformer` 是实现之一；调度测试继续用 FakeModel。
- **范围**：不引入训练循环——只做 `forward` 正确性。
- **异常**（可选）：非法 `input_ids` 越界可翻译为领域错误，或保留清晰的 PyTorch 错误并在边界记录。

---

### 3.5 本周串讲（收束用）

```text
Day 15 Packaging     源码 → wheel
Day 16 CI            规范 → 自动门禁
Day 17 并发          请求 → 队列 / 背压
Day 18 Benchmark     感觉 → 可复核数据
Day 19 PyTorch       Module / Tensor 执行模型
Day 20 Attention     核心算子
Day 21 Transformer   端到端 logits
```

前两周的类型、Protocol、组合注入、Adapter 隔离，使本周能把 `torch` 关在模型层而不污染 Engine——这是高级工程师课程真正要练的「迁移能力」。

---

## 4. 练习设计（3 个递进）

> 前置假设：Day 20 `MiniAttention` 测试已绿；`src/mini_infer/model/` 可扩展。

### 练习 1（基础 · 30 min）：实现 Block + MiniTransformer

**目标**：跑通 ids → logits。

**任务**：
```text
src/mini_infer/model/
  attention.py      # Day 20
  transformer.py    # Block + MiniTransformer
```
实现：
- `TransformerBlock`（pre-norm + residual + FFN + MiniAttention）
- `MiniTransformer.forward(input_ids) -> logits`

**检查点**：CPU 上小配置一次前向无异常；输出 shape `[B,T,V]`。

---

### 练习 2（进阶 · 22 min）：分层单元测试

**目标**：每个模块可独立证伪。

**任务**：
- Embedding 输出 shape `[B,T,H]`
- Block 保形 `[B,T,H] → [B,T,H]`
- 全模型 `[B,T] → [B,T,V]`
- 弱因果断言（可选）：固定权重下，改未来 token 不改变位置 `i` 的 logits

**检查点**：
```bash
python -m pytest tests/unit/test_attention.py tests/unit/test_transformer.py -q
```

---

### 练习 3（挑战 · 28 min）：shape-flow + Protocol + Week 3 核对

**目标**：文档交付 + 架构边界 + 本周验收。

**任务**：
1. 产出 `docs/mini-transformer-shape-flow.md`（或 mermaid），标注每一跳 shape；链接 Day 20 attention 图。
2. （推荐）Engine 仅依赖 `Model` Protocol；`MiniTransformer` 作为实现注册/注入；FakeModel 仍用于调度测试。
3. 对照下方「Week 3 输出成果核对清单」自检。
4. 口头完成综合自测五问（见 §5 / §6）。

**检查点 / 预期输出**：
```bash
python -m pytest tests/unit/test_attention.py tests/unit/test_transformer.py -q
python -m build   # 确认本周工程线仍绿；torch 测试在对应 job
```
断言：CPU 小配置 forward 通过；shape-flow 文档存在；清单项可勾选。

---

## 5. 课后测验 / 思考题

### 选择题

1. `MiniTransformer.forward` 的输出最后一维应是？
   a) `hidden_size`
   b) `num_heads`
   c) `vocab_size`
   d) `batch`

2. 残差连接要求子层输出 shape？
   a) 任意
   b) 与输入相同（通常 `[B,T,H]`）
   c) 必须是 `[B,H,T]`
   d) 必须是 logits

3. 本课默认 pre-norm 指？
   a) Norm 在子层后
   b) Norm 在子层前
   c) 不做 Norm
   d) Norm 只在 embedding

4. 为何本课坚持小词表小 H？
   a) 为了上线刷榜
   b) 保证 CPU 可测、可懂、可调试
   c) PyTorch 不支持大模型
   d) 为了避免写测试

### 编码思考题

5. 画出（或用文字列出）从 `input_ids` 到 `logits` 的每一步 shape。

6. 写一段伪代码：从 logits 取最后一个时间步并交给 `sampler.sample`（为 Day 24 预习）。

### 思考题（开放）+ Week 3 综合自测

**不看资料口答 5 题**（roadmap Week 3 自测标准）：

1. 如何构建 wheel 并在干净环境验证安装？验收命令是什么？
2. 写一个 async 队列时，timeout 与取消如何避免 future 泄漏？
3. 可信 benchmark 的报告必须包含哪六段字段？
4. `Module.__call__` 与 `forward` 有何区别？为什么推理要 `eval` + `inference_mode`？
5. 手写 causal attention 时，如何用测试证明「未来 token 权重为 0」？

---

## 6. 总结与延伸阅读建议

### 今日一句话总结
**把 Attention 嵌回 Block，再接到 Embedding 与 LM Head，得到可测的 `[B,T]→[B,T,V]`；这是生成循环与 KV cache 的挂载点。**

### 三条今天必须刻进肌肉记忆的规则
1. 先保形再谈对错；残差两侧 shape 必须一致。
2. logits 最后一维是词表，不是 hidden。
3. 小模型是特性：可测、可懂、可对照源码。

### 延伸阅读
- The Illustrated Transformer（形态直觉）。
- 任选一篇 decoder-only 结构说明（GPT-2 类 block 图即可）。
- **roadmap 衔接**：Day 24 naive generation；Day 25 给 Attention 加 KV cache；Day 29 对照 Transformers 源码中的同名结构。

### 给讲师的复盘提示
- 用 10 分钟做 Week 3 五问口答，暴露薄弱环节比再讲一层 FFN 更有价值。
- 检查 shape-flow 文档是否与测试一致——文档撒谎比缺文档更糟。
- 预告 Week 4：Tokenizer 流水线、autoregressive loop、KV cache、continuous batching、vLLM 导航——本周的 `forward` 将成为主战场。

---

## 附：Week 3 输出成果核对清单

对照 `roadmap.md`，本周结束时应有：

- [ ] 可构建、可安装的 wheel（干净 venv smoke 通过）
- [ ] 自动化 CI（lint / type / unit / integration / build / smoke）
- [ ] 可工作的异步请求队列（背压 / 超时 / 取消）
- [ ] benchmark 基线（`results.json` + `report.md`，结论含六段字段）
- [ ] 经过测试的最小 decoder-only Transformer
- [ ] 能从 shape 与数据流解释 `forward → attention → logits`
