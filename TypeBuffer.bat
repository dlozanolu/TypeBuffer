@echo off
cd /d "%~dp0"
set "PY=%LocalAppData%\Python\bin\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" "TypeBuffer.py" %*
if errorlevel 1 pause
