#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 -m pip install -r requirements-dev.txt
python3 -m PyInstaller --noconfirm --clean --onefile --noconsole --name TypeBuffer TypeBuffer.py

echo
echo "OK: dist/TypeBuffer"
echo "Autostart: python3 install_autostart.py --install"
