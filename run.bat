@echo off
REM Starts AirKeys from source (window UI). For the packaged .exe this is not needed.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" airkeys.py
) else (
    python airkeys.py
)
pause
