"""Prueba backends e indices de camara y dice cual funciona.

    python -m tools.probe_cam
"""
import cv2

BACKENDS = [
    ("MSMF", cv2.CAP_MSMF),
    ("DSHOW", cv2.CAP_DSHOW),
    ("ANY", cv2.CAP_ANY),
]

def main():
    ok_combos = []
    for name, be in BACKENDS:
        for idx in range(4):
            try:
                cap = cv2.VideoCapture(idx, be)
                opened = cap.isOpened()
                ret, frame = cap.read() if opened else (False, None)
                cap.release()
            except Exception as e:
                print(f"  {name:6} idx {idx}: EXCEPTION {e}")
                continue
            if ret and frame is not None:
                h, w = frame.shape[:2]
                print(f"  {name:6} idx {idx}: OK  {w}x{h}")
                ok_combos.append((name, be, idx))
            else:
                print(f"  {name:6} idx {idx}: no frame")
    print()
    if ok_combos:
        name, be, idx = ok_combos[0]
        print(f"USAR ESTO -> backend {name} ({be}), CAM_INDEX {idx}")
    else:
        print("NINGUN backend/indice funciono.")
        print("Revisa: Configuracion Windows > Privacidad > Camara > 'Permitir apps de escritorio'.")

if __name__ == "__main__":
    main()
