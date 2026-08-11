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
| 3.5 | API compatibility 与格式化门禁 | 8 min |
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

---

## 3. 详细讲解内容

### 3.1 快速测试与慢测试：为什么必须分层

**类比**：你们的 EDA 回归有 smoke / nightly / full——不是所有检查都适合每次存盘触发。Python 项目同理：把「装 wheel + 可选 HF + 真 CLI」和「纯逻辑单元测试」绑在同一条命令里，开发反馈会从秒级退化到分钟级，最后大家开始跳过测试。

| 类型 | 典型内容 | 期望时长 | CI 策略 |
|------|----------|----------|---------|
| unit | 纯逻辑、fake tokenizer/sampler、异常链 | 秒级 | 每次提交必跑；开发循环默认 |
| integration | 真 CLI、packaging smoke、可选 HF tokenizer | 十秒～分钟 | 必跑，可并行 job |
| slow / optional | 真模型、GPU、大依赖 | 分钟级 | nightly 或手动 |

```python
# tests/integration/test_cli.py
import pytest

@pytest.mark.integration
def test_cli_version():
    ...
```

```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = [
  "integration: slower tests that touch CLI, packaging, or optional deps",
]
testpaths = ["tests"]
```

本地命令约定：

```bash
python -m pytest -m "not integration"   # 开发循环
python -m pytest                        # 提交前全量（或 CI 分两步）
```

> 口诀：**分层不是偷懒，是保护反馈速度；门禁仍然要跑全量该跑的部分。**

---

### 3.2 覆盖率：有用的地板，危险的天花板

覆盖率回答：「这段代码有没有被执行到？」  
它**不**回答：「行为对不对？边界想没想过？并发安全吗？异常链保留了吗？」

| 健康用法 | 危险用法 |
|----------|----------|
| 设下限（如核心包 80%），防止明显裸奔 | 为冲 100% 写无断言测试 |
| 关键路径用行为断言（采样边界、Adapter 翻译） | 用 omit 静默藏起未测模块且不说明 |
| 看 `term-missing` 指导补测 | 把覆盖率当唯一合并条件 |

```bash
python -m pytest --cov=mini_infer --cov-report=term-missing --cov-fail-under=80
```

对「故意不测」的文件：在配置里 **显式 omit**，并在注释或文档写原因（例如「可选 GPU 扩展，仅 nightly」）。禁止静默忽略。

---

### 3.3 矩阵、fail-fast、可复现构建

**矩阵测试**常见维度：

- Python 3.10 / 3.11 / 3.12
- extras：`dev` only vs `dev,torch`

不是每个维度都要笛卡尔积爆炸——先保证「最小支持版本 + 默认开发组合」，再按风险加 `torch` job。

**fail-fast**：lint / type 失败时尽早停掉昂贵的 integration 与 build，节省 CI 分钟数。顺序本身就是策略：

```text
便宜且稳定的检查 → 越往后越贵
ruff / mypy → unit → integration → build → smoke
```

**reproducible build**：

- 约束依赖上下界（或锁文件，按团队规范）。
- 不把本机 `dist/`、`*.egg-info`、虚拟环境提交进仓库。
- CI **每次从干净 checkout** 构建 wheel——验证的是仓库状态，不是开发者笔记本残留。

---

### 3.4 发布门禁六步流水线（与 roadmap 对齐）

每次提交固定：

```text
1. lint          (ruff check / format check)
2. type check    (mypy --strict)
3. unit tests
4. integration tests
5. build wheel
6. smoke install (干净 venv 装 wheel → mini-infer --version)
```

原则：

1. **禁止提交未格式化代码**（`ruff format --check` 或 pre-commit）。
2. **缓存 pip/uv 依赖**，加速安装。
3. **不要缓存 `dist/`、`.pytest_cache`、`.coverage` 作为成功证据**——产物必须当场构建。
4. smoke install 验证的是**产物**，不是 `pip install -e .` 的开发树。

示例（GitHub Actions 骨架，可按团队换成 GitLab CI / 内部 Jenkins）：

```yaml
jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: python -m ruff check .
      - run: python -m ruff format --check .
      - run: python -m mypy --strict src
      - run: python -m pytest -m "not integration" --cov=mini_infer --cov-fail-under=80
      - run: python -m pytest -m integration
      - run: python -m build
      - name: smoke install
        run: |
          python -m venv /tmp/mi-smoke
          /tmp/mi-smoke/bin/pip install dist/*.whl
          /tmp/mi-smoke/bin/mini-infer --version
```

> 项目落点：Day 15 手工做过的干净环境步骤，今天变成机器每次替你跑——**回归 packaging 的唯一可靠方式**。

---

### 3.5 API compatibility 与「门禁在守什么」

CI 不只是「测试绿了」。对库作者，门禁在守三类契约：

| 契约 | 手段 |
|------|------|
| 代码形状 | ruff / format |
| 类型契约 | mypy strict |
| 行为与产物 | pytest + build + smoke |

破坏 `__all__` 公开符号时：应有显式测试（导入公共 API 快照）或 MAJOR bump 记录。这与 Day 15 semver 讲的是同一件事——CI 可以加一个极小的 `test_public_api.py`：

```python
import mini_infer as mi

def test_public_api_names():
    assert "SamplingConfig" in mi.__all__
    assert "InferenceEngine" in mi.__all__
```

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
1. 开发跑 `not integration`，门禁跑全量该跑的部分 + build + smoke。
2. 覆盖率有下限，但不替代行为测试。
3. 缓存依赖加速；`dist/` 必须当场构建并在干净环境验证。

### 延伸阅读
- pytest markers 官方文档；GitHub Actions / GitLab CI 缓存最佳实践。
- PyPA：「Publishing package distribution releases」检查清单。
- **roadmap 衔接**：Day 17 异步队列测试如何标记；Day 18 benchmark **默认不进** PR fail-fast（噪声大，放 nightly）。

### 给讲师的复盘提示
- 强调「smoke install 测产物」——这是连接 Day 15 与本周工程线的关键句。
- 若团队无 GitHub，用 GitLab/`Jenkinsfile` 同构六步即可，不要卡在 YAML 方言。
- 预告：明天开始并发——CI 绿了才能安心改 scheduler，否则异步 bug 与打包 bug 会搅在一起。
