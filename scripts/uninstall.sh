#!/bin/bash
# Remove a LinDriveSpace install made by scripts/install.sh (same options: --system, --prefix DIR).
set -euo pipefail
APP_ID="com.mensuramedia.lindrivespace"; PREFIX="$HOME/.local"; SUDO=""; MODE="user"
while [ $# -gt 0 ]; do
    case "$1" in
        --system) PREFIX="/usr/local"; SUDO="sudo"; MODE="system" ;;
        --prefix) PREFIX="$2"; shift ;;
    esac; shift
done
[ "$MODE" = "system" ] && [ "$(id -u)" -eq 0 ] && SUDO=""
run() { if [ -n "$SUDO" ]; then sudo "$@"; else "$@"; fi; }
run rm -rf "$PREFIX/share/lindrivespace"
run rm -f "$PREFIX/bin/lindrivespace" "$PREFIX/share/applications/$APP_ID.desktop" "$PREFIX/share/metainfo/$APP_ID.metainfo.xml"
run find "$PREFIX/share/icons/hicolor" -name "$APP_ID.*" -delete 2>/dev/null || true
if [ "$MODE" = "system" ]; then
    run rm -rf /usr/libexec/lindrivespace
    run rm -f "/usr/share/polkit-1/actions/$APP_ID.policy"
fi
command -v update-desktop-database >/dev/null && run update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && run gtk-update-icon-cache -f -t "$PREFIX/share/icons/hicolor" 2>/dev/null || true
echo "LinDriveSpace removed from $PREFIX (settings in ~/.config/lindrivespace and cache in ~/.cache/lindrivespace are kept)."
