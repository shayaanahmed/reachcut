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
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

case "$CHANNEL" in
  stable)
    APP_NAME="ReachCut"
    ARTIFACT_NAME="ReachCut"
    BUNDLE_ID="com.reachcut.desktop"
    AGENT_ID="com.reachcut.agent"
    ;;
  personal)
    APP_NAME="ReachCut Personal"
    ARTIFACT_NAME="ReachCut-Personal"
    BUNDLE_ID="com.reachcut.personal"
    AGENT_ID="com.reachcut.personal.agent"
    ;;
  *) echo "channel must be personal or stable" >&2; exit 2 ;;
esac

ARCH="$(uname -m)"
APP_BUNDLE="$APP_NAME.app"
APP_DIR="$BUILD_DIR/root/Applications/$APP_BUNDLE"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources/app"
# Build-host quarantine and Finder metadata must not leak into the application payload.
cp -R -X "$STAGE_DIR/." "$APP_DIR/Contents/Resources/app/"
cp "$SCRIPT_DIR/ReachCut" "$APP_DIR/Contents/MacOS/ReachCut"
chmod 755 "$APP_DIR/Contents/MacOS/ReachCut"
sed \
  -e "s/__REACHCUT_VERSION__/$VERSION/g" \
  -e "s/__REACHCUT_NAME__/$APP_NAME/g" \
  -e "s/__REACHCUT_BUNDLE_ID__/$BUNDLE_ID/g" \
  "$SCRIPT_DIR/Info.plist" > "$APP_DIR/Contents/Info.plist"

mkdir -p "$BUILD_DIR/root/Library/LaunchAgents" "$OUTPUT_DIR"
sed \
  -e "s/__REACHCUT_AGENT_ID__/$AGENT_ID/g" \
  -e "s/__REACHCUT_APP_BUNDLE__/$APP_BUNDLE/g" \
  "$SCRIPT_DIR/com.reachcut.agent.plist" \
  > "$BUILD_DIR/root/Library/LaunchAgents/$AGENT_ID.plist"

pkgbuild \
  --root "$BUILD_DIR/root" \
  --identifier "$BUNDLE_ID" \
  --version "$VERSION" \
  --install-location / \
  "$OUTPUT_DIR/$ARTIFACT_NAME-$VERSION-macos-$ARCH.pkg"

mkdir -p "$BUILD_DIR/dmg"
cp -R -X "$APP_DIR" "$BUILD_DIR/dmg/$APP_BUNDLE"
ln -s /Applications "$BUILD_DIR/dmg/Applications"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$BUILD_DIR/dmg" \
  -ov \
  -format UDZO \
  "$OUTPUT_DIR/$ARTIFACT_NAME-$VERSION-macos-$ARCH.dmg"
