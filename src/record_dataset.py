"""Grabador de dataset con auto-etiquetado.

Idea (la misma del paper 'Typing on Any Surface'):
  1. Pon la webcam mirando tus manos sobre un TECLADO REAL.
  2. Escribe texto normal. Cada tecla real que pulsas queda registrada con timestamp.
  3. Cada frame de video se etiqueta con la tecla pulsada en ese instante (o 'none').
  => Dataset perfecto sin etiquetar a mano.

Cuando el modelo ya funcione, quitas el teclado y escribes sobre mesa vacia.

Uso:
    python -m src.record_dataset --name sesion01
Controles:
    ESC  -> terminar y guardar
Solo se registran las pulsaciones fisicas; NO se envian a otras apps.
Los datos quedan en local en data/. Sirven para entrenar tu propio modelo.
"""
import argparse
import time

import cv2
import numpy as np
from pynput import keyboard

import config as C
from src.hand_tracker import HandTracker, draw
from src.camera import open_camera


def key_to_name(key):
    """Normaliza una tecla de pynput a un nombre de clase o None si se ignora."""
    if key == keyboard.Key.space:
        return "space"
    ch = getattr(key, "char", None)
    if ch and ch.isalpha():
        return ch.lower()
    return None  # ignoramos numeros, modificadores, etc. (amplia TARGET_KEYS si quieres)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default=time.strftime("sesion_%Y%m%d_%H%M%S"))
    args = ap.parse_args()

    tracker = HandTracker()
    cap = open_camera()

    frames_t, frames_f, frames_raw_present = [], [], []
    key_events = []  # (timestamp, name)

    def on_press(key):
        name = key_to_name(key)
        if name is not None:
            key_events.append((time.perf_counter(), name))

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    print("[REC] Escribe normal sobre el teclado. ESC en la ventana para terminar.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if C.FLIP_HORIZONTAL:
                frame = cv2.flip(frame, 1)
            t = time.perf_counter()
            feat, res = tracker.process(frame)
            frames_t.append(t)
            frames_f.append(feat)

            hands_present = len(res.hand_landmarks) if res.hand_landmarks else 0
            draw(frame, res)
            frames_raw_present.append(hands_present)

            cv2.putText(frame, f"frames:{len(frames_t)}  teclas:{len(key_events)}  manos:{hands_present}",
                        (12, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow("AirKeys - grabando (ESC o q para terminar)", frame)
            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord("q")):   # ESC o q (la ventana debe tener foco)
                break
    except KeyboardInterrupt:
        print("\n[REC] Ctrl+C -> guardando lo grabado...")
    finally:
        listener.stop()
        cap.release()
        cv2.destroyAllWindows()
        tracker.close()

    if not frames_t:
        print("[REC] Sin frames. Nada que guardar.")
        return

    # --- Alineado por timestamp: etiqueta cada frame ---
    ts = np.array(frames_t)
    labels = np.array([C.NONE_LABEL] * len(ts), dtype=object)
    for kt, name in key_events:
        idx = int(np.argmin(np.abs(ts - kt)))
        if abs(ts[idx] - kt) <= C.LABEL_TOL_S:
            labels[idx] = name
            # "unta" la etiqueta a los frames vecinos (solo si estaban vacios)
            for s in range(1, C.LABEL_SPREAD + 1):
                for j in (idx - s, idx + s):
                    if 0 <= j < len(labels) and labels[j] == C.NONE_LABEL:
                        labels[j] = name

    feats = np.stack(frames_f).astype(np.float32)
    present = np.array(frames_raw_present, dtype=np.int8)
    out = C.DATA_DIR / f"{args.name}.npz"
    np.savez_compressed(out, features=feats, labels=labels.astype("U8"),
                        timestamps=ts, present=present)

    n_key = int((labels != C.NONE_LABEL).sum())
    print(f"[REC] Guardado {out}")
    print(f"[REC] {len(ts)} frames | {n_key} frames con tecla | {len(key_events)} pulsaciones")
    if n_key < len(key_events) * 0.8:
        print("[REC] Aviso: pocas teclas alineadas. Sube LABEL_TOL_S o revisa los FPS.")


if __name__ == "__main__":
    main()
