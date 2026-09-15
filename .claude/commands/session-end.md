---
description: "End-of-session wrap-up: write logs, update memory, verify git status"
---

# /session-end — End-of-Session Wrap-Up

Run this before ending a work session to ensure nothing is lost.

## Workflow

1. **Write session log** to `.claude/memory/sessions/YYYY-MM-DD_HHmm_summary.md`:
   - What was done (bullet list)
   - Key decisions made and rationale
   - Issues encountered and resolutions
   - Files changed
   - What's next / unfinished work

2. **Write change manifests** for any significant changes made this session
   (to `.claude/memory/changes/`)

3. **Update tracking files:**
   - `decisions.md` — if any architectural decisions were made
   - `pending.md` — add any unfinished work or open questions
   - `MEMORY.md` — add pointers to new session logs or change manifests
   - `changelog.md` — verify all changes from this session are logged

4. **Verify git status:**
   - Show uncommitted changes
   - Remind user to commit if there are staged/unstaged changes

5. **Report session summary** to the user with next steps.
