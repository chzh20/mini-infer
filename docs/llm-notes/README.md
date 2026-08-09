# 大模型（LLM）学习笔记 · 副本

本目录内容从 `review` 仓库（`git@github.com:chzh20/review.git`，`workbuddy` 分支）整理复制而来，存放于 mini-infer 项目的 `docs/llm-notes/`。所有文件均与原始记录逐字节一致（已用 md5 校验，25/25 完全匹配）。

## 目录结构

- `transformer/` — Transformer 论文精读、算法核心原理与易错点、Tokenization 详解、GPT Tokenizer 亲手实现笔记
- `vllm/` — vLLM 学习指南（含合并版 HTML）、整体概览、学习编排 prompt
- `llm-course/` — LLM 推理系统工程师培养课程、20 周逐日计划、EDA→LLM 转型路径复审、AI 转型路线图、每日面试练习手册、课程审查与优化报告
- `mini-infer-course/` — mini-infer（迷你 LLM 推理框架）课程方案：Day4 异常设计与资源管理 / Day5 日志与可观测性 / Day6 pytest 测试设计 / 第二周教学计划及 Day8–Day14 每日教程

## 复制说明

- 复制日期：2026-08-09
- 来源分支：`review` 仓库 `workbuddy` 分支
- 已排除：`review` 中的 C++ / QT / English / 通用 Python 基础 / 项目代码（`mini-infer`、`mini-infer_副本`）等非大模型主题内容
- 待确认项：`notes/python-exception-resource-course.md` 与 `notes/python-logging-observability-course.md` 为通用 Python 工程课程（主题非大模型），本次未纳入；如需加入请告知
