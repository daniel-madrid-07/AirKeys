"""Motor unificado de AirKeys: un solo bucle de camara, 3 modos.

    mouse    -> raton (mano derecha): mover + clicks
    keyboard -> teclado invisible (taps -> teclas)
    gaming   -> las dos a la vez (mano derecha raton, mano izquierda teclado)

Reutiliza los subsistemas ya probados (VirtualMouse, FingerButtons, FlowSensor,
TapDetector, modelo multi-experto). Un solo procesado de MediaPipe por frame.
"""
import time
from collections import deque

import cv2
import numpy as np

import config as C
from src.hand_tracker import HandTracker, draw
from src.camera import open_camera, orient
from src.mouse_control import (VirtualMouse, FingerButtons, MouseOut,
                               hand_mask, _pick_hand)
from src.flow_sensor import FlowSensor

MODES = ("mouse", "keyboard", "gaming")


class MouseRunner:
    def __init__(self, type_real):
        self.mouse = VirtualMouse()
        self.buttons = FingerButtons()
        self.flow = FlowSensor()
        self.out = MouseOut(type_real)

    def tick(self, frame, gray, res, now):
        h, w = frame.shape[:2]
        mask = hand_mask(res, w, h)
        d = self.flow.delta(gray, mask)
        ext = (d[0] / w, d[1] / h) if d is not None else None
        info = self.mouse.update(res, now, ext_delta=ext)
        ev = self.buttons.update(_pick_hand(res, C.MOUSE_HAND),
                                 info["frozen"] if info else True)
        self.out.apply(ev)
        if info and not info["frozen"]:
            self.out.move(info["sx"], info["sy"])
        return info, ev

    def close(self):
        self.out.release_all()


class KeyboardRunner:
    """Detecta taps y teclea. hand_filter='Left'/'Right' limita a una mano (gaming)."""

    def __init__(self, type_real, hand_filter=None):
        try:
            import torch  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "El modo teclado necesita PyTorch, que no viene en el ejecutable.\n"
                "Usa la instalacion desde codigo (install.bat) para el teclado.\n"
                "El raton y el gaming funcionan sin torch.")
        from src.model import load_fingers
        from src.tap import TapDetector
        from src.fingers import _hand_slot
        model_path = C.MODEL_DIR / "fingers.pt"
        if not model_path.exists():
            raise FileNotFoundError(
                "No hay modelo de teclado (models/fingers.pt). Graba y entrena:\n"
                "  python -m src.record_air --name aire01\n"
                "  python -m src.train")
        self.model, self.classes = load_fingers(model_path)
        self.sf2e = {}
        for i, m in enumerate(self.model.experts_meta):
            if hand_filter and m["hand"] != hand_filter:
                continue
            self.sf2e[(_hand_slot(m["hand"]), m["finger"])] = i
        self.det = TapDetector(self.sf2e.keys())
        self.buf = deque(maxlen=C.WINDOW * 3)
        self.last = {}
        self.recent = deque(maxlen=16)
        self.kb = None
        if type_real:
            from pynput.keyboard import Controller
            self.kb = Controller()

    def _classify(self, slot, finger, peak_t):
        import torch
        ei = self.sf2e.get((slot, finger))
        if ei is None or len(self.buf) < C.WINDOW:
            return None, 0.0
        times = np.array([bt for bt, _ in self.buf])
        idx = int(np.argmin(np.abs(times - peak_t)))
        start = max(0, min(idx - C.CENTER, len(self.buf) - C.WINDOW))
        win = np.stack([f for _, f in list(self.buf)[start:start + C.WINDOW]]).astype(np.float32)
        with torch.no_grad():
            prob = torch.softmax(self.model.expert_logits(ei, torch.from_numpy(win[None])), 1)[0]
        li = int(prob.argmax())
        if li == 0:
            return None, float(prob[li])
        return self.model.experts_meta[ei]["local_classes"][li], float(prob[li])

    def tick(self, feat, now):
        self.buf.append((now, feat))
        for slot, finger, peak_t, amp in self.det.update(feat, now):
            key, conf = self._classify(slot, finger, peak_t)
            if key and conf >= C.KEY_CONF_MIN and now - self.last.get(key, -1e9) >= C.DEBOUNCE_S:
                self.last[key] = now
                ch = " " if key == "space" else key
                self.recent.append(ch)
                if self.kb:
                    self.kb.type(ch)

    def close(self):
        pass


class Engine:
    """Procesa UN frame y devuelve (frame_anotado, texto_estado). Comparten esto el
    modo consola (cv2.imshow) y la GUI (pinta el frame dentro de la ventana)."""

    def __init__(self, mode, type_real=False):
        assert mode in MODES, f"modo desconocido: {mode}"
        self.mode = mode
        self.tracker = HandTracker()
        self.mouse = MouseRunner(type_real) if mode in ("mouse", "gaming") else None
        self.keyboard = KeyboardRunner(type_real) if mode == "keyboard" else None
        self.gaming = None
        if mode == "gaming":
            from src.gaming import KeyOut, HeldFingerKeys
            self.gaming = HeldFingerKeys(KeyOut(type_real))

    def process(self, frame, now=None):
        now = time.perf_counter() if now is None else now
        h = frame.shape[0]
        feat, res = self.tracker.process(frame)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if self.mouse else None
        draw(frame, res)

        status = self.mode
        if self.mouse:
            info, ev = self.mouse.tick(frame, gray, res, now)
            if info:
                status = "PLANA (congelado)" if info["frozen"] else "raton"
                if ev["left"]:
                    status += " · IZQ"
                if ev["right"]:
                    status += " · DER"
                # valores en vivo para afinar (i=curvatura indice, t=pulgar abierto)
                cv2.putText(frame, f"i:{ev['idx']:.2f}  t:{ev['thumb']:.2f}",
                            (12, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
        if self.keyboard:
            self.keyboard.tick(feat, now)
            if self.keyboard.recent:
                cv2.putText(frame, "".join(self.keyboard.recent), (12, h - 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
        if self.gaming:
            held = self.gaming.update(feat)
            pressed = [self.gaming.keys[f] for f, d in held.items() if d]
            if pressed:
                cv2.putText(frame, " ".join(pressed).upper(), (12, h - 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)

        cv2.putText(frame, status, (12, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, (0, 255, 0), 2)
        return frame, status

    def close(self):
        if self.mouse:
            self.mouse.close()
        if self.keyboard:
            self.keyboard.close()
        if self.gaming:
            self.gaming.close()
        self.tracker.close()


def run(mode, type_real=False):
    """Modo consola: bucle propio con ventana OpenCV. (La GUI usa Engine aparte.)"""
    engine = Engine(mode, type_real)
    cap = open_camera()
    title = f"AirKeys [{mode}]  ESC/q para salir"
    print(f"[APP] modo {mode} | type_real={type_real}")
    if not type_real:
        print("[APP] MODO PRUEBA: no se envian teclas/clicks reales. Añade --real.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame, _ = engine.process(orient(frame))
            cv2.imshow(title, frame)
            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord("q")):
                break
            if cv2.getWindowProperty(title, cv2.WND_PROP_VISIBLE) < 1:
                break
    except KeyboardInterrupt:
        pass
    finally:
        engine.close()
        cap.release()
        cv2.destroyAllWindows()
