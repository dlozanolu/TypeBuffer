@echo off
setlocal
cd /d "%~dp0"

set "PY=%LocalAppData%\Python\bin\python.exe"
if not exist "%PY%" set "PY=python"

echo Installing dependencies...
pip install -r requirements-dev.txt
if errorlevel 1 pause & exit /b 1

echo Building TypeBuffer.exe ...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --noconsole --name TypeBuffer TypeBuffer.py
if errorlevel 1 pause & exit /b 1

echo.
echo SUCCESS: dist\TypeBuffer.exe
echo For login autostart run:  python setup_autostart.py --install
echo.
pause