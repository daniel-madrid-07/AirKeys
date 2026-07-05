"""Sensor de movimiento por FLUJO OPTICO — la camara como raton optico gigante.

Un raton optico real no 'entiende' la superficie: compara imagenes consecutivas y
mide cuanto se desplazo la textura. Esto es lo mismo con tu mano:

  1. Se eligen ~100 puntos de textura de la piel (esquinas, goodFeaturesToTrack).
  2. Se rastrean frame a frame con Lucas-Kanade piramidal (precision SUB-PIXEL).
  3. Check ida-vuelta: un punto solo vale si al rastrearlo hacia atras vuelve a su
     sitio (<1 px). Elimina puntos malos.
  4. Movimiento de la mano = MEDIANA de todos los vectores. El temblor aleatorio de
     puntos individuales se cancela; el resultado es ordenes de magnitud mas estable
     que cualquier landmark.

MediaPipe ya NO decide el movimiento: solo da la caja de la mano (donde buscar
textura), el estado levantada/apoyada y los taps para los clicks.
"""
import cv2
import numpy as np

_FEAT = dict(maxCorners=120, qualityLevel=0.01, minDistance=7, blockSize=7)
_LK = dict(winSize=(21, 21), maxLevel=3,
           criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
_FB_MAX = 1.0        # error maximo ida-vuelta (px) para aceptar un punto
_MIN_PTS = 12        # puntos minimos para dar una medida
_RESEED_EVERY = 24   # frames entre re-siembras de puntos


class FlowSensor:
    def __init__(self):
        self.prev_gray = None
        self.pts = None
        self.age = 0
        self.n_good = 0

    def reset(self):
        self.prev_gray = None
        self.pts = None

    def _seed(self, gray, mask):
        self.pts = cv2.goodFeaturesToTrack(gray, mask=mask, **_FEAT)
        self.age = 0

    def delta(self, gray, mask):
        """Desplazamiento (dx, dy) en PIXELES del contenido de la MASCARA entre el
        frame anterior y este. None si no hay medida fiable.

        mask: uint8 (0/255) con la SILUETA de la mano. Clave de precision: solo se
        rastrea piel de la mano; ningun punto del fondo (mesa) entra en la mediana.
        """
        if mask is None or cv2.countNonZero(mask) < 400:
            self.reset()
            return None
        if self.prev_gray is None:
            self.prev_gray = gray
            self._seed(gray, mask)
            return None
        if self.pts is None or len(self.pts) < _MIN_PTS or self.age >= _RESEED_EVERY:
            self._seed(self.prev_gray, mask)
            if self.pts is None or len(self.pts) < _MIN_PTS:
                self.prev_gray = gray
                self.pts = None
                return None

        p1, st, _ = cv2.calcOpticalFlowPyrLK(self.prev_gray, gray, self.pts, None, **_LK)
        p0b, st_b, _ = cv2.calcOpticalFlowPyrLK(gray, self.prev_gray, p1, None, **_LK)
        fb = np.linalg.norm((self.pts - p0b).reshape(-1, 2), axis=1)
        good = (st.ravel() == 1) & (st_b.ravel() == 1) & (fb < _FB_MAX)

        self.prev_gray = gray
        self.age += 1
        if int(good.sum()) < _MIN_PTS:
            self.n_good = int(good.sum())
            self.pts = None
            return None

        p1g = p1[good].reshape(-1, 1, 2)
        vecs = (p1 - self.pts).reshape(-1, 2)[good]

        # rechazo extra de outliers: descarta vectores lejos de la mediana (MAD).
        # protege la medida si algun punto se engancho a otra cosa (borde, sombra).
        med = np.median(vecs, axis=0)
        dev = np.linalg.norm(vecs - med, axis=1)
        mad = float(np.median(dev))
        keep = dev < 3.0 * mad + 0.5
        if int(keep.sum()) >= _MIN_PTS:
            vecs = vecs[keep]
            p1g = p1g[keep]
            med = np.median(vecs, axis=0)

        self.n_good = len(vecs)
        self.pts = p1g                              # seguir con los puntos buenos
        return float(med[0]), float(med[1])
