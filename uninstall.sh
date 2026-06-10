#!/usr/bin/env bash
# uninstall.sh – remove WadwaitaUp desktop integration
#
# Usage:
#   bash uninstall.sh

set -e

INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/wadwaitaup"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
DESKTOP_FILE="com.nakanomk.WadwaitaUp.desktop"
LAUNCHER="$BIN_DIR/wadwaitaup"

echo "==> Uninstalling WadwaitaUp..."

# Remove application files
if [ -d "$INSTALL_DIR" ]; then
  rm -rf "$INSTALL_DIR"
  echo "→ Removed $INSTALL_DIR"
fi

# Remove launcher
if [ -f "$LAUNCHER" ]; then
  rm -f "$LAUNCHER"
  echo "→ Removed $LAUNCHER"
fi

# Remove desktop entry
if [ -f "$DESKTOP_DIR/$DESKTOP_FILE" ]; then
  rm -f "$DESKTOP_DIR/$DESKTOP_FILE"
  echo "→ Removed desktop entry"
fi

# Remove icon
if [ -f "$ICON_DIR/com.nakanomk.WadwaitaUp.svg" ]; then
  rm -f "$ICON_DIR/com.nakanomk.WadwaitaUp.svg"
  echo "→ Removed icon"
fi

# Update caches
if command -v gtk-update-icon-cache &>/dev/null; then
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi
if command -v update-desktop-database &>/dev/null; then
  update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo ""
echo "  ✅ WadwaitaUp uninstalled."
echo "     User data in ./data/ is preserved in the source directory."
echo "     System dependencies (GTK4, etc.) are NOT removed."
