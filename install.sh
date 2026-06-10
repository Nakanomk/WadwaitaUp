#!/usr/bin/env bash
# install.sh – install WadwaitaUp dependencies for the current platform
# Supports: Arch Linux, Debian/Ubuntu, Fedora, macOS, Windows/MSYS2
#
# Note: webkit2gtk-4.1 is optional (enables the built-in HUST HUB browser).
# The app will gracefully show install instructions if it is missing.

set -e

case "$(uname -s)" in
  Darwin)
    echo "macOS detected – installing via Homebrew..."
    brew install pygobject3 gtk4 libadwaita webkitgtk
    ;;
  Linux)
    if command -v pacman &>/dev/null; then
      echo "Arch Linux (pacman) detected..."
      sudo pacman -Syu --needed python python-gobject gtk4 libadwaita webkit2gtk-4.1
    elif command -v dnf &>/dev/null; then
      echo "Fedora (dnf) detected..."
      sudo dnf install -y python3-gobject gtk4 libadwaita webkit2gtk4.1
    elif command -v apt &>/dev/null; then
      echo "Debian/Ubuntu (apt) detected..."
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
    ;;
  MINGW*|MSYS*|CYGWIN*)
    echo "Windows/MSYS2 detected – installing via pacman (MINGW64)..."
    # MSYS2 pacman does not use sudo; run this in an MSYS2 MINGW64 shell.
    pacman -S --needed \
      mingw-w64-x86_64-python-gobject \
      mingw-w64-x86_64-gtk4 \
      mingw-w64-x86_64-libadwaita \
      mingw-w64-x86_64-webkit2gtk-4.1
    ;;
  *)
    echo "Unsupported platform: $(uname -s)"
    echo "Please install GTK4, Libadwaita, and PyGObject manually."
    exit 1
    ;;
esac

echo ""
echo "Done! Run the app with:  python main.py"
