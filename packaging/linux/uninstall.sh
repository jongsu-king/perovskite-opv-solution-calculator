#!/bin/sh
# Remove what install.sh added. Your settings in ~/.config/<program name>/ are kept.
set -e
ID="@ID@"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -f "$HOME/.local/bin/$ID" "$DATA/applications/$ID.desktop" "$DATA/icons/hicolor/256x256/apps/$ID.png"
rm -rf "$DATA/$ID"
echo "Removed $ID"
