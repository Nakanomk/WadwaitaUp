# WadwaitaUp

Maybe it will be realized sometime.

An Adwaita-themed Wakeup-like software.

## Dependencies

```
# For Arch Linux
sudo pacman -Syu --needed python python-gobject gtk4 libadwaita

# For Debian Series
sudo apt update
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
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
