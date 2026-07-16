# Skill 编写与使用指南

Agentic Skill 是一个可移植、可校验、不可变版本化的 Runbook 包。它向 Planner 与 ReAct 提供当前 Run 的操作说明和资源，但不是 DAG、插件安装器，也不会在 API 主机上直接执行脚本。

## 标准目录

```text
my-skill/
├── SKILL.md               # 必需；UTF-8 Markdown + YAML frontmatter
├── scripts/               # 可选；在 Session Sandbox 内按说明使用
├── references/            # 可选；说明、模板和领域资料
└── assets/                # 可选；图片、样例等二进制资源
```

符号链接、路径穿越、绝对路径、重复归一化路径和非常规文件会被拒绝。归档内必须只有一个 Skill 根目录；包经规范化后生成确定性字节和 SHA-256。

## SKILL.md

```markdown
---
name: report-writer
description: Create an evidence-based report from supplied sources.
license: MIT
compatibility: Agentic sandbox with read_file and write_file
metadata:
  author: Example Team
  version: "1.0"
allowed-tools: read_file write_file search_web
---

# Report Writer

1. Clarify the requested audience and decision.
2. Inspect supplied sources before drafting.
3. Separate evidence, inference and recommendation.
4. Write the final artifact to the requested path.
```

支持的 frontmatter 字段如下：

- `name`：必需；1–64 字符，仅小写字母、数字和单连字符，不能以连字符开头或结尾。
- `description`：必需；1–1024 字符，用一句话说明能力和适用场景。自动选择主要依赖它。
- `license`、`compatibility`：可选字符串。
- `metadata`：可选字符串键值表。
- `allowed-tools`：可选字符串；用于声明预期工具。运行时仍以用户实际可用工具和系统策略为准。

未知字段会校验失败。正文应写可执行的判断标准、步骤、失败降级和产物要求；避免把密钥、用户数据或机器绝对路径写进包。

## 限制

默认限制可通过部署设置调整：归档 50 MiB、解压后 100 MiB、最多 256 个文件、单文件 10 MiB、`SKILL.md` 256 KiB、相对路径 240 字符。作者应把大型资料放入受控存储，让 Skill 只保留索引和使用方式。

## 创建与发布

在“我的 Skills”中可新建草稿、导入 `.skill`/`.zip`，或使用内置 `skill-creator` 对话创建。Creator 只能操作当前用户的隔离草稿，不能发布；用户必须在编辑器中检查文件、通过校验并显式点击发布。发布后生成新版本，已有版本和 SHA-256 不会被覆盖。

修改已发布 Skill 时，新建同名草稿并再次发布即可形成下一版本。Marketplace 内容不可直接修改；“Fork 并编辑”会把指定市场版本复制为个人草稿，显式发布后记录来源 Skill 与来源版本。

## 调用方式

- 手动调用：在消息输入区选择 Skill。手动选择优先，且必须属于当前用户可见目录。
- 自动调用：启用“自动调用”后，选择器根据消息和 manifest 判断；选择失败会降级为不使用 Skill，不阻断普通 Run。
- Marketplace：只有当前用户安装且启用的固定版本进入手动和自动目录。第一版 `auto_update=false`，新版本不会静默改变当前安装。

每个 Run 都重新选择和物化包。内容只出现在该 Session Sandbox 的 `/home/ubuntu/.agentic/skills/<run_id>/...`，下一 Run 不继承 Prompt 或路径。Trace 保存来源、选择模式、版本、hash、原因和沙箱路径，可用于复现历史 Run。

## Runbook 建议

优先描述“何时判断、做什么、失败怎么办”，例如：

1. 校验输入是否足够；不足时先澄清。
2. 读取附件和 references，不猜测缺失事实。
3. 仅调用 `allowed-tools` 中且当前可用的工具。
4. 对外部写入或高风险动作遵守确认策略。
5. 验证最终文件或结构，再返回路径与摘要。

不要在 Skill 内假设脚本已执行，也不要指示绕过 Sandbox、权限、确认或 Trace。

## 常见问题

- 校验提示 manifest 无效：检查 YAML 缩进、未知字段、`name` 格式和 `description`。
- 导入提示 unsafe archive：移除符号链接、绝对路径、`..`、重复路径或多根目录。
- 手动选择后未生效：确认 Skill 已发布并启用；Marketplace Skill 还需当前用户安装。
- 自动选择不到：完善 `description`，确认自动调用开关和工具兼容性；必要时改用手动选择。
- Run 中包加载失败：在 Trace 查看固定版本、SHA-256、存储 provider 和物化错误；不要覆盖旧对象。
- Creator 没有发布：这是预期安全边界；从会话工具卡进入草稿编辑器后显式发布。
