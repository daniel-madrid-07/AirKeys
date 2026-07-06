"""Inferencia en vivo con deteccion de TAP (dos etapas).

    python -m src.infer            # solo muestra lo que detecta (no teclea)
    python -m src.infer --type     # ADEMAS teclea de verdad en la app activa

Etapa 1: TapDetector decide CUANDO y con QUE dedo hay una pulsacion real.
Etapa 2: solo en ese instante corre el experto de ESE dedo y elige la tecla.
Si no hay tap -> no se escribe nada (adios letras fantasma).
"""
import argparse
import time
from collections import deque

import cv2
import numpy as np
import torch

import config as C
from src.hand_tracker import HandTracker, draw
from src.camera import open_camera, orient
from src.model import load_fingers
from src.fingers import _hand_slot
from src.tap import TapDetector


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", action="store_true", help="emitir teclas reales (pynput)")
    ap.add_argument("--model", default=str(C.MODEL_DIR / "fingers.pt"))
    args = ap.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, classes = load_fingers(args.model, device)
    print(f"[INFER] modelo multi-experto ({len(classes)} clases) en {device}")

    # (slot, finger) -> indice de experto
    slot_finger_to_expert = {}
    for i, m in enumerate(model.experts_meta):
        slot_finger_to_expert[(_hand_slot(m["hand"]), m["finger"])] = i
    detector = TapDetector(slot_finger_to_expert.keys())

    controller = None
    if args.type:
        from pynput.keyboard import Controller
        controller = Controller()
        print("[INFER] --type ACTIVO: se enviaran pulsaciones reales.")

    tracker = HandTracker()
    cap = open_camera()

    buf = deque(maxlen=C.WINDOW * 3)   # (t, feat)
    last_emit = {}
    recent = deque(maxlen=12)
    n_taps = 0

    def classify_tap(slot, finger, peak_t):
        ei = slot_finger_to_expert.get((slot, finger))
        if ei is None or len(buf) < C.WINDOW:
            return None, 0.0
        times = np.array([bt for bt, _ in buf])
        idx = int(np.argmin(np.abs(times - peak_t)))
        start = max(0, min(idx - C.CENTER, len(buf) - C.WINDOW))
        win = np.stack([f for _, f in list(buf)[start:start + C.WINDOW]]).astype(np.float32)
        x = torch.from_numpy(win[None]).to(device)
        with torch.no_grad():
            prob = torch.softmax(model.expert_logits(ei, x), 1)[0]
        li = int(prob.argmax())
        m = model.experts_meta[ei]
        if li == 0:                       # el experto dice 'ninguna'
            return None, float(prob[li])
        return m["local_classes"][li], float(prob[li])

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = orient(frame)
            now = time.perf_counter()
            feat, res = tracker.process(frame)
            buf.append((now, feat))
            draw(frame, res)

            for slot, finger, peak_t, amp in detector.update(feat, now):
                n_taps += 1
                key, conf = classify_tap(slot, finger, peak_t)
                if key and conf >= C.KEY_CONF_MIN:
                    if now - last_emit.get(key, -1e9) >= C.DEBOUNCE_S:
                        last_emit[key] = now
                        ch = " " if key == "space" else key
                        recent.append(ch)
                        if controller:
                            controller.type(ch)

            cv2.putText(frame, f"taps:{n_taps}", (12, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 220, 255), 2)
            cv2.putText(frame, "".join(recent), (12, C.FRAME_H - 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2)
            cv2.imshow("AirKeys - infer (ESC o q para salir)", frame)
            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord("q")):
                break
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        tracker.close()


if __name__ == "__main__":
    main()
