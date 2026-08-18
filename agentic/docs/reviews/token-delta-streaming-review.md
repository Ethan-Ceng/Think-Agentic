# Token Delta Streaming 代码审查

## 审查范围

- 目标基线：Lead Agent Runtime Unification（`ce71be8`）
- 变更分支：`feature/token-delta-streaming`
- 变更范围：`ce71be8..working tree`
- 设计文档：`agentic/docs/designs/token-delta-streaming.zh-CN.md`
- 计划文档：`agentic/docs/plans/token-delta-streaming-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-08-18

## 需求符合度

- [x] 符合设计文档和验收标准。
- [x] Provider 聚合、字段投影、Agent 接线、Redis/SSE、Web 草稿、TTFT 和迁移均已落地。
- [x] 未修改 Sandbox、Durable Runtime、Sub Agent/A2A、Responses API 或多模态协议。
- [x] 当前运行实例的迁移版本漂移已记录为部署前置条件，没有通过覆盖旧服务绕过。

## 正确性

- [x] 空流、usage-only chunk、reasoning、分片 Tool Call、Unicode/escape、retry/reset/abort/final 均有覆盖。
- [x] Streaming 明确不兼容只在收到任何流事件之前回退块调用；消费开始后绝不隐式重放完整请求。
- [x] Final 与 abort 会封闭前端 stream，迟到 Delta 不能改写权威消息或复活草稿。
- [x] Delta 不进入 Session/Trace，Final 只沿现有持久化路径保存一次。
- [x] SSE Event ID 与 `stream_id + sequence` 覆盖重放去重和顺序防御。

## 安全性

- [x] 字段名由 Agent 代码固定，用户不能指定投影字段。
- [x] 公共 Delta 只包含选定顶层字符串；原始 JSON、reasoning 和 Tool Arguments 不进入 SSE。
- [x] Pydantic/Direct 安全校验失败会 abort 草稿，不能提交临时文本为最终事实。
- [x] 权限继续复用 Session 所有权校验，没有新增外部访问入口。
- [x] 本批未新增文件、命令或 Sandbox 执行权限。

## 可维护性

- [x] Provider 内部事件、Agent 投影事件和公共 SSE 事件分层明确。
- [x] `VisibleMessageStream` 统一维护 stream ID、sequence 与终止语义。
- [x] Feature Flag 默认关闭；无 `stream()` Fake、显式不兼容 Provider 和旧历史记录均保持兼容。
- [x] 数据迁移单 head、可正反执行，`ttft_ms` 为 nullable。

## 测试质量

- [x] 核心 Direct/React/Plan/Tool Loop/Finalizer 路径有自动化覆盖。
- [x] 两项审查缺陷均新增回归测试。
- [x] 中途异常、重试耗尽、无流式能力、参数不兼容、重连、乱序和终态迟到事件均有覆盖。
- [x] 使用真实 `deepseek-v4-pro` 验证 Provider、Lead 三模式、React Goal 与 Plan Step，而非只验证 Mock。

## 问题列表

未发现未解决的 blocking、major 或 minor 问题。

### [major][已修复] Provider 明确拒绝 Streaming 时没有降级

位置：`agentic/api/app/core/llm/openai_llm.py`、`agentic/api/app/core/agent/base.py`

问题：Provider 暴露 `stream()`，但模型或兼容端明确拒绝 `stream=true` 时，原实现只会重复流式重试，不能回到已有 `invoke()` 路径。

影响：开启 Flag 后，原本可用的非流式 Provider 会导致 Run 失败，违反兼容性验收。

处置：增加 `LLMStreamingUnsupportedError`；Provider 只在创建流阶段识别明确不兼容，BaseAgent 只在尚未收到任何流事件时回退块调用。收到任意事件后继续沿现有 reset/retry/abort，避免重复请求。Provider 与 Agent 层回归测试均已通过。

### [major][已修复] Final/abort 后的迟到 Delta 可改写终态

位置：`agentic/web/src/lib/session-events.ts`

问题：原时间线聚合只记录 sequence，没有把 Final 或 abort 标记为流终态；同一 `stream_id` 的迟到 append 可重新修改 Final 或复活草稿。

影响：在异常重放或乱序情况下，前端可能暂时显示非权威内容，并重新进入 streaming 状态。

处置：增加 closed stream 集合；Final/abort 后忽略同 stream 的所有 Delta，并新增两类终态回归测试。

## 无法验证项

- 未对当前 `http://localhost:8088` 做原地升级黑盒测试。运行中的 `manus-api` 是未挂载工作区的旧镜像，其数据库 revision 为仓库不存在的 `20260728_0001`；直接重建会覆盖现有文档处理版本。已改用只读挂载当前源码的隔离容器连接现有 Provider 做真实模型验证。
- 未执行长时间 Staging 压测、断网抖动注入和浏览器性能录制；Feature Flag 因此保持默认关闭。
- 本次是同一 Agent 自检，不具备独立 Reviewer 的视角隔离；合并前由另一位 Reviewer 快速复核高风险边界会更可靠。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 自审未发现 blocking。 |
| 无未处理 major | 通过 | 两项 major 已修复并补回归。 |
| 验收标准满足 | 通过 | 设计验收清单全部完成；真实 Provider/Agent 输出通过。 |
| 相关测试通过 | 通过 | Backend 全量 452 passed；Web 44 files / 183 passed。 |
| 构建通过 | 通过 | Ruff、compileall、vue-tsc、Vite build、git diff check 均通过。 |
| 数据迁移已验证 | 通过 | PostgreSQL 16 upgrade/downgrade/upgrade；唯一 head `20260818_0001`，列为 nullable integer。 |

## 审查结论

- 结论：`APPROVED`
- 理由：设计范围完整实现，自动化与真实模型验证通过，两项审查 major 已关闭，无未解决合并阻塞项。
- 剩余风险：当前运行实例的未入库文档迁移必须在部署前回收；默认开关应保持关闭，先在 Staging 观察 TTFT、错误率和 Redis/SSE 事件量；同一 Agent 自审仍建议独立复核。
- 下一步：可以提交/合并当前功能分支；未经用户授权不执行提交、推送、PR 或合并。部署前先统一运行镜像、源码和 Alembic 迁移链。
