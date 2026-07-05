"""Calibra el detector de tap con TUS datos grabados.

Mide, por dedo, cuanto sube la señal s en las pulsaciones reales frente al reposo,
y sugiere TAP_SIGN / TAP_ENTER / TAP_EXIT para tu camara y postura.

    python -m tools.calibrate_tap
    python -m tools.calibrate_tap --file data/aire01.npz
"""
import argparse
import glob

import numpy as np

import config as C
from src.fingers import FINGER_MAP, _hand_slot
from src.tap import finger_signal, present


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None)
    args = ap.parse_args()

    files = [args.file] if args.file else sorted(glob.glob(str(C.DATA_DIR / "*.npz")))
    if not files:
        print("No hay datasets en data/.")
        return

    # acumula s por dedo en frames de tap y en reposo
    tap_s = {}      # (slot,finger) -> [s en pulsaciones]
    idle_s = {}
    for f in files:
        d = np.load(f, allow_pickle=False)
        feats = d["features"]
        labels = d["labels"].astype(str)
        for i in range(len(feats)):
            lab = labels[i]
            for key, (hand, finger) in FINGER_MAP.items():
                slot = _hand_slot(hand)
                if not present(feats[i], slot):
                    continue
                s = finger_signal(feats[i], slot, finger)
                k = (slot, finger)
                if lab == key:
                    tap_s.setdefault(k, []).append(s)
                elif lab == C.NONE_LABEL:
                    idle_s.setdefault(k, []).append(s)

    print(f"{'dedo':<14}{'reposo':>8}{'tap':>8}{'amplitud':>10}{'n_tap':>7}")
    amps = []
    for k in sorted(tap_s, key=lambda x: (x[0], x[1])):
        slot, finger = k
        tp = np.array(tap_s[k])
        idl = np.array(idle_s.get(k, [0.0]))
        base = np.median(idl)
        peak = np.median(tp)
        amp = peak - base
        amps.append(amp)
        name = f"{'L' if slot == 0 else 'R'}-{finger}"
        print(f"{name:<14}{base:>8.3f}{peak:>8.3f}{amp:>10.3f}{len(tp):>7}")

    if not amps:
        print("Sin pulsaciones. ¿Grabaste con record_air?")
        return
    med_amp = float(np.median([a for a in amps]))
    sign = 1.0 if med_amp >= 0 else -1.0
    m = abs(med_amp)
    print("\n--- Sugerencia para config.py ---")
    print(f"TAP_SIGN  = {sign:+.0f}     # amplitud mediana {med_amp:+.3f}")
    print(f"TAP_ENTER = {0.5 * m:.3f}")
    print(f"TAP_EXIT  = {0.25 * m:.3f}")
    if m < 0.02:
        print("AVISO: amplitud muy pequeña. La camara quiza no ve bien el gesto vertical.")
        print("       Prueba a inclinar la camara ~45 grados o subirla.")


if __name__ == "__main__":
    main()
