"""Calibracion del raton v2 — dos gestos, 8 segundos total.

Aprende COMO se mueve TU mano en TU camara. Dos fases:
  1. Mueve la mano hacia la DERECHA (un movimiento lento y recto, como con el raton)
  2. Mueve la mano hacia ALANTE (alejandola de ti, sobre la mesa)

De cada gesto saca direccion + amplitud en la imagen. Con eso el raton relativo
sabe que es "derecha" y que es "arriba", da igual el angulo de la camara.

    python -m tools.calibrate_mouse

Guarda models/mouse_axes.npz.
"""
import time

import cv2
import numpy as np

import config as C
from src.hand_tracker import HandTracker, draw
from src.camera import open_camera
from src.mouse_control import AXES_PATH, _pick_hand

PHASES = [
    ("DERECHA", "mueve la mano hacia la DERECHA, lento y recto"),
    ("ALANTE",  "mueve la mano hacia ALANTE (lejos de ti), lento y recto"),
]
SETTLE_S = 3.0     # colocarse antes de cada gesto
GESTO_S = 3.0      # duracion de captura del gesto
MIN_AMP = 0.03     # amplitud minima del gesto en la imagen


def big(frame, text, y, scale=1.1, color=(0, 220, 255), thick=2):
    cv2.putText(frame, text, (20, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)


def gesture_vector(points):
    """Direccion con signo + amplitud del gesto: fin - inicio (medianas)."""
    pts = np.array(points)
    n = max(5, len(pts) // 10)
    start = np.median(pts[:n], axis=0)
    end = np.median(pts[-n:], axis=0)
    vec = end - start
    amp = float(np.linalg.norm(vec))
    return (vec / amp if amp > 0 else vec), amp


def main():
    tracker = HandTracker()
    cap = open_camera()

    axes = []          # [(dir, amp)] para DERECHA y ALANTE
    phase = 0
    t_gesto = time.perf_counter() + SETTLE_S
    points = []

    print("[CALIB] Dos gestos. Manten la mano APOYADA en la mesa, como con el raton.")
    try:
        while phase < len(PHASES):
            ok, frame = cap.read()
            if not ok:
                break
            if C.FLIP_HORIZONTAL:
                frame = cv2.flip(frame, 1)
            _, res = tracker.process(frame)
            draw(frame, res)
            now = time.perf_counter()

            name, desc = PHASES[phase]
            lms = _pick_hand(res, C.MOUSE_HAND)
            tip = lms[C.MOUSE_LANDMARK] if lms else None

            big(frame, f"[{phase+1}/2] {desc}", 50, 0.85)
            if now < t_gesto:
                big(frame, f"colocate (mano al inicio)... {t_gesto - now:.1f}s",
                    110, 1.0, (255, 255, 255))
                points = []
            elif now < t_gesto + GESTO_S:
                if tip is not None:
                    points.append((tip.x, tip.y))
                big(frame, f"AHORA: {name}  ({t_gesto + GESTO_S - now:.1f}s)",
                    110, 1.5, (0, 255, 0), 3)
                if tip is None:
                    big(frame, "NO VEO LA MANO", 170, 1.0, (0, 0, 255))
            else:
                if len(points) < 20:
                    print(f"[CALIB] {name}: no vi la mano. Repetimos fase.")
                    t_gesto = time.perf_counter() + SETTLE_S
                    continue
                vec, amp = gesture_vector(points)
                if amp < MIN_AMP:
                    print(f"[CALIB] {name}: gesto muy corto ({amp:.3f}). Repetimos: "
                          "mueve MAS la mano.")
                    t_gesto = time.perf_counter() + SETTLE_S
                    continue
                print(f"[CALIB] {name}: direccion {vec.round(3)} amplitud {amp:.3f}")
                axes.append((vec, amp))
                phase += 1
                t_gesto = time.perf_counter() + SETTLE_S

            cv2.imshow("AirKeys - calibrar raton (ESC/q aborta)", frame)
            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord("q")):
                print("[CALIB] Abortado.")
                return
    finally:
        cap.release()
        cv2.destroyAllWindows()
        tracker.close()

    if len(axes) < 2:
        print("[CALIB] Incompleto. Nada guardado.")
        return

    (u, amp_x), (v, amp_y) = axes
    # aviso si los ejes no son razonablemente perpendiculares en la imagen
    cosang = abs(float(u @ v))
    np.savez(AXES_PATH, u=u, v=v, amp_x=amp_x, amp_y=amp_y)
    print(f"[CALIB] Guardado {AXES_PATH}")
    if cosang > 0.7:
        print("[CALIB] AVISO: 'derecha' y 'alante' salieron casi paralelos. "
              "Repite la calibracion con gestos mas distintos.")
    else:
        print("[CALIB] OK. Prueba: python -m tools.mouse_test")


if __name__ == "__main__":
    main()
