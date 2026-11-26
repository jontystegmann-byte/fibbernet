#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
BUILD_PYTHON="${BUILD_PYTHON:-.build-venv/bin/python}"
"$BUILD_PYTHON" -m PyInstaller --noconfirm --clean --onedir --name linewatch-engine \
  --add-data "$(pwd)/assets:assets" --add-data "$(pwd)/config.example.json:." \
  --distpath build/engine --workpath build/pyinstaller --specpath build engine.py
APP="dist/Linewatch.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -O -target "$(uname -m)-apple-macosx14.0" -framework AppKit -framework WebKit -framework ServiceManagement -framework Carbon macos/Linewatch.swift -o "$APP/Contents/MacOS/Linewatch"
cp macos/Info.plist "$APP/Contents/Info.plist"
rm -rf "$APP/Contents/Resources/engine"
cp -R build/engine/linewatch-engine "$APP/Contents/Resources/engine"
mkdir -p "$APP/Contents/Resources/Notices"
cp THIRD_PARTY_NOTICES.md "$APP/Contents/Resources/Notices/"
"$BUILD_PYTHON" - "$APP/Contents/Resources/Notices" <<'PY'
import importlib.metadata
from pathlib import Path
import shutil
import sys
import sysconfig
destination = Path(sys.argv[1])
source = Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt'
if not source.exists():
    raise SystemExit('CPython license not found in the Python installation')
shutil.copyfile(source, destination / 'Python-LICENSE.txt')
distribution = importlib.metadata.distribution('pyinstaller')
for file in distribution.files:
    if 'COPYING' in str(file) or str(file).endswith('LICENSE'):
        candidate = Path(distribution.locate_file(file))
        if candidate.is_file():
            shutil.copyfile(candidate, destination / ('PyInstaller-' + candidate.name))
PY
cp assets/app-icon.png build/AppIcon.png
mkdir -p build/AppIcon.iconset
for s in 16 32 128 256 512; do
  sips -z "$s" "$s" build/AppIcon.png --out "build/AppIcon.iconset/icon_${s}x${s}.png" >/dev/null
  twice=$((s * 2))
  sips -z "$twice" "$twice" build/AppIcon.png --out "build/AppIcon.iconset/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns build/AppIcon.iconset -o "$APP/Contents/Resources/AppIcon.icns"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
ARCH="$(uname -m)"
ditto -c -k --sequesterRsrc --keepParent "$APP" "dist/Linewatch-1.1.0-${ARCH}.zip"
echo "Built $APP and dist/Linewatch-1.1.0-${ARCH}.zip"
