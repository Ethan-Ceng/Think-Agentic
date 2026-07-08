# OpenSquilla MetaSkill 设计与实现总结

> 基于本仓库源码与文档在 2026-07-07 的本地审阅整理。本文聚焦 MetaSkill 的设计方案、执行模型、实现链路、运行状态、审计回放和可借鉴点。

## 1. 核心判断

OpenSquilla 的 MetaSkill 不是 Mermaid、BPMN 或传统流程设计器。它更接近一套 Agent 工作流协议层：

```text
Skill Manifest
  -> MetaPlan / Execution Graph
  -> MetaOrchestrator / Graph Runtime
  -> Step Executors
  -> MetaRunWriter / Audit / Replay
```

它要解决的问题是：复杂任务如果每次都让 Agent 临场发挥，结果难复用、难审计、难稳定提升。MetaSkill 把高价值、多步骤任务沉淀成可声明、可执行、可暂停、可回放、可改进的任务协议。

可以把它理解为：

```text
普通 Skill = 一个能力说明书 / 一个专长包
MetaSkill = 多个 Skill、工具、LLM 步骤、人工输入和最终汇总组成的 DAG 工作流
```

项目文档里的类比也很准确：MetaSkill 之于 Skill/Tool，就像 Makefile 之于 shell command。Makefile 不发明新命令，但定义命令如何组合；MetaSkill 不发明新的执行原子，但定义现有能力如何编排。

## 2. 和“Skill Manifest + Execution Graph + Runtime”的对应关系

| 抽象概念 | OpenSquilla 实现 |
| --- | --- |
| Skill Manifest | `SKILL.md` + frontmatter + `SkillSpec` |
| 能力描述 | `name`、`description`、`triggers`、`metadata` |
| 风险和能力 | `metadata.opensquilla.risk`、`capabilities` |
| 输入模板 | `request_template`、`user_input` / `clarify` |
| 输出契约 | `output_contract`、`final_text_mode` |
| Execution Graph | `composition.steps` |
| 节点 | `MetaStep` |
| 边 | `depends_on` |
| 条件执行 | `when` |
| 分支路由 | `route` |
| 失败处理 | `on_failure` |
| Runtime | `MetaOrchestrator` + `scheduler.run_dag()` |
| Step 执行器 | `agent`、`llm_chat`、`llm_classify`、`tool_call`、`skill_exec`、`user_input` |
| 运行状态 | `MetaResult`、`MetaStepStateEvent`、`MetaRunAnnouncedEvent`、`MetaRunCompletedEvent` |
| 审计回放 | `MetaRunWriter`、meta run CLI / RPC 报告 |
| UI 展示 | Web UI step ribbon，不是执行源 |

结论：OpenSquilla 的核心执行格式就是机器友好的结构化 DAG，而不是 Mermaid/BPMN。可视化只是后续展示层。

## 3. Manifest 结构

一个 MetaSkill 是一个 `SKILL.md` 文件，关键字段通常包括：

```yaml
---
name: meta-example
kind: meta
description: "When to use this workflow."
triggers:
  - "example trigger"
meta_priority: 50
always: false
final_text_mode: auto
request_template:
  outcome: "Expected outcome."
  fields: []
output_contract:
  required_sections: []
metadata:
  opensquilla:
    risk: low
    capabilities: []
composition:
  steps: []
---
```

其中：

- `kind: meta` 是 MetaSkill 的识别标志。
- `triggers` 用于显式或自动触发匹配。
- `meta_priority` 用于多个候选工作流的排序。
- `request_template` 描述运行前需要确认或收集的字段。
- `output_contract` 声明最终交付物的结构要求。
- `metadata.opensquilla.risk` 和 `capabilities` 用于风险、审计和自动启用判断。
- `composition.steps` 是真正的执行图。

## 4. Execution Graph 模型

MetaSkill 的执行图由 `composition.steps` 定义，解析后变成 `MetaPlan` 和多个 `MetaStep`。

每个 `MetaStep` 支持：

| 字段 | 含义 |
| --- | --- |
| `id` | 节点 ID，必须唯一。 |
| `kind` | 节点执行类型。 |
| `skill` | 对 `agent` / `skill_exec` 节点，指定调用哪个普通 Skill。 |
| `with` | 模板化输入参数。 |
| `depends_on` | 依赖哪些前置节点。 |
| `when` | 条件表达式，为 false 时跳过。 |
| `route` | 根据输入或上游输出选择实际 skill。 |
| `output_choices` | `llm_classify` 的闭集标签。 |
| `tool` / `tool_args` | `tool_call` 的工具名与参数。 |
| `tool_allowlist` | 单节点工具白名单。 |
| `on_failure` | 失败时转入的替代节点。 |
| `clarify` | `user_input` 的结构化用户输入 schema。 |
| `label` | UI 进度条上的短标签。 |
| `progress_emits` | 是否允许该步骤向 UI 发进度文本。 |

一个简化例子：

```yaml
composition:
  steps:
    - id: classify
      kind: llm_classify
      output_choices: [DOCS, BUG, SECURITY]
      with:
        text: "{{ inputs.user_message | xml_escape | truncate(512) }}"

    - id: handle
      kind: agent
      skill: summarize
      depends_on: [classify]
      route:
        - when: "outputs.classify == 'DOCS'"
          to: writer
        - when: "outputs.classify == 'BUG'"
          to: debugger
      with:
        request: "{{ inputs.user_message | xml_escape | truncate(512) }}"
```

## 5. Plan 解析与校验

核心实现：`src/opensquilla/skills/meta/parser.py`。

解析器负责把 `SkillSpec.composition_raw` 转换成 `MetaPlan`。主要校验包括：

- 非 `kind: meta` 的 Skill 不会被解析成 MetaPlan；
- `composition` 必须是 dict；
- `composition.steps` 必须是非空 list；
- step 必须是 mapping；
- step id 必须存在且唯一；
- `kind` 必须属于支持集合；
- `agent` / `skill_exec` 必须声明 `skill`；
- `llm_classify` 必须声明 `output_choices`；
- `tool_call` 必须声明合法 `tool` / `tool_args`；
- `tool_allowlist` 必须包含实际 tool；
- `user_input` 必须声明合法 `clarify` schema；
- `depends_on` 必须是 list；
- `with` 必须是 mapping；
- `on_failure` 必须引用合法替代 step；
- 图必须无环。

这一步相当于 Plan Validator。它保证执行前图结构是可理解、可排序、可审计的。

## 6. Step 执行类型

MetaSkill 支持六类执行节点。

### 6.1 `agent`

实现：`src/opensquilla/skills/meta/executors/agent.py`。

用途：启动一个子 Agent，用指定普通 Skill 的 `SKILL.md` 作为 system prompt，完整走 Agent 工具循环。

特点：

- 适合开放式推理、搜索、写作、综合；
- 子 Agent 的工具事件可以透传给外层 UI；
- 子 Agent 的最终文本会被收集成该 step 的输出；
- 禁止组合另一个 MetaSkill，避免递归；
- 会检查该 Skill 是否被 operator 配置禁用。

### 6.2 `llm_chat`

实现：`src/opensquilla/skills/meta/executors/llm_classify.py`。

用途：单次 LLM 调用，不开工具循环。

适合：

- intake normalization；
- 轻量生成；
- 最终审查；
- 小范围摘要；
- 不需要工具的中间步骤。

### 6.3 `llm_classify`

实现：同上。

用途：单次受限分类，输出必须落入 `output_choices`。

特点：

- 系统提示要求模型只输出一个 label；
- 如果输出不严格，会尝试用一次 LLM repair 修复；
- 最后仍会做 choice coercion；
- 适合路由、triage、模式选择。

### 6.4 `tool_call`

实现：`src/opensquilla/skills/meta/executors/tool_call.py`。

用途：绕过 LLM，直接调用工具。

特点：

- `tool_args` 会通过 Jinja 模板渲染；
- 运行时再次检查 `tool_allowlist`；
- 如果 `tool_invoker` 不存在，会退化成一个子 Agent 模拟工具调用；
- 适合确定性副作用，例如保存记忆、发出固定文本、写文件等。

### 6.5 `skill_exec`

实现：`src/opensquilla/skills/meta/executors/skill_exec.py`。

用途：执行带 `entrypoint` 的 CLI 型 Skill。

特点：

- 不经过 LLM；
- 渲染 `command`、`args`、`env`、`stdin`、`assemble`；
- 可先把模板文件写入工作目录，再运行命令；
- 支持 `parse: text | json | lines`；
- 会校验 cwd 和 assemble 目标不能逃逸允许根目录；
- 适合文档转换、报告生成、脚本型能力。

### 6.6 `user_input`

实现：`src/opensquilla/skills/meta/executors/user_input.py`。

用途：暂停工作流，收集结构化用户输入。

特点：

- 支持 `form` / `chat` 模式；
- 字段类型支持 `string`、`enum`、`int`、`bool`；
- 支持 `required`、`default`、`min`、`max`、`max_chars`；
- 支持 `skip_if`；
- 支持 `nl_extract`，可从上下文自动提取字段；
- 成功进入等待态时抛出 `MetaPaused`；
- 恢复后由 `MetaOrchestrator.resume()` 继续 DAG。

这类节点是 MetaSkill 很重要的 Agent-native 能力：它允许流程中途让用户确认或补充信息，而不是一次性跑到底。

## 7. 模板系统与安全边界

核心实现：`src/opensquilla/skills/meta/templating.py`。

MetaSkill 使用 Jinja 渲染 step 参数，但不是裸 Jinja，而是受限环境：

- `ImmutableSandboxedEnvironment`
- `StrictUndefined`
- 清空 globals
- 限定 filters
- 阻断 Python 属性内省和可变操作

允许的典型 filter：

- `xml_escape`
- `truncate`
- `slugify`
- `tojson`
- `default`
- `join`
- `lower`
- `extract_path`
- `contains_cjk`
- `int`

`when` 和 `route` 也是通过受限 Jinja expression 执行。

作者文档明确要求：

- 用户输入必须 escape 或 truncate；
- 上游 step 输出必须 truncate 或 tojson；
- 不要裸传 `inputs.user_message`；
- 不要裸传 `outputs.some_step`。

这套设计是在控制 prompt injection、模板逃逸和上下文污染。

## 8. 触发机制

默认触发方式是显式命令：

```text
/meta
/meta <meta-skill-name>
```

自动触发不是默认行为，需要配置：

```toml
[meta_skill]
auto_trigger = true
```

触发链路：

1. `meta_resolution.py` 扫描已加载的 `kind == meta` Skill。
2. 根据 triggers、`meta_priority`、语义匹配等确定候选。
3. 将 `MetaMatch` 写入 turn metadata。
4. 向 system prompt 注入提示：如果意图匹配，应调用 `meta_invoke(name=...)`。
5. 对确定性 trigger，可以强制下一次工具选择 `meta_invoke`。
6. Agent 在工具调用阶段拦截 `meta_invoke`，启动 MetaOrchestrator。

`meta_invoke` 本身注册在工具系统里，但它的 handler 不应该真正执行。它是一个工具表面和路由信号，实际执行由 Agent 拦截。

这个设计的好处是：MetaSkill 可以复用工具可见性、工具选择、事件流和审计链路，同时又不把整个 DAG 当普通工具 handler 执行。

## 9. Orchestrator 与 Runtime

核心实现：`src/opensquilla/skills/meta/orchestrator.py`。

`MetaOrchestrator` 是门面层，不直接拥有所有重型依赖，而是接收注入：

- `agent_runner`
- `skill_loader`
- `llm_chat`
- `tool_invoker`
- `workspace_dir`
- `run_writer`
- `dao`

它负责：

- 调用 `scheduler.run_dag()`；
- 给 scheduler 注入 step dispatch 函数；
- 给 scheduler 注入持久化 hooks；
- 解析最终 `MetaResult`；
- 按 `final_text_mode` 生成最终文本；
- 修复最终输出语言；
- 附加 artifact verification notice；
- 附加 output contract block；
- 处理 preflight confirmation；
- 处理暂停和恢复。

这是一种比较清楚的分层：Orchestrator 管依赖和最终包装，Scheduler 管 DAG 调度，Executor 管单步执行。

## 10. DAG 调度器

核心实现：`src/opensquilla/skills/meta/scheduler.py`。

调度器做的是 Graph Runtime 的核心工作：

```text
拓扑排序
  -> 找到 ready steps
  -> 按 max_parallelism 并行执行
  -> 收集事件
  -> 更新 outputs
  -> 解锁下游依赖
  -> 处理失败、替代、暂停、取消
  -> 产出 MetaResult
```

主要能力：

- 无依赖 step 可并行；
- 有 `depends_on` 的 step 等前置完成；
- `when` 为 false 的 step 会被跳过；
- `route` 可动态选择实际 skill；
- 任一 step 硬失败会取消兄弟任务；
- 有 `on_failure` 时启动替代 step；
- 替代 step 的输出会镜像到原失败 step，保证下游依赖继续可用；
- `user_input` 暂停时会取消其他运行任务并返回 paused MetaResult；
- Generator 被关闭或任务被取消时会清理运行中 step；
- 会产生 step state 事件和 run completed 事件；
- 会尽量保证 UI 工具卡片 start/result 成对出现。

这部分已经很像一个小型工作流引擎。

## 11. 运行状态与事件

MetaSkill 的运行不是黑盒。它会发出结构化事件：

- `MetaRunAnnouncedEvent`
- `MetaStepStateEvent`
- `MetaRunCompletedEvent`
- `ToolUseStartEvent`
- `ToolResultEvent`
- `MetaPreflightEvent`
- 最终 `MetaResult`

Web UI 可以用这些事件渲染 step ribbon：当前运行节点、高亮、成功、跳过、失败、替代、暂停等状态。

这说明可视化是从 runtime event 派生出来的，而不是反过来由可视化图驱动运行。

## 12. 暂停、澄清与恢复

`user_input` 节点会把运行状态转为 `awaiting_user`。

流程大致是：

1. step 判断 `skip_if`；
2. 如果不跳过，构造 clarify schema；
3. 可选运行 `nl_extract` 从上下文提取字段；
4. 通过 `MetaRunWriter.try_claim_awaiting()` 写入等待态；
5. 抛出 `MetaPaused`；
6. scheduler 捕获后返回 paused `MetaResult`；
7. 用户在 Web/CLI/渠道回复；
8. `meta_resolution.py` 解析补充信息；
9. `MetaRunWriter.try_claim_resume()` 竞争恢复权；
10. `MetaOrchestrator.resume()` 用已完成 outputs 继续 DAG。

这里用 CAS/claim 的思路避免重复恢复同一个等待任务。

## 13. 持久化、审计与回放

核心实现：`src/opensquilla/persistence/meta_run_writer.py`。

`MetaRunWriter` 是同步 SQLite writer，但：

- `check_same_thread=False`
- Python lock 串行化 SQL 调用
- WAL
- `foreign_keys=ON`
- `busy_timeout=5000`
- Orchestrator 通过 executor/thread 包装调用
- 写入失败 fail-open，只记录 warning

它记录：

- run id；
- meta skill name；
- meta skill digest；
- plan snapshot；
- triggered_by；
- session_key；
- turn_id；
- owner_pid；
- run status；
- inputs；
- final_text；
- failed_step_id；
- error；
- 每个 step 的 rendered inputs；
- step output；
- step error；
- substitute_step_id；
- usage summary；
- truncated fields；
- awaiting_user 状态。

配套 read-model 在 `src/opensquilla/skills/meta/run_reports.py`，支持：

- run summary；
- step summary；
- run diff；
- replay request；
- preflight confirmation message。

用户侧命令包括：

```sh
opensquilla skills meta runs list
opensquilla skills meta runs show <run-id>
opensquilla skills meta runs steps <run-id>
opensquilla skills meta runs replay <run-id> --dry-run
```

这让 MetaSkill 不只是“跑一个流程”，而是有审计账本。

## 14. 最终输出策略

`final_text_mode` 控制最终交付物：

```yaml
final_text_mode: auto
final_text_mode: raw
final_text_mode: "step:some_step"
```

含义：

- `auto`：由 Orchestrator 对多个 step 输出做最终总结；
- `raw`：直接返回最后一个非替代 step 的输出；
- `step:<id>`：指定某个 step 的输出作为最终结果。

`output_contract` 可以声明：

- required sections；
- assumptions；
- unverified facts；
- artifacts；
- forbidden terms；
- 是否把 contract 检查块追加到最终文本。

这让 MetaSkill 的输出比普通 Agent 回复更有结构化约束。

## 15. 失败处理

失败处理分几层：

1. 解析期失败
   `parse_meta_plan` 抛 `MetaPlanError`，该 MetaSkill 被跳过或不可用。

2. Step 执行失败
   如果 step 有 `on_failure`，调度器启动替代 step；否则取消兄弟任务并返回失败结果。

3. 暂停不是失败
   `MetaPaused` 被 scheduler 特殊处理，返回 paused 结果。

4. 审计写入失败不影响任务
   `MetaRunWriter` 是 observability 层，fail-open。

5. LLM 分类输出不合规
   先严格匹配，再尝试 repair，再 coercion。

6. CLI / skill_exec 失败
   非零退出、超时、JSON 解析失败、路径逃逸等都会变成 RuntimeError，交给调度器失败路径处理。

## 16. 风险控制

MetaSkill 的风险控制散布在多个层面：

- `metadata.opensquilla.risk` 声明风险等级；
- `metadata.opensquilla.capabilities` 声明副作用能力；
- `tool_call` 有 `tool_allowlist`；
- `skill_exec` 检查工作目录和文件写入不能逃逸允许根；
- `agent` 和 `skill_exec` 检查被组合 Skill 是否 live available；
- 禁止 MetaSkill 组合另一个 MetaSkill；
- Jinja 使用 sandbox；
- 作者指南要求 escape/truncate 用户输入和 step 输出；
- 默认手动 `/meta` 触发，自动触发默认关闭；
- 高风险操作仍需要用户授权和工具权限系统兜底。

这套控制不等于企业级权限治理，但已经比简单 prompt workflow 严谨很多。

## 17. 真实内置 MetaSkill 形态

当前稳定内置 MetaSkill 包括：

- `meta-kid-project-planner`
- `meta-paper-write`
- `meta-short-drama`
- `meta-skill-creator`

以 `meta-kid-project-planner` 为例，它包含：

- `request_template`：项目主题、年龄段、预算、受众、语言；
- `output_contract`：Feasibility verdict、Step-by-step plan、Materials、Safety notes、Guardian objectives；
- `eval_prompts`：质量基准；
- `policy_tags`：child-safety、age-appropriate；
- `composition.steps`：
  - `preferences`：`llm_chat` 提取偏好；
  - `project_clarify`：`user_input` 澄清缺失字段；
  - `feasibility`：`llm_classify` 判断可行性；
  - 后续 step 继续完成安全改写、项目包生成、审计等。

以 `meta-skill-creator` 为例，它本身就是“生成新 MetaSkill 提案”的 MetaSkill，流程包括：

- 意图澄清；
- 判断是普通 Skill 还是 MetaSkill；
- 用户补充；
- 模式分类；
- 可选历史采集；
- 触发词冲突检查；
- lint；
- proposal persistence；
- 最终响应。

这说明 MetaSkill 不只是用户任务流程，也承担“把重复协作模式沉淀成新流程”的元能力。

## 18. 设计优点

1. 执行格式机器友好
   核心是 YAML/JSON-like DAG，不依赖图形流程语言。

2. 分层清晰
   Loader、Parser、Orchestrator、Scheduler、Executor、Writer 职责相对明确。

3. 执行原子丰富
   同一 DAG 可以混合子 Agent、单次 LLM、直接工具、CLI、人工输入。

4. 支持暂停恢复
   适合真实用户任务，而不是只能一次性跑完。

5. 可审计
   plan snapshot、step input/output、错误、替代、最终输出都有记录。

6. 可逐步治理
   risk、capabilities、tool allowlist、output contract、eval prompts 都为后续治理留了口子。

7. UI 不绑架运行时
   Web UI 只是从事件流渲染进度，不是执行源。

## 19. 局限与风险

1. 动态 Planner 不是核心默认路径
   当前更偏“预定义 MetaSkill + 显式启动”，不是默认由 Planner 每次生成任意新图。

2. Schema 仍偏软
   `request_template`、`output_contract` 已有结构，但不是严格企业级 input/output schema enforcement。

3. 权限还不是完整企业 RBAC/ABAC
   有 risk、capabilities、tool gate，但还不是组织级策略引擎。

4. LLM step 仍有不确定性
   `llm_chat` 和 `agent` step 的质量依赖模型、提示词和上下文。

5. 作者门槛较高
   写好一个 MetaSkill 需要懂 DAG、模板安全、工具权限、失败路径和输出契约。

6. Runtime 已经复杂
   暂停、恢复、替代、并行、事件、持久化叠加后，测试成本不低。

## 20. 对企业 Agent 平台的借鉴

如果要做自己的企业 Agent 平台，可以借鉴它的方向，但第一版不必照搬全部复杂度。

建议保留：

```text
Skill Manifest
Execution Graph
Plan Validator
Graph Runtime
Step State
Approval / Human Input
Audit Log
Replay / Debug
```

第一版可以简化：

- 只支持少数 step kind：`skill`、`tool`、`llm`、`approval`；
- 强化 input/output schema；
- 强化 permission / risk；
- 每个节点都必须声明幂等性、超时、重试策略；
- 审计日志从第一天就做；
- 可视化从 Execution Graph 生成，而不是反过来。

不要一开始做：

- Mermaid 作为执行格式；
- BPMN 作为核心底座；
- 拖拽设计器；
- 复杂自动 Planner；
- 无边界的递归 Agent 编排。

## 21. 总结

OpenSquilla 的 MetaSkill 可以概括为：

```text
SKILL.md Manifest
+ composition.steps DAG
+ MetaPlan Validator
+ MetaOrchestrator
+ DAG Scheduler
+ Step Executors
+ Pause/Resume
+ MetaRun Audit Ledger
```

它的核心价值不是“多了一个 `/meta` 命令”，而是把 Agent 能力从一次性对话推进到可沉淀的流程资产：

- 可复用；
- 可审计；
- 可暂停；
- 可回放；
- 可治理；
- 可持续改进。

如果普通 Agent 是临时解决问题，普通 Skill 是操作手册，那么 MetaSkill 就是标准作业流程、执行记录和复盘机制的结合体。
