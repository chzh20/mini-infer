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

## 2. 现代 Packaging 技术全景

先把它看成一条“从源码到用户环境”的交付链，而不是一份配置文件：

```text
2.1 分发产物      sdist / wheel
       │
2.2 构建系统      pyproject.toml → frontend → backend
       │
2.3 项目身份      name / version / Python 要求 / license
       │
2.4 依赖边界      核心 dependencies 与按需 extras
       │
2.5 分发面        CLI、package data、src layout、公共 API
       │
2.6 安装与验收    editable 开发 → wheel 安装 → 干净 venv smoke
```

| 模块 | 需要回答的问题 | `mini-infer` 的落点 |
|---|---|---|
| 2.1 分发产物 | 要交付源码、安装包，还是两者？ | `dist/*.tar.gz` + `dist/*.whl` |
| 2.2 构建系统 | 谁发起构建，谁实际生成产物？ | `build` → `setuptools.build_meta` |
| 2.3 metadata | 用户安装的包叫什么、是什么版本、支持哪些解释器？ | `[project]` |
| 2.4 依赖分层 | 默认安装必须拉取什么，哪些能力由用户选择？ | `dependencies` 与 `optional-dependencies` |
| 2.5 分发面 | 用户怎样 import/执行，资源和源码怎样进入 wheel？ | `__init__.py`、`[project.scripts]`、`src/` |
| 2.6 验收 | 如何证明交付物脱离开发树仍可用？ | 干净 venv 安装 wheel、import、CLI |

后文的 3.1–3.5 依此顺序展开；不要跳过 2.6。只有通过干净环境验收，前面所有配置才是
实际可交付的行为。

---

## 3. 详细讲解内容

### 3.1 什么是 sdist / wheel，为什么需要 build backend

#### 3.1.1 先区分产物、前端与后端

**类比（C++/Java 工程师最熟悉）**：

| Python 概念 | 近似对应 | 本项目中的实例 |
|---|---|---|
| sdist（`.tar.gz`） | 源码发布包 / source jar | `mini_infer-0.1.0.dev0.tar.gz` |
| wheel（`.whl`） | 可直接安装的发布包 | `mini_infer-0.1.0.dev0-py3-none-any.whl` |
| build frontend | 调用构建的命令行工具 | PyPA 的 `build`，即 `python -m build` |
| build backend | CMake/Maven 中真正产出工件的一层 | `setuptools.build_meta` |
| installer | 将工件装入运行环境的工具 | `pip install dist/*.whl` |

```text
pyproject.toml + 源码树（src/mini_infer/...）
                    │
                    ▼
      build frontend：python -m build
      读取 [build-system]，准备隔离构建环境
                    │
                    ▼
      build backend：setuptools.build_meta
                    │
           ┌────────┴────────┐
           ▼                 ▼
        sdist              wheel
       .tar.gz             .whl
           │                 │
           └─────► pip install ◄─────┘
                         │
                         ▼
                    site-packages
```

**为什么不能只把目录 zip 一下？** 安装器需要标准 metadata（依赖、Python 版本、入口
脚本），并需要知道哪些文件属于包、哪些是开发垃圾（测试、本地 venv、`.pyc`）。
PEP 517 定义了前端和后端的协作协议，让构建工具不必绑定在某个具体后端上。

#### 3.1.2 本项目的后端：`setuptools.build_meta`

`setuptools.build_meta` 是 setuptools 提供的 PEP 517 build backend。它实现前端调用的
标准 hooks，例如 `build_sdist()` 与 `build_wheel()`：前者生成源码分发包，后者生成
wheel。它的职责是**构建分发包**；当前 `mini-infer` 是纯 Python 项目，因此这里并没有
编译 C/C++/CUDA 二进制代码。未来加入原生扩展后，backend 才会协调相应的编译步骤。

项目实际使用的配置是：

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

含义如下：

1. 构建前端在隔离环境中准备 `setuptools>=68`；
2. 前端导入 `setuptools.build_meta`，调用它实现的 PEP 517 hooks；
3. setuptools 读取 `[project]` 和 `[tool.setuptools.*]` 配置，发现 `src/mini_infer` 并生成
   metadata、wheel 与 sdist。

`setuptools` 是成熟、广泛使用的选择，但不是 PEP 517 所规定的唯一“官方推荐”后端；
hatchling、flit 等只要实现同一协议也能被同一个前端调用。对于本项目，没有必要为了
“现代化”而更换已经可用的 setuptools 后端。

一些旧模板会把 `wheel` 写入 `[build-system].requires`。它曾经很常见，但并不是本项目
必须保留的固定写法；应以所选 backend 的当前要求为准。当前 `setuptools>=68` 配置已能
成功构建 wheel，因此不要仅因复制模板而额外添加依赖。

> 口诀：**`pyproject.toml` 声明“项目是什么”和“用谁构建”；frontend 发起构建；backend
> 决定怎样产出分发包。**

#### 3.1.3 前端命令：`python -m build`

`build` 是 PyPA 维护的独立构建前端（需要安装的第三方包，不是 Python 标准库）。
`python -m build` 表示使用当前解释器运行它。它是旧式
`python setup.py sdist bdist_wheel` 的现代等价物，但可对接任意合规 backend，而非把构建
流程锁死在 setuptools 与当前开发环境。

在项目根目录执行默认命令时，`build` 会：

1. 读取 `[build-system]`，确定 backend 和构建期依赖；
2. 默认创建临时隔离环境并安装构建依赖；
3. 从源码构建 sdist；
4. 将 sdist 解压到临时目录，再从其中构建 wheel；
5. 将两项产物写入 `dist/`。

第 4 步很重要：默认流程不是只从工作树直接造 wheel，而是在验证“sdist 是否包含重建
wheel 所需的全部文件”。这正是发现遗漏 `package data`、`MANIFEST.in` 文件或错误包发现的
机会。

当前纯 Python 项目通常得到：

```text
dist/
├── mini_infer-0.1.0.dev0.tar.gz
└── mini_infer-0.1.0.dev0-py3-none-any.whl
```

`.whl` 是可直接安装的 **wheel 分发包**；`py3-none-any` 表示它是纯 Python、与平台和
Python ABI 无关，并不表示其中一定包含“二进制代码”。将来包含 C++/CUDA 扩展时，wheel
文件名会携带具体 Python ABI、操作系统和架构标签。

本项目的推荐操作如下（使用项目虚拟环境，避免依赖系统是否提供 `python` 命令）：

```bash
.venv/bin/python -m pip install "build>=1.2"
.venv/bin/python -m build
ls dist/
```

`dist/` 中的文件是可交付产物：可以被 `pip install` 安装，也可以在完成版本、测试和
安全检查后上传到包索引。构建成功仅证明“产物生成成功”；是否能交付仍须由后面的
“干净 venv 安装 wheel + import + CLI” smoke test 验证。

#### 3.1.4 用户执行 `pip install` 后到底发生什么

当用户执行 `pip install "mini-infer>=0.1"` 时，pip 先解析版本约束、Python 版本与平台
兼容性；若索引中存在匹配的 wheel，通常直接下载并安装该 wheel。若不存在匹配 wheel、但有
sdist，pip 会按该 sdist 的 `pyproject.toml` 建立构建环境、构建 wheel，再安装。对于带有
C/C++ 扩展的项目，这一步可能要求用户本机具备编译器和对应开发头文件；这正是发布多平台
原生 wheel 的价值。

安装成功后，环境中通常会出现：

```text
<venv>/lib/python3.x/site-packages/
├── mini_infer/                 # .py 文件；原生扩展时还可能有 .so/.pyd
└── mini_infer-0.1.0.dev0.dist-info/
    ├── METADATA                # 依赖、license、Python 版本等
    ├── entry_points.txt         # mini-infer CLI 映射
    └── RECORD                  # 本次安装写入的文件清单
```

因此，`dist-info` 不是无关紧要的附属目录：pip 用它来识别已安装版本、依赖和卸载范围。

延伸阅读：[PyPA build documentation](https://build.pypa.io/)、
[setuptools build system support](https://setuptools.pypa.io/en/latest/build_meta.html)、
[PyPA 的 pyproject.toml 指南](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)。

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

`name` 是**分发包名**，而 `mini_infer` 是 import package 名；二者可以不同。只有把包
上传到同一个包索引时，规范化后的 `name` 才必须在该索引中唯一。`requires-python` 会让安装器
在不兼容解释器上拒绝候选版本，而不是把语法错误推迟到运行时。`readme`、`license` 和
`authors` 虽不决定 import 行为，却决定包索引展示、许可证识别与用户信任，属于可交付物的一部分。

**语义化版本策略（`MAJOR.MINOR.PATCH`）**，对高级工程师的精确含义：

- **PATCH**：修复，公开 API 不变。
- **MINOR**：向后兼容的功能（新增符号、新增可选参数且有默认值）。
- **MAJOR**：破坏性变更（删除/改名公共 API、改默认行为导致静默语义变化）。

注意区分两件事：SemVer 是面向用户的兼容性沟通策略；Python 打包工具实际解析和比较
版本时遵循 [PEP 440](https://peps.python.org/pep-0440/)。当前的 `0.1.0.dev0` 是一个
PEP 440 开发预发布版本，不是完整稳定的 `0.1.0` 发布。项目不必机械地“严格遵循
SemVer”，但必须让版本策略与公开 API 的兼容性承诺一致。

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

生产依赖要尽量瘦；重型依赖（PyTorch、Transformers）进 optional extras——这与 Day 13 Adapter「核心层不 import 第三方」是同一条边界在**安装维度**的投影。`dependencies` 中的包会随每次普通安装拉取；extras 只有在用户显式选择时才被解析和安装。

下面是课程目标配置：当前仓库尚未实现 PyTorch/Transformers 后端，因此只能先将 `dev`
部分中的 `build` 落地；`torch` 和 `transformers` extra 应与相应能力一起加入，不能只加名称
却暗示功能已经可用。

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

安装器会在虚拟环境的 `bin/`（macOS/Linux）或 `Scripts/`（Windows）创建启动器，将命令
映射到 `mini_infer.cli:main`。这与 C++ 安装后的 `bin/` 可执行文件、Java 的
`Main-Class` / `jpackage` 入口属于同一类产品体验：用户装完第一件事不是 `python -m ...`，
而是敲命令名。

**package data**：非 `.py` 资源（默认词表、JSON schema、小配置模板）不会因为位于仓库中就必然进入 wheel，需按**实际 backend**显式纳入。`mini-infer` 使用 setuptools，因此示例应写成：

```toml
[tool.setuptools.package-data]
mini_infer = ["data/*.json", "schemas/*.json"]

# 只有在这些资源真实存在且运行时需要读取时才添加。
```

对于这类数据，运行时代码应使用 `importlib.resources` 读取包内资源，而不是假设仓库相对路径存在。构建后应以 `unzip -l dist/*.whl` 检查资源是否真的在 wheel 中。

**src layout 为什么能防止本地导入幻觉**：仓库根目录不直接包含 `mini_infer/`，解释器不能仅因当前工作目录恰好是项目根而导入它；开发者必须先安装项目，或显式把 `src/` 放入 import path。这使“开发环境能 import、wheel 却漏包”的错误更早暴露。当前的 `where = ["src"]` 正是告诉 setuptools 从 `src/` 发现包。今天仍必须用**干净 venv + 装 wheel**做最终证明。

---

### 3.5 editable vs 普通 install；公共 API 复核

| 方式 | 命令 | 行为 |
|------|------|------|
| editable | `pip install -e .` | 安装器创建指向开发树的可编辑导入机制（常见为 `.pth` 或 import hook）；改源码立即生效，适合开发 |
| 普通 | `pip install .` 或 `pip install dist/*.whl` | 前者先构建再安装，后者直接安装已有 wheel；文件进入 site-packages，改仓库源码不影响已安装包 |

**今天必须做一次「干净 venv + 装 wheel」**——这是发现「漏打进包的文件 / 错误的 package discovery / entry point 未生效」的最快方法。editable 下「能 import」不代表 wheel 里真有那些模块。

公共 API 复核（呼应 Day 3）：

```python
# 用户应能：
from mini_infer import InferenceEngine, SamplingConfig

# 用户不应依赖：
from mini_infer.engine.scheduler import _internal_helper  # 私有约定
```

`__all__` 主要约束 `from mini_infer import *`，但更重要的作用是作为维护者写下的 API 承诺。
以下划线开头的模块或符号是“非公开实现”的信号，而不是 Python 强制访问控制；真正防止用户
耦合内部结构的方式是提供足够的顶层稳定入口、在文档中只使用这些入口，并把兼容性变更反映在版本策略中。

验收命令（roadmap）：

```bash
.venv/bin/python -m build
task_tmp_dir="$(mktemp -d)"
.venv/bin/python -m venv "$task_tmp_dir/venv"
"$task_tmp_dir/venv/bin/python" -m pip install --no-deps dist/mini_infer-*.whl
"$task_tmp_dir/venv/bin/mini-infer" --version
```

---

## 4. 练习设计（3 个递进，全部基于 mini-infer 真实场景）

> 前置假设：项目已有 Day 1 的 `pyproject.toml` 骨架、`src/mini_infer`、`cli.py`、公共 `__init__.py`。练习在其上完善为「可发布」。

### 练习 1（基础 · 22 min）：完善 `pyproject.toml`

**目标**：metadata、extras、scripts 一次配齐。

**任务**：
1. 核对现有 `[build-system]`（`setuptools.build_meta`）与 `[project]`：name / version / requires-python / license / readme / description。不要无理由切换 backend。
2. 保持核心 `dependencies` 为空或极瘦，并在 `dev` extra 加入 `build`。为未来设计 `torch` /
   `transformers` extra 的接口，但只在相应后端实际落地时再将其写入发布配置。
3. 配置 `[project.scripts]`：`mini-infer = "mini_infer.cli:main"`。
4. 确认 backend 能发现 `src/mini_infer`（必要时加 hatch/setuptools 的 packages 配置）。

**检查点 / 预期输出**：
```bash
.venv/bin/python -c "import tomllib, pathlib; print('ok')"
# 人工检查 pyproject.toml 含 build-system、dev extra、project.scripts
```
断言：文件可被 TOML 解析；构建工具位于 `dev` 而非核心依赖；`torch` 不在核心
`dependencies` 里。

---

### 练习 2（进阶 · 20 min）：构建 sdist + wheel

**目标**：走通 `python -m build`，看懂 `dist/` 产物。

**任务**：
1. `.venv/bin/python -m pip install "build>=1.2"`（后续可将它加入 `dev` extra）。
2. 执行 `.venv/bin/python -m build`。
3. 列出 `dist/`，确认同时存在 `.tar.gz` 与 `.whl`。
4. （可选）`unzip -l dist/*.whl | head` 确认 `mini_infer/` 与 `METADATA` 存在。

**检查点 / 预期输出**：
```bash
.venv/bin/python -m build
# Successfully built mini_infer-0.1.0.dev0.tar.gz and mini_infer-0.1.0.dev0-py3-none-any.whl
ls dist/
```
断言：两种产物都在；wheel 名含 `py3-none-any`（纯 Python 包的典型标签）。

---

### 练习 3（挑战 · 28 min）：干净环境 smoke + 发布清单

**目标**：用「别人的机器视角」验收；留下可复用清单。

**任务**：
1. 执行：
```bash
.venv/bin/python -m build
task_tmp_dir="$(mktemp -d)"
.venv/bin/python -m venv "$task_tmp_dir/venv"
"$task_tmp_dir/venv/bin/python" -m pip install --no-deps dist/mini_infer-*.whl
"$task_tmp_dir/venv/bin/python" -c "from mini_infer import SamplingConfig; print(SamplingConfig())"
"$task_tmp_dir/venv/bin/mini-infer" --version
```
2. 在**未**安装 `[torch]` 的环境中，确认核心 import 不强制加载 torch（若模型模块顶层 import torch，需改为惰性导入或拆 optional 子包——发现即修）。
3. 写 `docs/packaging-checklist.md`，至少包含：version 是否 bump、extras 是否正确、干净环境可装、CLI 可用、README quick start 对非 editable 用户成立。

**检查点 / 预期输出**：
```text
mini-infer 0.1.0.dev0
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

5. 写出一段最小 `pyproject.toml` 片段：包含 `setuptools.build_meta`、`dev`/`torch` extras、以及 `mini-infer` console script。

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
