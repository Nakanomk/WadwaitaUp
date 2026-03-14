# android/main.py – WadwaitaUp Android entry point (Kivy-based)
#
# GTK4/Libadwaita is not available on Android, so this file provides
# a Kivy-based UI for the Android platform.  Desktop platforms continue
# to use the GTK4 main.py in the repository root.

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window


class WadwaitaUpApp(App):
    def build(self):
        Window.clearcolor = (0.12, 0.12, 0.12, 1)

        root = BoxLayout(orientation="vertical", padding=16, spacing=12)

        title = Label(
            text="WadwaitaUp",
            font_size="24sp",
            bold=True,
            size_hint_y=None,
            height=48,
        )
        root.add_widget(title)

        subtitle = Label(
            text="课程表 / Course Schedule",
            font_size="14sp",
            size_hint_y=None,
            height=28,
            color=(0.7, 0.7, 0.7, 1),
        )
        root.add_widget(subtitle)

        note = Label(
            text="Android support is under active development.\n"
                 "For full functionality please use the desktop version.",
            font_size="12sp",
            halign="center",
            text_size=(Window.width - 32, None),
            color=(0.6, 0.8, 1, 1),
        )
        root.add_widget(note)

        return root


if __name__ == "__main__":
    WadwaitaUpApp().run()
