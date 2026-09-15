#!/bin/bash
# PreToolUse hook — Security gate
# Blocks tool calls that attempt to read, write, or expose secret files.
#
# Claude Code pipes tool input as JSON to stdin.
#
# Exit codes:
#   0 = allow (action proceeds)
#   2 = block (stderr message shown to Claude, action rejected)

set -euo pipefail

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

# ─── Bash command security ───────────────────────────────────────────────────
if [ "$TOOL_NAME" = "Bash" ]; then
    COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

    # Block reading secret files
    if echo "$COMMAND" | grep -qEi '(cat|less|head|tail|more|bat|vim|nano|code)\s+.*\.(env|pem|key|secret|credentials)'; then
        echo "SECURITY BLOCK: Attempt to read potential secret file" >&2
        exit 2
    fi

    # Block destructive recursive deletes on critical paths
    if echo "$COMMAND" | grep -qE 'rm\s+(-rf|-fr)\s+(/|~|\$HOME|\.git)'; then
        echo "SECURITY BLOCK: Destructive delete on critical path" >&2
        exit 2
    fi
fi

# ─── File edit/write security ────────────────────────────────────────────────
if [ "$TOOL_NAME" = "Edit" ] || [ "$TOOL_NAME" = "Write" ]; then
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

    # Block writing to secret files
    if echo "$FILE_PATH" | grep -qEi '\.(env|pem|key|secret|credentials)$'; then
        echo "SECURITY BLOCK: Attempt to modify secret/credential file: $FILE_PATH" >&2
        exit 2
    fi

    # Block writing to git internals
    if echo "$FILE_PATH" | grep -qE '\.git/'; then
        echo "SECURITY BLOCK: Attempt to modify git internals" >&2
        exit 2
    fi
fi

exit 0
