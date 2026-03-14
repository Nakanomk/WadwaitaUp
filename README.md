# WadwaitaUp

Maybe it will be realized sometime.

An Adwaita-themed Wakeup-like software.

## Dependencies

WadwaitaUp requires **GTK4** and **Libadwaita**. Install them for your platform:

```bash
# Arch Linux
sudo pacman -Syu --needed python python-gobject gtk4 libadwaita

# Debian / Ubuntu
sudo apt update
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1

# macOS (Homebrew)
brew install pygobject3 gtk4 libadwaita

# Windows (MSYS2 — use the MINGW64 shell)
pacman -S mingw-w64-x86_64-python-gobject \
          mingw-w64-x86_64-gtk4 \
          mingw-w64-x86_64-libadwaita
```

## How to run?

```
python main.py
```

## A way to easily add courses

1. Visit https://hubs.hust.edu.cn/basicInformation/scheduleInformation/index
2. Click on the "总课表" button
3. Press f12 to see the source code, find the '`<div class="el-row">`' tag, copy all the contents under it.
4. Paste the contents to a LLM and paste the standard format given in the program. Ask the LLM to generate a 'json' file with the second type(class period type) as possible
5. Paste the json given by AI into the program, and start enjoy your term!

## JSON import format

Two formats are supported side-by-side.  Single-session (legacy):

```json
[
  {
    "name": "高等数学",
    "day": 1,
    "start": "08:00",
    "end": "09:40",
    "location": "东1-101",
    "teacher": "张老师",
    "weeks": "1-16"
  }
]
```

Multi-session — one entry with multiple class slots (avoids duplicate names):

```json
[
  {
    "name": "英语",
    "location": "北1-310",
    "teacher": "王老师",
    "weeks": "1-16",
    "sessions": [
      {"day": 2, "start": "10:10", "end": "11:50"},
      {"day": 4, "start_period": 5, "end_period": 6}
    ]
  }
]
```

When importing, if any course name matches an existing course you will be asked
whether to **skip** (only add new-name courses) or **overwrite** (replace all
same-name courses with the imported ones).

