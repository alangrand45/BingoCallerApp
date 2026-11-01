[app]

# (str) Title of your application
title = Bingo Caller App

# (str) Package name
package.name = bingocaller

# (str) Package domain (needed for android packaging)
package.domain = org.bingo

# (str) Source directory where the application lives
source.dir = .

# (list) Source files to include
source.include_exts = py,png,jpg,kv,atlas,mp3,wav

# (str) Application main file
source.main_file = bingo1_1.py

# (str) Application versioning
version = 0.1

# (list) Application requirements
requirements = python3,kivy

# (list) Permissions
android.permissions = INTERNET

# (str) Supported orientations
orientation = portrait

# (bool) Fullscreen
fullscreen = 0

# --- Android Specific Settings ---
# (int) Target Android API
android.api = 31

# (int) Minimum API your APK will support
android.min_api = 21

# (int) Android SDK version to use
android.sdk = 31

# (str) Android NDK version to use
android.ndk = 25b

# (str) Android arch to build for
android.archs = arm64-v8a

# (bool) Automatically accept Android SDK license agreements
android.accept_sdk_license = True

[buildozer]

# (int) Log level
log_level = 2

# (int) Warn on root
warn_on_root = 1
