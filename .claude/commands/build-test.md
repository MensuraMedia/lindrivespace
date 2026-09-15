---
description: "Run the project's full build, lint, and test pipeline from CLAUDE.md"
---

# /build-test — Run Build and Test Suite

Run the project's full build and test pipeline as defined in CLAUDE.md.

## Workflow

1. **Read CLAUDE.md** to find the project's build, test, and lint commands.

2. **Run in order:**
   - Build command (e.g., `make`, `pnpm build`, `cargo build`, `cmake --build .`)
   - Lint command if defined (e.g., `pnpm lint`, `pylint`, `golangci-lint run`)
   - Test command (e.g., `pnpm test`, `pytest`, `cargo test`, `ctest`)

3. **Report results:**
   - If all pass: confirm success with a one-line summary
   - If any fail: show the failure output and suggest fixes
   - Do NOT auto-fix failures — present them for user review

## Notes
- Always use the commands from CLAUDE.md, not hardcoded defaults
- If CLAUDE.md doesn't define a command, skip that step and note it
- Run from the project root directory
