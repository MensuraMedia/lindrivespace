"""LinDriveSpace core engine.

Pure Python: nothing in this package imports GTK, GLib, Gio or cairo.
See .claude/rules/core-purity.md. The UI talks to the core only through the
event dataclasses in :mod:`lindrivespace.core.events`.
"""
