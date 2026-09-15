# Change: launcher, installer, .deb, menu entry and icon; real README screenshots

**Date:** 2026-09-15 · **Type:** packaging (user request)

- `bin/lindrivespace`: POSIX sh launcher; resolves the checkout from its own location (symlink
  safe) or uses the absolute root the installer substitutes for `__ROOT__` (path-shape test, so a
  global sed cannot break the comparison — the first version did exactly that).
- `scripts/install.sh` / `scripts/uninstall.sh`: `~/.local` (default) or `--system` (`/usr/local`,
  sudo, + polkit helper under /usr/libexec) or `--prefix DIR`; copies `src/` + `data/`, launcher,
  desktop entry, metainfo, hicolor icons; refreshes desktop database and icon cache.
- `scripts/build-deb.sh`: `dist/lindrivespace_<version>_all.deb` via `dpkg-deb --root-owner-group`;
  layout /usr/lib/lindrivespace/src, /usr/share/lindrivespace (css…), /usr/share/{applications,
  metainfo,icons/hicolor,polkit-1/actions}, /usr/libexec/lindrivespace; Depends on python3-gi,
  gir1.2-gtk-3.0, python3-cairo, python3-psutil, python3-pyudev; postinst/postrm refresh caches.
- `data/com.mensuramedia.lindrivespace.desktop` (validated) and `.metainfo.xml` (appstreamcli OK).
- Icon redrawn (`data/icons/hicolor/scalable/apps/*.svg`) + PNGs 16/22/24/32/48/64/128/256/512.
- `app.py::data_path()` checks `$LINDRIVESPACE_DATA_DIR` first (launcher sets it).
- `docs/screenshots/*.png` captured from the running app; README Screens/Install rewritten.
- Verified: checkout launcher, user-installed launcher (`~/.local/bin/lindrivespace --smoke`), and
  the launcher from the extracted .deb tree all exit 0; menu icon resolves through hicolor.
