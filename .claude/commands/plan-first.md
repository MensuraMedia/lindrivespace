---
description: "Enforce plan-first workflow for any complex task"
argumentHint: "[task description]"
---

# /plan-first — Plan Before Executing

Use this command before starting any complex, multi-step, or risky task.

## Workflow

1. **Analyze** the request and identify:
   - Files that need to be read, edited, or created
   - Commands that need to be run
   - Dependencies between steps
   - Potential risks or breaking changes
   - Success criteria (how we know it's done)

2. **Output a detailed plan** as a numbered list with:
   - Each step clearly described
   - Files affected per step
   - Any decisions that need user input
   - Rollback strategy if something goes wrong

3. **Wait for explicit user approval** before proceeding.
   Do NOT begin execution until the user confirms with "approve", "go", "yes", or similar.

4. **Execute** the approved plan step by step, reporting progress.

5. **After completion:**
   - Update changelog.md with what was done
   - Write to Auto Memory if learnings are worth preserving
   - Update decisions.md if architectural choices were made

## When to Use
- Features that touch 3+ files
- Refactoring or migration work
- Anything involving database schema changes
- Changes to build configuration or CI/CD
- Security-sensitive modifications
