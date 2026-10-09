#!/bin/sh
set -eu

if [ "$#" -ne 3 ]; then
  echo "usage: build-installer.sh STAGE_DIR OUTPUT_DIR VERSION" >&2
  exit 2
fi

STAGE_DIR="$(CDPATH= cd -- "$1" && pwd)"
OUTPUT_DIR="$2"
VERSION="$3"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPOSITORY_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

ARCH_RAW="$(uname -m)"
case "$ARCH_RAW" in
  x86_64) DEB_ARCH=amd64 ;;
  aarch64|arm64) DEB_ARCH=arm64 ;;
  *) echo "unsupported Linux architecture: $ARCH_RAW" >&2; exit 1 ;;
esac

PACKAGE_ROOT="$BUILD_DIR/reachcut"
mkdir -p \
  "$PACKAGE_ROOT/DEBIAN" \
  "$PACKAGE_ROOT/opt/reachcut" \
  "$PACKAGE_ROOT/usr/bin" \
  "$PACKAGE_ROOT/usr/lib/systemd/user" \
  "$PACKAGE_ROOT/usr/share/applications" \
  "$PACKAGE_ROOT/usr/share/icons/hicolor/scalable/apps" \
  "$OUTPUT_DIR"

cp -R "$STAGE_DIR/." "$PACKAGE_ROOT/opt/reachcut/"
cp "$SCRIPT_DIR/reachcut" "$PACKAGE_ROOT/usr/bin/reachcut"
cp "$SCRIPT_DIR/reachcut-agent.service" "$PACKAGE_ROOT/usr/lib/systemd/user/reachcut-agent.service"
cp "$SCRIPT_DIR/reachcut.desktop" "$PACKAGE_ROOT/usr/share/applications/reachcut.desktop"
cp "$REPOSITORY_ROOT/apps/web/app/icon.svg" "$PACKAGE_ROOT/usr/share/icons/hicolor/scalable/apps/reachcut.svg"
cp "$SCRIPT_DIR/postinst" "$PACKAGE_ROOT/DEBIAN/postinst"
cp "$SCRIPT_DIR/prerm" "$PACKAGE_ROOT/DEBIAN/prerm"
chmod 755 \
  "$PACKAGE_ROOT/usr/bin/reachcut" \
  "$PACKAGE_ROOT/DEBIAN/postinst" \
  "$PACKAGE_ROOT/DEBIAN/prerm"

cat > "$PACKAGE_ROOT/DEBIAN/control" <<EOF
Package: reachcut
Version: $VERSION
Section: video
Priority: optional
Architecture: $DEB_ARCH
Maintainer: ReachCut <support@reachcut.local>
Depends: libc6, libgcc-s1, libstdc++6
Description: Local AI video clipping application
 ReachCut runs its API, web interface, media tools, and AI workflow locally.
EOF

dpkg-deb --root-owner-group --build \
  "$PACKAGE_ROOT" \
  "$OUTPUT_DIR/ReachCut-$VERSION-linux-$DEB_ARCH.deb"

PORTABLE_DIR="$BUILD_DIR/ReachCut-$VERSION-linux-$DEB_ARCH"
mkdir -p "$PORTABLE_DIR"
cp -R "$STAGE_DIR/." "$PORTABLE_DIR/"
cp "$SCRIPT_DIR/reachcut-portable" "$PORTABLE_DIR/reachcut"
chmod 755 "$PORTABLE_DIR/reachcut"
tar -C "$BUILD_DIR" -czf \
  "$OUTPUT_DIR/ReachCut-$VERSION-linux-$DEB_ARCH-portable.tar.gz" \
  "$(basename "$PORTABLE_DIR")"
