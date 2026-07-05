@echo off
REM Instalacion desde codigo fuente: crea el entorno y las dependencias.
REM Necesita Python 3.11-3.13 instalado (python.org, marca "Add to PATH").
cd /d "%~dp0"
echo == Creando entorno virtual ==
python -m venv .venv || goto :err
echo == Instalando dependencias (tarda unos minutos) ==
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :err
echo == Comprobando camara y entorno ==
".venv\Scripts\python.exe" airkeys.py check
echo.
echo LISTO. Arranca con "Iniciar AirKeys.bat"
pause
exit /b 0
:err
echo.
echo ERROR en la instalacion. Revisa que Python este instalado y en el PATH.
pause
exit /b 1
