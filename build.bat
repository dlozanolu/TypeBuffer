@echo off
setlocal
cd /d "%~dp0"

set "PY=%LocalAppData%\Python\bin\python.exe"
if not exist "%PY%" set "PY=python"

echo Instalando dependencias...
pip install -r requirements-dev.txt
if errorlevel 1 pause & exit /b 1

echo Compilando TypeBuffer.exe ...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --noconsole --name TypeBuffer TypeBuffer.py
if errorlevel 1 pause & exit /b 1

echo.
echo OK: dist\TypeBuffer.exe
echo Para arranque al login:  python install_autostart.py --install
echo.
pause
