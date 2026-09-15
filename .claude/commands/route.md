---
description: "Score task intensity and recommend the right agent + model tier"
argumentHint: "[task description]"
---

# /route — Evaluate Task and Recommend Agent

Score a task's intensity and recommend the right agent + model tier.

## Workflow

1. **Read the task description** provided by the user.

2. **Score intensity (1-10)** based on:
   - Files affected: 1-2 = low, 3-5 = medium, 6+ = high
   - Architectural impact: none = low, local = medium, cross-cutting = high
   - Risk level: safe = low, moderate = medium, breaking changes = high
   - Domain complexity: straightforward = low, nuanced = medium, novel design = high

3. **Map to agent + model** using `@.claude/routing-rules.md`:
   - 1-3: Haiku agent (scout, data-checker)
   - 4-7: Sonnet agent (implementer, code-reviewer, specialists)
   - 8-10: Opus agent (architect)

4. **Present recommendation** to the user:
   ```
   Task: [description]
   Intensity: [score]/10
   Recommended: [agent-name] on [model-tier]
   Reasoning: [one line]
   ```

5. **If user approves**, delegate to the recommended agent using the Agent tool.

## Notes
- See `.claude/routing-rules.md` for the full scoring rubric
- Always prefer the cheapest model that can handle the task
- Log routing decisions in board.md for cost tracking
