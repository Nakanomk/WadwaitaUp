import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from window import WadwaitaUpWindow


class WadwaitaUpApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.nakanomk.WadwaitaUp")
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        win = self.props.active_window
        if not win:
            win = WadwaitaUpWindow(app)
        win.present()


if __name__ == "__main__":
    Adw.init()
    app = WadwaitaUpApp()
    app.run([])