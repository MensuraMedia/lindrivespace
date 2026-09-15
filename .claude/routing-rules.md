# Dynamic Model Routing Rules (Intensity-Based)

> Reference document for agent orchestration. When the team lead (or Claude directly)
> needs to delegate a task, use this intensity scoring to pick the right model tier.

## Intensity Scoring

Before delegating to a sub-agent, evaluate the task's complexity on a 1-10 scale:

| Intensity | Model Tier | Agent Types | Examples |
|-----------|-----------|-------------|---------|
| 1-3 (Low) | Haiku (`claude-haiku-4-5-20251001`) | scout, data-checker | File lookups, grep searches, config validation, simple questions |
| 4-7 (Medium) | Sonnet (`claude-sonnet-4-6`) | implementer, code-reviewer, specialists | Feature implementation, bug fixes, code review, refactoring |
| 8-10 (High) | Opus (`claude-opus-4-6`) | architect | System design, complex multi-file refactors, major decisions, cross-cutting changes |

## Routing Decision Process

1. **Describe the task** in one sentence
2. **Score intensity** based on:
   - Number of files affected (1-2 = low, 3-5 = medium, 6+ = high)
   - Architectural impact (none = low, local = medium, cross-cutting = high)
   - Risk level (safe = low, moderate = medium, breaking changes = high)
   - Domain complexity (straightforward = low, nuanced = medium, novel design = high)
3. **Select agent** matching the intensity tier
4. **Delegate** using Claude Code's Agent tool with `subagent_type` and `model` parameters

## Cost Optimization

- **Always prefer the cheapest model that can do the job** — don't use Opus for a grep search
- **Escalate, don't start high** — begin with Haiku/Sonnet; only escalate to Opus if the task proves too complex
- **Log routing decisions** in board.md for audit and cost tracking
- Haiku is ~10x cheaper than Opus per token — routing matters

## Using with Custom Commands

- `/route` — Evaluate a task and suggest the right agent + model
- `/team` — Launch a coordinated multi-agent workflow
