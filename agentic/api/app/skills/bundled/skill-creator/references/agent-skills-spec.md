# Supported Agent Skill format

A Skill is one directory whose root contains `SKILL.md`. The directory name and frontmatter `name` must be the same lowercase kebab-case value.

Supported frontmatter fields are `name`, `description`, `license`, `compatibility`, `metadata`, and `allowed-tools`. Only `name` and `description` are required. Unknown fields are rejected.

Use UTF-8 regular files only. Symbolic links, path traversal, multiple archive roots, reserved Windows names, and duplicate paths after case folding are rejected. Keep the package within the platform limits shown by validation diagnostics.

Optional conventional directories:

- `references/` for material loaded only when needed.
- `scripts/` for reusable automation that the agent may choose to run.
- `assets/` for templates and static inputs used in outputs.

The platform builds deterministic immutable package bytes at publish time. A new publish creates a new version; it never mutates an earlier version.
