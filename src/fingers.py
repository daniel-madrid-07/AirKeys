"""Mapeo tecla -> dedo, y como recortar del vector de features SOLO los landmarks
de un dedo. Base del modelo multi-experto: cada dedo ve unicamente lo suyo.

Mapeo dado por el usuario (solo letras + space entran en el modelo v1;
shift/ctrl/caps/enter/return/numeros se añadiran cuando esten en TARGET_KEYS):

  meñique izq : shift, ctrl, caps            (sin letras -> sin experto por ahora)
  anular  izq : a q z   (y 1)
  medio   izq : w s     (y 2 3),  e (medio/indice)
  indice  izq : d b r f t g x c v y h,  space (escritura; gaming = pulgar izq)
  indice  der : n m j u k i
  medio   der : l p o
  anular  der : return  (y enter con meñique der)  -> sin letras por ahora
"""
import config as C

# landmarks de MediaPipe que pertenecen a cada dedo (incluye muñeca=0 de ancla)
FINGER_LANDMARKS = {
    "thumb":  [0, 1, 2, 3, 4],
    "index":  [0, 5, 6, 7, 8],
    "middle": [0, 9, 10, 11, 12],
    "ring":   [0, 13, 14, 15, 16],
    "pinky":  [0, 17, 18, 19, 20],
}

# tecla -> (mano, dedo)
FINGER_MAP = {
    "a": ("Left", "ring"),   "q": ("Left", "ring"),   "z": ("Left", "ring"),
    "w": ("Left", "middle"), "s": ("Left", "middle"), "e": ("Left", "middle"),
    "d": ("Left", "index"),  "b": ("Left", "index"),  "r": ("Left", "index"),
    "f": ("Left", "index"),  "t": ("Left", "index"),  "g": ("Left", "index"),
    "x": ("Left", "index"),  "c": ("Left", "index"),  "v": ("Left", "index"),
    "y": ("Left", "index"),  "h": ("Left", "index"),
    "n": ("Right", "index"), "m": ("Right", "index"), "j": ("Right", "index"),
    "u": ("Right", "index"), "k": ("Right", "index"), "i": ("Right", "index"),
    "l": ("Right", "middle"), "p": ("Right", "middle"), "o": ("Right", "middle"),
    "space": ("Left", "index"),   # modo escritura; en gaming se pulsa con pulgar izq
}


def _hand_slot(hand):
    base = 0 if hand == "Left" else 1
    return base ^ (1 if C.SWAP_HANDS else 0)


def finger_indices(hand, finger):
    """Indices dentro del vector de features (FEATURE_DIM) de ese dedo.

    Layout por mano: [rel 63 (21*3)] [abs 42 (21*2)]; flags al final.
    Devuelve rel(xyz) + abs(xy) de cada landmark del dedo + flag de presencia.
    """
    h = _hand_slot(hand)
    lms = FINGER_LANDMARKS[finger]
    idx = []
    for i in lms:                                   # rel xyz
        b = h * C.PER_HAND + i * 3
        idx += [b, b + 1, b + 2]
    for i in lms:                                   # abs xy
        b = h * C.PER_HAND + C.PER_HAND_REL + i * 2
        idx += [b, b + 1]
    idx.append(C.PER_HAND * C.MAX_HANDS + h)        # flag de presencia de la mano
    return idx


def build_experts(classes):
    """Lista de expertos (uno por dedo con teclas). Orden deterministico."""
    to_idx = {c: i for i, c in enumerate(classes)}
    groups = {}  # (hand,finger) -> keys
    for key in C.TARGET_KEYS:
        if key in FINGER_MAP:
            groups.setdefault(FINGER_MAP[key], []).append(key)

    experts = []
    for (hand, finger), keys in groups.items():
        keys = [k for k in C.TARGET_KEYS if k in keys]          # orden estable
        local_classes = [C.NONE_LABEL] + keys
        experts.append({
            "hand": hand, "finger": finger, "keys": keys,
            "local_classes": local_classes,
            "indices": finger_indices(hand, finger),
            "local_to_global": [to_idx[c] for c in local_classes],
            "global_to_local": {to_idx[c]: li for li, c in enumerate(local_classes)},
        })
    return experts
