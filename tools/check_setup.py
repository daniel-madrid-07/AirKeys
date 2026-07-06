"""Comprueba que el entorno esta bien: imports, version y (opcional) camara.

    python -m tools.check_setup            # imports + versiones
    python -m tools.check_setup --cam      # ademas abre la webcam 2 segundos
"""
import argparse
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam", action="store_true")
    args = ap.parse_args()

    print(f"python {sys.version.split()[0]}")
    import numpy, cv2, mediapipe, pynput
    print(f"numpy {numpy.__version__}  opencv {cv2.__version__}  mediapipe {mediapipe.__version__}")
    try:
        import torch
        print(f"torch {torch.__version__}  (modo teclado disponible)")
    except ImportError:
        print("torch NO instalado -> raton y gaming OK; el modo teclado no.")

    import config as C
    from src.hand_tracker import HandTracker
    print(f"FEATURE_DIM={C.FEATURE_DIM}  WINDOW={C.WINDOW}  clases={1+len(C.TARGET_KEYS)}")

    # HandTracker sobre un frame negro (sin manos) -> vector de ceros
    import numpy as np
    ht = HandTracker()
    feat, _ = ht.process(np.zeros((C.FRAME_H, C.FRAME_W, 3), np.uint8))
    ht.close()
    assert feat.shape == (C.FEATURE_DIM,)
    print("HandTracker OK (frame vacio -> vector correcto)")

    if args.cam:
        import time
        from src.camera import open_camera, reported_fps
        cap = open_camera()
        ok, fr = cap.read()
        t0 = time.time(); n = 0
        while time.time() - t0 < 2 and ok:
            ok, fr = cap.read(); n += 1
        rep = reported_fps(cap)
        cap.release()
        print(f"camara: {'OK' if ok else 'FALLO'}  ~{n/2:.0f} fps captura (reporta {rep:.0f})")

    print("SETUP OK")


if __name__ == "__main__":
    main()
