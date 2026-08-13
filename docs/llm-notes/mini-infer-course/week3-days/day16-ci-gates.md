# Day 16：CI、测试分层与发布门禁 — 课程方案

> 所属项目：`mini-infer`（可扩展的迷你 LLM 推理流水线框架）
> 前置基础：Day 1 质量门禁命令 / Day 6 pytest 分层 / Day 8 `mypy --strict` / Day 15 wheel 构建与干净环境 smoke
> 学员画像：EDA 工程师，C++/Java 背景（熟悉 Jenkins / GitLab CI / 预提交检查 / 覆盖率门禁）
> 设计依据：`roadmap.md` Day 16「把工程规范变成自动反馈」

---

## 0. 课程概览与时间分配（总时长 ≈ 2.8 小时）

| 环节 | 内容 | 时长 |
|------|------|------|
| 开场 | 课程目标、从「本地能发」到「每次提交自动验」 | 5 min |
| 3.1 | 快速测试 vs 慢测试；`@pytest.mark.integration` | 15 min |
| 3.2 | 覆盖率阈值的信号与局限 | 12 min |
| 3.3 | 矩阵测试、fail-fast、可复现构建 | 15 min |
| 3.4 | 发布门禁六步流水线；缓存依赖不缓存产物 | 15 min |
| 3.5 | API 兼容性信号与格式化门禁 | 8 min |
| 练习 1 | marker 分层 + 本地快/慢两套命令 | 20 min |
| 练习 2 | 覆盖率门禁 + omit 显式化 | 20 min |
| 练习 3 | CI 六步 + smoke install + 本地一键脚本 | 30 min |
| 收尾 | 课后测验讲解 + 总结与延伸阅读 | 14 min |

> 标注为「可压缩」：3.5 可并入 3.4；练习 2 的 omit 策略可课后补。核心不可删：**integration marker、六步门禁顺序、干净环境 smoke、缓存依赖不缓存 dist/**。

---

## 1. 课程目标

学完今天，学员应当能够：

1. **分层反馈**：用 `@pytest.mark.integration` 区分快测与慢测，开发循环与提交门禁使用不同命令。
2. **正确看待覆盖率**：设置合理 `--cov-fail-under`，同时能说清「覆盖率不是正确性证明」。
3. **设计门禁顺序**：按 lint → type → unit → integration → build → smoke 排列，理解 fail-fast 省的是什么。
4. **把 Day 15 自动化**：每次提交构建 wheel，并在干净 venv 中 smoke install。
5. **定缓存原则**：缓存 pip/uv 依赖加速 CI；不把 `dist/`、覆盖率产物当「成功证据」缓存。
6. **留下本地复现路径**：`scripts/ci_local.sh`（或等价 Makefile）使个人机器能跑通与 CI 同构的主路径。

---

## 2. 知识点大纲

```text
CI、测试分层与发布门禁
├── 2.1 测试分层
│      ├── unit vs integration vs slow/optional
│      ├── @pytest.mark.integration
│      └── 本地快反馈 vs 提交全量
├── 2.2 覆盖率策略
│      ├── 覆盖率能回答 / 不能回答什么
│      ├── fail-under 阈值
│      └── 禁止无断言刷覆盖率
├── 2.3 矩阵与可复现
│      ├── Python 版本 × extras 矩阵
│      ├── fail-fast
│      └── reproducible build（干净 checkout）
├── 2.4 发布门禁流水线
│      ├── 六步：lint/type/unit/integration/build/smoke
│      ├── 格式化检查 / pre-commit
│      └── 缓存依赖、不缓存工作区产物
└── 2.5 API 兼容性信号
       ├── 公开 __all__ 破坏 → MAJOR
       └── 兼容性测试或显式变更记录
```

一句话概括今天的主线：**把规范从"口头约定"变成"每次提交的自动拒绝"**。你不靠人记，靠机器守。

---

## 3. 详细讲解内容

### 3.1 测试分层：为什么不能一把梭

#### 3.1.1 问题场景

想象一下：你改了一行代码，按保存，然后等了 3 分钟才看到测试结果——因为测试套件里混着启动 Docker Redis、拉取 HuggingFace 模型、跑 GPU 推理的用例。等你拿到结果，思路早就断了。

这就是"不分层"的代价。解决方案很直接：**把测试按速度和依赖分成三层，本地只跑快的，慢的交给 CI。**

#### 3.1.2 三层测试对照

| 层级 | 测试什么 | 典型时长 | 外部依赖 | 何时跑 |
|------|----------|----------|----------|-------|
| **Unit（单元）** | 孤立的函数或类 | 毫秒级 | 全部 mock 掉 | 本地每次保存 |
| **Integration（集成）** | 多模块协同 / 真实外部服务 | 秒级～分钟级 | Docker 容器、API 沙盒 | CI 每次提交 |
| **Slow / Optional** | E2E 流程、压测、GPU 训练 | 分钟级以上 | 真模型 / GPU / 大数据 | nightly 或手动触发 |

> **类比**：EDA 回归里有 smoke / nightly / full——不是所有检查都适合每次存盘触发。Python 项目同理：把「装 wheel + 可选 HF + 真 CLI」和「纯逻辑单元测试」绑在一起，开发反馈从秒级退化到分钟级，最后大家开始跳过测试。

#### 3.1.3 用 pytest marker 实现分层

pytest 的自定义标记（Markers）可以给测试打标签，然后按标签选择性执行。

**第一步**：在 `pyproject.toml` 注册标记：

```toml
[tool.pytest.ini_options]
markers = [
    "integration: marks tests as integration tests (slow)",
]
testpaths = ["tests"]
```

**第二步**：在测试代码上打标记：

```python
# tests/integration/test_cli.py
import pytest

@pytest.mark.integration
def test_cli_version():
    ...
```

**第三步**：用不同命令跑不同层：

```bash
# 本地开发——只跑单元测试，3 秒内出结果
python -m pytest -m "not integration" -q

# CI 全量——跑集成测试
python -m pytest -m "integration" -q

# 提交前全量——两个都跑
python -m pytest -q
```

#### 3.1.4 两种反馈模式

| 模式 | 触发时机 | 跑什么 | 目标 |
|------|----------|--------|------|
| **本地快反馈** | 每次保存代码 | 只跑相关单元测试 | 反馈 < 3 秒，维持开发专注度 |
| **提交全量** | Push / PR 到远程 | 全量测试 + 多版本矩阵 + build + smoke | 用机器时间换主干安全 |

> 口诀：**分层不是偷懒，是保护反馈速度；门禁仍然要跑全量该跑的部分。**

---

### 3.2 覆盖率：有用的地板，危险的天花板

#### 3.2.1 覆盖率能回答什么 / 不能回答什么

覆盖率工具做的事情很简单：记录每一行代码在测试执行期间有没有被跑到。这就决定了它的能力边界：

| ✅ 能回答 | ❌ 不能回答 |
|----------|------------|
| 哪些代码行从未被执行过 | 代码逻辑是否正确 |
| 哪里是"未测试死角" | 边界条件（None、空列表、超时）是否被覆盖 |
| 哪些代码可能是冗余的 | 断言质量是否足够 |

**关键理解**：覆盖率 100% 的代码，如果缺乏核心断言，或者没有对边界条件进行设计，依然会发生线上崩溃。覆盖率告诉你"路有没有被走过"，不告诉你"走到终点了没"。

#### 3.2.2 fail-under：设一道硬门槛

不要让覆盖率流于形式。在 CI 中用 `--cov-fail-under` 设置硬性下限：

```bash
python -m pytest --cov=mini_infer --cov-report=term-missing --cov-fail-under=80
```

**机制**：如果测试覆盖率低于 80%，CI 流水线直接变红、拒绝合入。这倒逼团队在开发新功能时同步编写测试。

> **建议**：核心包设 80% 起步，按项目实际情况微调，但**必须有一个数**。不能是"尽量高"——没有阈值等于没有门禁。

#### 3.2.3 禁止无断言刷覆盖率

**作弊现象**：为了应付 fail-under 检查，写只调用函数、但不 assert 返回值的"空壳测试"：

```python
# ❌ 刷覆盖率——调用了，但没验证任何东西
def test_sampling_config():
    config = SamplingConfig(temperature=0.8)
    # 没 assert，这行代码被"覆盖"了，但什么都没测

# ✅ 有断言——验证了实际行为
def test_sampling_config():
    config = SamplingConfig(temperature=0.8)
    assert config.temperature == 0.8
    assert config.top_k == 50  # 默认值
```

**防御手段**：

| 手段 | 做法 | 效果 |
|------|------|------|
| Code Review | 重点审查新增测试的断言质量 | 人工把关，防明显空测 |
| 变异测试（mutmut） | 工具自动修改源码逻辑，看测试是否还能发现 | 如果改了代码测试仍然通过，说明覆盖率是无效的 |

#### 3.2.4 对"故意不测"的文件：显式 omit

有些文件确实不需要在常规 CI 中测（如可选 GPU 扩展、仅 nightly 跑的模块）。正确做法是**显式声明**并写明原因，而不是静默忽略：

```toml
[tool.coverage.run]
omit = [
    # 可选 GPU 扩展，仅 nightly CI 有 GPU runner
    "src/mini_infer/gpu/*",
]
```

> 禁止静默 omit——不说明原因的 omit 等于藏起未测模块，是技术债的温床。

---

### 3.3 矩阵、fail-fast、可复现构建

#### 3.3.1 多版本矩阵：Python × extras

Python 生态版本碎片化严重——你的库声明支持 3.10～3.12，就得在每个版本上都验证过。而且可选依赖（extras）的导入逻辑（`try...except ImportError`）也必须测试。

**两个维度**：

| 维度 | 测试组合 | 为什么要测 |
|------|----------|------------|
| **版本轴** | Python 3.10 / 3.11 / 3.12 | 不同版本语法、标准库行为有差异 |
| **依赖轴** | 核心包 only vs `pip install -e ".[torch]"` | 确保 extras 的导入条件判断正确 |

```yaml
# GitHub Actions 矩阵示例
strategy:
  fail-fast: true
  matrix:
    python-version: ["3.10", "3.11", "3.12"]
    extras: ["", "torch"]
```

> **不必笛卡尔积爆炸**——先保证「最小支持版本 + 默认开发组合」，再按风险加 `torch` job。

#### 3.3.2 fail-fast：快速失败，省算力

在矩阵配置中强烈建议开启 `fail-fast: true`：

**原理**：矩阵中一旦有任意一个组合失败（例如 Python 3.10 + 核心依赖），CI 立即终止其他正在排队或运行的组合。

**优势**：节约 CI 算力，让开发者以最快速度拿到报错反馈去修代码。

但要注意：**fail-fast 不只是矩阵级别的开关，检查顺序本身也是策略**。六步门禁从便宜到昂贵排列，前一步失败就不跑后面的：

```text
便宜且稳定的检查 → 越往后越贵
ruff / mypy → unit → integration → build → smoke
```

lint 都没过，就别浪费分钟跑 integration 了。

#### 3.3.3 可复现构建（reproducible build）

防止"在我的电脑上能打包，在别人的电脑上报错"的玄学问题，三条铁律：

1. **干净 checkout**：CI 每次运行都从零拉取代码，不依赖服务器本地残留的缓存文件。
2. **不提交构建产物**：不把本机 `dist/`、`*.egg-info`、虚拟环境提交进仓库。
3. **一致产出**：相同源码下，每次构建的 Wheel 哈希值和构建行为应该完全一致。

> CI 构建验证的是**仓库状态**，不是开发者笔记本上的残留。

---

### 3.4 发布门禁六步流水线

#### 3.4.1 六步重力筛选法

一个成熟的项目合入主干或发布前，必须依次通过以下六道关卡。顺序有讲究——**从便宜到昂贵，前一步失败就不跑后面的**：

| 步骤 | 命令 | 验证什么 | 耗时 |
|------|------|----------|------|
| 1. 🪥 Lint | `ruff check` | 代码风格与语法缺陷 | 秒级 |
| 2. 🏷️ Type | `mypy --strict` | 静态类型检查，消灭隐式类型错误 | 秒级 |
| 3. 🧪 Unit | `pytest -m "not integration"` | 快速单元测试 | 秒级 |
| 4. 🔗 Integration | `pytest -m "integration"` | 重型集成测试 | 十秒～分钟 |
| 5. 📦 Build | `python -m build` | 打包成 wheel | 秒级 |
| 6. 🚬 Smoke | 干净 venv 装 wheel → `mini-infer --version` | 最后一公里验收 | 秒级 |

**为什么 smoke 要用干净 venv？** 因为它验证的是**打包产物**，不是 `pip install -e .` 的开发树。开发树能 import 不代表 wheel 里文件齐全——这是 Day 15 手动验证过的，今天交给机器自动跑。

#### 3.4.2 格式化检查 / pre-commit

**核心思路**：不要把代码格式化（空格、缩进、单双引号）的口水战留到 Code Review 阶段。

**最佳实践**：配置 `pre-commit` 钩子。在开发者执行 `git commit` 的瞬间，本地自动运行 `ruff format`。只有格式合规的代码才能被成功提交：

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff-check
      - id: ruff-format
```

CI 中也要跑 `ruff format --check .` 作为第二道防线——万一有人绕过了 pre-commit。

#### 3.4.3 缓存依赖，不缓存工作区产物

这是 CI 加速的核心策略，但必须分清"什么能缓存、什么不能"：

| ✅ 可以缓存 | ❌ 绝不能缓存 |
|-------------|---------------|
| pip 全局下载目录 | `dist/`（上次构建的 wheel） |
| uv / poetry 虚拟环境 | `build/`（构建中间文件） |
| 下载的 Python 解释器 | `.pytest_cache/`、`.coverage` |

**为什么依赖能缓存？** 依赖包很少变动，缓存后 CI 安装时间从几分钟缩到几十秒。

**为什么产物不能缓存？** 如果缓存了上次的 `dist/*.whl`，CI 可能"复用"旧产物冒充本次构建成功——你发布了一个上次版本的 wheel 却以为是最新的。每一轮流水线的工作区必须是纯净、无污染的。

#### 3.4.4 完整 CI 配置示例

```yaml
# .github/workflows/ci.yml（骨架，可按团队换成 GitLab CI / Jenkinsfile）
jobs:
  quality:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: true
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      # 缓存 pip 依赖——加速安装
      - uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ matrix.python-version }}-${{ hashFiles('pyproject.toml') }}
      - run: pip install -e ".[dev]"
      # 六步门禁，从便宜到贵
      - run: python -m ruff check .
      - run: python -m ruff format --check .
      - run: python -m mypy --strict src
      - run: python -m pytest -m "not integration" --cov=mini_infer --cov-fail-under=80
      - run: python -m pytest -m "integration"
      - run: python -m build
      # smoke：干净 venv 装 wheel
      - name: smoke install
        run: |
          python -m venv /tmp/mi-smoke
          /tmp/mi-smoke/bin/pip install dist/*.whl
          /tmp/mi-smoke/bin/mini-infer --version
```

> 项目落点：Day 15 手工做过的干净环境步骤，今天变成机器每次替你跑——**回归 packaging 的唯一可靠方式**。

---

### 3.5 API 兼容性信号：门禁在守什么

#### 3.5.1 不仅仅是"测试绿了"

对库作者来说，CI 门禁守的不只是测试通过，而是三类契约：

| 契约 | 守护手段 |
|------|----------|
| 代码形状 | ruff / format check |
| 类型契约 | mypy --strict |
| 行为与产物 | pytest + build + smoke |

但还有一类容易被忽略的契约：**公共 API 的兼容性**。

#### 3.5.2 公开 `__all__` 破坏 → MAJOR

根据语义化版本（SemVer）规范，你的顶层 `__init__.py` 中定义的 `__all__` 列表，就是对用户承诺的公共 API 边界。

```python
# src/mini_infer/__init__.py
__all__ = [
    "SamplingConfig",
    "InferenceEngine",
    "Pipeline",
]
```

**破坏性信号**：一旦你修改了 `__all__` 中暴露的类名、删除了函数、或改变了必填参数的顺序，使用该包的用户升级时就会遭遇代码崩溃。此时**必须**递增主版本号（MAJOR）。

#### 3.5.3 两种守护手段

**手段一：自动兼容性测试**

用工具（如 [griffe](https://mkdocstrings.github.io/griffe/)）在 CI 中自动对比当前代码分支与 PyPI 上最新稳定版的 API 签名。一旦发现未声明的公共方法缺失，CI 自动发出警告。

也可以写一个极小的测试来锁定公共 API 快照：

```python
# tests/test_public_api.py
import mini_infer as mi

def test_public_api_names():
    """公共 API 列表不能被意外破坏。"""
    assert "SamplingConfig" in mi.__all__
    assert "InferenceEngine" in mi.__all__
```

**手段二：显式变更记录（CHANGELOG.md）**

每次发布必须维护一份人类可读的变更记录，按以下四类标注：

| 标签 | 含义 |
|------|------|
| **Added** | 新增特性 |
| **Changed** | 已有行为变更 |
| **Deprecated** | 废弃预警，未来会移除 |
| **Removed** | 已移除（破坏性变更，对应 MAJOR bump） |

> 给下游依赖你的开发者留出足够的缓冲和重构时间。一个 `Removed` 不应该出现在 minor 版本升级里。

---

## 4. 练习设计（3 个递进）

> 前置假设：Day 15 已能 `python -m build` 且干净环境可装；已有 `tests/unit` 与 `tests/integration`。

### 练习 1（基础 · 20 min）：marker 分层落地

**目标**：快/慢两套命令真正可用。

**任务**：
1. 给现有集成测试打上 `@pytest.mark.integration`。
2. 在 `pyproject.toml` 注册 marker。
3. 确认：
```bash
python -m pytest -m "not integration" -q
python -m pytest -m integration -q
```

**检查点**：两套命令都能收集到预期用例；unit 路径不再误跑 CLI/packaging 慢测。

---

### 练习 2（进阶 · 20 min）：覆盖率门禁

**目标**：有地板、有 omit 说明、无空测刷分。

**任务**：
1. 接入 `pytest-cov`，为核心包设 `--cov-fail-under`（建议 80，可按现状微调，但必须有数）。
2. 对故意不测的文件显式 omit，并在注释说明原因。
3. 浏览 `term-missing`，为一条关键未覆盖分支补**带断言**的测试（异常链或配置校验均可）。

**检查点**：
```bash
python -m pytest -m "not integration" --cov=mini_infer --cov-report=term-missing --cov-fail-under=80
```
断言：阈值生效；新增测试有真正 assert。

---

### 练习 3（挑战 · 30 min）：CI 六步 + 本地一键脚本

**目标**：机器与人使用同一条主路径。

**任务**：
1. 添加 `.github/workflows/ci.yml`（或团队等价文件），顺序：lint → format check → mypy → unit → integration → build → smoke。
2. 配置依赖缓存；确保 `dist/` 不作为「跳过构建」的缓存捷径。
3. 增加 `scripts/ci_local.sh`（或 Makefile target），文档写明：提交前至少跑通该脚本。

**检查点 / 预期输出**：
```bash
bash scripts/ci_local.sh
# 各步 exit 0；smoke 打印版本号
```
断言：CI 配置存在；integration marker 生效；smoke 步骤在 CI 中可见且用干净 venv。

---

## 5. 课后测验 / 思考题

### 选择题

1. 为什么 CI 里要单独做「干净 venv 装 wheel」，而不是只跑 `pip install -e .` 后的测试？
   a) editable 更慢
   b) 验证的是分发产物，而非开发树
   c) wheel 不能包含测试
   d) mypy 只能在 venv 里跑

2. `--cov-fail-under=80` 通过，能否证明 TopK 采样边界正确？
   a) 能，覆盖率即正确性
   b) 不能，仍需行为断言与边界用例
   c) 能，只要 integration 也绿
   d) 不能，因为覆盖率只对 C 扩展有意义

3. fail-fast 场景下，应优先先跑？
   a) 最慢的 GPU integration
   b) lint / type 等廉价检查
   c) 先 build wheel 再 lint
   d) 只跑 coverage

4. 「缓存依赖但不缓存工作区产物」中，不应作为成功证据缓存的是？
   a) pip wheel 缓存
   b) `dist/*.whl` 上次构建结果冒充本次成功
   c) 下载的 Python 解释器
   d) GitHub Actions 的 checkout 动作本身

### 编码思考题

5. 写出 `pytest` 两行命令：只跑非 integration；只跑 integration。

6. 在 CI smoke 步骤中，为什么要用 `python -m venv /tmp/...` 新环境，而不是在当前 job 的 editable 环境里 `pip install dist/*.whl`？列出至少两个风险。

### 思考题（开放）

7. 你们现有 C++/Java CI 里，哪一步最接近 Python 的「smoke install」？若没有，发布后在用户机器上才发现缺符号/缺资源的事故，应如何用今天的六步预防？

---

## 6. 总结与延伸阅读建议

### 今日一句话总结

**CI 把规范从「口头约定」变成「每次提交的自动拒绝」；分层保速度，六步保产物，覆盖率只当地板。**

### 三条今天必须刻进肌肉记忆的规则

1. **开发跑 `not integration`，门禁跑全量该跑的部分 + build + smoke。**
   - 分层保速度，但不意味着门禁可以少跑。
2. **覆盖率有下限，但不替代行为测试。**
   - 80% 覆盖率是地板不是天花板；无断言的测试等于没有测试。
3. **缓存依赖加速；`dist/` 必须当场构建并在干净环境验证。**
   - 缓存的旧产物冒充成功是最危险的 CI 假阳性。

### 延伸阅读

- pytest markers 官方文档；GitHub Actions / GitLab CI 缓存最佳实践。
- PyPA：「Publishing package distribution releases」检查清单。
- 变异测试工具 [mutmut](https://mutmut.readthedocs.io/)；API 兼容性检查工具 [griffe](https://mkdocstrings.github.io/griffe/)。
- **roadmap 衔接**：Day 17 异步队列测试如何标记；Day 18 benchmark **默认不进** PR fail-fast（噪声大，放 nightly）。

### 给讲师的复盘提示

- 强调「smoke install 测产物」——这是连接 Day 15 与本周工程线的关键句。
- 若团队无 GitHub，用 GitLab/`Jenkinsfile` 同构六步即可，不要卡在 YAML 方言。
- 预告：明天开始并发——CI 绿了才能安心改 scheduler，否则异步 bug 与打包 bug 会搅在一起。
