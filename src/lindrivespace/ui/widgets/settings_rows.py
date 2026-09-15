"""Small layout helpers for the Settings page (WP12).

``PrefRow`` lines up a label (with an optional dim description underneath) on
the left and a single control flush right — the "form row" pattern used
throughout the Settings page. ``PrefGroup`` wraps a titled stack of rows in a
``card`` (see ``data/css/app.css``) with a ``section-title`` heading, matching
the styling ``KpiTile``/``MountCard`` already use elsewhere in the app.

Both widgets only lay other widgets out; they never own colours directly —
everything comes from CSS classes already defined for the app theme.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402

_SPACING = Layout.spacing


class PrefRow(Gtk.Box):
    """One settings row: label (+ optional description) left, control right."""

    __gtype_name__ = "LdsPrefRow"

    def __init__(
        self,
        label: str,
        control: Gtk.Widget,
        description: str | None = None,
        *,
        accessible_name: str | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=_SPACING.MD)
        self.get_style_context().add_class("pref-row")
        self.set_hexpand(True)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_valign(Gtk.Align.CENTER)

        self.label_widget = Gtk.Label(label=label)
        self.label_widget.set_xalign(0.0)
        self.label_widget.set_line_wrap(True)
        text_box.pack_start(self.label_widget, False, False, 0)

        self.description_widget: Gtk.Label | None = None
        if description:
            desc = Gtk.Label(label=description)
            desc.set_xalign(0.0)
            desc.set_line_wrap(True)
            desc.get_style_context().add_class("dim")
            text_box.pack_start(desc, False, False, 0)
            self.description_widget = desc

        self.pack_start(text_box, True, True, 0)

        control.set_valign(Gtk.Align.CENTER)
        control.set_halign(Gtk.Align.END)
        self.pack_start(control, False, False, 0)

        self.control = control
        control.get_accessible().set_name(accessible_name or label)
        # Associates the label with the control for screen readers and lets a
        # mnemonic on the label move focus to it (harmless when there is none).
        self.label_widget.set_mnemonic_widget(control)


class PrefGroup(Gtk.Box):
    """A titled card holding a vertical stack of ``PrefRow`` (or any widget)."""

    __gtype_name__ = "LdsPrefGroup"

    def __init__(self, title: str) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=_SPACING.MD)
        self.get_style_context().add_class("card")

        title_label = Gtk.Label(label=title)
        title_label.set_xalign(0.0)
        title_label.get_style_context().add_class("section-title")
        self.pack_start(title_label, False, False, 0)
        self.title_widget = title_label

        self._rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=_SPACING.MD)
        self.pack_start(self._rows, False, False, 0)

    def add_row(self, row: Gtk.Widget) -> None:
        self._rows.pack_start(row, False, False, 0)

    def add_separator(self) -> None:
        self._rows.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0
        )
