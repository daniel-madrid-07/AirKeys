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
& $py -m PyInstaller --noconfirm --clean packaging\airkeys.spec

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
