@echo off
REM Install from source: creates the virtual env and installs dependencies.
REM Requires Python 3.11-3.13 (python.org, check "Add to PATH").
cd /d "%~dp0"
echo == Creating virtual environment ==
python -m venv .venv || goto :err
echo == Installing dependencies (takes a few minutes) ==
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :err
echo == Checking camera and environment ==
".venv\Scripts\python.exe" airkeys.py check
echo.
echo DONE. Start with run.bat
pause
exit /b 0
:err
echo.
echo Install ERROR. Check that Python is installed and on PATH.
pause
exit /b 1
