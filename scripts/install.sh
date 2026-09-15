#!/bin/bash
# LinDriveSpace installer (no packaging tools needed).
#   scripts/install.sh            install for the current user (~/.local, no root)
#   scripts/install.sh --system   install for all users under /usr/local (uses sudo)
#   scripts/install.sh --prefix DIR   custom prefix (bin/, share/ created under DIR)
# Installs the program, launcher, desktop menu entry, icons, AppStream metadata and the
# polkit policy for "Scan as administrator" (system install only), then refreshes the caches.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="com.mensuramedia.lindrivespace"
MODE="user"; PREFIX="$HOME/.local"; SUDO=""
while [ $# -gt 0 ]; do
    case "$1" in
        --system) MODE="system"; PREFIX="/usr/local"; SUDO="sudo" ;;
        --prefix) PREFIX="$2"; MODE="prefix"; shift ;;
        -h|--help) sed -n 2,7p "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done
[ "$MODE" = "system" ] && [ "$(id -u)" -eq 0 ] && SUDO=""
run() { if [ -n "$SUDO" ]; then sudo "$@"; else "$@"; fi; }

if ! python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo "PyGObject / GTK 3 not found. Install the dependencies first:" >&2
    echo "  sudo apt install python3-gi gir1.2-gtk-3.0 python3-cairo python3-psutil python3-pyudev fonts-ubuntu policykit-1" >&2
    exit 1
fi

ROOT="$PREFIX/share/lindrivespace"       # src/ + data/ live here
BIN="$PREFIX/bin"
APPS="$PREFIX/share/applications"
ICONS="$PREFIX/share/icons/hicolor"
META="$PREFIX/share/metainfo"
echo "Installing LinDriveSpace ($MODE) to $PREFIX"

run mkdir -p "$ROOT" "$BIN" "$APPS" "$META"
run rm -rf "$ROOT/src" "$ROOT/data"
run cp -r "$SRC/src" "$ROOT/src"
run cp -r "$SRC/data" "$ROOT/data"
run find "$ROOT" \( -name __pycache__ -o -name "*.egg-info" \) -type d -exec rm -rf {} + 2>/dev/null || true
run cp "$SRC/README.md" "$SRC/changelog.md" "$ROOT/" 2>/dev/null || true

# launcher with the install root baked in
tmp="$(mktemp)"; sed "s|__ROOT__|$ROOT|" "$SRC/bin/lindrivespace" > "$tmp"
run install -m 755 "$tmp" "$BIN/lindrivespace"; rm -f "$tmp"

run install -m 644 "$SRC/data/$APP_ID.desktop" "$APPS/$APP_ID.desktop"
run install -m 644 "$SRC/data/$APP_ID.metainfo.xml" "$META/$APP_ID.metainfo.xml"
for dir in "$SRC"/data/icons/hicolor/*/apps; do
    size="$(basename "$(dirname "$dir")")"
    run mkdir -p "$ICONS/$size/apps"
    run cp "$dir"/$APP_ID*.* "$ICONS/$size/apps/"
done
if [ "$MODE" = "system" ]; then
    run mkdir -p /usr/libexec/lindrivespace /usr/share/polkit-1/actions
    run install -m 755 "$SRC/data/bin/lindrivespace-scan-helper" /usr/libexec/lindrivespace/lindrivespace-scan-helper
    run install -m 644 "$SRC/data/polkit/$APP_ID.policy" "/usr/share/polkit-1/actions/$APP_ID.policy"
fi

# caches (best effort)
command -v update-desktop-database >/dev/null && run update-desktop-database "$APPS" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && run gtk-update-icon-cache -f -t "$ICONS" 2>/dev/null || true

case ":$PATH:" in *":$BIN:"*) ;; *)
    echo "note: $BIN is not on your PATH; the menu entry still works, or run $BIN/lindrivespace" ;;
esac
echo "Installed. Launch from the menu (System › LinDriveSpace) or run: lindrivespace"
echo "Remove with: scripts/uninstall.sh${SUDO:+ --system}"
