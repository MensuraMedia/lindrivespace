#!/bin/bash
# run.sh — launch LinDriveSpace from a checkout using the system Python and
# system PyGObject (no virtualenv required). Any arguments are passed through:
#   ./run.sh                      open the Overview
#   ./run.sh /mnt/data            open and scan a folder
#   ./run.sh --smoke              build the window and exit (CI check)
#   ./run.sh --screenshot out.png render the window to a PNG and exit

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

if ! python3 -c "import gi; gi.require_version('Gtk', '3.0'); from gi.repository import Gtk" 2>/dev/null; then
    echo "PyGObject / GTK 3 not found. Install with:" >&2
    echo "  sudo apt install python3-gi gir1.2-gtk-3.0 python3-cairo python3-psutil python3-pyudev fonts-ubuntu" >&2
    exit 1
fi

export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m lindrivespace "$@"
