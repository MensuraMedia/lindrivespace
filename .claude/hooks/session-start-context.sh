#!/bin/bash
# SessionStart hook — Injects project context at the start of each session.
# Stdout is added to Claude's context automatically.
#
# Exit codes:
#   0 = success (stdout added to context)

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"

echo "=== Session Context ==="

# Show pending items if they exist
if [ -f "$PROJECT_DIR/.claude/memory/pending.md" ]; then
    PENDING=$(cat "$PROJECT_DIR/.claude/memory/pending.md")
    if ! echo "$PENDING" | grep -q "No pending items"; then
        echo ""
        echo "--- Pending Items ---"
        echo "$PENDING"
    fi
fi

# Show most recent session log filename (if any)
if [ -d "$PROJECT_DIR/.claude/memory/sessions" ]; then
    LATEST=$(ls -t "$PROJECT_DIR/.claude/memory/sessions/"*.md 2>/dev/null | head -1)
    if [ -n "$LATEST" ]; then
        echo ""
        echo "--- Last Session: $(basename "$LATEST") ---"
        head -20 "$LATEST"
    fi
fi

# Show last 5 changelog entries
if [ -f "$PROJECT_DIR/changelog.md" ]; then
    echo ""
    echo "--- Recent Changes ---"
    tail -6 "$PROJECT_DIR/changelog.md" | head -5
fi

echo ""
echo "Remember: Use /memory for Auto Memory. Update changelog.md as you work."
echo "=== End Session Context ==="

exit 0
