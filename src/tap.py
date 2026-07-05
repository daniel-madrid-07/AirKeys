"""Detector de pulsacion (tap) por dedo. Geometrico, sin entrenar.

Señal por dedo:  s = TAP_SIGN * (y_punta - y_nudillo) / tamaño_de_mano
NORMALIZADA por el tamaño aparente de la mano -> la misma pulsacion da la misma
señal estes cerca o lejos de la camara. Unidades: "tamaños de mano".
Al pulsar, la punta baja respecto al nudillo -> s sube; al levantar -> s baja.

Maquina de estados por dedo (streaming):
  - reposo: se sigue el nivel base (hover) con una media suave.
  - si s supera base + TAP_ENTER -> "armado"; se guarda el pico y su instante.
  - si estando armado s cae por debajo de pico - TAP_EXIT -> se DISPARA un tap
    (en el instante del pico = fondo de la pulsacion) y se vuelve a reposo.
  - refractario por dedo para no disparar dos veces.

Trabaja sobre el VECTOR DE FEATURES (usa la parte de posicion absoluta), asi que es
identico al grabar (calibracion) y al inferir.
"""
import config as C

# landmark de punta y de nudillo (MCP) por dedo
TIP = {"thumb": 4, "index": 8, "middle": 12, "ring": 16, "pinky": 20}
MCP = {"thumb": 2, "index": 5, "middle": 9, "ring": 13, "pinky": 17}


def abs_xy(feat, slot, landmark):
    """(x, y) (0..1) de un landmark en la parte absoluta del vector de features."""
    base = slot * C.PER_HAND + C.PER_HAND_REL + landmark * 2
    return float(feat[base]), float(feat[base + 1])


def abs_y(feat, slot, landmark):
    return abs_xy(feat, slot, landmark)[1]


def present(feat, slot):
    return feat[C.PER_HAND * C.MAX_HANDS + slot] > 0.5


def hand_scale(feat, slot):
    """Tamaño aparente de la mano: distancia muñeca(0) -> nudillo corazon(9)."""
    wx, wy = abs_xy(feat, slot, 0)
    mx, my = abs_xy(feat, slot, 9)
    return ((wx - mx) ** 2 + (wy - my) ** 2) ** 0.5 + 1e-6


def finger_signal(feat, slot, finger):
    """Señal de pulsacion normalizada por tamaño de mano (invariante a distancia)."""
    s = abs_y(feat, slot, TIP[finger]) - abs_y(feat, slot, MCP[finger])
    return C.TAP_SIGN * s / hand_scale(feat, slot)


class TapDetector:
    """Detecta taps para una lista de (slot, finger). Devuelve eventos por frame."""

    def __init__(self, targets):
        # targets: iterable de (slot, finger)
        self.targets = list(targets)
        self.base = {}          # nivel de reposo
        self.armed = {}
        self.peak = {}
        self.peak_t = {}
        self.last_fire = {}
        self.ready = {}         # ¿se levanto el dedo desde el ultimo tap?
        for k in self.targets:
            self.base[k] = None
            self.armed[k] = False
            self.peak[k] = 0.0
            self.peak_t[k] = 0.0
            self.last_fire[k] = -1e9
            self.ready[k] = True

    def update(self, feat, t):
        """Procesa un frame. Devuelve lista de taps: (slot, finger, t_pico, amplitud)."""
        taps = []
        for k in self.targets:
            slot, finger = k
            if not present(feat, slot):
                self.armed[k] = False        # mano fuera -> desarmar
                continue
            s = finger_signal(feat, slot, finger)
            if self.base[k] is None:
                self.base[k] = s
                continue

            if not self.armed[k]:
                if s > self.base[k] + C.TAP_ENTER and self.ready[k]:
                    self.armed[k] = True                 # baja el dedo -> pulsacion
                    self.peak[k] = s
                    self.peak_t[k] = t
                else:
                    a = C.TAP_BASELINE_ALPHA
                    self.base[k] = (1 - a) * self.base[k] + a * s
                    if s < self.base[k] - C.TAP_LIFT:    # dedo levantado -> habilita
                        self.ready[k] = True
            else:
                if s > self.peak[k]:
                    self.peak[k] = s
                    self.peak_t[k] = t
                if s < self.peak[k] - C.TAP_EXIT:      # el dedo sube -> fin del tap
                    if t - self.last_fire[k] >= C.TAP_REFRACTORY_S:
                        taps.append((slot, finger, self.peak_t[k],
                                     self.peak[k] - self.base[k]))
                        self.last_fire[k] = t
                        self.ready[k] = False          # hay que levantar antes del sig.
                    self.armed[k] = False
        return taps
