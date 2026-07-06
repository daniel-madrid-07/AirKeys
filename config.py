"""Configuracion central de AirKeys."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Modo empaquetado (PyInstaller): los assets de solo-lectura viven en el bundle
# (_MEIPASS) y los datos escribibles (settings, datasets, modelos entrenados,
# calibracion) junto al .exe. En desarrollo, todo en la raiz del repo.
if getattr(sys, "frozen", False):
    BUNDLE = Path(getattr(sys, "_MEIPASS", ROOT))
    APP_DIR = Path(sys.executable).resolve().parent
else:
    BUNDLE = APP_DIR = ROOT

DATA_DIR = APP_DIR / "data"
MODEL_DIR = APP_DIR / "models"
DATA_DIR.mkdir(exist_ok=True)
MODEL_DIR.mkdir(exist_ok=True)

# --- Camara ---
# Se elige por NOMBRE (robusto: DroidCam/OBS mueven los indices). Si el nombre no
# aparece, usa CAM_INDEX/CAM_BACKEND. Vacia CAM_NAME para forzar el indice.
CAM_NAME = "Microsoft"   # subcadena del nombre de la webcam a usar
CAM_INDEX = 1            # fallback si no se encuentra por nombre
CAM_BACKEND = 700        # cv2.CAP_DSHOW (mismo orden que pygrabber). MSMF=1400, ANY=0
FRAME_W = 1280
FRAME_H = 720
TARGET_FPS = 60      # webcam a 60fps (MJPG). El proceso real puede ir algo menos.
# Espejo horizontal. False = orientacion real (qwerty se lee qwerty).
# True = vista selfie. Debe ser IGUAL al grabar y al inferir.
FLIP_HORIZONTAL = False
# Rotacion de la imagen en grados (0/90/180/270). Por defecto 180 para camara
# CENITAL (montada arriba mirando abajo): la mano se ve NATURAL (dedos hacia arriba,
# izquierda a la izquierda). Si tu montaje la deja al reves, cambia a 0/90/270 en
# Ajustes hasta que salga natural.
CAM_ROTATE = 180
# Vista de la camara: "overhead" (arriba mirando abajo, la usada ahora) o "side".
CAM_VIEW = "overhead"

# --- MediaPipe Hands (API Tasks) ---
# Preferimos el modelo escribible (MODEL_DIR); si no, el empaquetado (BUNDLE).
HAND_MODEL = MODEL_DIR / "hand_landmarker.task"
if not HAND_MODEL.exists() and (BUNDLE / "models" / "hand_landmarker.task").exists():
    HAND_MODEL = BUNDLE / "models" / "hand_landmarker.task"
MAX_HANDS = 2
MIN_DET_CONF = 0.6
MIN_TRACK_CONF = 0.6
# MediaPipe procesa el frame REDUCIDO (mas FPS, menos latencia; los landmarks son
# normalizados asi que nada mas cambia). El flujo optico sigue a resolucion completa.
MP_SCALE = 0.5       # 1.0 = resolucion completa

# --- Features ---
# Por mano combinamos DOS representaciones:
#   - relativa (postura): 21*3 respecto a muñeca y escalada -> invariante a posicion
#   - absoluta (donde esta): 21*2 (x,y en el frame) -> distingue QUE tecla (posicion)
# La absoluta es clave: sin ella el modelo no sabe si el dedo pulsa 'q' o 'p'.
LANDMARKS_PER_HAND = 21
PER_HAND_REL = LANDMARKS_PER_HAND * 3           # 63
PER_HAND_ABS = LANDMARKS_PER_HAND * 2           # 42
PER_HAND = PER_HAND_REL + PER_HAND_ABS          # 105
FEATURE_DIM = PER_HAND * MAX_HANDS + MAX_HANDS  # 212

# --- Ventana temporal del modelo ---
WINDOW = 13         # frames por muestra (~215ms a 60fps)
CENTER = WINDOW // 2

# --- Etiquetado ---
# etiqueta cada pulsacion en los frames dentro de +-LABEL_TOL_S, y ademas
# "unta" LABEL_SPREAD frames a cada lado -> muchos mas ejemplos positivos.
LABEL_TOL_S = 0.05
LABEL_SPREAD = 2
NONE_LABEL = "none"

# --- Teclas objetivo (v1: fila central + comunes). Amplia a tu gusto. ---
TARGET_KEYS = list("abcdefghijklmnopqrstuvwxyz") + ["space"]

# --- Manos: izquierda/derecha ---
# MediaPipe a veces reporta la mano al reves segun el flip. Si las teclas de una
# mano no se aprenden, pon esto en True para intercambiar izquierda<->derecha.
SWAP_HANDS = False

# --- Entrenamiento (modelo multi-experto por dedo) ---
# Cada dedo tiene su propio mini-GRU que ve SOLO sus landmarks -> se centra en lo
# importante. Ver src/fingers.py para el mapeo tecla->dedo.
FINGER_HIDDEN = 64
FINGER_LAYERS = 1
FINGER_DROPOUT = 0.1
LR = 1e-3
EPOCHS = 40
BATCH = 128
NONE_WEIGHT = 0.15   # baja el peso de la clase 'none' (dominante)

# --- Deteccion de pulsacion (TAP) ---
# Clave para la precision: solo se emite tecla cuando un dedo hace el gesto real de
# bajar-tocar-subir. Señal por dedo = ((y punta) - (y nudillo)) / tamaño de mano:
# NORMALIZADA -> no depende de a que distancia estes de la camara.
# Unidades: "tamaños de mano". Recalibra con tools/calibrate_tap tras grabar.
TAP_SIGN = 1.0        # +1 si al pulsar s sube (normal). Ponlo -1 si va al reves.
TAP_ENTER = 0.30      # cuanto debe subir s sobre el reposo para "armar" el tap
TAP_EXIT = 0.15       # cuanto debe bajar s desde el pico para confirmar (dedo sube)
TAP_REFRACTORY_S = 0.20   # tiempo minimo entre taps del MISMO dedo
TAP_BASELINE_ALPHA = 0.12 # suavizado del nivel de reposo (hover)
# "Levantar antes de pulsar": una tecla solo cuenta si ANTES el dedo se levanto
# (s cayo por debajo del reposo en TAP_LIFT). Evita que dedos quietos/bajos repitan.
TAP_LIFT = 0.18

# --- Teclado GEOMETRICO (por defecto, SIN entrenar) ---
# Ver src/keyboard_geo.py: calibracion home-row (manos quietas en la mesa) +
# strike por reversion de velocidad + tecla por posicion en la rejilla QWERTY.
KB_DECODER = "geo"        # "geo" (sin modelo, por defecto) | "model" (GRU entrenado)
                          # | "auto" (model si existe models/fingers.pt, si no geo)
KB_VEL_ENTER = 0.9        # velocidad de bajada de s (1/seg) que arma un strike
KB_MIN_DROP = 0.08        # excursion minima de s en la bajada (tamaños de mano)
KB_STRIKE_MAX_S = 0.35    # una bajada mas larga que esto no es un tap
KB_REFRACTORY_S = 0.18    # tiempo minimo entre strikes del mismo dedo
KB_STILL_EPS = 0.35       # |v| por debajo = dedo/mano quietos (para calibrar)
KB_CALIB_STILL_S = 0.8    # segundos quieto para (re)calibrar el reposo
KB_WRIST_MAX_V = 0.8      # velocidad de muñeca por encima = recolocacion, no tecla
KB_ROW_SCALE = 0.85       # separacion vertical entre filas, relativa al pitch
KB_MAX_KEY_DIST = 0.75    # distancia maxima a una tecla (en pitch) para aceptarla

# --- Inferencia (modo con modelo entrenado) ---
KEY_CONF_MIN = 0.30  # confianza minima del experto para aceptar la tecla de un tap
DEBOUNCE_S = 0.12    # tiempo minimo entre dos emisiones de la misma tecla

# --- Grabador guiado (metronomo, sin teclado fisico -> sin domain gap) ---
AIR_BPM = 40         # pulsaciones por minuto que marca el metronomo
AIR_LEAD_S = 0.9     # antelacion con que se muestra la tecla antes del beat

# --- Gaming: teclado por dedos (mano izquierda), SIN modelo ---
# Cada dedo = una tecla. Dedo BAJADO = tecla mantenida. Nombres: una letra, o
# "space"/"shift"/"ctrl"/"alt"/"tab"/"enter"/"esc" (teclas especiales de pynput).
GAMING_HAND = "Left"
GAMING_KEYS = {"pinky": "shift", "ring": "a", "middle": "w", "index": "d",
               "thumb": "space"}
GAMING_PRESS = 0.22     # cuanto baja el dedo sobre su reposo para APRETAR (tam. mano)
GAMING_RELEASE = 0.10   # por debajo, suelta
GAMING_BASE_ALPHA = 0.10

# --- Raton (v2: relativo puro, como un raton real) ---
MOUSE_HAND = "Right"                       # mano que mueve el raton (Left/Right)
MOUSE_LANDMARK = 5                         # 5 = nudillo del indice (estable al hacer
                                           # click con la punta). 8 = punta del indice.
# Sensibilidad: un gesto igual al de calibracion = cruzar UNA pantalla * GAIN.
MOUSE_GAIN = 1.0
# Suavizado del movimiento (modo flujo optico). El cursor sigue una velocidad
# suavizada -> fluido, sin tirones. Menor = MAS fluido pero MAS lag.
MOUSE_SMOOTH = 0.35
# Zona muerta: ignora el micro-movimiento con la mano quieta (fraccion de imagen).
# Mata el tembleque de coordenadas en reposo. Subir si sigue vibrando; bajar si
# los movimientos lentos/finos no responden.
MOUSE_DEADZONE = 0.0009
# Aceleracion de puntero (como los ratones reales): mover LENTO = precision (x1),
# mover RAPIDO = alcance (hasta x(1+ACCEL)). 0 = desactivada.
MOUSE_ACCEL = 1.2
MOUSE_ACCEL_REF = 0.006    # velocidad (fraccion de imagen/frame) donde ya acelera
MOUSE_MAX_STEP = 0.06      # delta maximo por frame (anti-glitch del sensor)
MOUSE_MINCUTOFF = 1.2                       # One Euro (fallback por landmarks)
MOUSE_BETA = 0.03
# CLUTCH por MANO PLANA: extiende la mano (dedos rectos, apoyada) y el cursor se
# CONGELA. La postura de mover es el PUÑO (rectitud baja), asi que la rectitud media
# separa bien plana (~1.0) de puño (~0.2). No importa si los dedos van juntos.
MOUSE_FLAT_ENTER = 0.85    # rectitud media de la mano para CONGELAR
MOUSE_FLAT_EXIT = 0.72     # por debajo (puño), se mueve

# CLICKS (camara CENITAL; posicion normal = PUÑO):
#   IZQUIERDO = ABRIR/alejar el pulgar de la mano (sube la distancia pulgar<->mano).
#   DERECHO   = ESTIRAR el indice (sube su rectitud).
# Ambos MANTENIDOS mientras dure el gesto. Histeresis. En pantalla se ve i:/t:.
MOUSE_THUMB_OPEN = 0.55    # apertura (0..1 reescalada) POR ENCIMA = click IZQ
MOUSE_THUMB_CLOSE = 0.35   # por DEBAJO suelta el izquierdo
MOUSE_INDEX_EXTEND = 0.80  # extension del indice (0..1 reescalada: puño=0,
                           # estirado=1) POR ENCIMA = click DER
MOUSE_INDEX_RETRACT = 0.62 # por DEBAJO suelta el derecho
MOUSE_BTN_COOLDOWN = 8     # frames sin clicks tras volver de plana / perder la mano

# --- Overrides de usuario ---
# Crea un settings.json junto a este archivo con claves en MAYUSCULAS para
# sobreescribir cualquier valor sin tocar el codigo. Ej:
#   { "MOUSE_GAIN": 1.4, "CAM_NAME": "Logitech", "MOUSE_HAND": "Left" }
import json as _json  # noqa: E402
_SETTINGS = APP_DIR / "settings.json"
if _SETTINGS.exists():
    try:
        for _k, _v in _json.loads(_SETTINGS.read_text(encoding="utf-8")).items():
            if _k.isupper() and _k in globals():
                globals()[_k] = _v
            else:
                print(f"[CONFIG] settings.json: clave desconocida '{_k}' (ignorada)")
    except Exception as _e:
        print(f"[CONFIG] settings.json invalido: {_e} (usando valores por defecto)")
