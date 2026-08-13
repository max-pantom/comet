#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="Comet.app"
SOURCE_APP="$ROOT_DIR/build/bin/$APP_NAME"
INSTALL_DIR="/Applications"

(
  cd "$ROOT_DIR"
  "$(go env GOPATH)/bin/wails" build -clean
)

if [[ -d "$INSTALL_DIR/TikTok Scout.app" ]]; then
  rm -rf "$INSTALL_DIR/TikTok Scout.app"
fi
if [[ -d "$INSTALL_DIR/$APP_NAME" ]]; then
  rm -rf "$INSTALL_DIR/$APP_NAME"
fi

ditto "$SOURCE_APP" "$INSTALL_DIR/$APP_NAME"
echo "Installed $INSTALL_DIR/$APP_NAME"
