#!/bin/bash
# SubagentStart / SubagentStop hook — Agent lifecycle logging
#
# Logs agent spawn and completion events to board.md for audit and cost tracking.
# Claude Code passes event data as JSON to stdin.
#
# Hook events:
#   SubagentStart — fired when a sub-agent is spawned
#   SubagentStop  — fired when a sub-agent completes
#
# Exit codes:
#   0 = success (stdout added to context)

set -euo pipefail

INPUT=$(cat)
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
BOARD="$PROJECT_DIR/.claude/board.md"
TIMESTAMP=$(date +%Y-%m-%dT%H:%M:%S)

# Extract agent info from JSON input
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // .subagent_type // "unknown"' 2>/dev/null)
EVENT_TYPE=$(echo "$INPUT" | jq -r '.hook_event_name // "unknown"' 2>/dev/null)

if [ "$EVENT_TYPE" = "SubagentStart" ]; then
    echo "[AGENT] $AGENT_TYPE spawned at $TIMESTAMP"
    # Log to board if it exists
    if [ -f "$BOARD" ]; then
        echo "| $TIMESTAMP | SPAWN | $AGENT_TYPE | Started |" >> "$BOARD"
    fi
elif [ "$EVENT_TYPE" = "SubagentStop" ]; then
    echo "[AGENT] $AGENT_TYPE completed at $TIMESTAMP"
    if [ -f "$BOARD" ]; then
        echo "| $TIMESTAMP | DONE | $AGENT_TYPE | Completed |" >> "$BOARD"
    fi
fi

exit 0
