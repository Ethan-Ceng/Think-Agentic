# Prompt Locale 路由缺失

## 文档状态

- 状态：`READY_TO_MERGE`
- 修复分支：`feature/lead-agent-runtime-unification`
- 创建日期：2026-08-18
- 最近更新：2026-08-18

## 问题描述

`agentic/api/app/core/prompts/en` 保存了英文 System、Planner、React Prompt，但运行时 Agent 固定导入主目录 Prompt。英文文件没有进入模型调用，并且已经与中文主版本发生字段和能力约束漂移。本批新增 Lead 后若只继续使用双语字符串，可以改善输出，但仍无法恢复原有双目录的职责，也会增加每次执行 Prompt 的 Token。

## 预期行为

- Lead Decide 在尚未产生可靠工作语言前使用精简双语路由规则。
- Lead 决策产生 `language` 后，Planner、React Goal、Step 和 Finalizer 按 `zh/en` 选择对应 Prompt Pack。
- Legacy Planner 首轮根据用户消息选择 `zh/en`；后续以 Plan 的 `language` 为准。
- HITL Resume 使用已持久化的 `lead_language` 或 Plan `language`，不重新猜测语言。
- 同一 Agent Memory 即使跨 Run 使用不同语言，每次模型调用也看到当前 Run 的本地化 System Prompt。

## 实际行为

- `PlannerAgent` 固定导入 `app.core.prompts.planner` 与 `app.core.prompts.system`。
- `ReActAgent` 固定导入 `app.core.prompts.react` 与 `app.core.prompts.system`。
- `prompts/en` 没有生产代码调用者；先前只有新增测试直接导入英文镜像。
- 参考目录 `mooc-manus/api` 具有相同静态导入方式，也没有 locale 配置、UI 开关或启动期替换逻辑。

## 复现步骤

1. 运行 `rg -n "from .*prompts\\.en|import .*prompts\\.en" mooc-manus agentic`。
2. 排除测试和文档结果。
3. 检查 Planner/ReAct 的模块级 imports 与类级 `_system_prompt`。

- 复现频率：每次。
- 最小复现：Prompt Catalog 回归测试在实现前因模块不存在或英文 Prompt 未进入 LLM messages 而失败。

## 日志和证据

### 证据 1：英文 Prompt 没有生产调用者

```text
agentic/api/tests/app/core/agent/test_lead_decision.py: from app.core.prompts.en.react import ...
生产代码无 app.core.prompts.en 导入。
```

- 获取命令：`rg -n "from .*prompts\\.en|import .*prompts\\.en" mooc-manus agentic`
- 说明：证明英文目录当前不进入运行链路。

### 证据 2：参考项目同样没有接线

```text
mooc-manus/api/app/domain/services/agents/planner.py -> prompts.planner + prompts.system
mooc-manus/api/app/domain/services/agents/react.py  -> prompts.react + prompts.system
配置、UI 和启动脚本无 prompt locale 选择项。
```

- 获取命令：`rg -n -i "language|locale|i18n|prompts\\.en" mooc-manus/api mooc-manus/ui/src`
- 说明：参考目录可提供英文内容，但不能提供运行时选择实现。

## 调用链

```text
AgentTaskRunner -> Lead/Legacy -> PlannerAgent/ReActAgent
  -> 模块级中文 Prompt 常量 -> BaseAgent 持久化中文 System Prompt -> LLM
```

- 正常路径：Lead Decide 得到工作语言后选择对应 Prompt Pack，并在本次 LLM view 中覆盖 System Prompt。
- 故障路径：模块 import 时固定中文常量，`prompts/en` 永远不可达。
- 关键差异：Prompt Locale 没有成为运行时上下文。

## 根因假设

### 假设 1

- 假设：根因是 Prompt 在模块/类加载期绑定，而 Runtime 没有 Prompt Catalog 和每次调用的 System Prompt 覆盖能力。
- 依据：所有生产 import 指向主目录；BaseAgent 只在 Memory 为空时写入类级 `_system_prompt`。
- 最小验证：增加测试，分别用 `language=en` 和 `language=zh-CN` 执行 Planner/ReAct，断言模型 messages 中出现对应语言 Prompt 且用户内容只出现一次。
- 预期结果：修复前英文断言失败；引入 Catalog 和 runtime system override 后通过。

## 假设验证

| 假设 | 命令或实验 | 实际结果 | 结论 |
| --- | --- | --- | --- |
| 假设 1 | 静态 import 搜索与 BaseAgent Memory 调用链检查 | 英文目录无生产引用，System Prompt 只在空 Memory 时写入 | 成立 |

## 最终根因

升级保留了中英两套 Prompt 资产，却没有把 Locale 纳入 Agent Runtime；同时 System Prompt 被持久化到 Memory，单纯修改类属性或新增英文文件都不能保证跨 Run 切换。这也是英文镜像持续漂移且新增字段遗漏的原因。

## 修复方案

- 修复位置：`agentic/api/app/core/prompts/catalog.py`、`agentic/api/app/core/agent/base.py`、`planner.py`、`react.py`、Lead/Legacy 调用点。
- 最小修改：新增 `zh/en` Prompt Catalog；Lead Decide 保持双语；其余阶段按已知 language 选择；BaseAgent 仅在模型调用视图中覆盖当前 System Prompt，不改历史 Memory 数据。
- 不采用的方案：继续让所有执行 Prompt 中英并列会增加稳定 Token；部署期全局 locale 无法支持同一实例的中英文会话。
- 相同模式检查：System、Planner、React 三组主/英文 Prompt 全部纳入 Catalog 和一致性测试。

## 回归测试

- 测试文件：`agentic/api/tests/app/core/agent/test_prompt_locale_routing.py`
- 覆盖行为：locale 规范化、Lead 后执行 Prompt 选择、Legacy 首轮选择、跨 Run System Prompt 覆盖、HITL 已持久化语言复用。
- RED 命令：`uv run pytest tests/app/core/agent/test_prompt_locale_routing.py -q`
- RED 结果：Exit 1，测试收集失败：`ModuleNotFoundError: No module named 'app.core.prompts.catalog'`。
- GREEN 命令：`uv run pytest tests/app/core/agent/test_prompt_locale_routing.py -q`
- GREEN 结果：初次 Exit 0，19 passed；增量审查补充非中文 CJK 标签用例后 Exit 0，21 passed。

## 验证结果

- 回归测试：Prompt Locale 21/21 通过。
- 相关测试：最终聚焦单元/集成回归 128/128 通过，伴随 10 个既有 Pydantic deprecation warnings。
- 构建或静态检查：聚焦 Ruff、compileall、`git diff --check` 通过。
- 手工复现：生产代码现已通过 Catalog 导入 `prompts/en`；英文 Planner/React 的记录 LLM messages 已由测试验证。
- 审查整改：通用 CJK 判断曾把 `日语`、`日本語` 误选为中文 Pack；现改为仅识别明确中文标记，其余非中文 language 使用英文指令 Pack，并已重新执行完整回归。
- 未验证项：真实目标模型的中英文路由质量和 Token/延迟对比。

## 审查与最终状态

- 审查文档：`agentic/docs/reviews/lead-agent-runtime-unification-review.md`
- 审查结论：`APPROVED`；无未解决 blocking/major。
- 最终状态：`READY_TO_MERGE`。Feature Flag 因真实目标模型质量/延迟尚未评测而继续默认关闭。
