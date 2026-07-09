# Agentic 文档索引

整理日期：2026-07-09

这个目录按“当前事实优先，规划其次，历史方案归档”的方式维护。阅读时不要把 `archive/` 或 `reference/` 里的内容当成当前实现。

## 推荐阅读顺序

1. [current-state.zh-CN.md](current-state.zh-CN.md)
   当前 `agentic` 的数据库、认证、配置、工具治理、API 和部署基线。
2. [roadmap.zh-CN.md](roadmap.zh-CN.md)
   后续产品路线，已把旧文档里的冲突顺序收敛为一个实施顺序。
3. [run-trace-tooling-research.zh-CN.md](run-trace-tooling-research.zh-CN.md)
   对比 `agentic` 与 `llmops` 的工具管理、Trace、tool_calls、model_calls，实现差异和落地细节。
4. [tool-management.zh-CN.md](tool-management.zh-CN.md)
   工具管理当前实现、未完成项和下一步。

## 目录说明

| 路径 | 状态 | 用途 |
| --- | --- | --- |
| `current-state.zh-CN.md` | 活跃 | 以当前代码为准的状态说明。 |
| `roadmap.zh-CN.md` | 活跃 | 当前建议执行路线。 |
| `run-trace-tooling-research.zh-CN.md` | 活跃 | Run / Trace 与工具治理落地调研。 |
| `tool-management.zh-CN.md` | 活跃 | 工具治理专项说明。 |
| `reference/` | 参考 | OpenSquilla 调研材料，只用于借鉴设计。 |
| `archive/` | 归档 | 早期规划和旧基线，保留上下文但不代表当前状态。 |

## 维护规则

- 活跃文档必须反映当前代码；如果实现已经落地，不再写成“建议新增”。
- 产品路线只保留一个主线：先增强 `agentic` 的可执行、可配置、可复盘能力，不照搬重型 LLMOps。
- Workflow 暂不作为第一阶段核心能力；成熟 Skill 后再考虑 Runbook/Workflow 演进。
- OpenSquilla 文档只作为外部参考，不混入 `agentic` 当前能力说明。
