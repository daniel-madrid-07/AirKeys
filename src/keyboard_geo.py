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
import json
from statistics import median

import config as C
from src.fingers import _hand_slot, FINGER_MAP
from src.tap import TIP, MCP, abs_xy, present, hand_scale

# calibracion por voz (tools/calibrate_keys): muestras crudas y mapa ajustado
SAMPLES_PATH = C.DATA_DIR / "kb_calib.json"
MAP_PATH = C.MODEL_DIR / "kb_map.json"

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

_FINGERS = ["index", "middle", "ring", "pinky"]        # dedos de letras
_ALL = _FINGERS + ["thumb"]                            # + espacio

# El reparto tecla->dedo es el DEL USUARIO (src/fingers.py FINGER_MAP): solo el
# dedo dueño de una tecla compite por ella. Ej.: indice derecho = N M J U K I;
# indice izquierdo cubre D B R F T G X C V Y H (estilo personal, cruza columnas).
_cands_cache = {}
_homecol_cache = {}


def _candidates(hand, finger):
    """Teclas (de TARGET_KEYS) que puede pulsar ese dedo segun FINGER_MAP."""
    key = (hand, finger)
    if key in _cands_cache:
        return _cands_cache[key]
    if finger == "thumb":
        out = ["space"] if "space" in C.TARGET_KEYS else []
    else:
        out = [k for k in C.TARGET_KEYS
               if FINGER_MAP.get(k) == (hand, finger) and k in KEY_GRID]
    _cands_cache[key] = out
    return out


def _home_col(hand, finger):
    """Columna de reposo del dedo: mediana de las columnas de sus teclas de la
    fila home (o de todas si no tiene ninguna en home)."""
    key = (hand, finger)
    if key in _homecol_cache:
        return _homecol_cache[key]
    ks = _candidates(hand, finger)
    cols = sorted(KEY_GRID[k][1] for k in ks if KEY_GRID[k][0] == HOME_ROW)
    if not cols:
        cols = sorted(KEY_GRID[k][1] for k in ks) if ks else []
    # mediana BAJA: con {J(6), K(7)} el reposo natural del indice es J
    out = cols[(len(cols) - 1) // 2] if cols else None
    _homecol_cache[key] = out
    return out


def fit_map(samples):
    """Ajusta el mapa de teclas desde muestras {key, hand, finger, ux, uy}
    (ux/uy = posicion del contacto relativa al home, en unidades de PITCH).
    Robusto: centro = mediana, dispersion = MAD escalado (con suelo)."""
    by = {}
    for s in samples:
        by.setdefault(s["key"], []).append(s)
    out = {}
    for key, ss in by.items():
        uxs = [s["ux"] for s in ss]
        uys = [s["uy"] for s in ss]
        cx, cy = median(uxs), median(uys)
        sx = max(0.18, median([abs(x - cx) for x in uxs]) * 1.4826)
        sy = max(0.18, median([abs(y - cy) for y in uys]) * 1.4826)
        hf = {}
        for s in ss:
            k = (s["hand"], s["finger"])
            hf[k] = hf.get(k, 0) + 1
        hand, finger = max(hf, key=hf.get)
        out[key] = {"hand": hand, "finger": finger, "ux": cx, "uy": cy,
                    "sx": sx, "sy": sy, "n": len(ss)}
    return out


def save_map(kmap):
    MAP_PATH.write_text(json.dumps(kmap, indent=1), encoding="utf-8")


def load_map():
    if not MAP_PATH.exists():
        return None
    try:
        m = json.loads(MAP_PATH.read_text(encoding="utf-8"))
        return m if isinstance(m, dict) and m else None
    except Exception:
        return None


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

    def __init__(self, use_map=True):
        self.hands = {}         # hand -> (slot, _HandCalib, {finger: _FingerFSM})
        for hand in ("Left", "Right"):
            slot = _hand_slot(hand)
            self.hands[hand] = (slot, _HandCalib(hand),
                                {f: _FingerFSM() for f in _ALL})
        self.wrist_prev = {}    # slot -> (x, y, t)
        # mapa calibrado por voz (si existe): posiciones REALES de tus teclas
        self.kmap = load_map() if use_map else None

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

    def _contact_uxy(self, feat, slot, finger, cal):
        """Posicion de la punta en el contacto, relativa a su home y en unidades
        de PITCH (invariante a mano/camara/distancia)."""
        wx, wy = abs_xy(feat, slot, 0)
        sc = hand_scale(feat, slot)
        tx, ty = abs_xy(feat, slot, TIP[finger])
        hx, hy = cal.home_rel[finger]
        return (((tx - wx) / sc - hx) / cal.pitch,
                ((ty - wy) / sc - hy) / cal.pitch)

    def _decode(self, hand, finger, ux, uy):
        """Tecla desde la posicion del contacto. Si hay mapa calibrado por voz,
        se usan TUS posiciones reales; si no, la rejilla QWERTY ideal."""
        if self.kmap:
            cands = [(k, m) for k, m in self.kmap.items()
                     if m["hand"] == hand and m["finger"] == finger]
            if cands:
                best, best_d2 = None, None
                for k, m in cands:
                    d2 = (((ux - m["ux"]) / m["sx"]) ** 2 +
                          ((uy - m["uy"]) / m["sy"]) ** 2)
                    if best_d2 is None or d2 < best_d2:
                        best, best_d2 = k, d2
                return best if best_d2 <= C.KB_MAX_MAHA ** 2 else None
            # dedo sin muestras en el mapa -> cae a la rejilla ideal
        cands = _candidates(hand, finger)
        if not cands:
            return None
        if finger == "thumb":
            return "space"
        # sentido de la fila superior: los dedos apuntan "arriba" en la imagen
        # (GUIDE: rotar la camara hasta que salga natural), asi que la fila 0
        # (QWERTY) queda a MENOR y de imagen que la home: uy negativo.
        col0 = _home_col(hand, finger)
        if col0 is None:
            return None
        best, best_d2 = None, None
        for k in cands:
            row, col = KEY_GRID[k]
            kx = col - col0
            ky = (row - HOME_ROW) * C.KB_ROW_SCALE
            d2 = (ux - kx) ** 2 + (uy - ky) ** 2
            if best_d2 is None or d2 < best_d2:
                best, best_d2 = k, d2
        return best if best_d2 is not None and best_d2 <= C.KB_MAX_KEY_DIST ** 2 else None

    def strikes(self, feat, t):
        """Eventos de contacto de este frame (sin decodificar):
        [{hand, finger, ux, uy}] con ux/uy relativos al home en unidades de pitch.
        Lo usa update() para teclear y tools/calibrate_keys para etiquetar."""
        out = []
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
                    ux, uy = self._contact_uxy(feat, slot, f, cal)
                    out.append({"hand": hand, "finger": f, "ux": ux, "uy": uy})
            cal.try_capture(feat, slot, fsms, wrist_v, t)
        return out

    def update(self, feat, t):
        typed = []
        for ev in self.strikes(feat, t):
            key = self._decode(ev["hand"], ev["finger"], ev["ux"], ev["uy"])
            if key:
                typed.append(key)
        return typed
