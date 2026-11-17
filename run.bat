@echo off
REM Runs iPhone Panic Analyzer from source. First run installs what it needs (needs internet).
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python is not installed.
  echo Install Python 3.12 or newer from https://www.python.org/downloads/windows/
  echo IMPORTANT: tick "Add python.exe to PATH" during install, then run this file again.
  start "" "https://www.python.org/downloads/windows/"
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating environment, first run only...
  py -3 -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fail
)
start "" ".venv\Scripts\pythonw.exe" app\main.py %*
exit /b 0
:fail
echo Setup failed. See the messages above.
pause
exit /b 1
