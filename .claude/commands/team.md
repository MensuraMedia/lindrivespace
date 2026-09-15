---
description: "Launch a coordinated multi-agent workflow with intensity-based routing"
argumentHint: "[task description or team name: default|dev|review]"
---

# /team — Launch Coordinated Multi-Agent Workflow

Orchestrate a complex task across multiple agents using intensity-based routing.

## Workflow

1. **Analyze the task** and break it into sub-tasks:
   - Identify research/exploration tasks (scout — Haiku)
   - Identify implementation tasks (implementer — Sonnet)
   - Identify review tasks (code-reviewer — Sonnet)
   - Identify architecture/design tasks (architect — Opus)

2. **Score each sub-task's intensity** using `.claude/routing-rules.md`

3. **Present the execution plan** to the user:
   ```
   Team Plan for: [task description]

   Phase 1 — Research (parallel)
     - Scout (Haiku): [what to explore]
     - Data-checker (Haiku): [what to validate]

   Phase 2 — Implementation (sequential/parallel)
     - Implementer (Sonnet): [what to build]

   Phase 3 — Review
     - Code-reviewer (Sonnet): [what to review]

   Estimated agents: [count] | Models: [Haiku x2, Sonnet x2]
   ```

4. **Wait for user approval** before proceeding.

5. **Execute phases in order**:
   - Launch parallel agents where tasks are independent
   - Pass results between phases via the conversation context
   - Update board.md with status after each phase

6. **After completion**:
   - Summarize what each agent did
   - Update changelog.md
   - Write to Auto Memory if learnings are worth preserving
   - Log routing decisions and costs in board.md

## Team Configurations

Reference team templates in `.claude/agent-teams/` for pre-defined configurations:
- `default-team.md` — General-purpose (scout + implementer + reviewer)
- `dev-team.md` — Full development (architect + implementer + reviewer + scout)
- `review-team.md` — Code review focus (scout + reviewer + data-checker)

## Notes
- All agent delegation uses Claude Code's native Agent tool
- Agents are spawned via `subagent_type` parameter — no external tools needed
- board.md serves as the shared coordination surface between phases
- Each agent inherits the project's rules, hooks, and permissions
