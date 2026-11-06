@echo off
setlocal
cd /d "%~dp0"
if not exist "requirements.txt" (
  echo The app files are missing. Right-click the downloaded ZIP, choose Extract All, then run this launcher from the extracted folder.
  pause
  exit /b 1
)
if not exist "monitor\app.py" (
  echo The monitor folder is missing. Extract the entire ZIP before running this launcher.
  pause
  exit /b 1
)
if exist ".venv\Scripts\python.exe" goto run
py -3 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3 was not found. Install Python 3.11 or newer from python.org with the Python launcher and Tcl/Tk enabled.
  pause
  exit /b 1
)
py -3 -m venv .venv
if errorlevel 1 goto failed
:run
.venv\Scripts\python.exe -c "import PIL" >nul 2>&1
if errorlevel 1 (
  .venv\Scripts\python.exe -m pip install -r requirements.txt
  if errorlevel 1 goto failed
)
.venv\Scripts\python.exe -m monitor.app
if errorlevel 1 goto failed
exit /b 0
:failed
echo Setup or launch failed. Read the error above. Check Python installation and internet access, then try again.
pause
exit /b 1
