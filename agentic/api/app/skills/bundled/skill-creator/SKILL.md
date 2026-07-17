---
name: skill-creator
description: Create or improve a standard Agent Skill from a user's goal, examples, constraints, and reusable resources.
license: Apache-2.0
compatibility: Requires the platform Skill draft tools; publishing always requires explicit user review.
metadata:
  author: Agentic
  version: "1.0"
---

# Skill Creator

Create a focused, reusable Skill rather than a one-off answer.

## Workflow

1. Capture the intended outcome, representative requests, non-goals, required resources, and any tool or environment assumptions. Ask only for information that materially changes the package.
2. Choose a short kebab-case name. Design the smallest useful directory: keep the core procedure in `SKILL.md`, move detailed facts to `references/`, reusable automation to `scripts/`, and static inputs to `assets/`.
3. Call `skill_draft_create`, then use `skill_draft_tree`, `skill_draft_read`, and `skill_draft_write` to prepare the package. These operations are already scoped to the authenticated user; never request or invent an owner ID.
4. Keep frontmatter standard and minimal. Write a precise description that says both what the Skill does and when it should be selected. Put operational guidance in Markdown, not custom frontmatter fields.
5. Apply progressive disclosure: concise decision guidance first, ordered execution steps next, and specialized details in directly linked reference files. Avoid repeating the same facts in multiple files.
6. Call `skill_draft_validate`. Fix every diagnostic, validate again, and inspect the final tree and important files.
7. Hand the validated draft back with a short summary of its behavior and assumptions. Do not publish it: the user must review and click Publish.

Use [the supported specification](references/agent-skills-spec.md) and the [quality checklist](references/quality-checklist.md) while drafting.

When improving an existing Skill, preserve behavior the user relies on, explain material changes, and validate after every revision.
