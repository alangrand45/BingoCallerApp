[app]

# (str) Title of your application
title = Bingo Caller App

# (str) Package name
package.name = bingocaller

# (str) Package domain (needed for android packaging)
package.domain = org.bingo

# (list) Source files to include (letting it include your Python script and media assets)
source.include_exts = py,png,jpg,kv,atlas,mp3,wav

# (str) Application main file (Must match your actual filename!)
source.main_file = bingo1_1.py

# (str) Application versioning
version = 0.1

# (list) Application requirements
# Add pillow for image handling, and ensure python3 and kivy are included
requirements = python3,kivy,pillow

# (list) Permissions
# (If your app needs vibrations or internet later, you can add them here)
android.permissions = INTERNET

# (str) Supported orientations (portrait, landscape or all)
orientation = portrait

# (bool) Indicate whether the application should be fullscreen or not
fullscreen = 0

# (string) Presplash background color
# android.presplash_color = #FFFFFF

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug with command output)
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1

# (str) Android arch to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
android.archs = arm64-v8a

# (bool) Automatically accept Android SDK license agreements (Required for GitHub Actions!)
android.accept_sdk_license = True
