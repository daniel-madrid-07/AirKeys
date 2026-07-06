"""Servidor local de AirKeys: sirve la interfaz web y el video en vivo (MJPEG),
y controla el motor por una API. La ventana nativa (pywebview / WebView2) carga
esta pagina, asi la interfaz es HTML/CSS pero todo corre local, sin navegador.
"""
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import cv2
from flask import Flask, Response, request, jsonify, send_from_directory

import config as C
from src.camera import open_camera, orient, list_devices
from src.app import Engine

STATIC = Path(__file__).resolve().parent / "static"

# ajustes que expone la interfaz
SETTING_KEYS = ["MOUSE_GAIN", "MOUSE_SMOOTH", "MOUSE_DEADZONE", "MOUSE_ACCEL",
                "CAM_ROTATE", "FLIP_HORIZONTAL", "MOUSE_THUMB_OPEN",
                "MOUSE_INDEX_EXTEND", "CAM_NAME"]


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
        # preview: la camara en vivo SIN motor (siempre activa salvo que un
        # tool externo necesite la camara)
        self.pv_thread = None
        self.pv_stop = threading.Event()


S = _State()


def _preview_loop():
    """Solo camara: sirve frames a /video sin procesar gestos."""
    cap = None
    t_prev = time.perf_counter()
    try:
        cap = open_camera()
        while not S.pv_stop.is_set():
            ok, frame = cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            ok, buf = cv2.imencode(".jpg", orient(frame),
                                   [cv2.IMWRITE_JPEG_QUALITY, 80])
            now = time.perf_counter()
            dt = now - t_prev
            t_prev = now
            with S.lock:
                if ok:
                    S.jpeg = buf.tobytes()
                S.fps = 0.9 * S.fps + 0.1 * (1.0 / dt if dt > 0 else 0)
    except Exception as e:
        S.error = str(e)
    finally:
        if cap:
            cap.release()


def preview_alive():
    return S.pv_thread is not None and S.pv_thread.is_alive()


def start_preview():
    if S.running or preview_alive():
        return
    S.error = None
    S.pv_stop.clear()
    S.pv_thread = threading.Thread(target=_preview_loop, daemon=True)
    S.pv_thread.start()


def stop_preview():
    S.pv_stop.set()
    if S.pv_thread:
        S.pv_thread.join(timeout=2.0)
    S.pv_thread = None


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
    stop_preview()                 # el motor toma la camara
    S.error = None
    S.stop.clear()
    S.mode, S.real, S.running = mode, real, True
    S.thread = threading.Thread(target=_loop, args=(mode, real), daemon=True)
    S.thread.start()


def stop(restart_preview=True):
    S.stop.set()
    if S.thread:
        S.thread.join(timeout=2.0)
    S.thread = None
    S.running = False
    if restart_preview:
        start_preview()            # la camara vuelve al preview


def _spawn(args):
    if getattr(sys, "frozen", False):
        return [sys.executable] + args
    return [sys.executable, str(Path(__file__).resolve().parents[2] / "airkeys.py")] + args


app = Flask(__name__, static_folder=None)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# herramientas externas que la UI puede lanzar (whitelist)
ALLOWED_TOOLS = {"calibrate-mouse", "check", "record", "train", "calibrate-tap"}


@app.before_request
def _only_localhost():
    """Defensa anti DNS-rebinding: el servidor es local; cualquier peticion cuyo
    Host no sea localhost viene de una web externa y se rechaza."""
    host = (request.host or "").split(":")[0]
    if host not in ("127.0.0.1", "localhost"):
        return jsonify(error="forbidden"), 403


def _json_body():
    """Cuerpo JSON estricto (Content-Type: application/json). Las webs de terceros
    no pueden mandar esto sin preflight CORS -> corta el CSRF trivial."""
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


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
    d = _json_body()
    if d is None:
        return jsonify(error="bad request"), 400
    mode = d.get("mode", "mouse")
    if mode not in ("mouse", "keyboard", "gaming"):
        return jsonify(error="bad mode"), 400
    start(mode, bool(d.get("real")))
    return jsonify(ok=True)


@app.route("/api/stop", methods=["POST"])
def api_stop():
    stop()
    S.error = None
    return jsonify(ok=True)


@app.route("/api/status")
def api_status():
    with S.lock:
        info = dict(S.info)
        fps = round(S.fps, 1)
    return jsonify(running=S.running, mode=S.mode, real=S.real,
                   error=S.error, fps=fps, info=info,
                   preview=preview_alive())


@app.route("/api/cameras")
def api_cameras():
    """Camaras disponibles (nombres DSHOW) y la seleccionada."""
    return jsonify(cameras=list_devices(), current=getattr(C, "CAM_NAME", ""))


@app.route("/api/preview", methods=["POST"])
def api_preview():
    """Enciende/apaga el preview (p.ej. reanudar tras cerrar un tool)."""
    d = _json_body()
    if d is None:
        return jsonify(error="bad request"), 400
    if d.get("on") and not S.running:
        S.error = None
        start_preview()
    elif not d.get("on"):
        stop_preview()
    return jsonify(ok=True)


@app.route("/api/tool", methods=["POST"])
def api_tool():
    d = _json_body()
    name = d.get("name") if d else None
    if name not in ALLOWED_TOOLS:
        return jsonify(error="unknown tool"), 400
    stop(restart_preview=False)
    stop_preview()                 # el tool externo necesita la camara libre
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
        body = _json_body()
        if body is None:
            return jsonify(error="bad request"), 400
        data = {k: v for k, v in body.items() if k in SETTING_KEYS}  # whitelist
        _apply_live(data)                       # efecto inmediato
        cur.update(data)
        path.write_text(json.dumps(cur, indent=2), encoding="utf-8")
        if "CAM_NAME" in data:                  # cambio de camara -> reabrir
            if S.running:
                m, r = S.mode, S.real
                stop(restart_preview=False)
                start(m, r)
            else:
                stop_preview()
                start_preview()
        return jsonify(ok=True)
    return jsonify({k: cur.get(k, getattr(C, k)) for k in SETTING_KEYS})


# ------------------------------------------------------------------ updates
# Busca la ultima release del repo, descarga el Setup.exe y lo lanza en modo
# silencioso; el instalador cierra/actualiza y relanza la app.
_UPD = {"state": "idle", "progress": 0.0, "error": "", "latest": ""}


def _ver_parts(tag):
    """'v0.9.1-beta' -> ((0, 9, 1), es_prerelease)."""
    core = tag.strip().lstrip("vV")
    pre = "-" in core
    nums = []
    for p in core.split("-")[0].split("."):
        if p.isdigit():
            nums.append(int(p))
    return tuple(nums), pre


def _is_newer(latest, current):
    ln, lpre = _ver_parts(latest)
    cn, cpre = _ver_parts(current)
    if ln != cn:
        return ln > cn
    return cpre and not lpre        # misma version numerica: estable > beta


def _gh_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AirKeys",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


@app.route("/api/update/check")
def api_update_check():
    try:
        rel = _gh_json(f"https://api.github.com/repos/{C.UPDATE_REPO}/releases/latest")
        tag = rel.get("tag_name", "")
        asset = next((a for a in rel.get("assets", [])
                      if a["name"].startswith("AirKeys") and a["name"].endswith("Setup.exe")),
                     None)
        return jsonify(ok=True, current=C.APP_VERSION, latest=tag.lstrip("vV"),
                       update=bool(asset) and _is_newer(tag, C.APP_VERSION),
                       url=asset["browser_download_url"] if asset else "")
    except Exception as e:
        return jsonify(ok=False, current=C.APP_VERSION, error=str(e))


def _download_and_install(url, version):
    try:
        path = Path(tempfile.gettempdir()) / f"AirKeys-{version}-Setup.exe"
        req = urllib.request.Request(url, headers={"User-Agent": "AirKeys"})
        with urllib.request.urlopen(req, timeout=30) as r, open(path, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total:
                    _UPD["progress"] = got / total
        _UPD["state"] = "installing"
        stop(restart_preview=False)
        stop_preview()                          # libera la camara
        # /SILENT: instala con barra de progreso y relanza AirKeys al acabar
        subprocess.Popen([str(path), "/SILENT", "/NORESTART"])
        threading.Timer(1.5, lambda: os._exit(0)).start()   # cierra esta instancia
    except Exception as e:
        _UPD["state"] = "error"
        _UPD["error"] = str(e)


@app.route("/api/update/download", methods=["POST"])
def api_update_download():
    if _UPD["state"] in ("downloading", "installing"):
        return jsonify(ok=True)
    d = _json_body() or {}
    url, version = d.get("url", ""), d.get("version", "")
    if not (url.startswith(f"https://github.com/{C.UPDATE_REPO}/releases/download/")
            and url.endswith(".exe")):
        return jsonify(ok=False, error="bad url"), 400
    _UPD.update(state="downloading", progress=0.0, error="", latest=version)
    threading.Thread(target=_download_and_install, args=(url, version),
                     daemon=True).start()
    return jsonify(ok=True)


@app.route("/api/update/status")
def api_update_status():
    return jsonify(**_UPD)


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
    start_preview()                # camara encendida desde el arranque
    time.sleep(0.4)
    url = f"http://127.0.0.1:{port}/"
    try:
        import webview
    except Exception:
        webview = None
    try:
        if webview:
            webview.create_window("AirKeys", url,
                                  width=1040, height=800, min_size=(880, 680),
                                  background_color="#eef6fc")
            webview.start()
        else:                       # sin WebView2/pywebview -> navegador del sistema
            import webbrowser
            print(f"[APP] UI en el navegador: {url}  (Ctrl+C para salir)")
            webbrowser.open(url)
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop(restart_preview=False)
        stop_preview()


if __name__ == "__main__":
    main()
