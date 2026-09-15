"""Layout metrics (px). Adapted from the starter's config_layout.py and extended
with the tree, bar, card and ring metrics from the concept document §7.3."""


class Dimensions:
    # Window
    WINDOW_DEFAULT_WIDTH = 1200
    WINDOW_DEFAULT_HEIGHT = 800
    WINDOW_MIN_WIDTH = 900
    WINDOW_MIN_HEIGHT = 600

    # Sidebar (starter: 150 px, square logo area)
    SIDEBAR_WIDTH = 150
    LOGO_AREA_HEIGHT = 150
    LOGO_IMAGE_SIZE = 64
    NAV_BUTTON_HEIGHT = 32
    NAV_ICON_SIZE = 16

    # Header bar
    HEADER_HEIGHT = 44

    # Content
    CONTENT_MARGIN = 24
    CONTENT_SPACING = 18

    # Tree-table
    ROW_HEIGHT = 24
    HEADER_ROW_HEIGHT = 28
    BAR_WIDTH = 96
    BAR_HEIGHT = 12
    BAR_RADIUS = 3
    INDENT = 16

    # Cards & rings
    CARD_WIDTH = 300
    CARD_WIDTH_COMPACT = 210
    CARD_HEIGHT = 132
    CARD_RADIUS = 6
    RING_SIZE = 64
    RING_STROKE = 8
    KPI_HEIGHT = 96

    # Insight panel
    PANEL_WIDTH = 372
    PANEL_COLLAPSE_BELOW = 1100


class Spacing:
    UNIT = 4
    XS = 4
    SM = 8
    MD = 12
    LG = 18
    XL = 24


class Layout:
    dimensions = Dimensions
    spacing = Spacing
