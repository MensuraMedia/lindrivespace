# Review Team

> Focused team for code review, quality assurance, and validation tasks.
> Optimized for thoroughness over speed.

## Team Composition

| Role | Agent File | Model | Intensity Range | Responsibility |
|------|-----------|-------|----------------|---------------|
| Scout | `scout.md` | Haiku | 1-3 | Gather context: find related code, recent changes, test coverage |
| Reviewer | `code-reviewer.md` | Sonnet | 4-7 | Deep code review: quality, security, correctness |
| Data Checker | `data-checker.md` | Haiku | 1-3 | Validate configs, check for data issues, verify JSON/YAML |

## Coordination Protocol

1. **Context Gathering**: Spawn scout to find all files related to the review target
2. **Deep Review**: Spawn reviewer with scout's context for thorough analysis
3. **Data Validation**: Spawn data-checker in parallel for config/data checks
4. **Synthesis**: Main session combines findings into a prioritized report

## When to Use

- PR reviews before merge
- Security audits
- Post-implementation quality checks
- Pre-release validation
- Any task where the goal is finding issues, not writing code

## Output Format

The review team should produce:
```
## Review Summary
- **Critical**: [issues that must be fixed]
- **Warning**: [issues that should be fixed]
- **Info**: [suggestions and notes]
- **Files reviewed**: [list]
- **Coverage**: [what was and wasn't checked]
```
