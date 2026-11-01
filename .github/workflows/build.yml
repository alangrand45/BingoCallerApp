name: Build Android APK

on:
  push:
    branches: [ main, master ]

jobs:
  build:
    runs-on: ubuntu-22.04

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Build with Buildozer
        uses: kivy/buildozer-action@v1
        with:
          command: buildozer android debug
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Upload APK Artifact
        uses: actions/upload-artifact@v4
        with:
          name: package
          path: bin/*.apk
