"""Servidor local de AirKeys: sirve la interfaz web y el video en vivo (MJPEG),
y controla el motor por una API. La ventana nativa (pywebview / WebView2) carga
esta pagina, asi la interfaz es HTML/CSS pero todo corre local, sin navegador.
"""
import json
import logging
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
from flask import Flask, Response, request, jsonify, send_from_directory

import config as C
from src.camera import open_camera, orient
from src.app import Engine

STATIC = Path(__file__).resolve().parent / "static"

# ajustes que expone la interfaz
SETTING_KEYS = ["MOUSE_GAIN", "MOUSE_SMOOTH", "MOUSE_DEADZONE", "MOUSE_ACCEL",
                "CAM_ROTATE", "FLIP_HORIZONTAL", "MOUSE_THUMB_OPEN",
                "MOUSE_INDEX_EXTEND"]


class _State:
    def __init__(self):
        self.thread = None
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.jpeg = None
        self.info = {}
        self.running = False
        self.mode = "mouse"
        self.real = False
        self.error = None
        self.fps = 0.0


S = _State()


def _loop(mode, real):
    eng = cap = None
    t_prev = time.perf_counter()
    try:
        eng = Engine(mode, real)
        cap = open_camera()
        while not S.stop.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            frame, info = eng.process(orient(frame))
            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            now = time.perf_counter()
            dt = now - t_prev
            t_prev = now
            with S.lock:
                if ok:
                    S.jpeg = buf.tobytes()
                S.info = info
                S.fps = 0.9 * S.fps + 0.1 * (1.0 / dt if dt > 0 else 0)
    except Exception as e:
        S.error = str(e)
    finally:
        if eng:
            eng.close()
        if cap:
            cap.release()
        S.running = False


def start(mode, real):
    if S.running:
        return
    S.error = None
    S.stop.clear()
    S.mode, S.real, S.running = mode, real, True
    S.thread = threading.Thread(target=_loop, args=(mode, real), daemon=True)
    S.thread.start()


def stop():
    S.stop.set()
    if S.thread:
        S.thread.join(timeout=2.0)
    S.thread = None
    S.running = False


def _spawn(args):
    if getattr(sys, "frozen", False):
        return [sys.executable] + args
    return [sys.executable, str(Path(__file__).resolve().parents[2] / "airkeys.py")] + args


app = Flask(__name__, static_folder=None)
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@app.route("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.route("/static/<path:f>")
def static_files(f):
    return send_from_directory(STATIC, f)


@app.route("/video")
def video():
    def gen():
        while True:
            with S.lock:
                jpg = S.jpeg
            if jpg is None:
                time.sleep(0.05)
                continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
            time.sleep(1 / 60)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/start", methods=["POST"])
def api_start():
    d = request.get_json(force=True)
    start(d.get("mode", "mouse"), bool(d.get("real")))
    return jsonify(ok=True)


@app.route("/api/stop", methods=["POST"])
def api_stop():
    stop()
    return jsonify(ok=True)


@app.route("/api/status")
def api_status():
    with S.lock:
        info = dict(S.info)
        fps = round(S.fps, 1)
    return jsonify(running=S.running, mode=S.mode, real=S.real,
                   error=S.error, fps=fps, info=info)


@app.route("/api/tool", methods=["POST"])
def api_tool():
    stop()
    name = request.get_json(force=True).get("name")
    if name:
        try:
            subprocess.Popen(_spawn([name]))
        except Exception as e:
            return jsonify(ok=False, error=str(e))
    return jsonify(ok=True)


def _apply_live(data):
    """Aplica ajustes al modulo config EN CALIENTE. Como los subsistemas leen
    C.LO_QUE_SEA en cada frame, el cambio surte efecto al instante, sin reiniciar."""
    for k, v in data.items():
        if not hasattr(C, k):
            continue
        cur = getattr(C, k)
        try:
            if isinstance(cur, bool):
                v = bool(v)
            elif isinstance(cur, int):
                v = int(v)
            elif isinstance(cur, float):
                v = float(v)
        except (TypeError, ValueError):
            pass
        setattr(C, k, v)


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    path = C.APP_DIR / "settings.json"
    cur = {}
    if path.exists():
        try:
            cur = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            cur = {}
    if request.method == "POST":
        data = request.get_json(force=True)
        _apply_live(data)                       # efecto inmediato
        cur.update(data)
        path.write_text(json.dumps(cur, indent=2), encoding="utf-8")
        return jsonify(ok=True)
    return jsonify({k: cur.get(k, getattr(C, k)) for k in SETTING_KEYS})


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    port = _free_port()
    threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, threaded=True,
                               debug=False, use_reloader=False),
        daemon=True).start()
    time.sleep(0.4)
    import webview
    webview.create_window("AirKeys", f"http://127.0.0.1:{port}/",
                          width=1040, height=800, min_size=(880, 680),
                          background_color="#0b0e14")
    webview.start()
    stop()


if __name__ == "__main__":
    main()
