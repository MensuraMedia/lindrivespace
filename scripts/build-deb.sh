#!/bin/bash
# Build a Debian package: dist/lindrivespace_<version>_all.deb (needs only dpkg-deb).
#   scripts/build-deb.sh        then: sudo apt install ./dist/lindrivespace_*.deb
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_ID="com.mensuramedia.lindrivespace"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/src/lindrivespace/__init__.py")"
BUILD="$SRC/build/deb"; OUT="$SRC/dist"
rm -rf "$BUILD"; mkdir -p "$BUILD/DEBIAN" "$OUT"
ROOT="$BUILD/usr/lib/lindrivespace"          # src/ (Python package)
SHARE="$BUILD/usr/share/lindrivespace"       # data/ (css, icons, polkit, bin) — found by data_path()
mkdir -p "$ROOT" "$SHARE" "$BUILD/usr/bin" "$BUILD/usr/share/applications" "$BUILD/usr/share/metainfo" \
         "$BUILD/usr/share/icons/hicolor" "$BUILD/usr/libexec/lindrivespace" "$BUILD/usr/share/polkit-1/actions" \
         "$BUILD/usr/share/doc/lindrivespace"
cp -r "$SRC/src" "$ROOT/src"
find "$ROOT" \( -name __pycache__ -o -name "*.egg-info" \) -type d -exec rm -rf {} + 2>/dev/null || true
cp -r "$SRC/data/." "$SHARE/"
rm -rf "$SHARE/icons" "$SHARE/bin" "$SHARE/polkit" "$SHARE/$APP_ID.desktop" "$SHARE/$APP_ID.metainfo.xml"
for dir in "$SRC"/data/icons/hicolor/*/apps; do
    size="$(basename "$(dirname "$dir")")"; mkdir -p "$BUILD/usr/share/icons/hicolor/$size/apps"
    cp "$dir"/$APP_ID*.* "$BUILD/usr/share/icons/hicolor/$size/apps/"
done
install -m 644 "$SRC/data/$APP_ID.desktop" "$BUILD/usr/share/applications/"
install -m 644 "$SRC/data/$APP_ID.metainfo.xml" "$BUILD/usr/share/metainfo/"
install -m 755 "$SRC/data/bin/lindrivespace-scan-helper" "$BUILD/usr/libexec/lindrivespace/"
install -m 644 "$SRC/data/polkit/$APP_ID.policy" "$BUILD/usr/share/polkit-1/actions/"
install -m 644 "$SRC/README.md" "$BUILD/usr/share/doc/lindrivespace/README.md"
install -m 644 "$SRC/LICENSE.md" "$BUILD/usr/share/doc/lindrivespace/copyright"
gzip -9n -c "$SRC/changelog.md" > "$BUILD/usr/share/doc/lindrivespace/changelog.gz"
sed "s|__ROOT__|/usr/lib/lindrivespace|" "$SRC/bin/lindrivespace" > "$BUILD/usr/bin/lindrivespace"
# the package keeps data under /usr/share/lindrivespace: point the launcher there
sed -i 's|LINDRIVESPACE_DATA_DIR="${LINDRIVESPACE_DATA_DIR:-$LINDRIVESPACE_ROOT/data}"|LINDRIVESPACE_DATA_DIR="${LINDRIVESPACE_DATA_DIR:-/usr/share/lindrivespace}"|' "$BUILD/usr/bin/lindrivespace"
chmod 755 "$BUILD/usr/bin/lindrivespace"
SIZE="$(du -sk "$BUILD/usr" | cut -f1)"
cat > "$BUILD/DEBIAN/control" <<CTL
Package: lindrivespace
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Maintainer: MensuraMedia <artisanstock@gmail.com>
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, python3-cairo, python3-psutil, python3-pyudev
Recommends: fonts-ubuntu, policykit-1, hicolor-icon-theme
Homepage: https://github.com/MensuraMedia/lindrivespace
Description: Disk space explorer for Linux desktops (GTK 3)
 LinDriveSpace lists every mount and partition, scans them in the
 background and lets you drill from folders down to files with sizes,
 share bars and dates. It adds a treemap and largest-files analysis,
 automatic usage history with change drill-down, a scheduled background
 collector and a hardware page - TreeSize/WizTree for Linux Mint.
CTL
cat > "$BUILD/DEBIAN/postinst" <<'PI'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
exit 0
PI
cp "$BUILD/DEBIAN/postinst" "$BUILD/DEBIAN/postrm"; chmod 755 "$BUILD/DEBIAN/postinst" "$BUILD/DEBIAN/postrm"
find "$BUILD/usr" -type d -exec chmod 755 {} + ; find "$BUILD/usr" -type f ! -perm -u+x -exec chmod 644 {} +
DEB="$OUT/lindrivespace_${VERSION}_all.deb"
dpkg-deb --root-owner-group --build "$BUILD" "$DEB" >/dev/null
echo "built: $DEB ($(du -h "$DEB" | cut -f1))"
echo "install with: sudo apt install $DEB"
