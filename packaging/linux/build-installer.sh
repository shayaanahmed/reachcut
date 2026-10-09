#!/bin/sh
set -eu

if [ "$#" -ne 4 ]; then
  echo "usage: build-installer.sh STAGE_DIR OUTPUT_DIR VERSION CHANNEL" >&2
  exit 2
fi

STAGE_DIR="$(CDPATH= cd -- "$1" && pwd)"
OUTPUT_DIR="$2"
VERSION="$3"
CHANNEL="$4"
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

case "$CHANNEL" in
  stable)
    DISPLAY_NAME="ReachCut"
    ARTIFACT_NAME="ReachCut"
    PACKAGE_NAME="reachcut"
    SLUG="reachcut"
    ;;
  personal)
    DISPLAY_NAME="ReachCut Personal"
    ARTIFACT_NAME="ReachCut-Personal"
    PACKAGE_NAME="reachcut-personal"
    SLUG="reachcut-personal"
    ;;
  *) echo "channel must be personal or stable" >&2; exit 2 ;;
esac

INSTALL_ROOT="/opt/$SLUG"
SERVICE_NAME="$SLUG-agent.service"

PACKAGE_ROOT="$BUILD_DIR/$PACKAGE_NAME"
mkdir -p \
  "$PACKAGE_ROOT/DEBIAN" \
  "$PACKAGE_ROOT$INSTALL_ROOT" \
  "$PACKAGE_ROOT/usr/bin" \
  "$PACKAGE_ROOT/usr/lib/systemd/user" \
  "$PACKAGE_ROOT/usr/share/applications" \
  "$PACKAGE_ROOT/usr/share/icons/hicolor/scalable/apps" \
  "$OUTPUT_DIR"

cp -R "$STAGE_DIR/." "$PACKAGE_ROOT$INSTALL_ROOT/"
sed "s|@REACHCUT_INSTALL_ROOT@|$INSTALL_ROOT|g" \
  "$SCRIPT_DIR/reachcut" > "$PACKAGE_ROOT/usr/bin/$SLUG"
sed \
  -e "s|@REACHCUT_INSTALL_ROOT@|$INSTALL_ROOT|g" \
  -e "s|@REACHCUT_DISPLAY_NAME@|$DISPLAY_NAME|g" \
  "$SCRIPT_DIR/reachcut-agent.service" \
  > "$PACKAGE_ROOT/usr/lib/systemd/user/$SERVICE_NAME"
sed \
  -e "s|@REACHCUT_DISPLAY_NAME@|$DISPLAY_NAME|g" \
  -e "s|@REACHCUT_SLUG@|$SLUG|g" \
  "$SCRIPT_DIR/reachcut.desktop" \
  > "$PACKAGE_ROOT/usr/share/applications/$SLUG.desktop"
cp "$REPOSITORY_ROOT/apps/web/app/icon.svg" \
  "$PACKAGE_ROOT/usr/share/icons/hicolor/scalable/apps/$SLUG.svg"
sed "s|@REACHCUT_SERVICE@|$SERVICE_NAME|g" \
  "$SCRIPT_DIR/postinst" > "$PACKAGE_ROOT/DEBIAN/postinst"
sed "s|@REACHCUT_SERVICE@|$SERVICE_NAME|g" \
  "$SCRIPT_DIR/prerm" > "$PACKAGE_ROOT/DEBIAN/prerm"
chmod 755 \
  "$PACKAGE_ROOT/usr/bin/$SLUG" \
  "$PACKAGE_ROOT/DEBIAN/postinst" \
  "$PACKAGE_ROOT/DEBIAN/prerm"

cat > "$PACKAGE_ROOT/DEBIAN/control" <<EOF
Package: $PACKAGE_NAME
Version: $VERSION
Section: video
Priority: optional
Architecture: $DEB_ARCH
Maintainer: ReachCut <support@reachcut.local>
Depends: libc6, libgcc-s1, libstdc++6
Description: $DISPLAY_NAME local AI video clipping application
 $DISPLAY_NAME runs its API, web interface, media tools, and AI workflow locally.
EOF

dpkg-deb --root-owner-group --build \
  "$PACKAGE_ROOT" \
  "$OUTPUT_DIR/$ARTIFACT_NAME-$VERSION-linux-$DEB_ARCH.deb"

PORTABLE_DIR="$BUILD_DIR/$ARTIFACT_NAME-$VERSION-linux-$DEB_ARCH"
mkdir -p "$PORTABLE_DIR"
cp -R "$STAGE_DIR/." "$PORTABLE_DIR/"
cp "$SCRIPT_DIR/reachcut-portable" "$PORTABLE_DIR/reachcut"
chmod 755 "$PORTABLE_DIR/reachcut"
tar -C "$BUILD_DIR" -czf \
  "$OUTPUT_DIR/$ARTIFACT_NAME-$VERSION-linux-$DEB_ARCH-portable.tar.gz" \
  "$(basename "$PORTABLE_DIR")"
