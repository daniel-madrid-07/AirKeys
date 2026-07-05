"""Envuelve MediaPipe HandLandmarker (API Tasks) y produce un vector de features
normalizado por frame.

En Python 3.13 mediapipe solo trae la API 'Tasks' (no la vieja mp.solutions),
por eso usamos vision.HandLandmarker y un modelo .task local.

Salida por frame: np.ndarray shape (FEATURE_DIM,) float32.
Layout: [mano_izq(63)] [mano_der(63)] [flag_izq] [flag_der].

Normalizacion por mano (clave para generalizar a cualquier zona de la mesa):
    - se resta la muñeca (landmark 0)
    - se escala por la distancia muñeca -> nudillo del corazon (landmark 9)
"""
import numpy as np
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

import config as C

_WRIST = 0
_MIDDLE_MCP = 9

# Conexiones estandar de la mano (para dibujar), sin depender de la API.
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),           # pulgar
    (0, 5), (5, 6), (6, 7), (7, 8),           # indice
    (5, 9), (9, 10), (10, 11), (11, 12),      # corazon
    (9, 13), (13, 14), (14, 15), (15, 16),    # anular
    (13, 17), (17, 18), (18, 19), (19, 20),   # meñique
    (0, 17),                                  # palma
]


class HandTracker:
    def __init__(self, model_path=None):
        model_path = str(model_path or C.HAND_MODEL)
        opts = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=C.MAX_HANDS,
            min_hand_detection_confidence=C.MIN_DET_CONF,
            min_hand_presence_confidence=C.MIN_TRACK_CONF,
            min_tracking_confidence=C.MIN_TRACK_CONF,
        )
        self.landmarker = vision.HandLandmarker.create_from_options(opts)
        self._t = 0

    def _hand_features(self, lms) -> np.ndarray:
        pts = np.array([[p.x, p.y, p.z] for p in lms], dtype=np.float32)  # (21,3)
        abs_xy = pts[:, :2].reshape(-1)                # (42,) posicion en el frame
        rel = pts - pts[_WRIST]                         # postura relativa a muñeca
        scale = np.linalg.norm(rel[_MIDDLE_MCP]) + 1e-6
        rel = (rel / scale).reshape(-1)                 # (63,) invariante a posicion/tamaño
        return np.concatenate([rel, abs_xy])            # (105,)

    def process(self, frame_bgr, timestamp_ms=None):
        """Devuelve (feature_vector, result) para un frame BGR de OpenCV.

        VIDEO mode exige timestamps crecientes; usamos un contador interno
        salvo que pases timestamp_ms explicito.
        """
        # MediaPipe con frame reducido: ~3x mas rapido, landmarks normalizados
        # identicos. El resto del pipeline (flujo optico) usa el frame completo.
        if getattr(C, "MP_SCALE", 1.0) < 1.0:
            frame_bgr = cv2.resize(frame_bgr, None, fx=C.MP_SCALE, fy=C.MP_SCALE,
                                   interpolation=cv2.INTER_AREA)
        rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        if timestamp_ms is None:
            self._t += 1
            timestamp_ms = self._t
        res = self.landmarker.detect_for_video(mp_img, int(timestamp_ms))

        feat = np.zeros(C.FEATURE_DIM, dtype=np.float32)
        if res.hand_landmarks:
            for lms, handed in zip(res.hand_landmarks, res.handedness):
                label = handed[0].category_name  # 'Left' / 'Right'
                slot = 0 if label == "Left" else 1
                off = slot * C.PER_HAND
                feat[off:off + C.PER_HAND] = self._hand_features(lms)
                feat[C.PER_HAND * C.MAX_HANDS + slot] = 1.0
        return feat, res

    def close(self):
        self.landmarker.close()


def draw(frame_bgr, result):
    """Dibuja landmarks y conexiones sobre el frame (in-place)."""
    if not result.hand_landmarks:
        return frame_bgr
    h, w = frame_bgr.shape[:2]
    for lms in result.hand_landmarks:
        pts = [(int(p.x * w), int(p.y * h)) for p in lms]
        for a, b in HAND_CONNECTIONS:
            cv2.line(frame_bgr, pts[a], pts[b], (0, 200, 0), 2)
        for x, y in pts:
            cv2.circle(frame_bgr, (x, y), 3, (0, 0, 255), -1)
    return frame_bgr
