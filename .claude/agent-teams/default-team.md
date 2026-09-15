# Default Development Team

> Orchestration guide for the standard multi-agent workflow.
> Use with the `/team` command to launch coordinated task execution.

## Team Composition

| Role | Agent File | Model | Intensity Range | Responsibility |
|------|-----------|-------|----------------|---------------|
| Scout | `scout.md` | Haiku | 1-3 | Fast codebase exploration, file lookups, data gathering |
| Implementer | `implementer.md` | Sonnet | 4-7 | Feature implementation, bug fixes, code changes |
| Reviewer | `code-reviewer.md` | Sonnet | 4-7 | Code quality, security review, best practices |
| Data Checker | `data-checker.md` | Haiku | 1-3 | Config validation, data integrity checks |

## Coordination Protocol

1. **Task Intake**: Main session receives the task from the user
2. **Planning**: Break task into sub-tasks, score each for intensity (see `routing-rules.md`)
3. **Approval**: Present plan to user, wait for confirmation
4. **Research Phase**: Spawn scout(s) in parallel for information gathering
5. **Implementation Phase**: Spawn implementer with research results as context
6. **Review Phase**: Spawn reviewer to check the implementer's work
7. **Synthesis**: Main session summarizes results, updates changelog and board

## When to Use

- Tasks touching 3+ files
- Feature additions that need research first
- Bug fixes requiring investigation before implementation
- Any task where you'd benefit from a second opinion (reviewer)

## Communication

Agents don't message each other directly. The main session acts as coordinator:
- Collects results from each agent
- Passes relevant context to the next agent in the pipeline
- Updates `board.md` with status after each phase
- Resolves conflicts between agent recommendations

## Escalation

If a Sonnet agent reports the task is too complex, escalate to Opus (architect).
If a Haiku agent can't find what it needs, escalate to Sonnet (implementer with broader tools).
