"""InsightPanel — Direction D's collapsible side panel (WP9).

A tabbed dock (Treemap / Top files / Types / Age) that ``ExplorerPage`` attaches
through its existing ``add_side_panel``/``remove_side_panel`` API (see
``.claude/memory/changes/2026-09-14-wp8-explorer.md``). This widget owns no
scan state: :meth:`set_node` is the only way data flows in, driven by the
page's ``node-selected`` signal.

Each tab view computes lazily: :meth:`set_node` marks every view dirty but
only the currently visible tab is refreshed immediately; the others refresh
the first time the user switches to them (``Gtk.Stack``'s
``notify::visible-child-name``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GLib", "2.0")
from gi.repository import GLib, GObject, Gtk  # noqa: E402

from lindrivespace.config.layout import Layout  # noqa: E402
from lindrivespace.config.settings import Settings  # noqa: E402
from lindrivespace.config.theme import ThemeDefinition  # noqa: E402
from lindrivespace.ui.widgets.age_view import AgeView  # noqa: E402
from lindrivespace.ui.widgets.file_types_view import FileTypesView  # noqa: E402
from lindrivespace.ui.widgets.top_files_view import TopFilesView  # noqa: E402
from lindrivespace.ui.widgets.treemap_view import TreemapView  # noqa: E402

if TYPE_CHECKING:
    from lindrivespace.core.fsnode import FsNode
    from lindrivespace.models.tree_model import ScanTreeModel

_DIMS = Layout.dimensions
_TABS = ("treemap", "top_files", "types", "age")
_FOOTNOTE = "estimated from the largest files of each folder"


def _icon_name(preferred: str, fallback: str) -> str:
    theme = Gtk.IconTheme.get_default()
    if theme is not None and theme.has_icon(preferred):
        return preferred
    return fallback


def _footnote_label() -> Gtk.Label:
    label = Gtk.Label(label=_FOOTNOTE)
    label.set_xalign(0.0)
    label.set_line_wrap(True)
    label.get_style_context().add_class("dim")
    return label


class InsightPanel(Gtk.Box):
    """Tabbed treemap/top-files/types/age dock for the Explorer."""

    __gtype_name__ = "LdsInsightPanel"
    __gsignals__ = {
        "node-activated": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        "collapse-requested": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, theme: ThemeDefinition, settings: Settings) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._theme = theme
        self._settings = settings
        self._node: FsNode | None = None
        self._model: ScanTreeModel | None = None

        self.get_style_context().add_class("insight-panel")
        self.set_size_request(_DIMS.PANEL_WIDTH, -1)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.set_border_width(4)
        self.switcher = Gtk.StackSwitcher()
        self.switcher.set_stack(self.stack)
        self.switcher.set_hexpand(True)
        header.pack_start(self.switcher, True, True, 0)

        self.collapse_button = Gtk.Button()
        self.collapse_button.set_relief(Gtk.ReliefStyle.NONE)
        self.collapse_button.get_style_context().add_class("flat")
        collapse_icon = _icon_name("pan-end-symbolic", "go-last-symbolic")
        self.collapse_button.set_image(
            Gtk.Image.new_from_icon_name(collapse_icon, Gtk.IconSize.MENU)
        )
        self.collapse_button.set_tooltip_text("Collapse panel (F9)")
        self.collapse_button.connect("clicked", lambda _b: self.emit("collapse-requested"))
        header.pack_end(self.collapse_button, False, False, 0)
        self.pack_start(header, False, False, 0)

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        title_box.set_border_width(8)
        self.title_label = Gtk.Label(label="")
        self.title_label.set_xalign(0.0)
        self.title_label.set_use_markup(True)
        title_box.pack_start(self.title_label, False, False, 0)
        self.subtitle_label = Gtk.Label(label="")
        self.subtitle_label.set_xalign(0.0)
        self.subtitle_label.get_style_context().add_class("mono")
        self.subtitle_label.get_style_context().add_class("dim")
        title_box.pack_start(self.subtitle_label, False, False, 0)
        self.pack_start(title_box, False, False, 0)

        self.pack_start(self.stack, True, True, 0)

        # ---- Treemap tab ----------------------------------------------------
        self.treemap = TreemapView(theme)
        self.treemap.connect("item-activated", self._on_treemap_item_activated)
        treemap_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        treemap_box.set_border_width(4)
        up_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self._up_button = Gtk.Button(label="Up")
        self._up_button.set_relief(Gtk.ReliefStyle.NONE)
        self._up_button.set_tooltip_text("Zoom out one level")
        self._up_button.set_sensitive(False)
        self._up_button.connect("clicked", self._on_up_clicked)
        up_row.pack_start(self._up_button, False, False, 0)
        treemap_box.pack_start(up_row, False, False, 0)
        treemap_box.pack_start(self.treemap, True, True, 0)
        self.stack.add_titled(treemap_box, "treemap", "Treemap")

        # ---- Top files tab ----------------------------------------------------
        self.top_files = TopFilesView(theme)
        top_scroller = Gtk.ScrolledWindow()
        top_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        top_scroller.add(self.top_files)
        self.stack.add_titled(top_scroller, "top_files", "Top files")

        # ---- Types tab ----------------------------------------------------
        self.file_types = FileTypesView(theme)
        types_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        types_box.set_border_width(4)
        types_scroller = Gtk.ScrolledWindow()
        types_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        types_scroller.add(self.file_types)
        types_box.pack_start(types_scroller, True, True, 0)
        types_box.pack_start(_footnote_label(), False, False, 0)
        self.stack.add_titled(types_box, "types", "Types")

        # ---- Age tab ----------------------------------------------------
        self.age = AgeView(theme)
        age_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        age_box.set_border_width(4)
        age_box.pack_start(self.age, True, True, 0)
        age_box.pack_start(_footnote_label(), False, False, 0)
        self.stack.add_titled(age_box, "age", "Age")

        self._views: dict[str, object] = {
            "treemap": self.treemap,
            "top_files": self.top_files,
            "types": self.file_types,
            "age": self.age,
        }

        saved_tab = settings.get("explorer.panel_tab", "treemap")
        if saved_tab in _TABS:
            self.stack.set_visible_child_name(saved_tab)
        self.stack.connect("notify::visible-child-name", self._on_tab_switched)

    # ---- data -----------------------------------------------------------

    def set_node(self, node: FsNode | None, model: ScanTreeModel) -> None:
        self._node = node
        self._model = model
        self._update_title()
        for view in self._views.values():
            view.set_node(node, model)  # type: ignore[attr-defined]
        self._up_button.set_sensitive(False)
        self._refresh_visible()

    def _update_title(self) -> None:
        node = self._node
        model = self._model
        if node is None or model is None:
            self.title_label.set_markup("")
            self.subtitle_label.set_text("")
            return
        self.title_label.set_markup(f"<b>{GLib.markup_escape_text(node.name)}</b>")
        self.subtitle_label.set_text(
            f"{node.dirs:,} folders · {model.fmt_bytes(model.primary(node))}"
        )

    def _refresh_visible(self) -> None:
        view = self._views.get(self.current_tab)
        if view is not None:
            view.ensure_fresh()  # type: ignore[attr-defined]

    # ---- tabs -------------------------------------------------------------

    @property
    def current_tab(self) -> str:
        return self.stack.get_visible_child_name() or "treemap"

    @current_tab.setter
    def current_tab(self, name: str) -> None:
        if name in _TABS:
            self.stack.set_visible_child_name(name)

    def _on_tab_switched(self, *_args: object) -> None:
        name = self.current_tab
        self._settings.set("explorer.panel_tab", name)
        self._refresh_visible()

    # ---- treemap wiring -----------------------------------------------------

    def _on_treemap_item_activated(self, _treemap: TreemapView, node: FsNode) -> None:
        self._up_button.set_sensitive(self.treemap.is_zoomed)
        self.emit("node-activated", node)

    def _on_up_clicked(self, _button: Gtk.Button) -> None:
        self.treemap.zoom_out()
        self._up_button.set_sensitive(self.treemap.is_zoomed)

    # ---- theme --------------------------------------------------------------

    def set_theme(self, theme: ThemeDefinition) -> None:
        self._theme = theme
        for view in self._views.values():
            view.set_theme(theme)  # type: ignore[attr-defined]
