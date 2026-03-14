# buildozer.spec – WadwaitaUp Android build configuration
# Documentation: https://buildozer.readthedocs.io/en/latest/specifications.html

[app]

title           = WadwaitaUp
package.name    = wadwaitaup
package.domain  = com.nakanomk

# The Android entry point lives in the android/ subdirectory so that
# it doesn't interfere with the desktop GTK4 main.py in the root.
source.dir      = android
source.include_exts = py

version         = 0.1

# Runtime dependencies (Python for Android handles these)
requirements    = python3==3.11.0,kivy==2.3.0

# UI / display
orientation     = portrait
fullscreen      = 0

# Android SDK / NDK targets
android.api     = 33
android.minapi  = 21
android.ndk     = 25b
android.arch    = arm64-v8a

# Auto-accept SDK license prompts in CI (Buildozer uses pexpect to send "y")
android.accept_sdk_license = True

# Permissions (add more as features are developed)
android.permissions = INTERNET

# Icons / presplash (use defaults for now)
# icon.filename = %(source.dir)s/data/icon.png
# presplash.filename = %(source.dir)s/data/presplash.png

[buildozer]
log_level   = 2
warn_on_root = 0
