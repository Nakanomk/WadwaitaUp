#!/usr/bin/env bash
# install.sh – install WadwaitaUp dependencies for the current platform

set -e

case "$(uname -s)" in
  Darwin)
    echo "macOS detected – installing via Homebrew..."
    brew install pygobject3 gtk4 libadwaita
    ;;
  Linux)
    if command -v pacman &>/dev/null; then
      echo "Arch Linux detected..."
      sudo pacman -Syu --needed python python-gobject gtk4 libadwaita
    elif command -v apt &>/dev/null; then
      echo "Debian/Ubuntu detected..."
      sudo apt update
      sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
    else
      echo "Unsupported Linux distribution. Please install GTK4, Libadwaita, and PyGObject manually."
      exit 1
    fi
    ;;
  MINGW*|MSYS*|CYGWIN*)
    echo "Windows/MSYS2 detected – installing via pacman (MINGW64)..."
    # MSYS2 pacman does not use sudo; run this in an MSYS2 MINGW64 shell.
    pacman -S --needed \
      mingw-w64-x86_64-python-gobject \
      mingw-w64-x86_64-gtk4 \
      mingw-w64-x86_64-libadwaita
    ;;
  *)
    echo "Unsupported platform: $(uname -s)"
    echo "Please install GTK4, Libadwaita, and PyGObject manually."
    exit 1
    ;;
esac

echo ""
echo "Done! Run the app with:  python main.py"
