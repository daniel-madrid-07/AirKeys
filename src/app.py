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


class GeoKeyboardRunner:
    """Teclado geometrico SIN modelo (src/keyboard_geo.py): calibracion home-row +
    strikes por velocidad + tecla por posicion. Funciona sin entrenar."""

    def __init__(self, type_real):
        from src.keyboard_geo import GeoKeyboard
        self.geo = GeoKeyboard()
        self.recent = deque(maxlen=16)
        self.last = {}
        self.kb = None
        if type_real:
            from pynput.keyboard import Controller
            self.kb = Controller()

    @property
    def state(self):
        return "ready" if self.geo.calibrated else "calibrating"

    def tick(self, feat, now):
        for key in self.geo.update(feat, now):
            if now - self.last.get(key, -1e9) < C.DEBOUNCE_S:
                continue
            self.last[key] = now
            ch = " " if key == "space" else key
            self.recent.append(ch)
            if self.kb:
                self.kb.type(ch)

    def close(self):
        pass


class KeyboardRunner:
    """Teclado con MODELO entrenado (taps + experto por dedo).
    hand_filter='Left'/'Right' limita a una mano (gaming)."""

    state = "ready"

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
                "  python airkeys.py record\n"
                "  python airkeys.py train")
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
        self.keyboard = self._make_keyboard(type_real) if mode == "keyboard" else None
        self.gaming = None
        if mode == "gaming":
            from src.gaming import KeyOut, HeldFingerKeys
            self.gaming = HeldFingerKeys(KeyOut(type_real))

    @staticmethod
    def _make_keyboard(type_real):
        """Elige el decodificador de teclado segun KB_DECODER:
        geo (sin entrenar, por defecto) o model (GRU entrenado)."""
        dec = getattr(C, "KB_DECODER", "auto")
        model_path = C.MODEL_DIR / "fingers.pt"
        if dec == "model" or (dec == "auto" and model_path.exists()):
            try:
                return KeyboardRunner(type_real)
            except (RuntimeError, FileNotFoundError) as e:
                if dec == "model":
                    raise
                print(f"[KB] modelo no disponible ({e}); uso el decodificador geometrico.")
        return GeoKeyboardRunner(type_real)

    def process(self, frame, now=None):
        """Devuelve (frame_con_landmarks, info). info es un dict con el estado para
        que lo pinte la interfaz (HTML) o el modo consola. NO escribe texto sobre el
        frame: solo dibuja los landmarks."""
        now = time.perf_counter() if now is None else now
        feat, res = self.tracker.process(frame)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if self.mouse else None
        draw(frame, res)

        info = {"mode": self.mode, "status": self.mode, "frozen": False,
                "left": False, "right": False, "idx": 0.0, "thumb": 0.0,
                "keys": "", "hand": bool(res.hand_landmarks)}
        if self.mouse:
            minfo, ev = self.mouse.tick(frame, gray, res, now)
            if minfo:
                info["frozen"] = minfo["frozen"]
                info["left"], info["right"] = ev["left"], ev["right"]
                info["idx"], info["thumb"] = ev["idx"], ev["thumb"]
                info["status"] = "congelado" if minfo["frozen"] else "raton"
        if self.keyboard:
            self.keyboard.tick(feat, now)
            info["keys"] = "".join(self.keyboard.recent)
            info["kb"] = self.keyboard.state
        if self.gaming:
            held = self.gaming.update(feat)
            info["keys"] = " ".join(self.gaming.keys[f] for f, d in held.items() if d).upper()
        return frame, info

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
            frame, info = engine.process(orient(frame))
            txt = info["status"]
            if info["left"]:
                txt += " IZQ"
            if info["right"]:
                txt += " DER"
            cv2.putText(frame, txt, (12, 40), cv2.FONT_HERSHEY_SIMPLEX,
                        0.9, (0, 255, 0), 2)
            if info["keys"]:
                cv2.putText(frame, info["keys"], (12, frame.shape[0] - 24),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
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
