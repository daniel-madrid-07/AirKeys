# PyInstaller spec para AirKeys. Genera dist/AirKeys/AirKeys.exe
# Uso:  pyinstaller packaging/airkeys.spec   (desde la raiz del proyecto)
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.getcwd())

# MediaPipe necesita sus .tflite/.binarypb empaquetados
mp_datas = collect_data_files("mediapipe", include_py_files=False)
hidden = (collect_submodules("mediapipe") + collect_submodules("comtypes")
          + ["pygrabber", "pygrabber.dshow_graph"])

datas = mp_datas + [
    (os.path.join(ROOT, "models", "hand_landmarker.task"), "models"),
    (os.path.join(ROOT, "settings.example.json"), "."),
    (os.path.join(ROOT, "GUIDE.md"), "."),
]

a = Analysis(
    ["../airkeys.py"],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    # OJO: mediapipe importa matplotlib internamente -> no se puede excluir.
    # tkinter se usa para la GUI.
    excludes=["PyQt5", "PySide2"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AirKeys",
    console=False,          # aplicacion de ventana (GUI)
    icon=None,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="AirKeys",
)
