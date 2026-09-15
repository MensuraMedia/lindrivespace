# Full Development Team

> Extended team for complex feature work that requires architecture decisions.
> Adds the Architect (Opus) for high-intensity design and coordination.

## Team Composition

| Role | Agent File | Model | Intensity Range | Responsibility |
|------|-----------|-------|----------------|---------------|
| Architect | `architect.md` | Opus | 8-10 | System design, task breakdown, architectural decisions |
| Scout | `scout.md` | Haiku | 1-3 | Fast codebase exploration and information gathering |
| Implementer | `implementer.md` | Sonnet | 4-7 | Feature implementation and code changes |
| Reviewer | `code-reviewer.md` | Sonnet | 4-7 | Code quality, security, and correctness review |
| Data Checker | `data-checker.md` | Haiku | 1-3 | Config and data validation |

## Coordination Protocol

1. **Architecture Phase**: Spawn architect to analyze the task, design the approach, and break it into sub-tasks with intensity scores
2. **Research Phase**: Spawn scout(s) in parallel based on architect's plan
3. **Implementation Phase**: Spawn implementer with architect's design + scout's findings
4. **Review Phase**: Spawn reviewer to validate against architect's design
5. **Synthesis**: Main session collects all results, updates changelog and board

## When to Use

- New features requiring design decisions
- Major refactoring across multiple modules
- Cross-cutting concerns (auth, logging, error handling)
- Performance optimization that requires architectural analysis
- Any task scoring 8+ on the intensity scale

## Cost Note

This team includes Opus, which is ~10x more expensive than Haiku per token.
Use the default-team.md for tasks that don't require architectural decisions.
