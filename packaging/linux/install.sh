#!/bin/sh
# Install this folder for the current user (no root needed):
#   program  -> ~/.local/share/<id>/        command -> ~/.local/bin/<id>
#   menu     -> ~/.local/share/applications/<id>.desktop
# The in-app updater replaces ~/.local/share/<id>/ when a new release is out.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
ID="@ID@"
EXE="@EXE@"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
DEST="$DATA/$ID"
mkdir -p "$DATA"
if [ "$HERE" != "$DEST" ]; then
  rm -rf "$DEST.new"; cp -R "$HERE" "$DEST.new"; rm -rf "$DEST"; mv "$DEST.new" "$DEST"
fi
mkdir -p "$HOME/.local/bin" "$DATA/applications" "$DATA/icons/hicolor/256x256/apps"
ln -sf "$DEST/$EXE" "$HOME/.local/bin/$ID"
cp "$DEST/$ID.png" "$DATA/icons/hicolor/256x256/apps/$ID.png"
sed "s|@EXEC@|$DEST/$EXE|" "$DEST/$ID.desktop" > "$DATA/applications/$ID.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA/applications" || true
echo "Installed to $DEST"
echo "Start it from the applications menu or with: $ID   (make sure ~/.local/bin is on PATH)"
