@echo off
REM Arranca AirKeys desde el codigo fuente (menu interactivo).
REM Para el .exe ya empaquetado no hace falta esto.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" airkeys.py
) else (
    python airkeys.py
)
pause
