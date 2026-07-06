"""Smoke test del teclado GEOMETRICO (sin camara ni modelo).

Simula landmarks de dos manos reposando (calibracion home), luego strikes
sinteticos del indice derecho sobre J (home), sobre U (fila superior) y del
pulgar (espacio), y comprueba que el decodificador devuelve esas teclas.

    python -m tools.smoke_geo
"""
import numpy as np

import config as C
from src.fingers import _hand_slot
from src.keyboard_geo import GeoKeyboard
from src.tap import TIP, MCP

FPS = 30.0
DT = 1.0 / FPS


class Hand:
    """Posiciones absolutas (x, y) de los landmarks que usa el pipeline."""

    def __init__(self, wrist, sign):
        self.wrist = list(wrist)                  # lm 0
        self.mcp9 = [wrist[0], wrist[1] - 0.10]   # lm 9 -> scale = 0.10
        x0, y0 = wrist
        # puntas home (dedos apuntando "arriba" de la imagen), pitch ~0.033
        self.tips = {
            "index":  [x0 - sign * 0.050, y0 - 0.150],
            "middle": [x0 - sign * 0.017, y0 - 0.160],
            "ring":   [x0 + sign * 0.016, y0 - 0.150],
            "pinky":  [x0 + sign * 0.049, y0 - 0.140],
            "thumb":  [x0 - sign * 0.070, y0 - 0.030],
        }
        self.mcps = {f: [t[0], t[1] + 0.08] for f, t in self.tips.items()}
        self.mcps["middle"] = self.mcp9

    def feat_into(self, feat, slot):
        base = slot * C.PER_HAND + C.PER_HAND_REL

        def put(lm, xy):
            feat[base + lm * 2] = xy[0]
            feat[base + lm * 2 + 1] = xy[1]

        put(0, self.wrist)
        put(9, self.mcp9)
        for f in ("index", "middle", "ring", "pinky", "thumb"):
            put(TIP[f], self.tips[f])
            if TIP[f] != 12:                       # el mcp del corazon es lm 9
                put(MCP[f], self.mcps[f])
        feat[C.PER_HAND * C.MAX_HANDS + slot] = 1.0


def run():
    left = Hand((0.35, 0.75), sign=-1)
    right = Hand((0.65, 0.75), sign=+1)
    slot_l, slot_r = _hand_slot("Left"), _hand_slot("Right")
    kb = GeoKeyboard()
    typed = []
    t = 0.0

    def step(n=1):
        nonlocal t
        for _ in range(n):
            feat = np.zeros(C.FEATURE_DIM, np.float32)
            left.feat_into(feat, slot_l)
            right.feat_into(feat, slot_r)
            typed.extend(kb.update(feat, t))
            t += DT

    idx = right.tips["index"]
    home_y = idx[1]
    pitch_abs = 0.033                       # separacion real entre puntas
    row_up = pitch_abs * C.KB_ROW_SCALE     # desplazamiento de fila 0 en imagen

    # 1) reposo -> calibracion de las dos manos
    step(int(1.5 * FPS))
    assert kb.calibrated, "no calibro con las manos quietas"

    # 2) strike J (tecla home del indice derecho): lift + bajada rapida
    for dy in (-0.004, -0.008, -0.012, -0.015, -0.015):   # levanta (lento)
        idx[1] = home_y + dy
        step()
    for dy in (-0.010, -0.004, 0.0):                      # golpea (rapido)
        idx[1] = home_y + dy
        step()
    step(int(0.3 * FPS))                                  # quieto tras el golpe

    # 3) strike U (fila superior): lift + viaje hacia arriba + bajada corta
    for k in range(8):                                    # sube hacia U + hover
        idx[1] = home_y - (row_up + 0.015) * (k + 1) / 8.0
        step()
    for dy in (0.010, 0.015):                             # baja hasta la superficie
        idx[1] = home_y - row_up - 0.015 + dy
        step()
    step(int(0.3 * FPS))
    for k in range(12):                                   # vuelve a home SUAVE
        idx[1] = home_y - row_up + row_up * (k + 1) / 12.0
        step()
    step(int(0.4 * FPS))

    # 4) espacio con el pulgar
    th = right.tips["thumb"]
    th_y = th[1]
    for dy in (-0.005, -0.010, -0.014, -0.014):
        th[1] = th_y + dy
        step()
    for dy in (-0.009, -0.003, 0.0):
        th[1] = th_y + dy
        step()
    step(int(0.3 * FPS))

    print(f"[SMOKE] teclas detectadas: {typed}")
    assert typed == ["j", "u", "space"], f"esperaba ['j','u','space'], salio {typed}"
    print("[SMOKE] OK: calibracion home + strike por velocidad + decode geometrico.")


if __name__ == "__main__":
    run()
