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
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

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

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_label = Gtk.Label(label=title)
        title_label.set_xalign(0.0)
        title_label.get_style_context().add_class("section-title")
        title_label.get_style_context().add_class("large")  # card titles read as headings
        header.pack_start(title_label, True, True, 0)
        self.copy_button: Gtk.Button | None = None
        self._header = header
        self.pack_start(header, False, False, 0)
        self.title_widget = title_label
        self.title = title

        self._rows = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=_SPACING.MD)
        self.pack_start(self._rows, False, False, 0)

    def add_row(self, row: Gtk.Widget) -> None:
        self._rows.pack_start(row, False, False, 0)

    # ---- copy ------------------------------------------------------------------

    def enable_copy(self) -> Gtk.Button:
        """Add a flat "Copy" button to the card header that copies :meth:`as_text`."""
        if self.copy_button is None:
            button = Gtk.Button()
            button.set_image(Gtk.Image.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.MENU))
            button.set_relief(Gtk.ReliefStyle.NONE)
            button.get_style_context().add_class("flat")
            button.get_style_context().add_class("copy-icon")
            button.set_tooltip_text(f"Copy the {self.title} card as text")
            button.get_accessible().set_name(f"Copy {self.title}")
            button.connect("clicked", self._on_copy_clicked)
            self._header.pack_end(button, False, False, 0)
            button.show()
            self.copy_button = button
        return self.copy_button

    def _on_copy_clicked(self, _button: Gtk.Button) -> None:
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(self.as_text(), -1)
        clipboard.store()

    def as_text(self) -> str:
        """Plain-text rendering of the card: title, then one line per row / table row."""
        lines = [self.title, "-" * len(self.title)]
        for child in self._rows.get_children():
            lines.extend(_widget_text(child))
        return "\n".join(line for line in lines if line is not None)

    def add_separator(self) -> None:
        self._rows.pack_start(
            Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0
        )


def _widget_text(widget: Gtk.Widget) -> list[str]:
    """Text lines for a row widget: PrefRow -> "label: value", TreeView -> tab rows, else labels."""
    if isinstance(widget, PrefRow):
        value = " ".join(_leaf_texts(widget.control)).strip()
        return [f"{widget.label_widget.get_text()}: {value}"]
    if isinstance(widget, Gtk.TreeView):
        return _treeview_text(widget)
    if isinstance(widget, Gtk.ScrolledWindow):
        inner = widget.get_child()
        if isinstance(inner, Gtk.Viewport):
            inner = inner.get_child()
        return _widget_text(inner) if inner is not None else []
    if isinstance(widget, Gtk.Label):
        return [widget.get_text()]
    if isinstance(widget, Gtk.Container):
        out: list[str] = []
        for child in widget.get_children():
            out.extend(_widget_text(child))
        return out
    return []


def _leaf_texts(widget: Gtk.Widget) -> list[str]:
    if isinstance(widget, Gtk.Label):
        return [widget.get_text()]
    if isinstance(widget, Gtk.Entry):
        return [widget.get_text()]
    if isinstance(widget, Gtk.Switch):
        return ["on" if widget.get_active() else "off"]
    if isinstance(widget, Gtk.SpinButton):
        return [widget.get_text()]
    if isinstance(widget, Gtk.ComboBoxText):
        return [widget.get_active_text() or ""]
    if isinstance(widget, Gtk.ToggleButton):
        return [f"{widget.get_label() or ''}{' (on)' if widget.get_active() else ''}".strip()]
    if isinstance(widget, Gtk.Button):
        return [widget.get_label() or ""]
    if isinstance(widget, Gtk.Container):
        out: list[str] = []
        for child in widget.get_children():
            out.extend(_leaf_texts(child))
        return out
    return []


def _treeview_text(tree: Gtk.TreeView) -> list[str]:
    model = tree.get_model()
    if model is None:
        return []
    columns = [c for c in tree.get_columns() if c.get_visible()]
    lines = ["\t".join(c.get_title() for c in columns)]
    it = model.get_iter_first()
    n_cols = model.get_n_columns()
    while it is not None:
        cells: list[str] = []
        for col in range(n_cols):
            value = model.get_value(it, col)
            if isinstance(value, str | int | float) and not isinstance(value, bool):
                cells.append(str(value))
        lines.append("\t".join(cells))
        it = model.iter_next(it)
    return lines
