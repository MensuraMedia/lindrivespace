# Change: Hardware tables like the Overview list; menu check items in the accent

**Date:** 2026-09-15
**Type:** UI polish (user request)

- `ui/pages/hardware.py`: `_styled_table()` builds the Disks and I/O tables with the Overview
  list's classes (`mount-list`, `grid-table`, frame `mount-list-frame`, ShadowType.IN),
  6 px cell padding, mono family for device/number columns, sortable + resizable columns,
  Model / Device expand. Disks and I/O groups are packed first. Column widths widened
  (Device 132, Model 220, Link 136, Scheduler 110, Read/Write 110, IOPS 140, Util 90).
- `data/css/app.css`: `menu menuitem check|radio` rules — off = sunken grey with soft border,
  on = accent fill + white `object-select-symbolic` tick (radio: white dot), hover = hot accent.
  Root cause of the "blue check on orange": Mint-Y sets `-gtk-icon-source` to a blue bitmap on
  `menu menuitem check:checked`; our earlier override only covered `checkbutton check`.

Files: src/lindrivespace/ui/pages/hardware.py, data/css/app.css, changelog.md
