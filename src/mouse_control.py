"""Raton virtual v2 — desde cero, simple.

Principio: raton RELATIVO puro. Solo importan los DELTAS de la mano entre frames.
Nada de mapear posiciones absolutas ni homografias.

    delta_imagen -> proyectar sobre 2 ejes calibrados -> delta_cursor en px

Ejes: se calibran con 2 gestos (tools/calibrate_mouse):
    u = direccion de imagen de tu gesto "DERECHA"   (con su amplitud amp_x)
    v = direccion de imagen de tu gesto "ALANTE"    (con su amplitud amp_y)
Un swipe igual al de calibracion = cruzar UNA pantalla (por MOUSE_GAIN).

Clutch: mano PLANA y ABIERTA congela el cursor; puño lo reactiva.

Botones (FingerButtons): mano en PUÑO = nada; sacar INDICE = boton IZQUIERDO
mantenido; sacar MEDIO = boton DERECHO mantenido (por extension del dedo).
"""
import atexit
import ctypes
import math
import signal
import time

import cv2
import numpy as np

import config as C

AXES_PATH = C.MODEL_DIR / "mouse_axes.npz"


# ---------------------------------------------------------------- utilidades

class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def cursor_pos():
    p = _POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    return int(p.x), int(p.y)


def screens():
    """(vx, vy, vw, vh, pw, ph): escritorio virtual completo + pantalla principal."""
    u = ctypes.windll.user32
    try:
        u.SetProcessDPIAware()
    except Exception:
        pass
    return (int(u.GetSystemMetrics(76)), int(u.GetSystemMetrics(77)),
            int(u.GetSystemMetrics(78)), int(u.GetSystemMetrics(79)),
            int(u.GetSystemMetrics(0)), int(u.GetSystemMetrics(1)))


def _pick_hand(result, hand_label):
    if not result.hand_landmarks:
        return None
    for lms, handed in zip(result.hand_landmarks, result.handedness):
        if handed[0].category_name == hand_label:
            return lms
    return result.hand_landmarks[0]


_FINGER_CHAINS = [(5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20)]


def _p(lms, i):
    return np.array([lms[i].x, lms[i].y])


def hand_straightness(lms):
    """Media de rectitud de los 4 dedos. Recto -> ~1.0, curvado -> menor.
    Rectitud de un dedo = |MCP->TIP| / (suma de sus 3 falanges)."""
    vals = []
    for a, b, c, d in _FINGER_CHAINS:
        chain = (np.linalg.norm(_p(lms, a) - _p(lms, b)) +
                 np.linalg.norm(_p(lms, b) - _p(lms, c)) +
                 np.linalg.norm(_p(lms, c) - _p(lms, d)))
        straight = np.linalg.norm(_p(lms, a) - _p(lms, d))
        if chain > 1e-6:
            vals.append(straight / chain)
    return float(np.mean(vals)) if vals else 0.0


_CHAIN = {"index": (5, 6, 7, 8), "middle": (9, 10, 11, 12)}


def finger_straight(lms, finger):
    """Rectitud de UN dedo (0..1). Recogido en puño ~0.1, estirado ~1.0."""
    a, b, c, d = _CHAIN[finger]
    chain = (np.linalg.norm(_p(lms, a) - _p(lms, b)) +
             np.linalg.norm(_p(lms, b) - _p(lms, c)) +
             np.linalg.norm(_p(lms, c) - _p(lms, d)))
    return float(np.linalg.norm(_p(lms, a) - _p(lms, d)) / (chain + 1e-6))


def thumb_open(lms):
    """Apertura del pulgar = distancia punta-pulgar(4) -> nudillo-indice(5), en
    tamaños de mano. Pulgar recogido/pegado -> pequeño; abierto hacia fuera -> grande.
    Visible y estable desde arriba; independiente de que el indice se curve."""
    scale = np.linalg.norm(_p(lms, 0) - _p(lms, 9)) + 1e-6
    return float(np.linalg.norm(_p(lms, 4) - _p(lms, 5)) / scale)


class OneEuro:
    """Filtro One Euro (anti-temblor sin lag apreciable)."""

    def __init__(self, min_cutoff=1.0, beta=0.0, dcutoff=1.0):
        self.min_cutoff, self.beta, self.dcutoff = min_cutoff, beta, dcutoff
        self.x_prev = None
        self.dx_prev = 0.0
        self.t_prev = None

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t=None):
        t = time.perf_counter() if t is None else t
        if self.x_prev is None:
            self.x_prev, self.t_prev = x, t
            return x
        dt = max(1e-6, t - self.t_prev)
        dx = (x - self.x_prev) / dt
        a_d = self._alpha(self.dcutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * self.dx_prev
        a = self._alpha(self.min_cutoff + self.beta * abs(dx_hat), dt)
        x_hat = a * x + (1 - a) * self.x_prev
        self.x_prev, self.dx_prev, self.t_prev = x_hat, dx_hat, t
        return x_hat


# ---------------------------------------------------------------- raton

class VirtualMouse:
    def __init__(self):
        self.vx, self.vy, self.vw, self.vh, self.pw, self.ph = screens()
        print(f"[MOUSE] escritorio {self.vw}x{self.vh} en ({self.vx},{self.vy}) | "
              f"principal {self.pw}x{self.ph}")

        # ejes calibrados (direccion + amplitud de tus gestos)
        if AXES_PATH.exists():
            d = np.load(AXES_PATH)
            self.u, self.v = d["u"], d["v"]
            self.amp_x, self.amp_y = float(d["amp_x"]), float(d["amp_y"])
            print(f"[MOUSE] ejes calibrados: derecha={self.u.round(2)} "
                  f"alante={self.v.round(2)}")
        else:
            # Mapeo CENITAL por defecto (camara arriba mirando abajo, imagen ya
            # orientada): mano a la DERECHA = cursor derecha; mano ALANTE (hacia
            # arriba de la imagen) = cursor arriba. Funciona sin calibrar.
            self.u = np.array([1.0, 0.0])
            self.v = np.array([0.0, -1.0])
            self.amp_x = self.amp_y = 0.30
            print("[MOUSE] mapeo CENITAL por defecto (sin calibrar). Si un eje va al "
                  "reves, recalibra o ajusta CAM_ROTATE.")

        # Base de gestos -> matriz inversa. Un delta de imagen d se DESCOMPONE en
        # (cuanto gesto-derecha, cuanto gesto-alante) resolviendo A@steps = d.
        # Esto evita la diagonal cuando los ejes no son perpendiculares en la imagen
        # (proyectar sobre cada eje por separado mezclaba los dos).
        A = np.column_stack([self.u * self.amp_x, self.v * self.amp_y])
        if abs(np.linalg.det(A)) < 1e-8:
            print("[MOUSE] AVISO: ejes casi paralelos. Recalibra (gestos mas distintos).")
            A = np.array([[self.amp_x, 0.0], [0.0, -self.amp_y]])
        self.M = np.linalg.inv(A)

        self.fx = OneEuro(C.MOUSE_MINCUTOFF, C.MOUSE_BETA)
        self.fy = OneEuro(C.MOUSE_MINCUTOFF, C.MOUSE_BETA)
        self.prev = None            # posicion suavizada anterior (imagen)
        self.cur = None             # cursor virtual [x, y] px
        self.frozen = False         # mano plana -> congelado
        self.straight = 0.0
        self.vel = np.zeros(2)      # velocidad suavizada (glide, sin tirones)

    def _smooth(self, d):
        """Anti-glitch + zona muerta + aceleracion + suavizado de velocidad."""
        mag = float(np.linalg.norm(d))
        if mag > C.MOUSE_MAX_STEP:                   # medida absurda del sensor
            d = d * (C.MOUSE_MAX_STEP / mag)
            mag = C.MOUSE_MAX_STEP
        if mag < C.MOUSE_DEADZONE:
            d = np.zeros(2)
        else:
            d = d * (1.0 - C.MOUSE_DEADZONE / mag)   # resta zona muerta sin salto
            # aceleracion de puntero: lento = x1 (precision), rapido = hasta
            # x(1+MOUSE_ACCEL) (alcance). Curva saturante, sin escalones.
            d = d * (1.0 + C.MOUSE_ACCEL * mag / (mag + C.MOUSE_ACCEL_REF))
        self.vel = (1 - C.MOUSE_SMOOTH) * self.vel + C.MOUSE_SMOOTH * d
        return self.vel

    def _update_freeze(self, straight):
        """Mano PLANA (dedos rectos) congela; PUÑO mueve. Histeresis."""
        self.straight = straight
        if not self.frozen and straight > C.MOUSE_FLAT_ENTER:
            self.frozen = True
        elif self.frozen and straight < C.MOUSE_FLAT_EXIT:
            self.frozen = False

    def _apply(self, d):
        """Aplica un delta (unidades de imagen 0..1) al cursor via ejes calibrados."""
        step_x, step_y = self.M @ d                          # descomposicion exacta
        self.cur[0] += float(step_x) * self.pw * C.MOUSE_GAIN
        self.cur[1] -= float(step_y) * self.ph * C.MOUSE_GAIN  # alante = arriba
        self.cur[0] = min(self.vx + self.vw - 1, max(self.vx, self.cur[0]))
        self.cur[1] = min(self.vy + self.vh - 1, max(self.vy, self.cur[1]))

    def update(self, result, t=None, ext_delta=None):
        """Un frame. Devuelve estado o None si no hay mano.

        ext_delta: delta (dx, dy) en unidades de imagen 0..1 medido por un sensor
        externo (flujo optico). Si viene, es LA fuente del movimiento; los landmarks
        solo se usan de fallback cuando el sensor no da medida.
        """
        lms = _pick_hand(result, C.MOUSE_HAND)
        if lms is None:
            self.prev = None
            return None

        p = lms[C.MOUSE_LANDMARK]
        sx = self.fx(float(p.x), t)
        sy = self.fy(float(p.y), t)
        self._update_freeze(hand_straightness(lms))

        if self.cur is None:
            cx, cy = cursor_pos()
            self.cur = [float(cx), float(cy)]

        if self.frozen:
            self.prev = None                     # mano plana: congelado
            self.vel[:] = 0                      # sin inercia al reenganchar
        elif ext_delta is not None:
            self._apply(self._smooth(np.array(ext_delta, float)))   # flujo suavizado
            self.prev = (sx, sy)
        elif self.prev is not None:
            self._apply(self._smooth(np.array([sx - self.prev[0], sy - self.prev[1]])))
            self.prev = (sx, sy)
        else:
            self.prev = (sx, sy)                 # primer frame tras reenganche
            self.vel[:] = 0

        return {"sx": int(self.cur[0]), "sy": int(self.cur[1]),
                "frozen": self.frozen, "straight": self.straight,
                "nx": (self.cur[0] - self.vx) / self.vw,
                "ny": (self.cur[1] - self.vy) / self.vh}


# landmarks para la caja/mascara: muñeca + 4 dedos largos (SIN pulgar 1..4)
_BBOX_LMS = [0] + list(range(5, 21))


def hand_mask(result, frame_w, frame_h, dilate_px=14):
    """Mascara uint8 con la SILUETA de la mano (hull de landmarks, sin pulgar).
    Para el flujo optico: solo se rastrea piel; el fondo (mesa) queda fuera y no
    contamina la mediana del movimiento."""
    lms = _pick_hand(result, C.MOUSE_HAND)
    if lms is None:
        return None
    pts = np.array([[lms[i].x * frame_w, lms[i].y * frame_h] for i in _BBOX_LMS],
                   np.int32)
    hull = cv2.convexHull(pts)
    mask = np.zeros((frame_h, frame_w), np.uint8)
    cv2.fillConvexPoly(mask, hull, 255)
    if dilate_px:
        k = np.ones((dilate_px, dilate_px), np.uint8)
        mask = cv2.dilate(mask, k)
    return mask


def hand_bbox(result, frame_w, frame_h, margin=0.15):
    """Caja (x0,y0,x1,y1) en px de la mano del raton, o None. Ignora el pulgar."""
    lms = _pick_hand(result, C.MOUSE_HAND)
    if lms is None:
        return None
    xs = [lms[i].x for i in _BBOX_LMS]
    ys = [lms[i].y for i in _BBOX_LMS]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    x0 = max(0, int((min(xs) - margin * w) * frame_w))
    x1 = min(frame_w - 1, int((max(xs) + margin * w) * frame_w))
    y0 = max(0, int((min(ys) - margin * h) * frame_h))
    y1 = min(frame_h - 1, int((max(ys) + margin * h) * frame_h))
    if x1 - x0 < 20 or y1 - y0 < 20:
        return None
    return x0, y0, x1, y1


class FingerButtons:
    """Botones para camara CENITAL (mantenidos):
      IZQUIERDO = CURVAR el indice (su rectitud cae por debajo de MOUSE_LEFT_CURL).
      DERECHO   = ABRIR el pulgar (thumb_open sube por encima de MOUSE_THUMB_OPEN).
    Devuelve estado + flancos (press/release). Mientras 'frozen' (mano plana) no se
    pulsa nada; tras volver de plana hay un cooldown para no soltar clicks falsos."""

    def __init__(self):
        self.left = False
        self.right = False
        self.cooldown = 0

    def update(self, lms, frozen):
        idx = thumb = 0.0
        if lms is None or frozen:
            nl = nr = False
            self.cooldown = C.MOUSE_BTN_COOLDOWN
        else:
            idx = finger_straight(lms, "index")    # ~1.0 recto, baja al curvar
            thumb = thumb_open(lms)                 # sube al abrir el pulgar
            if self.cooldown > 0:
                self.cooldown -= 1
                nl = nr = False
            else:
                # IZQ: se activa cuando el indice CAE por debajo de CURL; suelta al
                # volver por encima de RELEASE (histeresis con umbrales invertidos).
                if not self.left:
                    nl = idx < C.MOUSE_LEFT_CURL
                else:
                    nl = idx < C.MOUSE_LEFT_RELEASE
                # DER: pulgar abierto por encima de OPEN; suelta por debajo de CLOSE.
                if not self.right:
                    nr = thumb > C.MOUSE_THUMB_OPEN
                else:
                    nr = thumb > C.MOUSE_THUMB_CLOSE
        ev = {"left": nl, "right": nr,
              "press_left": nl and not self.left,
              "release_left": self.left and not nl,
              "press_right": nr and not self.right,
              "release_right": self.right and not nr,
              "idx": idx, "thumb": thumb}
        self.left, self.right = nl, nr
        return ev


class MouseOut:
    """Salida real del raton (pynput) con SEGURIDAD anti-boton-pegado.
    Registra atexit + señales para SOLTAR los botones pase lo que pase al salir,
    para no dejar el raton del sistema con un boton apretado."""

    def __init__(self, enabled):
        self.ctrl = None
        self.left = self.right = False
        if not enabled:
            return
        from pynput.mouse import Controller, Button
        self.ctrl = Controller()
        self.Button = Button
        atexit.register(self.release_all)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._on_signal)
            except (ValueError, OSError):
                pass  # no siempre se puede en todos los hilos/plataformas

    def _on_signal(self, *_):
        self.release_all()
        raise KeyboardInterrupt

    def move(self, x, y):
        if self.ctrl:
            self.ctrl.position = (x, y)

    def apply(self, ev):
        if not self.ctrl:
            return
        if ev["press_left"]:
            self.ctrl.press(self.Button.left); self.left = True
        if ev["release_left"]:
            self.ctrl.release(self.Button.left); self.left = False
        if ev["press_right"]:
            self.ctrl.press(self.Button.right); self.right = True
        if ev["release_right"]:
            self.ctrl.release(self.Button.right); self.right = False

    def release_all(self):
        if not self.ctrl:
            return
        try:
            if self.left:
                self.ctrl.release(self.Button.left); self.left = False
            if self.right:
                self.ctrl.release(self.Button.right); self.right = False
        except Exception:
            pass
