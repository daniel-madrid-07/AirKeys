"""Prueba del sensor de flujo con MASCARA de mano sobre fondo con textura.

Simula el caso real que fallaba: la mano se mueve sobre una mesa CON textura.
Con la caja rectangular, los puntos del fondo (quietos) contaminaban la mediana y
frenaban el cursor. Con la mascara de silueta, solo se rastrea la 'piel'.

    python -m tools.smoke_flow
"""
import cv2
import numpy as np

from src.flow_sensor import FlowSensor


def main():
    rng = np.random.default_rng(0)
    H, W = 480, 640
    # fondo CON textura (mesa tipo marmol) y 'mano' con su propia textura
    bg = cv2.GaussianBlur(rng.uniform(0, 255, (H, W)).astype(np.float32), (0, 0), 3)
    hand_tex = cv2.GaussianBlur(rng.uniform(0, 255, (200, 160)).astype(np.float32),
                                (0, 0), 2)

    def frame_at(px, py):
        img = bg.copy()
        x, y = int(px), int(py)
        img[y:y + 200, x:x + 160] = hand_tex
        return img.astype(np.uint8)

    def mask_at(px, py):
        m = np.zeros((H, W), np.uint8)
        m[int(py) + 10:int(py) + 190, int(px) + 10:int(px) + 150] = 255
        return m

    # la mano avanza (2.0, -1.2) px/frame sobre fondo quieto. La escena se pega en
    # pixeles ENTEROS, asi que se compara contra el desplazamiento entero real.
    fs = FlowSensor()
    x, y = 100.0, 120.0
    fs.delta(frame_at(x, y), mask_at(x, y))
    errs = []
    for i in range(30):
        px_prev, py_prev = int(x), int(y)
        x += 2.0
        y -= 1.2
        true_d = (int(x) - px_prev, int(y) - py_prev)
        d = fs.delta(frame_at(x, y), mask_at(x, y))
        if d is not None:
            errs.append(abs(d[0] - true_d[0]) + abs(d[1] - true_d[1]))
    err = float(np.mean(errs))
    print(f"[SMOKE] mano sobre fondo texturizado: error medio {err:.3f}px "
          f"({len(errs)} medidas, pts {fs.n_good})")
    assert errs and err < 0.15, "la mascara no aisla la mano del fondo"
    print("[SMOKE] OK: el flujo con mascara mide el movimiento de la mano exacto.")


if __name__ == "__main__":
    main()
