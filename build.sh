#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -m pip install -r requirements-dev.txt
python3 -m PyInstaller --noconfirm --clean --onefile --noconsole --add-data "assets:assets" --name TypeBuffer TypeBuffer.py

echo
echo "SUCCESS: dist/TypeBuffer"
echo "Autostart: python3 setup_autostart.py --install"