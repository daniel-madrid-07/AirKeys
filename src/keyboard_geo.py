"""Teclado GEOMETRICO sin entrenar: calibracion home-row + strike por velocidad.

La profundidad de una pulsacion NO se puede medir con una webcam (el movimiento va
casi a lo largo del eje optico). Este modulo la evita con dos ideas:

1) CALIBRACION HOME (idea del teclado de superficie de Meta Quest): cuando las dos
   manos reposan quietas sobre la mesa (postura ASDF / JKLÑ), se captura por dedo su
   posicion de reposo relativa a la muñeca y el PITCH (separacion media entre puntas
   de dedos). Reposar = tocar la mesa, asi que eso ancla el plano de la superficie
   en unidades de imagen SIN saber la profundidad. Se recalibra sola cada vez que
   el usuario vuelve a apoyar las manos.

2) STRIKE POR REVERSION DE VELOCIDAD: una pulsacion real es bajada rapida de la
   punta -> parada seca (la mesa la frena) -> subida. Esa firma temporal (impulso
   de velocidad + cruce por cero) es independiente del angulo de camara y de la
   tecla objetivo; no requiere umbral de profundidad. La señal es la misma s de
   tap.py (punta vs nudillo, normalizada por tamaño de mano), pero la decision es
   sobre su DERIVADA, no sobre su nivel.

La tecla se decide por GEOMETRIA: en el contacto la punta esta sobre la superficie
(el mismo plano que en la calibracion), asi que su posicion relativa a la muñeca,
comparada con la rejilla QWERTY anclada al reposo, da la tecla. Cada dedo solo
compite por SUS columnas de mecanografia; los pulgares son espacio.
"""
import config as C
from src.fingers import _hand_slot
from src.tap import TIP, MCP, abs_xy, present, hand_scale

# rejilla QWERTY: tecla -> (fila, columna). fila 0 = superior (QWERTY),
# 1 = central/home (ASDF...), 2 = inferior (ZXCV...)
KEY_GRID = {
    "q": (0, 0), "w": (0, 1), "e": (0, 2), "r": (0, 3), "t": (0, 4),
    "y": (0, 5), "u": (0, 6), "i": (0, 7), "o": (0, 8), "p": (0, 9),
    "a": (1, 0), "s": (1, 1), "d": (1, 2), "f": (1, 3), "g": (1, 4),
    "h": (1, 5), "j": (1, 6), "k": (1, 7), "l": (1, 8),
    "z": (2, 0), "x": (2, 1), "c": (2, 2), "v": (2, 3), "b": (2, 4),
    "n": (2, 5), "m": (2, 6),
}
HOME_ROW = 1

# columnas de cada dedo (mecanografia estandar) y su columna home
FINGER_COLS = {
    ("Left", "pinky"): [0], ("Left", "ring"): [1], ("Left", "middle"): [2],
    ("Left", "index"): [3, 4],
    ("Right", "index"): [5, 6], ("Right", "middle"): [7],
    ("Right", "ring"): [8], ("Right", "pinky"): [9],
}
HOME_COL = {
    ("Left", "pinky"): 0, ("Left", "ring"): 1, ("Left", "middle"): 2,
    ("Left", "index"): 3,
    ("Right", "index"): 6, ("Right", "middle"): 7,
    ("Right", "ring"): 8, ("Right", "pinky"): 9,
}
_FINGERS = ["index", "middle", "ring", "pinky"]        # dedos de letras
_ALL = _FINGERS + ["thumb"]                            # + espacio


def _candidates(hand, finger):
    """Teclas (de TARGET_KEYS) que puede pulsar ese dedo."""
    if finger == "thumb":
        return ["space"] if "space" in C.TARGET_KEYS else []
    cols = FINGER_COLS[(hand, finger)]
    return [k for k, (r, c) in KEY_GRID.items()
            if c in cols and k in C.TARGET_KEYS]


def _signal(feat, slot, finger):
    """s = posicion vertical de la punta respecto a su nudillo, en tamaños de mano
    (misma señal que tap.py). Solo se usa su DERIVADA y desplazamientos relativos."""
    ty = abs_xy(feat, slot, TIP[finger])[1]
    my = abs_xy(feat, slot, MCP[finger])[1]
    return C.TAP_SIGN * (ty - my) / hand_scale(feat, slot)


class _FingerFSM:
    """Detector de strike de UN dedo sobre la derivada de s."""
    IDLE, DESCENT, COOLDOWN = 0, 1, 2

    def __init__(self):
        self.state = self.IDLE
        self.s_prev = None
        self.v = 0.0            # derivada suavizada de s (1/seg)
        self.t_prev = None
        self.t_start = 0.0
        self.t_fire = -1e9
        self.hist = []          # (t, s) recientes: el minimo marca el inicio real
                                # de la bajada (hover), sin depender del lag del EMA

    def update(self, s, t):
        """Devuelve True en el frame de CONTACTO."""
        if self.s_prev is None:
            self.s_prev, self.t_prev = s, t
            self.hist.append((t, s))
            return False
        dt = max(1e-3, t - self.t_prev)
        v_raw = (s - self.s_prev) / dt
        self.v = 0.5 * self.v + 0.5 * v_raw
        self.s_prev, self.t_prev = s, t
        self.hist.append((t, s))
        while self.hist and t - self.hist[0][0] > C.KB_STRIKE_MAX_S:
            self.hist.pop(0)

        if self.state == self.IDLE:
            if self.v > C.KB_VEL_ENTER:
                self.state = self.DESCENT
                self.t_start = t
        elif self.state == self.DESCENT:
            if t - self.t_start > C.KB_STRIKE_MAX_S:
                self.state = self.IDLE              # bajada demasiado larga: no es tap
            elif self.v < 0.25 * C.KB_VEL_ENTER:    # frenazo: la mesa para el dedo
                drop = s - min(sv for _, sv in self.hist)
                if drop >= C.KB_MIN_DROP:           # hubo excursion real -> CONTACTO
                    self.state = self.COOLDOWN
                    self.t_fire = t
                    return True
                self.state = self.IDLE              # amago sin recorrido: ignorar
        elif self.state == self.COOLDOWN:
            if t - self.t_fire > C.KB_REFRACTORY_S and self.v < 0.5 * C.KB_VEL_ENTER:
                self.state = self.IDLE
        return False

    def reset(self):
        self.state = self.IDLE
        self.s_prev = None
        self.v = 0.0
        self.hist = []


class _HandCalib:
    """Calibracion home de UNA mano: se captura cuando la mano lleva un rato
    completamente quieta (reposando = tocando la mesa)."""

    def __init__(self, hand):
        self.hand = hand
        self.ok = False
        self.home_rel = {}      # finger -> (x, y) relativo a muñeca, en tamaños de mano
        self.pitch = 0.0        # separacion media entre puntas adyacentes (id. unidades)
        self.still_since = None

    def tips_rel(self, feat, slot):
        wx, wy = abs_xy(feat, slot, 0)
        sc = hand_scale(feat, slot)
        out = {}
        for f in _ALL:
            tx, ty = abs_xy(feat, slot, TIP[f])
            out[f] = ((tx - wx) / sc, (ty - wy) / sc)
        return out

    def try_capture(self, feat, slot, fsms, wrist_v, t):
        quiet = (wrist_v < C.KB_STILL_EPS and
                 all(abs(fsms[f].v) < C.KB_STILL_EPS and fsms[f].state == _FingerFSM.IDLE
                     for f in _ALL))
        if not quiet:
            self.still_since = None
            return
        if self.still_since is None:
            self.still_since = t
            return
        if t - self.still_since < C.KB_CALIB_STILL_S:
            return
        rel = self.tips_rel(feat, slot)
        xs = sorted(rel[f][0] for f in _FINGERS)
        gaps = [abs(xs[i + 1] - xs[i]) for i in range(len(xs) - 1)]
        pitch = sum(gaps) / len(gaps) if gaps else 0.0
        if pitch < 0.05:                    # dedos juntos/mano de canto: no vale
            return
        self.home_rel = rel
        self.pitch = pitch
        self.ok = True
        self.still_since = t                # sigue refrescando mientras repose


class GeoKeyboard:
    """Pipeline completo: calibracion + strikes + decodificacion geometrica.

    update(feat, t) -> lista de teclas ('a'..'z', 'space') pulsadas en este frame.
    """

    def __init__(self):
        self.hands = {}         # hand -> (slot, _HandCalib, {finger: _FingerFSM})
        for hand in ("Left", "Right"):
            slot = _hand_slot(hand)
            self.hands[hand] = (slot, _HandCalib(hand),
                                {f: _FingerFSM() for f in _ALL})
        self.wrist_prev = {}    # slot -> (x, y, t)

    @property
    def calibrated(self):
        return any(cal.ok for _, cal, _ in self.hands.values())

    def _wrist_speed(self, feat, slot, t):
        wx, wy = abs_xy(feat, slot, 0)
        sc = hand_scale(feat, slot)
        prev = self.wrist_prev.get(slot)
        self.wrist_prev[slot] = (wx, wy, t)
        if prev is None:
            return 0.0
        dt = max(1e-3, t - prev[2])
        return (((wx - prev[0]) ** 2 + (wy - prev[1]) ** 2) ** 0.5) / sc / dt

    def _decode(self, feat, slot, hand, finger, cal):
        """Tecla mas cercana a la punta EN EL CONTACTO (esta sobre la superficie)."""
        cands = _candidates(hand, finger)
        if not cands:
            return None
        if finger == "thumb":
            return "space"
        wx, wy = abs_xy(feat, slot, 0)
        sc = hand_scale(feat, slot)
        tx, ty = abs_xy(feat, slot, TIP[finger])
        rel = ((tx - wx) / sc, (ty - wy) / sc)
        hx, hy = cal.home_rel[finger]
        dx, dy = rel[0] - hx, rel[1] - hy
        # sentido de la fila superior: los dedos apuntan "arriba" en la imagen
        # (GUIDE: rotar la camara hasta que salga natural), asi que la fila 0
        # (QWERTY) queda a MENOR y de imagen que la home: dy negativo.
        col0 = HOME_COL[(hand, finger)]
        best, best_d2 = None, None
        for k in cands:
            row, col = KEY_GRID[k]
            kx = (col - col0) * cal.pitch
            ky = (row - HOME_ROW) * cal.pitch * C.KB_ROW_SCALE
            d2 = (dx - kx) ** 2 + (dy - ky) ** 2
            if best_d2 is None or d2 < best_d2:
                best, best_d2 = k, d2
        lim = (C.KB_MAX_KEY_DIST * cal.pitch) ** 2
        return best if best_d2 is not None and best_d2 <= lim else None

    def update(self, feat, t):
        typed = []
        for hand, (slot, cal, fsms) in self.hands.items():
            if not present(feat, slot):
                for f in _ALL:
                    fsms[f].reset()
                cal.still_since = None
                self.wrist_prev.pop(slot, None)
                continue
            wrist_v = self._wrist_speed(feat, slot, t)
            for f in _ALL:
                s = _signal(feat, slot, f)
                fired = fsms[f].update(s, t)
                # mano desplazandose (recolocacion): no es una pulsacion
                if fired and wrist_v < C.KB_WRIST_MAX_V and cal.ok:
                    key = self._decode(feat, slot, hand, f, cal)
                    if key:
                        typed.append(key)
            cal.try_capture(feat, slot, fsms, wrist_v, t)
        return typed
