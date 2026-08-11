# Day 19：PyTorch 执行模型 — 课程方案

> 所属项目：`mini-infer`（可扩展的迷你 LLM 推理流水线框架）
> 前置基础：Day 9 Protocol（Model 抽象） / Day 10 组合注入 / Day 15 optional `torch` extra / Day 18 测量习惯
> 学员画像：EDA 工程师，C++/Java 背景（熟悉数组布局、虚函数表、RAII、调试器断点）
> 设计依据：`roadmap.md` Day 19「理解 Tensor、Module 和 forward 调用路径」

---

## 0. 课程概览与时间分配（总时长 ≈ 2.8 小时）

| 环节 | 内容 | 时长 |
|------|------|------|
| 开场 | shape-first 阅读习惯宣言；今日与 Day 20/21 的关系 | 5 min |
| 3.1 | Tensor 四元组：shape / dtype / device / stride | 18 min |
| 3.2 | `nn.Module`：parameter vs buffer；`train` / `eval` | 14 min |
| 3.3 | `__call__` vs `forward`；hook；state_dict | 16 min |
| 3.4 | `no_grad` / `inference_mode` | 10 min |
| 3.5 | 错误归因分层（Python / Module / Tensor / device·dtype） | 8 min |
| 练习 1 | 实现 `TinyModel` + 保形测试 | 20 min |
| 练习 2 | forward hook 打印 shape + shape-flow 文档 | 22 min |
| 练习 3 | state_dict 检查 + 故意 mismatch 归因 | 25 min |
| 收尾 | 课后测验讲解 + 总结与延伸阅读 | 14 min |

> 标注为「可压缩」：3.5 可并入练习 3；无 GPU 时 device mismatch 用叙述 + shape mismatch 代替。核心不可删：**四元组、`__call__`≠直接 `forward`、`eval`+`inference_mode`、hook 看 shape**。

---

## 1. 课程目标

学完今天，学员应当能够：

1. **读懂 Tensor**：从 shape / dtype / device / stride 四元组描述任意中间值，并建立 shape-first 阅读习惯。
2. **用对 Module**：区分 parameter 与 buffer，正确使用 `train()` / `eval()`。
3. **走对调用路径**：说清用户应调用 `module(x)` 而非 `module.forward(x)`，以及 `__call__` 多做了什么。
4. **会用调试器替代物**：注册 forward hook 打印每层 I/O shape；用 `state_dict` 确认子模块注册。
5. **选对推理上下文**：在推理路径使用 `torch.inference_mode()`（或说明与 `no_grad` 的差别）。
6. **分层归因错误**：对 dtype/device/shape mismatch，能指出错误发生在哪一层抽象。

---

## 2. 知识点大纲

```text
PyTorch 执行模型
├── 2.1 Tensor 基础
│      ├── shape / dtype / device / stride
│      └── view / transpose / contiguous 直觉
├── 2.2 nn.Module
│      ├── 子模块注册
│      ├── Parameter vs Buffer
│      └── train() / eval()
├── 2.3 调用与调试
│      ├── __call__ 与 forward
│      ├── forward hook
│      └── state_dict
├── 2.4 梯度上下文
│      ├── no_grad()
│      └── inference_mode()
└── 2.5 错误归因
       ├── Python 层
       ├── Module 层
       ├── Tensor 契约层（shape）
       └── device / dtype 层
```

---

## 3. 详细讲解内容

### 3.1 Tensor：先看 shape，再看算子

阅读任何 PyTorch / Transformers / vLLM 代码时，固定先问：

```text
输入 shape 是什么？
dtype / device 是否一致？
这一步之后 shape 变成什么？
```

这就是本周后半程（Attention、Transformer）以及 Week 4/5 源码阅读的**统一入口习惯**。

```python
import torch

x = torch.randn(2, 8, 16)  # [batch, seq, hidden]
print(x.shape, x.dtype, x.device, x.stride())
```

| 字段 | C++ 直觉 | 读源码时的问题 |
|------|----------|----------------|
| shape | 各维长度 | 这一层期望什么布局？ |
| dtype | 元素类型 | fp32/fp16 是否混用？ |
| device | 内存域（CPU/CUDA） | 是否跨设备？ |
| stride | 指针算术步长 | 是 view 还是拷贝？转置后连续吗？ |

**stride** 决定内存遍历方式。`view` / `transpose` / `contiguous` 相关 bug 往往是「shape 看起来对，但内存布局不对」——Day 20 分头时会再次踩到。

---

### 3.2 `nn.Module`：参数、缓冲与模式

roadmap 给定的最小模型：

```python
import torch
import torch.nn as nn


class TinyModel(nn.Module):
    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        self.proj_in = nn.Linear(hidden_size, hidden_size * 4)
        self.proj_out = nn.Linear(hidden_size * 4, hidden_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj_out(torch.relu(self.proj_in(x)))
```

| 概念 | 含义 |
|------|------|
| Parameter | 可学习，出现在 `parameters()`，默认进 `state_dict` |
| Buffer | 随模型保存/搬 device，但不参与梯度（如 BN running mean） |
| `train()` | 启用 dropout / BN 更新等训练行为 |
| `eval()` | 推理行为模式；**不自动关闭梯度** |

推理时通常组合：

```python
model.eval()
with torch.inference_mode():
    y = model(x)
```

> 口诀：**`eval()` 改模块行为；`inference_mode()` 关梯度追踪。两件套，缺一不可想当然。**

---

### 3.3 `__call__` 与 `forward`：不要绕过钩子

用户应写 `model(x)`，而不是 `model.forward(x)`。

原因：`nn.Module.__call__` 会处理 hook、训练模式相关逻辑等，再调用你的 `forward`。直接调 `forward` 会跳过这些路径——**调试钩子时尤其致命**。

类比：你重写了业务 `process()`，但框架入口是带 AOP/拦截器的 `execute()`——绕过入口等于关掉所有探针。

```python
def shape_hook(module: nn.Module, inputs: tuple, output: torch.Tensor) -> None:
    inn = inputs[0] if inputs else None
    print(
        module.__class__.__name__,
        getattr(inn, "shape", None),
        getattr(output, "shape", None),
    )


handle = model.proj_in.register_forward_hook(shape_hook)
_ = model(torch.randn(2, 8, 32))
handle.remove()
```

**state_dict**：名字 → tensor 的权重快照。检查键名是确认「层是否被正确注册」的最快方法——忘了 `super().__init__()`，或把子模块赋成普通属性 / 随后改成 `None`，权重会从树上消失，`.to(device)` 也会漏搬。

---

### 3.4 `no_grad` vs `inference_mode`

| API | 作用 | 教学建议 |
|-----|------|----------|
| `torch.no_grad()` | 禁用梯度追踪，省内存 | 与 autograd 边界交互时可能仍需要 |
| `torch.inference_mode()` | 更严格的推理优化 | **推理路径优先** |

本课实现与测试默认：`model.eval()` + `torch.inference_mode()`。

---

### 3.5 错误发生在哪一层？

故意制造问题时，按层归因（训练「读报错」能力）：

1. **Python 层**：类型/None、错误调用方式。
2. **Module 层**：子模块未注册、`eval` 未开。
3. **Tensor 契约层**：shape 不匹配（`mat1 and mat2 shapes cannot be multiplied`）。
4. **device/dtype 层**：CPU tensor 进 CUDA 权重、`float` vs `half`。

今天的调试任务是练习这种归因，而不是死记报错文本。Day 20/21 的 shape 错误会落在第 3 层；真实多卡系统会大量出现第 4 层。

---

## 4. 练习设计（3 个递进）

> 前置假设：`pip install -e ".[torch,dev]"`。核心库保持 Day 15 的 optional 边界；测试可用 `pytest.importorskip("torch")`。

### 练习 1（基础 · 20 min）：实现 `TinyModel`

**目标**：可测试的最小 Module。

**任务**：
1. 放到 `src/mini_infer/model/tiny.py`（或 `examples/`，若进包则保持惰性/optional）。
2. 单元测试：输入 `[B, T, H]`，输出同 shape；在 `eval()` + `inference_mode()` 下可跑。

**检查点**：
```bash
python -m pytest tests/unit/test_tiny_model.py -q
```

---

### 练习 2（进阶 · 22 min）：hook + shape-flow 文档

**目标**：用 hook 代替「猜」。

**任务**：
1. 注册 forward hook，打印 `proj_in` / `proj_out` 的输入输出 shape。
2. 把一次完整调用的 shape 流记入 `docs/tiny-model-shape-flow.md`。

**检查点**：文档中有逐步 shape；与 hook 输出一致。

---

### 练习 3（挑战 · 25 min）：state_dict + mismatch 归因

**目标**：注册正确性 + 分层归因。

**任务**：
1. 打印 `state_dict().keys()`，确认 Linear 权重名存在。
2. 故意破坏注册（例如赋值普通对象或置 `None`），对比 keys 变化并写清。
3. 至少两类错误各一例：dtype mismatch；shape mismatch（无 GPU 可用 shape 代替 device）。在笔记中回答：**错误发生在什么抽象层？**

**检查点 / 预期输出**：
```text
docs/tiny-model-shape-flow.md 存在
笔记中有 dtype/shape（或 device）错误的分层归因
```

---

## 5. 课后测验 / 思考题

### 选择题

1. 为什么 `model.forward(x)` 在有 hook 时行为可能与 `model(x)` 不同？
   a) forward 更快所以跳过
   b) `__call__` 才会走 hook 等框架逻辑
   c) forward 不接受 Tensor
   d) 两者永远完全相同

2. parameter 与 buffer 的核心差别是？
   a) buffer 不能搬到 GPU
   b) parameter 默认参与梯度 / 优化器；buffer 保存但不作为可学习参数
   c) 只有 buffer 进 state_dict
   d) 没有差别

3. 仅调用 `model.eval()` 而不进 `inference_mode()` / `no_grad()`，仍可能多消耗？
   a) 仅磁盘
   b) autograd 相关的内存与追踪开销
   c) 仅网络
   d) 仅 GIL

4. shape-first 阅读习惯中，看到 `Linear(H, 4H)` 后，输入最后一维必须是？
   a) 4H
   b) H
   c) 任意
   d) batch 维

### 编码思考题

5. 写出注册 hook 打印「模块名 + 输入 shape + 输出 shape」的最小代码。

6. 解释：为何 `self.proj = nn.Linear(...); self.proj = None` 会导致 `state_dict` 异常或键缺失？

### 思考题（开放）

7. 若你要在 Transformers 某模型的 `forward` 里快速定位「哪一层把 `[B,T,H]` 变成了别的」，你会用 hook、断点还是手动 print？如何保证不提交调试代码？（提示：context manager 临时挂载 hook）

---

## 6. 总结与延伸阅读建议

### 今日一句话总结
**Tensor 用四元组说话，Module 用 `__call__` 执行；推理两件套 `eval` + `inference_mode`，调试先挂 hook 看 shape。**

### 三条今天必须刻进肌肉记忆的规则
1. 调 `module(x)`，别直接 `forward`。
2. 子模块必须挂在 Module 树上，否则 `state_dict` / `.to` 会漏。
3. 报错先归因到 Python / Module / shape / device·dtype 哪一层。

### 延伸阅读
- PyTorch 文档：`torch.nn.Module`、`register_forward_hook`、`torch.inference_mode`。
- 建议浏览（先不深挖）：`Module.__call__` 源码附近，只回答「调用 `module(x)` 时多做了什么」。
- **roadmap 衔接**：Day 20 手写 Attention；Day 29 三层对照的第一层就是今天的机制。

### 给讲师的复盘提示
- 开场反复强调 shape-first——这是本周从工程切换到模型的认知闸门。
- 练习 3 的「故意弄坏」比「只讲正确用法」记忆更深。
- 无 GPU 不要硬上 device 实验；shape/dtype 足以练归因。
