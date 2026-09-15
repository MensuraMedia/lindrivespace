#!/bin/bash
# PostToolUse hook for Edit|Write events
# Auto-lints and formats files after Claude edits them.
#
# Claude Code pipes tool input as JSON to stdin.
# Extract the file path from the JSON input.
#
# IMPORTANT: Adapt the lint/format commands below for your project's
# language and toolchain. Examples provided for common stacks.
#
# Exit codes:
#   0 = success (stdout added to context)
#   1 = non-blocking warning (logged in verbose mode)
#   2 = blocking error (action rejected — avoid for post-edit)

set -euo pipefail

# Read tool input from stdin
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

if [ -z "$FILE_PATH" ] || [ ! -f "$FILE_PATH" ]; then
    exit 0
fi

EXTENSION="${FILE_PATH##*.}"

# ─── JavaScript / TypeScript ─────────────────────────────────────────────────
# Uncomment if your project uses Node.js:
#
# if [[ "$EXTENSION" =~ ^(js|jsx|ts|tsx|mjs|cjs)$ ]]; then
#     npx prettier --write "$FILE_PATH" 2>/dev/null || true
#     npx eslint --fix "$FILE_PATH" 2>/dev/null || true
# fi

# ─── Python ──────────────────────────────────────────────────────────────────
# Uncomment if your project uses Python:
#
if [[ "$EXTENSION" == "py" ]]; then
    PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
    if [ -x "$PROJECT_DIR/.venv/bin/ruff" ]; then
        "$PROJECT_DIR/.venv/bin/ruff" format "$FILE_PATH" 2>/dev/null || true
        "$PROJECT_DIR/.venv/bin/ruff" check --fix "$FILE_PATH" 2>/dev/null || true
    else
        python3 -m ruff format "$FILE_PATH" 2>/dev/null || true
        python3 -m ruff check --fix "$FILE_PATH" 2>/dev/null || true
    fi
fi

# ─── Go ──────────────────────────────────────────────────────────────────────
# Uncomment if your project uses Go:
#
# if [[ "$EXTENSION" == "go" ]]; then
#     gofmt -w "$FILE_PATH" 2>/dev/null || true
# fi

# ─── Rust ────────────────────────────────────────────────────────────────────
# Uncomment if your project uses Rust:
#
# if [[ "$EXTENSION" == "rs" ]]; then
#     rustfmt "$FILE_PATH" 2>/dev/null || true
# fi

# ─── C / C++ ────────────────────────────────────────────────────────────────
# Uncomment if your project uses C/C++:
#
# if [[ "$EXTENSION" =~ ^(c|h|cpp|hpp|cc)$ ]]; then
#     clang-format -i "$FILE_PATH" 2>/dev/null || true
# fi

exit 0
