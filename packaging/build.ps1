# Construye el ejecutable de AirKeys con PyInstaller.
#   powershell -ExecutionPolicy Bypass -File packaging\build.ps1
# Resultado: dist\AirKeys\AirKeys.exe  (+ opcional instalador si Inno Setup esta)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)   # raiz del proyecto

$py = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "== Instalando PyInstaller ==" -ForegroundColor Cyan
& $py -m pip install --quiet pyinstaller

Write-Host "== Limpiando build anterior ==" -ForegroundColor Cyan
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Write-Host "== Empaquetando (esto tarda) ==" -ForegroundColor Cyan
# --collect-all torch fuerza TODOS sus binarios (_C, DLLs) -> los 3 modos en el exe.
# NO se excluye mediapipe.genai (su __init__ lo importa); genai.converter es lazy
# (jax/sentencepiece solo para conversion LLM, que no usamos).
# NO --windowed (PyInstaller 6.21 pierde binarios); la GUI oculta su consola sola.
& $py -m PyInstaller --noconfirm --onedir --name AirKeys `
    --collect-all torch `
    --collect-all webview `
    --collect-all flask `
    --collect-submodules clr_loader `
    --collect-data mediapipe `
    --collect-submodules mediapipe `
    --collect-submodules comtypes `
    --hidden-import pygrabber.dshow_graph `
    --icon "packaging\icon.ico" `
    --exclude-module tensorflow `
    --add-data "models/hand_landmarker.task;models" `
    --add-data "settings.example.json;." `
    --add-data "GUIDE.md;." `
    --add-data "src/webgui/static;src/webgui/static" `
    --add-data "packaging/icon.ico;packaging" `
    airkeys.py

if (-not (Test-Path "dist\AirKeys\AirKeys.exe")) {
    Write-Error "No se genero el ejecutable."
}
Write-Host "OK -> dist\AirKeys\AirKeys.exe" -ForegroundColor Green

# Instalador opcional con Inno Setup si esta instalado
$iscc = Get-Command iscc.exe -ErrorAction SilentlyContinue
if ($iscc) {
    Write-Host "== Generando instalador (Inno Setup) ==" -ForegroundColor Cyan
    & $iscc.Source "packaging\installer.iss"
    Write-Host "OK -> dist\AirKeys-Setup.exe" -ForegroundColor Green
} else {
    Write-Host "Inno Setup no encontrado: se omite el instalador. (opcional)" -ForegroundColor Yellow
    Write-Host "Instalalo de https://jrsoftware.org/isdl.php y reejecuta para el .exe de instalacion."
}
