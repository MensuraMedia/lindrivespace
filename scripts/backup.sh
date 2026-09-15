#!/bin/bash
# Local backup of the project (source, docs, git history) to ~/backups.
# Usage: scripts/backup.sh [destination-dir]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$HOME/backups}"
mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$DEST/lindrivespace-$STAMP.tar.gz"
tar --exclude='.venv' --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.mypy_cache' \
    --exclude='.ruff_cache' --exclude='*.pyc' -C "$(dirname "$ROOT")" -czf "$OUT" "$(basename "$ROOT")"
sha256sum "$OUT" > "$OUT.sha256"
echo "backup written: $OUT ($(du -h "$OUT" | cut -f1))"
