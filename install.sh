#!/usr/bin/env bash
# install.sh – install WadwaitaUp dependencies + desktop integration
# Supports: Arch Linux, Debian/Ubuntu, Fedora, macOS, Windows/MSYS2
#
# Usage:
#   bash install.sh           # install dependencies + desktop integration
#   bash install.sh --deps-only  # install dependencies only
#
# Note: webkit2gtk-4.1 is optional (enables the built-in HUST HUB browser).
# The app will gracefully show install instructions if it is missing.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/wadwaitaup"
BIN_DIR="${HOME}/.local/bin"
DESKTOP_DIR="${HOME}/.local/share/applications"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
DESKTOP_FILE="com.nakanomk.WadwaitaUp.desktop"
ONLY_DEPS=false

[[ "$1" == "--deps-only" ]] && ONLY_DEPS=true

# ── Phase 1: System dependencies ─────────────────────────────

echo "==> Installing system dependencies..."

case "$(uname -s)" in
  Darwin)
    echo "→ macOS detected – installing via Homebrew..."
    brew install pygobject3 gtk4 libadwaita webkitgtk
    [ "$ONLY_DEPS" = true ] && { echo "Done (deps only)."; exit 0; }
    ;;
  Linux)
    if command -v pacman &>/dev/null; then
      echo "→ Arch Linux (pacman) detected..."
      sudo pacman -Syu --needed python python-gobject gtk4 libadwaita webkit2gtk-4.1
    elif command -v dnf &>/dev/null; then
      echo "→ Fedora (dnf) detected..."
      sudo dnf install -y python3-gobject gtk4 libadwaita webkit2gtk4.1
    elif command -v apt &>/dev/null; then
      echo "→ Debian/Ubuntu (apt) detected..."
      sudo apt update
      sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 \
              libwebkit2gtk-4.1-0 gir1.2-webkit2-4.1
    else
      echo "Unsupported Linux distribution."
      echo "Please install GTK4, Libadwaita, PyGObject, and optionally WebKitGTK manually."
      echo ""
      echo "  Arch:      sudo pacman -S python python-gobject gtk4 libadwaita webkit2gtk-4.1"
      echo "  Fedora:    sudo dnf install python3-gobject gtk4 libadwaita webkit2gtk4.1"
      echo "  Debian:    sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 libwebkit2gtk-4.1-0"
      echo "  macOS:     brew install pygobject3 gtk4 libadwaita webkitgtk"
      echo "  Windows:   (MSYS2) pacman -S mingw-w64-x86_64-python-gobject ..."
      exit 1
    fi
    [ "$ONLY_DEPS" = true ] && { echo "Done (deps only)."; exit 0; }
    ;;
  MINGW*|MSYS*|CYGWIN*)
    echo "→ Windows/MSYS2 detected – installing via pacman (MINGW64)..."
    pacman -S --needed \
      mingw-w64-x86_64-python-gobject \
      mingw-w64-x86_64-gtk4 \
      mingw-w64-x86_64-libadwaita \
      mingw-w64-x86_64-webkit2gtk-4.1
    [ "$ONLY_DEPS" = true ] && { echo "Done (deps only)."; exit 0; }
    ;;
  *)
    echo "Unsupported platform: $(uname -s)"
    exit 1
    ;;
esac

# ── Phase 2: Desktop integration ─────────────────────────────

echo ""
echo "==> Installing desktop integration..."

# Create directories
mkdir -p "$INSTALL_DIR" "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"

# Copy application files
echo "→ Copying application to $INSTALL_DIR"
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
      --exclude='data' --exclude='tmp' "$SCRIPT_DIR/" "$INSTALL_DIR/"

# Make main.py executable
chmod +x "$INSTALL_DIR/main.py"

# Install icon
if [ -f "$SCRIPT_DIR/icon.svg" ]; then
  cp "$SCRIPT_DIR/icon.svg" "$ICON_DIR/com.nakanomk.WadwaitaUp.svg"
  echo "→ Icon installed"
fi

# Create launcher script
cat > "$BIN_DIR/wadwaitaup" << 'LAUNCHER'
#!/usr/bin/env bash
exec python "${XDG_DATA_HOME:-$HOME/.local/share}/wadwaitaup/main.py" "$@"
LAUNCHER
chmod +x "$BIN_DIR/wadwaitaup"
echo "→ Launcher created: $BIN_DIR/wadwaitaup"

# Create .desktop file
cat > "$DESKTOP_DIR/$DESKTOP_FILE" << DESKTOP
[Desktop Entry]
Type=Application
Name=WadwaitaUp
Name[zh_CN]=WadwaitaUp 课程表
Comment=A sleek, Libadwaita-themed course schedule manager
Comment[zh_CN]=一个 Adwaita 风格的课程表管理应用
Icon=com.nakanomk.WadwaitaUp
Exec=${BIN_DIR}/wadwaitaup
Terminal=false
Categories=Education;Office;GNOME;GTK;
StartupNotify=true
DESKTOP
echo "→ Desktop entry created"

# Update icon cache if available
if command -v gtk-update-icon-cache &>/dev/null; then
  gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi
if command -v update-desktop-database &>/dev/null; then
  update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✅ WadwaitaUp installed successfully!"
echo ""
echo "  Run from terminal:  wadwaitaup"
echo "  Or find 'WadwaitaUp' in your application launcher."
echo "═══════════════════════════════════════════════════════"
