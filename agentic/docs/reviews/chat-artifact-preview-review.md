# Markdown 代码块与生成产物统一预览代码审查

## 审查范围

- 目标分支：`master`
- 变更分支：`feature/chat-artifact-preview`
- 变更范围：`2db46ed..0556c05` 加 Task 5 当前工作区安全整改
- 设计文档：`agentic/docs/designs/chat-artifact-preview.zh-CN.md`
- 计划文档：`agentic/docs/plans/chat-artifact-preview-plan.md`
- 审查者：同一 Agent 自检
- 审查日期：2026-07-25

## 需求符合度

- [x] 符合设计文档和验收标准。
- [x] 没有遗漏功能。
- [x] 没有擅自扩大范围。
- [x] 计划偏差均已记录并有依据。

实现保持 Inline Artifact 为 Assistant 消息的只读派生视图，没有新增数据库、后端 API、模型输出协议或运行依赖。生成文件继续使用既有鉴权下载链路；文件、工具、Artifact 与 Trace 使用单一选择状态协调，VNC 保持独立覆盖层。

## 正确性

- [x] 边界条件、空值和异常路径正确。
- [x] 错误处理不会隐藏失败。
- [x] 状态转换和数据一致性正确。
- [x] 并发和幂等风险已处理。

代码块只在已闭合且非空时获得操作；复制、下载和打开消费 render 时保存的原文。文件预览覆盖扩展名回退、未知类型、单次 Blob 复用、错误重试、快速切换竞态、延迟文本解析和对象 URL 清理。Session 切换会清空预览选择，自动工具只覆盖空选择或既有 auto-tool。

## 安全性

- [x] 权限和越权访问已检查。
- [x] 输入校验和注入风险已检查。
- [x] 敏感数据不会泄漏。
- [x] 文件和命令执行风险已检查。

Markdown 保持 `html: false`；HTML/SVG 只进入 `sandbox=""` iframe，并在用户内容之前注入严格 CSP。浏览器实测覆盖脚本、父页面读取、远程图片、子 frame、表单、refresh、弹窗和点击链接。浏览器内复制与 Blob 下载没有调用后端、shell 或沙箱文件写入。

### 已整改的 major：sandbox iframe 仍可进行自身导航

位置：`agentic/web/src/components/chat/SafeHtmlPreview.vue:43`

问题：首次 Chrome 验收发现，空 sandbox 虽会阻止脚本和顶层越权，但用户点击预览中的普通 `<a href>` 仍会让 iframe 自身请求外部地址；远程资源 URL 也可能进入浏览器请求管线。仅依赖 `navigate-to 'none'` 和资源 CSP 不能满足本设计“预览不发起网络请求”的严格边界。

影响：恶意或误导性 HTML 可在用户点击后尝试联网，违反安全验收标准。

整改：在构建 `srcdoc` 前使用惰性 `<template>` 解析内容，移除 refresh、导航、表单、嵌套文档和外部资源 URL；`src/poster` 仅保留 `data:`/`blob:`。空 sandbox 与 CSP 继续作为第二、第三道防线。

验证：新增组件回归测试，并用本机 Chrome 重跑恶意 HTML；脚本未执行、父页面未被修改，`evil.invalid` 请求数为 0。

## 可维护性

- [x] 命名和结构清晰。
- [x] 没有不必要的重复或过度抽象。
- [x] 与项目规范和现有模式一致。
- [x] 兼容性和迁移策略明确。

类型识别和 selection 规则均提取为小型纯函数；面板复用 MarkdownContent、SafeHtmlPreview、下载工具和既有侧栏 CSS。无数据库迁移，回滚仅涉及前端派生视图和选择状态。

## 测试质量

- [x] 核心行为有覆盖。
- [x] 审查发现的 Bug 有回归覆盖。
- [x] 异常和边界路径有覆盖。
- [x] 测试验证真实业务结果，不只验证 mock 或实现细节。

最终全量前端测试为 33 个文件、119 项；另使用真实 Chrome 挂载实际 Vue 组件，验证网络请求、桌面/390px 布局、暗色和键盘焦点。

## 问题列表

未发现未处理的 `blocking`、`major`、`minor` 或 `suggestion`。

## 无法验证项

- 未在已登录的真实 SSE Agent 会话中重新生成一条新回复；消息、Session、工具、Trace、分支、审批和 HITL 使用全量测试及组件级浏览器验收覆盖。
- 内置浏览器连接因插件版本引用失效而不可用，页面验收改用本机 Chrome + Playwright。

## 合并门禁

| 门禁 | 结果 | 证据 |
| --- | --- | --- |
| 无 blocking | 通过 | 完整 diff 自检未发现 blocking |
| 无未处理 major | 通过 | iframe 自身导航问题已整改并重验 |
| 验收标准满足 | 通过 | 自动化、安全浏览器、390px、暗色和键盘验收通过 |
| 相关测试通过 | 通过 | 33 个测试文件、119 项测试通过 |
| 构建通过 | 通过 | `pnpm build`，3665 个模块完成生产构建 |
| 数据迁移已验证 | 不适用 | 本批无后端或数据库变化 |

## 审查结论

- 结论：`APPROVED`
- 理由：已处理浏览器实测发现的 major，整改后安全验收、全量测试、类型检查、生产构建和变更边界均通过。
- 剩余风险：本次为同一 Agent 自检，独立 Reviewer 对安全边界的复核仍更可靠；未重复进行真实登录态 SSE 会话生成。
- 下一步：等待用户明确提交、推送或合并。
