"""AirKeys — aplicacion de ventana con VIDEO EN VIVO dentro de la ventana.

El motor (Engine) corre en un hilo: lee la camara, procesa y deja el frame en una
cola; la UI lo pinta. Modos raton/gaming/teclado se ven integrados (sin ventana
OpenCV aparte). Calibraciones y grabaciones se lanzan como proceso (tienen su propia
ventana interactiva). Ajustes y calibracion viven en un dialogo aparte.
"""
import json
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
from pathlib import Path

import cv2
from PIL import Image, ImageTk

import config as C
from src.camera import open_camera, orient
from src.app import Engine

# --- paleta ---
BG = "#0d1117"
PANEL = "#161b22"
CARD = "#1c2330"
FG = "#e6edf3"
MUT = "#8b98a5"
ACC = "#3ddc84"
ACC2 = "#ff6b6b"
BLU = "#4aa3ff"
F = ("Segoe UI", 10)
FB = ("Segoe UI", 10, "bold")
FH = ("Segoe UI", 20, "bold")

MODE_INFO = {
    "mouse":    ("Modo raton", "indice arriba mueve · CURVA el indice = clic izq · ABRE el pulgar = der · mano plana = congela"),
    "keyboard": ("Modo teclado", "escribir letras en el aire (requiere grabar y entrenar)"),
    "gaming":   ("Modo teclado + raton", "mano dcha = raton · mano izq = teclas mantenidas (WASD...)"),
}
MODE_ORDER = ("mouse", "keyboard", "gaming")
SLIDERS = [
    ("MOUSE_GAIN", "Sensibilidad del raton", 0.3, 3.0, 0.05),
    ("MOUSE_SMOOTH", "Respuesta (menor = mas suave)", 0.10, 0.80, 0.01),
    ("MOUSE_DEADZONE", "Zona muerta (anti-tembleque)", 0.0, 0.0030, 0.0001),
    ("MOUSE_ACCEL", "Aceleracion de puntero", 0.0, 3.0, 0.1),
]
SETTINGS_PATH = C.APP_DIR / "settings.json"


def _spawn(cmd_args):
    if getattr(sys, "frozen", False):
        return [sys.executable] + cmd_args
    return [sys.executable, str(Path(__file__).resolve().parent.parent / "airkeys.py")] + cmd_args


class App:
    def __init__(self, root):
        self.root = root
        self.mode = "mouse"
        self.real = tk.BooleanVar(value=False)

        # motor en hilo
        self.stop_flag = threading.Event()
        self.worker = None
        self.frameq = queue.Queue(maxsize=1)
        self.errq = queue.Queue()
        self._imgtk = None

        root.title("AirKeys")
        root.configure(bg=BG)
        root.geometry("900x760")
        root.minsize(760, 640)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        # cabecera
        head = tk.Frame(root, bg=BG)
        head.pack(fill="x", padx=22, pady=(16, 6))
        tk.Label(head, text="AirKeys", font=FH, fg=FG, bg=BG).pack(side="left")
        tk.Label(head, text="  raton y teclado invisibles", font=F, fg=MUT,
                 bg=BG).pack(side="left", pady=(8, 0))
        tk.Button(head, text="⚙  Ajustes y calibracion", font=F, bg=CARD, fg=FG,
                  bd=0, padx=12, pady=6, activebackground="#242c3a",
                  command=self.open_settings).pack(side="right")

        # video
        self.video = tk.Label(root, bg="#05070a", fg=MUT, font=("Segoe UI", 13),
                              text="\n\n▶  Elige un modo y pulsa Iniciar\n\n"
                                   "el video aparecera aqui")
        self.video.pack(fill="both", expand=True, padx=22, pady=8)

        # estado
        self.status = tk.Label(root, text="listo", font=FB, fg=MUT, bg=BG, anchor="w")
        self.status.pack(fill="x", padx=24)

        # barra de control
        bar = tk.Frame(root, bg=BG)
        bar.pack(fill="x", padx=22, pady=(6, 4))
        seg = tk.Frame(bar, bg=BG)
        seg.pack(side="left")
        self.mode_btns = {}
        for m in MODE_ORDER:
            b = tk.Button(seg, text=MODE_INFO[m][0], font=FB, bd=0, padx=14, pady=9,
                          command=lambda mm=m: self.set_mode(mm))
            b.pack(side="left", padx=(0, 6))
            self.mode_btns[m] = b
        tk.Checkbutton(bar, text="Control REAL", variable=self.real, font=F, fg=FG,
                       bg=BG, selectcolor=BG, activebackground=BG,
                       activeforeground=ACC, highlightthickness=0).pack(side="left", padx=14)
        self.stop_btn = tk.Button(bar, text="■  Detener", font=FB, bg=CARD, fg=ACC2,
                                  bd=0, padx=16, pady=9, state="disabled",
                                  command=self.stop)
        self.stop_btn.pack(side="right")
        self.start_btn = tk.Button(bar, text="▶  Iniciar", font=FB, bg=ACC,
                                   fg="#07140d", bd=0, padx=22, pady=9,
                                   command=self.start)
        self.start_btn.pack(side="right", padx=8)

        self.hint = tk.Label(root, text=MODE_INFO["mouse"][1], font=("Segoe UI", 9),
                             fg=MUT, bg=BG, anchor="w")
        self.hint.pack(fill="x", padx=24, pady=(0, 14))

        self.set_mode("mouse")
        self.root.after(33, self._tick_video)

    # ---------------------------------------------------------------- modos
    def set_mode(self, m):
        self.mode = m
        for k, b in self.mode_btns.items():
            on = (k == m)
            b.configure(bg=ACC if on else CARD, fg="#07140d" if on else FG,
                        activebackground=ACC if on else "#242c3a")
        self.hint.configure(text=MODE_INFO[m][1])

    def _busy(self, running):
        self.start_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")
        for b in self.mode_btns.values():
            b.configure(state="disabled" if running else "normal")

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        self.stop_flag.clear()
        mode, real = self.mode, self.real.get()
        self.worker = threading.Thread(target=self._engine_loop, args=(mode, real),
                                       daemon=True)
        self.worker.start()
        self._busy(True)
        self.status.configure(text=f"iniciando {MODE_INFO[mode][0]}"
                              + ("  ·  CONTROL REAL" if real else "  ·  prueba"),
                              fg=ACC if real else BLU)

    def stop(self):
        self.stop_flag.set()
        if self.worker:
            self.worker.join(timeout=2.0)
        self.worker = None
        self._busy(False)
        self.status.configure(text="detenido", fg=MUT)
        self.video.configure(image="", text="\n\n▶  Elige un modo y pulsa Iniciar\n")
        self._imgtk = None

    def _engine_loop(self, mode, real):
        engine = cap = None
        try:
            engine = Engine(mode, real)
            cap = open_camera()
            while not self.stop_flag.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.01)
                    continue
                frame, _ = engine.process(orient(frame))
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if self.frameq.full():
                    try:
                        self.frameq.get_nowait()
                    except queue.Empty:
                        pass
                self.frameq.put(rgb)
        except Exception as e:
            self.errq.put(str(e))
        finally:
            if engine:
                engine.close()
            if cap:
                cap.release()

    def _tick_video(self):
        try:
            while True:
                self.status.configure(text="ERROR: " + self.errq.get_nowait(), fg=ACC2)
                self.stop()
        except queue.Empty:
            pass
        try:
            rgb = self.frameq.get_nowait()
            self._show(rgb)
            if self.worker and self.worker.is_alive():
                m = MODE_INFO[self.mode][0]
                self.status.configure(
                    text=f"{m} en marcha"
                    + ("  ·  CONTROL REAL" if self.real.get() else "  ·  prueba (no controla)"),
                    fg=ACC if self.real.get() else BLU)
        except queue.Empty:
            pass
        self.root.after(33, self._tick_video)

    def _show(self, rgb):
        vw = max(320, self.video.winfo_width())
        vh = max(240, self.video.winfo_height())
        h, w = rgb.shape[:2]
        s = min(vw / w, vh / h)
        img = Image.fromarray(rgb)
        if s < 0.999 or s > 1.001:
            img = img.resize((max(1, int(w * s)), max(1, int(h * s))), Image.BILINEAR)
        self._imgtk = ImageTk.PhotoImage(img)
        self.video.configure(image=self._imgtk, text="")

    # ---------------------------------------------------------- subprocesos
    def _run_tool(self, args, label):
        self.stop()
        try:
            subprocess.Popen(_spawn(args))
            self.status.configure(text=f"{label}: ventana abierta aparte…", fg=BLU)
        except Exception as e:
            messagebox.showerror("AirKeys", str(e))

    # ----------------------------------------------------------- ajustes
    def open_settings(self):
        win = tk.Toplevel(self.root, bg=BG)
        win.title("Ajustes y calibracion")
        win.geometry("440x560")
        win.configure(bg=BG)

        tk.Label(win, text="Calibracion", font=FB, fg=MUT, bg=BG).pack(
            anchor="w", padx=18, pady=(16, 4))
        cal = tk.Frame(win, bg=BG)
        cal.pack(fill="x", padx=14)
        for i, (txt, args) in enumerate([
            ("Calibrar raton", ["calibrate-mouse"]),
            ("Comprobar camara", ["check"]),
            ("Calibrar tap", ["calibrate-tap"]),
            ("Grabar teclado", ["record"]),
            ("Entrenar teclado", ["train"]),
        ]):
            tk.Button(cal, text=txt, font=F, bg=CARD, fg=FG, bd=0, padx=10, pady=7,
                      activebackground="#242c3a",
                      command=lambda a=args, t=txt: self._run_tool(a, t)).grid(
                row=i // 2, column=i % 2, padx=4, pady=4, sticky="ew")
        cal.grid_columnconfigure(0, weight=1)
        cal.grid_columnconfigure(1, weight=1)

        cur = {}
        if SETTINGS_PATH.exists():
            try:
                cur = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            except Exception:
                cur = {}

        tk.Label(win, text="Camara (montaje arriba)", font=FB, fg=MUT, bg=BG).pack(
            anchor="w", padx=18, pady=(16, 4))
        camf = tk.Frame(win, bg=BG)
        camf.pack(fill="x", padx=18)
        self.s_rot = tk.IntVar(value=int(cur.get("CAM_ROTATE", getattr(C, "CAM_ROTATE", 0))))
        self.s_flip = tk.BooleanVar(value=bool(cur.get("FLIP_HORIZONTAL", C.FLIP_HORIZONTAL)))
        tk.Label(camf, text="Rotar imagen", font=F, fg=FG, bg=BG).pack(side="left")
        tk.OptionMenu(camf, self.s_rot, 0, 90, 180, 270).pack(side="left", padx=8)
        tk.Checkbutton(camf, text="espejo", variable=self.s_flip, font=F, fg=FG,
                       bg=BG, selectcolor=BG, activebackground=BG, activeforeground=ACC,
                       highlightthickness=0).pack(side="left", padx=12)

        tk.Label(win, text="Raton", font=FB, fg=MUT, bg=BG).pack(
            anchor="w", padx=18, pady=(16, 4))
        self.s_vars = {}
        for key, label, lo, hi, res in SLIDERS:
            row = tk.Frame(win, bg=BG)
            row.pack(fill="x", padx=18, pady=1)
            tk.Label(row, text=label, font=("Segoe UI", 9), fg=FG, bg=BG, width=30,
                     anchor="w").pack(side="left")
            v = tk.DoubleVar(value=float(cur.get(key, getattr(C, key))))
            self.s_vars[key] = v
            tk.Scale(row, variable=v, from_=lo, to=hi, resolution=res,
                     orient="horizontal", bg=BG, fg=FG, troughcolor=CARD,
                     highlightthickness=0, bd=0, length=150).pack(side="right")

        def save():
            data = dict(cur)
            for k, v in self.s_vars.items():
                data[k] = round(float(v.get()), 6)
            data["CAM_ROTATE"] = int(self.s_rot.get())
            data["FLIP_HORIZONTAL"] = bool(self.s_flip.get())
            SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            messagebox.showinfo("AirKeys", "Ajustes guardados.\n"
                                "Se aplican al (re)iniciar un modo.")
            win.destroy()

        tk.Button(win, text="Guardar ajustes", font=FB, bg=ACC, fg="#07140d", bd=0,
                  padx=14, pady=8, command=save).pack(pady=18)

    def on_close(self):
        self.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
