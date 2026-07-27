# ADR 0001: use src layout

- Status: accepted
- Date: 2026-07-27

## Context

课程目标包含可安装 wheel、严格测试和长期演进的多后端包。如果仓库根目录直接包含
`mini_infer/`，测试可能意外导入工作树代码，从而掩盖打包配置遗漏。

## Decision

采用 `src/mini_infer`，开发时使用 editable install；CI 还应构建 wheel 并在干净环境
做 smoke test。

## Consequences

- 测试与用户安装路径更接近。
- 本地直接运行前需要安装包，或由 pytest 明确设置 `pythonpath = ["src"]`。
- 打包元数据问题会更早暴露。

