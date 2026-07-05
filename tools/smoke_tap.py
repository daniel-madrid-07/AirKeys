"""Prueba de humo del detector de tap con señal sintetica.

Fabrica un flujo de features donde un dedo (slot 0, index) hace N taps limpios y
comprueba que TapDetector los cuenta bien.

    python -m tools.smoke_tap
"""
import numpy as np

import config as C
from src.tap import TapDetector, TIP, MCP


def set_finger_y(feat, slot, finger, tip_y, mcp_y):
    base_tip = slot * C.PER_HAND + C.PER_HAND_REL + TIP[finger] * 2
    base_mcp = slot * C.PER_HAND + C.PER_HAND_REL + MCP[finger] * 2
    feat[base_tip + 1] = tip_y
    feat[base_mcp + 1] = mcp_y
    # referencia de tamaño de mano (muñeca 0 y nudillo corazon 9): escala = 0.15
    base_w = slot * C.PER_HAND + C.PER_HAND_REL + 0 * 2
    base_9 = slot * C.PER_HAND + C.PER_HAND_REL + 9 * 2
    feat[base_w], feat[base_w + 1] = 0.5, 0.65
    feat[base_9], feat[base_9 + 1] = 0.5, 0.50
    feat[C.PER_HAND * C.MAX_HANDS + slot] = 1.0   # presencia


def main():
    slot, finger = 0, "index"
    det = TapDetector([(slot, finger)])
    fps = 60.0
    n_frames = 600
    tap_frames = [80, 180, 280, 380, 480]   # 5 taps
    rng = np.random.default_rng(0)

    fired = []
    for i in range(n_frames):
        t = i / fps
        # cada tecla = LEVANTAR (s baja) y luego PULSAR (s sube): bump neto por frame
        bump = 0.0
        for tf in tap_frames:
            d = i - tf
            if -14 <= d <= -8:                        # levantamiento previo
                bump = min(bump, -0.06)
            if -4 <= d <= 4:                          # pulsacion (pico en tf)
                bump = max(bump, 0.09 * (1 - abs(d) / 4.0))
        feat = np.zeros(C.FEATURE_DIM, np.float32)
        set_finger_y(feat, slot, finger,
                     tip_y=0.5 + bump + rng.normal(0, 0.002),
                     mcp_y=0.5)
        for (_, _, peak_t, amp) in det.update(feat, t):
            fired.append(peak_t * fps)

    print(f"[SMOKE] taps insertados={len(tap_frames)}  detectados={len(fired)}")
    print(f"[SMOKE] frames pico detectados ~= {[round(x) for x in fired]}")
    assert len(fired) == len(tap_frames), "el detector no cuenta bien los taps"
    for f, tf in zip(fired, tap_frames):
        assert abs(f - tf) <= 3, f"pico detectado lejos del real ({f} vs {tf})"
    print("[SMOKE] OK: TapDetector detecta y ubica los taps.")


if __name__ == "__main__":
    main()
