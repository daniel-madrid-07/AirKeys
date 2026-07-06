"""Grabador GUIADO por metronomo. Entrena SIN teclado fisico -> sin domain gap.

Problema: si grabas sobre un teclado real, tus manos no adoptan la misma postura
que sobre la mesa vacia. El modelo entrenado asi falla al usarlo en el aire.

Solucion: aqui NO hay teclado. La app te marca una tecla en cada beat del
metronomo; tu la pulsas EN EL AIRE sobre la mesa, en la misma posicion en la que
luego escribiras. La etiqueta la pone la app (sabe que tecla toca en cada beat).
Grabas exactamente en la condicion de uso.

Uso:
    python -m src.record_air --name aire01 --reps 12
Controles:
    ESC / q  -> terminar y guardar
Consejo: coloca las manos como si tuvieras un teclado imaginario y pulsa marcado.
"""
import argparse
import random
import time

import cv2
import numpy as np

import config as C
from src.hand_tracker import HandTracker, draw
from src.camera import open_camera, orient


def build_sequence(reps, seed=0):
    seq = C.TARGET_KEYS * reps
    random.Random(seed).shuffle(seq)
    return seq


def big_text(frame, text, y, scale, color, thick=3):
    (w, _), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    x = (frame.shape[1] - w) // 2
    cv2.putText(frame, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default=time.strftime("aire_%Y%m%d_%H%M%S"))
    ap.add_argument("--reps", type=int, default=5, help="veces que se repite cada tecla")
    args = ap.parse_args()

    seq = build_sequence(args.reps)
    period = 60.0 / C.AIR_BPM
    print(f"[AIR] {len(seq)} beats a {C.AIR_BPM} bpm (~{len(seq)*period/60:.1f} min).")

    tracker = HandTracker()
    cap = open_camera()

    frames_t, frames_f = [], []
    beat_events = []  # (t_beat, key)

    # cuenta atras inicial de 3s
    start = time.perf_counter() + 3.0
    i = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = orient(frame)
            now = time.perf_counter()
            feat, res = tracker.process(frame)
            frames_t.append(now)
            frames_f.append(feat)
            draw(frame, res)

            H = C.FRAME_H
            if now < start:
                big_text(frame, f"PREPARATE {int(start - now) + 1}", H // 2, 2.2, (0, 200, 255))
            elif i < len(seq):
                beat_time = start + i * period
                cur = seq[i]
                label = "ESPACIO" if cur == "space" else cur.upper()
                # cuando llega el beat, registra y avanza
                if now >= beat_time:
                    beat_events.append((beat_time, cur))
                    i += 1
                    flash = True
                else:
                    flash = False
                # barra de tiempo hasta el beat
                frac = max(0.0, min(1.0, 1 - (beat_time - now) / period))
                bw = int(frac * (C.FRAME_W - 120))
                cv2.rectangle(frame, (60, H - 60), (60 + bw, H - 40), (0, 200, 0), -1)
                color = (255, 255, 255) if flash else (0, 220, 255)
                big_text(frame, label, H // 2, 3.0, color, 5)
                nxt = seq[i] if i < len(seq) else "-"
                big_text(frame, f"siguiente: {'_' if nxt=='space' else nxt}", 70, 1.0, (180, 180, 180), 2)
            else:
                big_text(frame, "LISTO - ESC para guardar", H // 2, 1.6, (0, 255, 0))

            cv2.putText(frame, f"beat {i}/{len(seq)}  frames {len(frames_t)}",
                        (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow("AirKeys - grabador guiado (ESC/q)", frame)
            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord("q")):
                break
    except KeyboardInterrupt:
        print("\n[AIR] Ctrl+C -> guardando...")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        tracker.close()

    if not frames_t:
        print("[AIR] Sin frames.")
        return

    ts = np.array(frames_t)
    labels = np.array([C.NONE_LABEL] * len(ts), dtype=object)
    for bt, name in beat_events:
        idx = int(np.argmin(np.abs(ts - bt)))
        if abs(ts[idx] - bt) <= C.LABEL_TOL_S:
            labels[idx] = name
            for s in range(1, C.LABEL_SPREAD + 1):
                for j in (idx - s, idx + s):
                    if 0 <= j < len(labels) and labels[j] == C.NONE_LABEL:
                        labels[j] = name

    feats = np.stack(frames_f).astype(np.float32)
    out = C.DATA_DIR / f"{args.name}.npz"
    np.savez_compressed(out, features=feats, labels=labels.astype("U8"),
                        timestamps=ts, present=np.zeros(len(ts), np.int8))
    n_key = int((labels != C.NONE_LABEL).sum())
    print(f"[AIR] Guardado {out} | {len(ts)} frames | {n_key} con tecla | {len(beat_events)} beats")


if __name__ == "__main__":
    main()
