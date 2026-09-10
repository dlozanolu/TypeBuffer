@echo off
setlocal
cd /d "%~dp0"

set "PY=%LocalAppData%\Python\bin\python.exe"
if not exist "%PY%" set "PY=python"

echo Testing Tray Icon...
echo Look at your system tray (bottom right corner).
echo Right click it to see the menu or open Settings.
echo.

"%PY%" tray.py
if errorlevel 1 pause
