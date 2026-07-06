"""Apertura de camara. Elige la webcam por NOMBRE (robusto frente a DroidCam/OBS
que cambian los indices). pygrabber comparte orden con el backend DSHOW."""
import cv2

import config as C


def _fourcc(code="MJPG"):
    try:
        return cv2.VideoWriter_fourcc(*code)      # OpenCV 4
    except AttributeError:
        return cv2.VideoWriter.fourcc(*code)      # OpenCV 5


def list_devices():
    """Nombres de camara en orden de indice (DSHOW). [] si pygrabber no esta."""
    try:
        from pygrabber.dshow_graph import FilterGraph
        return list(FilterGraph().get_input_devices())
    except Exception:
        return []


def resolve():
    """Devuelve (index, backend, nombre) segun CAM_NAME; si no, el fallback."""
    name = getattr(C, "CAM_NAME", "")
    if name:
        for i, dev in enumerate(list_devices()):
            if name.lower() in dev.lower():
                return i, cv2.CAP_DSHOW, dev
    return C.CAM_INDEX, C.CAM_BACKEND, f"indice {C.CAM_INDEX}"


def open_camera(fps=None):
    fps = fps or C.TARGET_FPS
    idx, backend, name = resolve()
    print(f"[CAM] usando: {name} (idx {idx})")
    cap = cv2.VideoCapture(idx, backend)
    cap.set(cv2.CAP_PROP_FOURCC, _fourcc("MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, C.FRAME_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, C.FRAME_H)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # sin cola de frames -> menos latencia
    return cap


def reported_fps(cap):
    try:
        return float(cap.get(cv2.CAP_PROP_FPS))
    except Exception:
        return 0.0


_ROT = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE}


def orient(frame):
    """Aplica espejo + rotacion configurados. Usar en TODOS los bucles de camara
    para que grabar, calibrar e inferir vean la imagen igual (clave con la camara
    cenital, que suele quedar girada segun el montaje)."""
    if C.FLIP_HORIZONTAL:
        frame = cv2.flip(frame, 1)
    r = getattr(C, "CAM_ROTATE", 0)
    if r in _ROT:
        frame = cv2.rotate(frame, _ROT[r])
    return frame
