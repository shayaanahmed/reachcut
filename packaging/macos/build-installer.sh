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
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

ARCH="$(uname -m)"
APP_DIR="$BUILD_DIR/root/Applications/ReachCut.app"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources/app"
# Build-host quarantine and Finder metadata must not leak into the application payload.
cp -R -X "$STAGE_DIR/." "$APP_DIR/Contents/Resources/app/"
cp "$SCRIPT_DIR/ReachCut" "$APP_DIR/Contents/MacOS/ReachCut"
chmod 755 "$APP_DIR/Contents/MacOS/ReachCut"
sed "s/__REACHCUT_VERSION__/$VERSION/g" "$SCRIPT_DIR/Info.plist" > "$APP_DIR/Contents/Info.plist"

mkdir -p "$BUILD_DIR/root/Library/LaunchAgents" "$OUTPUT_DIR"
cp "$SCRIPT_DIR/com.reachcut.agent.plist" "$BUILD_DIR/root/Library/LaunchAgents/com.reachcut.agent.plist"

pkgbuild \
  --root "$BUILD_DIR/root" \
  --identifier com.reachcut.desktop \
  --version "$VERSION" \
  --install-location / \
  "$OUTPUT_DIR/ReachCut-$VERSION-macos-$ARCH.pkg"

mkdir -p "$BUILD_DIR/dmg"
cp -R -X "$APP_DIR" "$BUILD_DIR/dmg/ReachCut.app"
ln -s /Applications "$BUILD_DIR/dmg/Applications"
hdiutil create \
  -volname ReachCut \
  -srcfolder "$BUILD_DIR/dmg" \
  -ov \
  -format UDZO \
  "$OUTPUT_DIR/ReachCut-$VERSION-macos-$ARCH.dmg"
