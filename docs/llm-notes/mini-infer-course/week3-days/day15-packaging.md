# Day 15：现代 Packaging — 课程方案

> 所属项目：`mini-infer`（可扩展的迷你 LLM 推理流水线框架）
> 前置基础：Day 1 工程基线（`pyproject.toml` / `src` layout / 可编辑安装） / Day 3 公共 API 边界 / Day 14 无全局耦合
> 学员画像：EDA 工程师，C++/Java 背景（熟悉 `.so` / `.jar` / Maven 坐标 / CMake `install`）
> 设计依据：`roadmap.md` Day 15「从源码目录到 wheel」

---

## 0. 课程概览与时间分配（总时长 ≈ 2.8 小时）

| 环节 | 内容 | 时长 |
|------|------|------|
| 开场 | 课程目标、从「能跑」到「能发布」的跃迁 | 5 min |
| 3.1 | sdist vs wheel、build backend（CMake/Maven 对照） | 18 min |
| 3.2 | 项目 metadata 与 semantic versioning | 12 min |
| 3.3 | 生产依赖 vs optional extras（隔离重型 ML 依赖） | 15 min |
| 3.4 | entry point、package data、src layout 发现 | 12 min |
| 3.5 | editable install vs 普通 install；公共 API 复核 | 12 min |
| 练习 1 | 完善 `pyproject.toml`（metadata / extras / scripts） | 22 min |
| 练习 2 | `python -m build` 产出 sdist + wheel | 20 min |
| 练习 3 | 干净 venv 装 wheel + smoke + 发布清单 | 28 min |
| 收尾 | 课后测验讲解 + 总结与延伸阅读 | 14 min |

> 标注为「可压缩」：3.2 可并入 3.1；练习 3 的清单文档可课后完成。核心不可删：**sdist/wheel 区别、optional extras、干净环境装 wheel、entry point 可用**。

---

## 1. 课程目标

学完今天，学员应当能够：

1. **分清产物**：说清 source distribution（sdist）与 wheel 各自是什么、用户日常 `pip install` 通常拿到哪个。
2. **说清构建链**：解释 `pyproject.toml` 声明「是什么」、build backend 决定「怎么打成包」，并能对照 CMake/Maven 心智模型。
3. **配好依赖边界**：把核心依赖与 `dev` / `torch` / `transformers` 可选依赖分层，使核心库不强制装重型 ML 栈。
4. **落地分发面**：配置 CLI entry point、确认 `src` layout 被正确打进包、理解 semver 与 `__all__` 公开 API 的契约关系。
5. **验证可发布**：在干净虚拟环境安装 wheel，验证 import 与 `mini-infer --version`，发现「editable 能用、wheel 缺文件」类问题。
6. **写出清单**：留下最短发布检查清单，作为 Day 16 CI smoke 与 Day 30 发布的基线。

---

## 2. 知识点大纲

```text
现代 Packaging
├── 2.1 分发产物
│      ├── sdist（.tar.gz）vs wheel（.whl）
│      └── 用户安装路径实际拿到什么
├── 2.2 构建系统
│      ├── pyproject.toml 声明
│      ├── build backend（hatchling / setuptools）
│      └── python -m build 流水线
├── 2.3 项目 metadata 与版本
│      ├── name / version / requires-python / license
│      └── semantic versioning（MAJOR.MINOR.PATCH）
├── 2.4 依赖分层
│      ├── production dependencies（瘦核心）
│      └── optional-dependencies：dev / torch / transformers
├── 2.5 分发面细节
│      ├── [project.scripts] entry point
│      ├── package data（非 .py 资源）
│      └── src layout 包发现
└── 2.6 安装模式与验收
       ├── editable vs 普通 install
       ├── 干净 venv smoke
       └── 公共 API 边界复核
```

---

## 3. 详细讲解内容

### 3.1 什么是 sdist / wheel，为什么需要 build backend

**类比（C++/Java 工程师最熟悉）**：

| Python | 近似对应 |
|--------|----------|
| sdist（`.tar.gz`） | 源码包 / Maven source jar / `tar` 起来的源码树 |
| wheel（`.whl`） | 预构建可安装包（纯 Python 时无编译，但仍是「可直接装进 site-packages」的产物） |
| build backend | CMake / Maven 里「真正执行构建」的那一层 |
| `pip install` | 下载产物 →（必要时构建）→ 安装到环境 |

```text
源码树（src/mini_infer/...）
        │
        │  python -m build
        ▼
   ┌─────────────┬─────────────┐
   │  sdist      │  wheel      │
   │  .tar.gz    │  .whl       │
   └─────────────┴─────────────┘
        │              │
        │              └── 用户日常 pip 优先装这个
        └── 需要从源码再构建时用（或提供给需要编译扩展的消费者）
```

**为什么不能只靠「把目录 zip 一下」？** 因为现代安装工具需要标准 metadata（依赖、Python 版本、入口脚本），并且要知道哪些文件属于包、哪些是开发垃圾（测试、本地 venv、`.pyc`）。build backend 按规范读取 `pyproject.toml`，产出符合 [PyPA](https://packaging.python.org/) 约定的产物。

`pyproject.toml` 里的关键段：

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mini-infer"
version = "0.1.0"
description = "A minimal, extensible LLM inference pipeline"
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "mini-infer contributors" }]
```

> 口诀：**`pyproject.toml` 声明「是什么」；build backend 决定「怎么打成包」。** Day 1 的 `pip install -e .` 已经依赖这段配置；今天要验证它在**非可编辑**安装下同样正确。

---

### 3.2 项目 metadata 与 semantic versioning

**metadata 最少集合**（缺一项就会在发布或安装时埋雷）：

| 字段 | 作用 |
|------|------|
| `name` | PyPI / 安装坐标（注意与 import 名 `mini_infer` 可能不同） |
| `version` | 版本契约 |
| `requires-python` | 拒绝不支持的解释器 |
| `readme` / `license` / `authors` | 人类与工具可读的项目身份 |
| `dependencies` | 装上就能跑的最小集合 |

**Semantic Versioning（`MAJOR.MINOR.PATCH`）**，对高级工程师的精确含义：

- **PATCH**：修复，公开 API 不变。
- **MINOR**：向后兼容的功能（新增符号、新增可选参数且有默认值）。
- **MAJOR**：破坏性变更（删除/改名公共 API、改默认行为导致静默语义变化）。

把 Day 3 的 `mini_infer.__all__` 当作「公开 ABI」——**版本号承诺的是这部分，不是内部模块**。内部 `mini_infer.engine._helpers` 怎么改都不该偷偷涨 MAJOR；反过来，改了 `__all__` 里的签名却只涨 PATCH，会破坏下游信任。

```python
# src/mini_infer/__init__.py（示意）
from .config import SamplingConfig
from .engine.engine import InferenceEngine

__all__ = ["SamplingConfig", "InferenceEngine", "__version__"]
__version__ = "0.1.0"
```

> 工程提醒：`__version__` 与 `pyproject.toml` 的 `version` 应单一来源或同步策略明确，避免「CLI 报 0.1.0、metadata 却是 0.0.1」。

---

### 3.3 生产依赖 vs optional dependencies

生产依赖要尽量瘦；重型依赖（PyTorch、Transformers）进 optional extras——这与 Day 13 Adapter「核心层不 import 第三方」是同一条边界在**安装维度**的投影。

```toml
[project]
dependencies = [
  # 核心运行时：尽量无重型 ML 依赖
  # 例如：无 torch、无 transformers
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0",
  "pytest-cov>=5.0",
  "ruff>=0.6",
  "mypy>=1.11",
  "build>=1.2",
]
torch = ["torch>=2.2"]
transformers = ["transformers>=4.40"]
# 常用组合：
#   pip install "mini-infer[torch,transformers]"
#   pip install -e ".[dev,torch]"
```

| 安装方式 | 适用场景 |
|----------|----------|
| `pip install mini-infer` | 只要 tokenizer / scheduler / 纯 Python 逻辑 |
| `pip install "mini-infer[torch]"` | 需要 `MiniTransformer` forward |
| `pip install "mini-infer[transformers]"` | 需要 HF Adapter |
| `pip install -e ".[dev,torch]"` | 本机开发 + 模型测试 |

**反模式**：把 `torch` 放进 `project.dependencies`「图省事」——任何只想用队列与采样策略的用户都被迫下载数百 MB，且 CI 矩阵被拖慢。

> 项目落点：Week 3 后半程会实现 PyTorch 模型，但**打包边界今天就定死**——模型代码可以存在于仓库，安装时仍通过 extras 选择是否拉取 `torch`。

---

### 3.4 entry point、package data、src layout 发现

**CLI entry point**（把 Day 1 的 `python -m mini_infer.cli` 升级为真正的 console script）：

```toml
[project.scripts]
mini-infer = "mini_infer.cli:main"
```

安装后用户可直接：

```bash
mini-infer --version
```

这与 C++ 安装后的 `bin/` 可执行文件、Java 的 `Main-Class` / `jpackage` 入口是同一类产品体验：用户装完第一件事不是 `python -m ...`，而是敲命令名。

**package data**：非 `.py` 资源（默认词表、JSON schema、小配置模板）默认不一定进 wheel，需按 backend 显式纳入：

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/mini_infer"]

# 若有非代码资源，按 hatchling 文档配置 force-include / 包内资源约定
```

**src layout 为何在 packaging 时更关键**：可编辑安装时，工具知道去 `src/` 找包；一旦配置错误，常见翻车是「开发机 `import mini_infer` 成功（因为 PYTHONPATH/editable），wheel 里却是空包或旧结构」。今天必须用**干净 venv + 装 wheel**戳穿幻觉。

---

### 3.5 editable vs 普通 install；公共 API 复核

| 方式 | 命令 | 行为 |
|------|------|------|
| editable | `pip install -e .` | 改源码立即生效；适合开发 |
| 普通 | `pip install dist/*.whl` | 安装到 site-packages 的**拷贝**；改仓库源码不影响已安装包 |

**今天必须做一次「干净 venv + 装 wheel」**——这是发现「漏打进包的文件 / 错误的 package discovery / entry point 未生效」的最快方法。editable 下「能 import」不代表 wheel 里真有那些模块。

公共 API 复核（呼应 Day 3）：

```python
# 用户应能：
from mini_infer import InferenceEngine, SamplingConfig

# 用户不应依赖：
from mini_infer.engine.scheduler import _internal_helper  # 私有约定
```

验收命令（roadmap）：

```bash
python -m build
python -m venv /tmp/mini-infer-test
# 在新环境中安装 dist/*.whl 并运行 smoke test
```

---

## 4. 练习设计（3 个递进，全部基于 mini-infer 真实场景）

> 前置假设：项目已有 Day 1 的 `pyproject.toml` 骨架、`src/mini_infer`、`cli.py`、公共 `__init__.py`。练习在其上完善为「可发布」。

### 练习 1（基础 · 22 min）：完善 `pyproject.toml`

**目标**：metadata、extras、scripts 一次配齐。

**任务**：
1. 补齐 `[build-system]`（推荐 `hatchling`）与 `[project]`：name / version / requires-python / license / readme / description。
2. 声明 `dependencies`（核心尽量空或极瘦）与 `optional-dependencies`：`dev` / `torch` / `transformers`。
3. 配置 `[project.scripts]`：`mini-infer = "mini_infer.cli:main"`。
4. 确认 backend 能发现 `src/mini_infer`（必要时加 hatch/setuptools 的 packages 配置）。

**检查点 / 预期输出**：
```bash
python -c "import tomllib, pathlib; print('ok')"
# 人工检查 pyproject.toml 含 build-system、optional-dependencies、project.scripts
```
断言：文件可被 TOML 解析；三段关键配置都在；`torch` 不在核心 `dependencies` 里。

---

### 练习 2（进阶 · 20 min）：构建 sdist + wheel

**目标**：走通 `python -m build`，看懂 `dist/` 产物。

**任务**：
1. `pip install -e ".[dev]"`（或至少 `pip install build`）。
2. 执行 `python -m build`。
3. 列出 `dist/`，确认同时存在 `.tar.gz` 与 `.whl`。
4. （可选）`unzip -l dist/*.whl | head` 确认 `mini_infer/` 与 `METADATA` 存在。

**检查点 / 预期输出**：
```bash
python -m build
# Successfully built mini_infer-0.1.0.tar.gz and mini_infer-0.1.0-py3-none-any.whl
ls dist/
```
断言：两种产物都在；wheel 名含 `py3-none-any`（纯 Python 包的典型标签）。

---

### 练习 3（挑战 · 28 min）：干净环境 smoke + 发布清单

**目标**：用「别人的机器视角」验收；留下可复用清单。

**任务**：
1. 执行：
```bash
python -m build
python -m venv /tmp/mini-infer-test
source /tmp/mini-infer-test/bin/activate
pip install dist/mini_infer-*.whl
python -c "from mini_infer import SamplingConfig; print(SamplingConfig())"
mini-infer --version
```
2. 在**未**安装 `[torch]` 的环境中，确认核心 import 不强制加载 torch（若模型模块顶层 import torch，需改为惰性导入或拆 optional 子包——发现即修）。
3. 写 `docs/packaging-checklist.md`，至少包含：version 是否 bump、extras 是否正确、干净环境可装、CLI 可用、README quick start 对非 editable 用户成立。

**检查点 / 预期输出**：
```text
mini-infer 0.1.0
```
断言：干净环境安装成功；CLI 可用；核心 `import` 不依赖未声明的 extras；清单文档存在。

---

## 5. 课后测验 / 思考题

### 选择题

1. 用户执行 `pip install mini-infer` 时，通常优先安装的是？
   a) 仓库 git clone
   b) sdist，且从不构建 wheel
   c) wheel（若存在匹配的 wheel）
   d) 仅 editable 安装

2. 为什么建议把 `torch` 放进 optional-dependencies？
   a) PyPI 不允许主依赖里出现 torch
   b) 隔离重型依赖，保持核心安装面与 Adapter 边界一致
   c) optional 依赖会自动随 wheel 安装
   d) 可以绕过 `requires-python`

3. `pip install -e .` 能 import 某模块，但干净环境装 wheel 后失败，最可能的原因是？
   a) GIL 导致
   b) 包发现/资源未打进 wheel，或路径仅在开发树有效
   c) semver 写错
   d) 必须用 `python -m` 才能运行任何库

4. `[project.scripts] mini-infer = "mini_infer.cli:main"` 的作用是？
   a) 仅生成文档
   b) 安装后提供 console 可执行入口
   c) 替代 `pyproject.toml`
   d) 强制用户使用 editable 安装

### 编码思考题

5. 写出一段最小 `pyproject.toml` 片段：包含 hatchling backend、`dev`/`torch` extras、以及 `mini-infer` console script。

6. 若 `mini_infer/model/transformer.py` 顶层写了 `import torch`，基础 wheel 的用户 `import mini_infer` 时可能发生什么？给出两种工程修复策略（惰性导入 / 子包拆分）。

### 思考题（开放）

7. 对照你们团队发布 C++ 库的流程（头文件、`.so`、version script、符号可见性），Python wheel 的「公开 ABI」对应什么？你如何防止用户依赖以下划线开头的内部模块？

---

## 6. 总结与延伸阅读建议

### 今日一句话总结
**Packaging 把「开发机能跑」变成「陌生人能装」；用 optional extras 守住依赖边界，用干净 venv 装 wheel 做唯一可信验收。**

### 三条今天必须刻进肌肉记忆的规则
1. editable 通过 ≠ 可发布——必须干净环境验证产物。
2. `torch` / `transformers` 进 extras，不进核心 dependencies。
3. entry point + `__all__` + semver 共同定义对用户的契约。

### 延伸阅读
- [PyPA Packaging User Guide](https://packaging.python.org/) — 现代打包权威入口。
- [Writing your pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)。
- PEP 517 / PEP 518（build system）、PEP 621（project metadata）、PEP 440（版本号）。
- **roadmap 衔接**：Day 16 把 build + smoke install 串进 CI；Day 30 最终发布 checklist 会复用今天的清单。

### 给讲师的复盘提示
- 用「Maven jar / CMake install」开场，学员秒懂 sdist vs wheel。
- 练习 3 务必让学员亲眼看到 `/tmp/mini-infer-test` 里命令成功——这是本周工程线的信任锚点。
- 若有人顶层 `import torch` 导致基础安装失败，正好复习 Day 13 Adapter 与「边界隔离」——今天是安装维度的同构问题。
