@echo off
REM Builds a single iPhonePanicAnalyzer.exe in the "dist" folder.
cd /d "%~dp0"
where py >nul 2>nul || (echo Install Python 3.12+ from python.org first. & pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" py -3 -m venv .venv
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller || goto :fail
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --onefile --windowed ^
  --name iPhonePanicAnalyzer ^
  --icon app\assets\icon.ico ^
  --add-data "app\rules.json;." ^
  --add-data "app\assets;assets" ^
  --collect-all pymobiledevice3 ^
  --collect-all pycrashreport ^
  --collect-data developer_disk_image ^
  --recursive-copy-metadata pymobiledevice3 ^
  --paths app ^
  app\main.py || goto :fail
copy /y app\rules.json dist\rules.json >nul
echo.
echo Done. Your app is dist\iPhonePanicAnalyzer.exe
echo (dist\rules.json can be edited to add your own panic codes.)
pause
exit /b 0
:fail
echo Build failed. See the messages above.
pause
exit /b 1
