@echo off
rem The Different Engine - starter for Windows 10 and 11.
rem
rem The first time, this installs everything that is needed. After that it
rem simply starts the program. Just double-click it.

setlocal
title The Different Engine
cd /d "%~dp0"
echo.
echo   The Different Engine
echo.

rem --- Find Python 3.9 or newer ----------------------------------------------
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1 && set "PY=python"
if defined PY goto have_python

echo Python is not installed on this computer yet. It is free.
where winget >nul 2>&1 || goto manual_python
choice /C YN /M "Shall I install Python for you now"
if errorlevel 2 goto manual_python
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
echo.
echo Python should now be installed.
echo Please close this window and double-click Start-Windows.bat again.
pause
exit /b 0

:manual_python
echo.
echo Please download Python from https://www.python.org/downloads/
echo When the installer opens, tick "Add python.exe to PATH", then click "Install Now".
echo After that, double-click Start-Windows.bat again.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:have_python
rem --- A private Python workspace for the program ----------------------------
if exist ".venv\Scripts\python.exe" goto check_packages
echo First run: setting things up. This takes a few minutes and only happens once.
%PY% -m venv .venv
if errorlevel 1 goto venv_failed

:check_packages
if exist ".venv\installed.txt" goto run
echo Installing the Python packages (needs the internet)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pip_failed
echo installed> ".venv\installed.txt"

:run
rem The Stockfish engine and the speech model are downloaded by the program itself.
".venv\Scripts\python.exe" -m different_engine %*
if errorlevel 1 pause
exit /b 0

:venv_failed
echo.
echo Sorry, I couldn't set up Python's workspace (the .venv folder).
echo Try deleting the .venv folder, then double-click Start-Windows.bat again.
pause
exit /b 1

:pip_failed
echo.
echo Sorry, the Python packages could not be installed.
echo Please check the internet connection, then double-click Start-Windows.bat again.
echo (If it keeps happening, delete the .venv folder and try once more.)
pause
exit /b 1
