# Day 20：从公式到 Attention 实现 — 课程方案

> 所属项目：`mini-infer`（可扩展的迷你 LLM 推理流水线框架）
> 前置基础：Day 19 Tensor/Module/hook / Day 8 领域类型 / Day 6 参数化测试与数值近似断言
> 学员画像：EDA 工程师，C++/Java 背景（熟悉矩阵乘法、数值稳定、SIMD 思维）
> 设计依据：`roadmap.md` Day 20「理解 Transformer 的核心数据流」

---

## 0. 课程概览与时间分配（总时长 ≈ 2.9 小时）

| 环节 | 内容 | 时长 |
|------|------|------|
| 开场 | 今日只攻 Attention 数据流；与 Day 21 的分工 | 5 min |
| 3.1 | 公式、QKV、head_dim、reshape/transpose | 20 min |
| 3.2 | scaled dot-product 逐步 shape 契约 | 14 min |
| 3.3 | causal mask / padding mask；softmax 维 | 14 min |
| 3.4 | 数值稳定性；与参考实现对照策略 | 12 min |
| 练习 1 | 实现 `MiniAttention`（禁用 `nn.MultiheadAttention`） | 28 min |
| 练习 2 | shape + 因果权重测试 | 20 min |
| 练习 3 | 手算一致 + 参考近似 + shape-flow 图 | 28 min |
| 收尾 | 课后测验讲解 + 总结与延伸阅读 | 14 min |

> 标注为「可压缩」：3.4 对照可放练习 3；padding mask 可作为进阶。核心不可删：**分头 shape、`sqrt(d_k)`、causal → 未来权重为 0、softmax 在 key 维**。

---

## 1. 课程目标

学完今天，学员应当能够：

1. **从公式到代码**：推导 Q/K/V 投影 → 分头 → scores → mask → softmax → 加权 V → 合并头。
2. **算对维度**：掌握 `head_dim = hidden_size // num_heads`，以及 reshape/transpose 对 shape 的影响。
3. **手写核**：不使用 `nn.MultiheadAttention`，实现 scaled dot-product attention（含 causal mask）。
4. **证伪未来信息**：用测试证明 `j > i` 的注意力权重为 0（允许数值误差下的极小值）。
5. **稳住数值**：理解 `-inf` mask、除以 `sqrt(head_dim)`、softmax 维选择。
6. **对照参考**：与手算或 `scaled_dot_product_attention` / 自写第二实现做近似比较，并产出 shape-flow 图。

---

## 2. 知识点大纲

```text
从公式到 Attention 实现
├── 2.1 多头注意力数据流
│      ├── Q / K / V 投影
│      ├── head_dim = H // num_heads
│      └── reshape / transpose 分头与合并
├── 2.2 Scaled Dot-Product
│      ├── scores = Q K^T / sqrt(d_k)
│      ├── mask
│      ├── softmax(dim=key)
│      └── output = weights @ V
├── 2.3 Mask
│      ├── causal（禁止未来）
│      └── padding（忽略 pad）
├── 2.4 数值与验证
│      ├── -inf mask 与稳定性
│      ├── 单头手算
│      └── 与参考实现近似比较
└── 2.5 工程约束
       ├── 禁止把 MHA 当主路径黑盒
       └── 先核后层（先测 attention 核）
```

---

## 3. 详细讲解内容

### 3.1 公式、分头与 shape 契约

Scaled Dot-Product Attention：

\[
\mathrm{Attention}(Q,K,V)=\mathrm{softmax}\left(\frac{QK^{\top}}{\sqrt{d_k}}+\mathrm{mask}\right)V
\]

多头：把 `hidden_size`（记为 `H`）拆成 `num_heads * head_dim`，要求 **整除**；不能整除则是配置错误，应在构造期失败（呼应 Day 4 `ConfigurationError`）。

典型 shape 流（batch 优先）：

```text
x:            [B, T, H]
Q,K,V:        [B, T, H]          # 三次线性投影后
分头后:        [B, Hds, T, Dh]    # Hds=num_heads, Dh=head_dim
scores:       [B, Hds, T, T]     # q @ k^T
weights:      [B, Hds, T, T]     # softmax over last dim
out_heads:    [B, Hds, T, Dh]    # weights @ v
merge:        [B, T, H]          # transpose + reshape
out_proj:     [B, T, H]
```

**分头常见写法**：

```text
[B, T, H] → view(B, T, Hds, Dh) → transpose(1, 2) → [B, Hds, T, Dh]
```

> **转置错一维，后面所有 matmul 都会「能跑但语义错」**——必须靠测试抓，不能靠肉眼扫代码。

---

### 3.2 核心代码（教学版，与 roadmap 一致）

```python
import math
import torch


def attention_scores(
    q: torch.Tensor,
    k: torch.Tensor,
    v: torch.Tensor,
    *,
    head_dim: int,
    causal_mask: torch.Tensor,
) -> torch.Tensor:
    # q,k,v: [B, Hds, T, Dh]
    scores = q @ k.transpose(-2, -1)
    scores = scores / math.sqrt(head_dim)
    scores = scores.masked_fill(causal_mask, float("-inf"))
    weights = torch.softmax(scores, dim=-1)
    return weights @ v
```

讲解顺序建议（课堂上逐步板书 shape）：

1. 为什么 `@ k.transpose(-2, -1)` 得到 `[..., T, T]`？
2. 为什么除以 `sqrt(head_dim)`？（点积方差随维度增大，softmax 变「硬」）
3. 为什么 `masked_fill` 用 `-inf` 再 softmax？
4. 为什么 `softmax(..., dim=-1)` 是 **对每个 query 在 key 维上归一化**？

---

### 3.3 Causal mask 与 padding mask

**Causal（下三角可见）**：位置 `i` 不能看 `j > i` 的未来 token——decoder-only 的硬约束。

```python
T = seq_len
# True 表示「屏蔽」
causal = torch.triu(torch.ones(T, T, dtype=torch.bool), diagonal=1)
# 需要 broadcast 到 [B, Hds, T, T] 或依赖广播规则
```

**Padding mask**：pad 位置不应被 attend 到。可与 causal 合并为最终 bool mask（进阶任务）。

因果性断言：

```python
# 对任意 j > i，weights[..., i, j] ≈ 0
assert torch.all(weights[..., torch.arange(T)[:, None], torch.arange(T)] ...)
# 更直观：取 triu 区域检查 allclose(0)
```

---

### 3.4 数值稳定性与参考对照

| 做法 | 原因 |
|------|------|
| `masked_fill(..., -inf)` 再 softmax | 屏蔽位权重归零；避免「很大负数」在低精度下翻车 |
| `/ sqrt(head_dim)` | 控制点积幅度 |
| 先测「纯核」（给定 Q/K/V） | 排除投影权重布局差异 |
| 再测完整层 | 允许与 `nn.MultiheadAttention` 近似，注意 in_proj 打包差异 |

PyTorch 的 `MultiheadAttention` 仍是「投影 → 分头 → attention → 合并 → 输出投影」；满足条件时可能走优化 SDPA 路径。[docs.pytorch.org](https://docs.pytorch.org/docs/main/generated/torch.nn.modules.activation.MultiheadAttention.html)

**对照策略（推荐）**：

1. 先测纯 attention 核（相同 Q/K/V）。
2. 再测带投影的完整层（`torch.testing.assert_close` 设合理 atol/rtol）。
3. 单头极小例子（`T=2, Dh=2`）手算 scores → softmax → output。

> 口诀：**先核后层；先 shape 后数值；先因果后近似。**

---

## 4. 练习设计（3 个递进）

> 前置假设：已安装 `torch` extra；Day 19 hook 可用。文件落点：`src/mini_infer/model/attention.py`。

### 练习 1（基础 · 28 min）：实现 `MiniAttention`

**目标**：可调用的因果多头注意力层。

**任务**：
1. 实现类：`hidden_size`、`num_heads`、因果 mask；输入 `[B, T, H]`，输出同 shape。
2. **禁止**调用 `nn.MultiheadAttention` / `F.multi_head_attention_forward` 作为主路径。
3. 构造期检查 `hidden_size % num_heads == 0`。

**检查点**：模块可在 CPU 上 `eval()` + `inference_mode()` 前向。

---

### 练习 2（进阶 · 20 min）：shape + 因果性测试

**目标**：钉死硬约束。

**任务**：
```python
def test_attention_shape():
    ...
    assert out.shape == (B, T, H)

def test_causal_weights_no_future():
    # 通过返回 weights 的测试接口，或 hook 捕获 scores/weights
    ...
```

**检查点**：
```bash
python -m pytest tests/unit/test_attention.py -k "shape or causal" -q
```

---

### 练习 3（挑战 · 28 min）：手算 + 参考 + 文档

**目标**：正确性三角验证。

**任务**：
1. 构造极小手工例子（hardcode 期望 tensor），断言 `allclose`。
2. 相同 Q/K/V 下与 `torch.nn.functional.scaled_dot_product_attention`（若可用）或自写第二实现对比。
3. 把 shape 流图写入 `docs/attention-shape-flow.md`。

**检查点 / 预期输出**：
```bash
python -m pytest tests/unit/test_attention.py -q
# shape / causal / handcrafted / reference 四类断言全绿
```

---

## 5. 课后测验 / 思考题

### 选择题

1. `H=64, num_heads=8` 时 `head_dim` 是？
   a) 64
   b) 8
   c) 512
   d) 4

2. causal mask 屏蔽上三角，对应禁止的是？
   a) 过去 token
   b) 未来 token
   c) 全部 token
   d) 仅 CLS

3. 为什么要除以 `sqrt(head_dim)`？
   a) 为了改 shape
   b) 控制点积幅度，避免 softmax 过锐
   c) 为了启用 CUDA
   d) 只为了和论文页数一致

4. softmax 必须在哪一维？
   a) batch 维
   b) head 维
   c) key 维（通常最后一维）
   d) 任意维均可

### 编码思考题

5. 写出从 `[B,T,H]` 分头到 `[B,Hds,T,Dh]` 的两行 `view` + `transpose`。

6. 若误把 softmax 做到倒数第二维，因果测试通常会怎样失败？请描述可观察现象。

### 思考题（开放）

7. Day 25 引入 KV cache 后，哪些 shape 会变（K/V 的序列维），哪些不变（Q 在 decode 步常为 1）？今天的实现哪些假设需要改？

---

## 6. 总结与延伸阅读建议

### 今日一句话总结
**Attention 是带因果约束的加权平均；shape 与 mask 正确，比调用官方 MHA 黑盒更能支撑后续 KV cache 与源码阅读。**

### 三条今天必须刻进肌肉记忆的规则
1. 分头维序错 = 静默语义错；用测试钉死。
2. 未来位置权重必须为 0。
3. 先验证 attention 核，再包投影层。

### 延伸阅读
- [PyTorch MultiheadAttention](https://docs.pytorch.org/docs/main/generated/torch.nn.modules.activation.MultiheadAttention.html)
- 「Attention Is All You Need」中 Scaled Dot-Product 与 Multi-Head 两节（只读公式与图）。
- **roadmap 衔接**：Day 21 把 attention 嵌回完整 block；Day 25 给 Attention 加 KV cache。

### 给讲师的复盘提示
- 板书 shape 流比直接丢完整文件更有效；让学员跟写 `scores` shape。
- 因果测试是「魂」——没有它，Day 21/24 会带着错误进入生成循环。
- 强调禁止 MHA 黑盒：目标是可修改的理解，不是刷分。
