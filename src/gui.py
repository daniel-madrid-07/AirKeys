"""Interfaz grafica de AirKeys (tkinter, sin dependencias extra).

Panel de control: elige modo, control real o prueba, calibraciones y ajustes.
Cada accion corre en un subproceso (la ventana de camara es la de OpenCV);
la GUI captura su salida en el panel de log y puede detenerlo.
"""
import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk
from pathlib import Path

import config as C

# --- paleta (oscuro, un acento) ---
BG = "#101418"
PANEL = "#1a2027"
FG = "#e8edf2"
MUT = "#8b98a5"
ACC = "#3ddc84"      # verde accion
ACC2 = "#ff5d5d"     # rojo detener
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_H = ("Segoe UI", 18, "bold")

# ajustes expuestos en la GUI: (clave, etiqueta, min, max, resolucion)
SLIDERS = [
    ("MOUSE_GAIN", "Sensibilidad del raton", 0.3, 3.0, 0.05),
    ("MOUSE_SMOOTH", "Rapidez de respuesta (menos = mas suave)", 0.10, 0.80, 0.01),
    ("MOUSE_DEADZONE", "Zona muerta (anti-tembleque)", 0.0, 0.0030, 0.0001),
    ("MOUSE_ACCEL", "Aceleracion de puntero", 0.0, 3.0, 0.1),
]


def _spawn_args(cmd_args):
    """Argumentos para lanzar un subcomando de AirKeys (dev o empaquetado)."""
    if getattr(sys, "frozen", False):
        return [sys.executable] + cmd_args
    return [sys.executable, str(Path(__file__).resolve().parent.parent / "airkeys.py")] + cmd_args


class App:
    def __init__(self, root):
        self.root = root
        self.proc = None
        self.logq = queue.Queue()

        root.title("AirKeys")
        root.configure(bg=BG)
        root.geometry("560x680")
        root.minsize(520, 600)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        head = tk.Frame(root, bg=BG)
        head.pack(fill="x", padx=18, pady=(14, 4))
        tk.Label(head, text="AirKeys", font=FONT_H, fg=FG, bg=BG).pack(anchor="w")
        tk.Label(head, text="raton y teclado invisibles por camara",
                 font=FONT, fg=MUT, bg=BG).pack(anchor="w")

        # --- modos ---
        modes = tk.LabelFrame(root, text=" Modo ", font=FONT_B, fg=MUT, bg=PANEL,
                              bd=0, labelanchor="nw")
        modes.pack(fill="x", padx=18, pady=8, ipady=6)
        self.mode = tk.StringVar(value="mouse")
        for val, txt, sub in [
            ("mouse", "Raton", "puño mueve · indice clic izq · corazon clic der"),
            ("gaming", "Gaming", "mano dcha raton · mano izq teclas mantenidas"),
            ("keyboard", "Teclado", "escribir letras (requiere entrenar)"),
        ]:
            row = tk.Frame(modes, bg=PANEL)
            row.pack(fill="x", padx=10, pady=2)
            tk.Radiobutton(row, text=txt, variable=self.mode, value=val,
                           font=FONT_B, fg=FG, bg=PANEL, selectcolor=BG,
                           activebackground=PANEL, activeforeground=ACC,
                           highlightthickness=0).pack(side="left")
            tk.Label(row, text=sub, font=("Segoe UI", 8), fg=MUT, bg=PANEL).pack(
                side="left", padx=8)

        ctl = tk.Frame(root, bg=BG)
        ctl.pack(fill="x", padx=18, pady=4)
        self.real = tk.BooleanVar(value=False)
        tk.Checkbutton(ctl, text="Control REAL (mueve raton / teclea de verdad)",
                       variable=self.real, font=FONT, fg=FG, bg=BG, selectcolor=BG,
                       activebackground=BG, activeforeground=ACC,
                       highlightthickness=0).pack(anchor="w")
        btns = tk.Frame(ctl, bg=BG)
        btns.pack(fill="x", pady=6)
        self.start_btn = tk.Button(btns, text="▶  INICIAR", font=FONT_B,
                                   bg=ACC, fg="#08130c", bd=0, padx=18, pady=8,
                                   activebackground="#2fbf70", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = tk.Button(btns, text="■  Detener", font=FONT_B,
                                  bg=PANEL, fg=ACC2, bd=0, padx=14, pady=8,
                                  activebackground="#242c35", command=self.stop,
                                  state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        self.status = tk.Label(btns, text="listo", font=FONT, fg=MUT, bg=BG)
        self.status.pack(side="left", padx=10)

        # --- preparacion ---
        prep = tk.LabelFrame(root, text=" Preparacion ", font=FONT_B, fg=MUT,
                             bg=PANEL, bd=0)
        prep.pack(fill="x", padx=18, pady=8, ipady=4)
        grid = tk.Frame(prep, bg=PANEL)
        grid.pack(padx=10, pady=6)
        for i, (txt, args) in enumerate([
            ("Calibrar raton", ["calibrate-mouse"]),
            ("Comprobar camara", ["check"]),
            ("Grabar teclado", ["record"]),
            ("Entrenar teclado", ["train"]),
            ("Calibrar tap", ["calibrate-tap"]),
        ]):
            tk.Button(grid, text=txt, font=FONT, bg=BG, fg=FG, bd=0, padx=10,
                      pady=6, activebackground="#242c35", activeforeground=FG,
                      command=lambda a=args: self.run_tool(a)).grid(
                row=i // 3, column=i % 3, padx=4, pady=4, sticky="ew")

        # --- ajustes ---
        conf = tk.LabelFrame(root, text=" Ajustes ", font=FONT_B, fg=MUT,
                             bg=PANEL, bd=0)
        conf.pack(fill="x", padx=18, pady=8, ipady=4)
        self.vars = {}
        for key, label, lo, hi, res in SLIDERS:
            row = tk.Frame(conf, bg=PANEL)
            row.pack(fill="x", padx=10, pady=1)
            tk.Label(row, text=label, font=("Segoe UI", 9), fg=FG, bg=PANEL,
                     width=38, anchor="w").pack(side="left")
            v = tk.DoubleVar(value=float(getattr(C, key)))
            self.vars[key] = v
            tk.Scale(row, variable=v, from_=lo, to=hi, resolution=res,
                     orient="horizontal", bg=PANEL, fg=FG, troughcolor=BG,
                     highlightthickness=0, bd=0, length=170,
                     font=("Segoe UI", 7)).pack(side="right")
        # camara: orientacion (util para montaje cenital/arriba)
        camrow = tk.Frame(conf, bg=PANEL)
        camrow.pack(fill="x", padx=10, pady=(4, 0))
        tk.Label(camrow, text="Camara (montaje arriba)", font=("Segoe UI", 9),
                 fg=FG, bg=PANEL, width=38, anchor="w").pack(side="left")
        self.cam_flip = tk.BooleanVar(value=bool(C.FLIP_HORIZONTAL))
        tk.Checkbutton(camrow, text="espejo", variable=self.cam_flip, font=("Segoe UI", 9),
                       fg=FG, bg=PANEL, selectcolor=BG, activebackground=PANEL,
                       activeforeground=ACC, highlightthickness=0).pack(side="right")
        self.cam_rotate = tk.IntVar(value=int(getattr(C, "CAM_ROTATE", 0)))
        tk.Label(camrow, text="rotar", font=("Segoe UI", 9), fg=MUT, bg=PANEL).pack(
            side="right", padx=(0, 4))
        tk.OptionMenu(camrow, self.cam_rotate, 0, 90, 180, 270).pack(side="right")

        tk.Button(conf, text="Guardar ajustes", font=FONT, bg=BG, fg=ACC, bd=0,
                  padx=10, pady=5, activebackground="#242c35",
                  command=self.save_settings).pack(anchor="e", padx=10, pady=6)

        # --- log ---
        self.log = tk.Text(root, height=7, bg="#0b0e11", fg=MUT, bd=0,
                           font=("Consolas", 8), state="disabled")
        self.log.pack(fill="both", expand=True, padx=18, pady=(4, 14))
        self._log("AirKeys listo. Elige modo y pulsa INICIAR. "
                  "Los modos abren en PRUEBA salvo que marques Control REAL.")
        self.root.after(150, self._poll)

    # ------------------------------------------------------------ helpers
    def _log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _reader(self, proc):
        for line in iter(proc.stdout.readline, b""):
            try:
                self.logq.put(line.decode("utf-8", "replace"))
            except Exception:
                pass
        proc.wait()
        self.logq.put(f"__EXIT__{proc.returncode}")

    def _poll(self):
        try:
            while True:
                line = self.logq.get_nowait()
                if line.startswith("__EXIT__"):
                    self._log(f"[proceso terminado, codigo {line[8:]}]")
                    self.proc = None
                    self._set_running(False)
                else:
                    self._log(line)
        except queue.Empty:
            pass
        self.root.after(150, self._poll)

    def _set_running(self, running, what=""):
        self.start_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")
        self.status.configure(text=what if running else "listo",
                              fg=ACC if running else MUT)

    def _launch(self, args):
        if self.proc:
            self._log("Ya hay un proceso corriendo. Detenlo primero.")
            return
        flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        self.proc = subprocess.Popen(
            _spawn_args(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=flags)
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        self._set_running(True, " ".join(args))
        self._log(f"> {' '.join(args)}")

    # ------------------------------------------------------------ acciones
    def start(self):
        args = [self.mode.get()] + (["--real"] if self.real.get() else [])
        self._launch(args)

    def run_tool(self, args):
        self._launch(args)

    def stop(self):
        if self.proc:
            self.proc.kill()
            self._log("[detenido]")
            self.proc = None
        self._set_running(False)

    def save_settings(self):
        path = C.APP_DIR / "settings.json"
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        for key, var in self.vars.items():
            data[key] = round(float(var.get()), 6)
        data["CAM_ROTATE"] = int(self.cam_rotate.get())
        data["FLIP_HORIZONTAL"] = bool(self.cam_flip.get())
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._log(f"Ajustes guardados en {path.name}. "
                  "Se aplican al (re)iniciar un modo.")

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
