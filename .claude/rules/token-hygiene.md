---
paths:
  - "**/*"
---

# Token Hygiene & Context Management (2026)

## .claudeignore (Required for Every Project)
Every project MUST have a .claudeignore file excluding build artifacts and irrelevant files:
```
node_modules/
dist/
build/
*.log
coverage/
.env*
**/.git/
__pycache__/
*.pyc
.venv/
vendor/
*.o
*.so
*.a
```
Adapt for your project's language and build system.

## Context Management
1. Use /clear between unrelated tasks
2. Use sub-agents for heavy research tasks — don't pollute the main context
3. Keep CLAUDE.md under 200 lines — use @imports for details
4. Use path-scoped rules with YAML `paths:` frontmatter so rules only load when editing relevant files
5. Reference docs with @path instead of pasting content inline
6. Use official Auto Memory (/memory) for Claude's own learnings — supplement with project changelog.md and decisions.md
7. Only use /compact as a last resort — 1M+ context models handle large sessions natively
