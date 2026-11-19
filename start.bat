@echo off
rem Launcher for Windows (start.sh is the Linux / macOS twin).
rem   start.bat [--serial COM3] [--arduino-serial COM4] [--port 8080]
rem Find your COM ports with:  start.bat --list-ports
setlocal
cd /d "%~dp0"
if not defined PORT set "PORT=8080"

set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY where python >nul 2>&1 && set "PY=python"
if not defined PY (
  echo Python 3 not found. Install it from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^).
  pause
  exit /b 1
)

%PY% -c "import serial" >nul 2>&1 || (
  echo pyserial is not installed, so the display and sensor can't be used ^(simulation mode only^).
  echo Install it with:  %PY% -m pip install pyserial tzdata
  echo.
)

%PY% server.py --auto --port %PORT% %*
if errorlevel 1 pause
