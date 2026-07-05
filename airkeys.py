#!/usr/bin/env python
"""AirKeys — teclado y raton invisibles por camara.

Punto de entrada unico. Sin argumentos abre un menu. Con argumentos, directo:

    python airkeys.py                 # menu interactivo
    python airkeys.py mouse           # modo raton (prueba, no controla)
    python airkeys.py mouse --real    # modo raton con control real
    python airkeys.py gaming --real   # raton + teclado
    python airkeys.py calibrate-mouse # calibrar ejes del raton
    python airkeys.py calibrate-tap   # sugerir umbrales de pulsacion
    python airkeys.py record          # grabar datos de teclado (guiado)
    python airkeys.py train           # entrenar el modelo de teclado
    python airkeys.py check           # comprobar camara y entorno
"""
import argparse
import sys

BANNER = r"""
   _   _      _  __
  /_\ (_)_ _ | |/ /___ _  _ ___
 / _ \| | '_|| ' </ -_) || (_-<
/_/ \_\_|_|  |_|\_\___|\_, /__/
                       |__/   raton y teclado invisibles
"""

MENU = """
  MODOS
   1) Raton            (mano derecha: mover + clicks)
   2) Teclado          (taps -> teclas)  [requiere entrenar]
   3) Gaming           (raton + teclado a la vez)

  PREPARACION
   4) Calibrar raton   (2 gestos: derecha, alante)
   5) Calibrar tap     (umbrales de pulsacion desde tus datos)
   6) Grabar teclado   (grabador guiado por metronomo)
   7) Entrenar teclado
   8) Comprobar camara / entorno

   0) Salir
"""


def _run_mode(mode, real):
    from src.app import run
    run(mode, type_real=real)


def _dispatch(cmd, real):
    if cmd in ("mouse", "keyboard", "gaming"):
        _run_mode(cmd, real)
    elif cmd == "calibrate-mouse":
        from tools import calibrate_mouse
        calibrate_mouse.main()
    elif cmd == "calibrate-tap":
        from tools import calibrate_tap
        sys.argv = ["calibrate_tap"]
        calibrate_tap.main()
    elif cmd == "record":
        from src import record_air
        sys.argv = ["record_air"]
        record_air.main()
    elif cmd == "train":
        from src import train
        train.main()
    elif cmd == "check":
        from tools import check_setup
        sys.argv = ["check_setup", "--cam"]
        check_setup.main()
    else:
        print(f"Comando desconocido: {cmd}")


def _menu():
    print(BANNER)
    while True:
        print(MENU)
        choice = input("  Elige opcion: ").strip()
        real = {"1": "mouse", "2": "keyboard", "3": "gaming"}.get(choice)
        try:
            if real:
                r = input("  ¿Control REAL? (s = controla de verdad / Enter = prueba): ")
                _run_mode(real, r.strip().lower() == "s")
            elif choice == "4":
                _dispatch("calibrate-mouse", False)
            elif choice == "5":
                _dispatch("calibrate-tap", False)
            elif choice == "6":
                _dispatch("record", False)
            elif choice == "7":
                _dispatch("train", False)
            elif choice == "8":
                _dispatch("check", False)
            elif choice == "0":
                return
            else:
                print("  Opcion no valida.")
        except FileNotFoundError as e:
            print(f"\n[!] {e}\n")
        except Exception as e:
            print(f"\n[!] Error: {e}\n")


def main():
    ap = argparse.ArgumentParser(description="AirKeys")
    ap.add_argument("command", nargs="?", help="mouse|keyboard|gaming|calibrate-mouse|"
                    "calibrate-tap|record|train|check|menu (sin comando = ventana)")
    ap.add_argument("--real", action="store_true",
                    help="control real (envia teclas/clicks). Sin esto = modo prueba.")
    args = ap.parse_args()
    if args.command == "menu":
        _menu()
    elif args.command:
        _dispatch(args.command, args.real)
    else:
        from src.gui import main as gui_main   # sin argumentos -> aplicacion
        gui_main()


if __name__ == "__main__":
    main()
