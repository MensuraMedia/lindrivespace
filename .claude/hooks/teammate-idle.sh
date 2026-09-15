#!/bin/bash
# TeammateIdle hook — Fires when an agent team member becomes idle
#
# Use this to prompt for next actions or check if there's pending work.
# Claude Code passes event data as JSON to stdin.
#
# Exit codes:
#   0 = success (stdout added to context)

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

echo "[TEAMMATE IDLE] An agent team member is waiting for work."

# Check for pending items
if [ -f "$PROJECT_DIR/.claude/memory/pending.md" ]; then
    PENDING=$(cat "$PROJECT_DIR/.claude/memory/pending.md")
    if ! echo "$PENDING" | grep -q "No pending items"; then
        echo "Pending items exist — consider assigning to idle teammate."
    fi
fi

exit 0
