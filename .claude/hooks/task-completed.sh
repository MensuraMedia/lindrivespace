#!/bin/bash
# TaskCompleted hook — Fires when a task is marked as completed
#
# Enforces quality gates: checks for pending items and reminds
# about changelog updates.
#
# Exit codes:
#   0 = success (stdout added to context)

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

echo "[TASK COMPLETE] Verifying quality gates..."

# Remind about changelog
if [ -f "$PROJECT_DIR/changelog.md" ]; then
    echo "Reminder: Update changelog.md if this task introduced changes."
fi

# Check board for open items
if [ -f "$PROJECT_DIR/.claude/board.md" ]; then
    OPEN_ITEMS=$(grep -c "| SPAWN |" "$PROJECT_DIR/.claude/board.md" 2>/dev/null || echo "0")
    DONE_ITEMS=$(grep -c "| DONE |" "$PROJECT_DIR/.claude/board.md" 2>/dev/null || echo "0")
    if [ "$OPEN_ITEMS" -gt "$DONE_ITEMS" ]; then
        echo "Warning: $((OPEN_ITEMS - DONE_ITEMS)) agent(s) still in progress on the board."
    fi
fi

exit 0
