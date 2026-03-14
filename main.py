import sys
import pathlib

# Read version from the VERSION file bundled with the application
_VERSION_FILE = pathlib.Path(__file__).with_name("VERSION")
__version__ = _VERSION_FILE.read_text(encoding="utf-8").strip() if _VERSION_FILE.exists() else "unknown"

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw
except (ImportError, ValueError):
    print(
        "错误：未找到 GTK4 / Libadwaita 依赖库。\n"
        "Error: GTK4 / Libadwaita libraries not found.\n\n"
        "Linux (Arch):\n"
        "  sudo pacman -Syu --needed python python-gobject gtk4 libadwaita\n\n"
        "Linux (Debian/Ubuntu):\n"
        "  sudo apt install -y python3-gi python3-gi-cairo "
        "gir1.2-gtk-4.0 gir1.2-adw-1\n\n"
        "macOS (Homebrew):\n"
        "  brew install pygobject3 gtk4 libadwaita\n\n"
        "Windows (MSYS2 MINGW64):\n"
        "  pacman -S mingw-w64-x86_64-python-gobject "
        "mingw-w64-x86_64-gtk4 mingw-w64-x86_64-libadwaita\n",
        file=sys.stderr,
    )
    sys.exit(1)

from window import WadwaitaUpWindow


class WadwaitaUpApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.nakanomk.WadwaitaUp")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        win = self.props.active_window
        if not win:
            win = WadwaitaUpWindow(app, version=__version__)
        win.present()


if __name__ == "__main__":
    Adw.init()
    app = WadwaitaUpApp()
    app.run([])