"""Prueba del raton.

    python -m tools.mouse_test          # solo visual (NO toca tu cursor)
    python -m tools.mouse_test --move   # mueve el cursor y clicka de verdad

Que ver:
  - mini-mapa (arriba-dcha) = escritorio completo; punto = cursor virtual.
  - mano en PUÑO y moviendola -> el punto se mueve (relativo, como un raton).
  - SACAR el INDICE = boton IZQUIERDO mantenido (mientras este fuera).
  - SACAR el MEDIO  = boton DERECHO mantenido.
  - mano PLANA y ABIERTA = congelado (reposicionar sin mover el cursor).
ESC o q para salir.
"""
import argparse
import time

import cv2

import config as C
from src.hand_tracker import HandTracker, draw
from src.camera import open_camera, orient
from src.mouse_control import (VirtualMouse, FingerButtons, MouseOut,
                               hand_bbox, hand_mask, _pick_hand)
from src.flow_sensor import FlowSensor

WIN = "AirKeys - mouse (ESC/q)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--move", action="store_true",
                    help="mover el cursor real y accionar los botones")
    args = ap.parse_args()

    out = MouseOut(args.move)
    if args.move:
        print("[MOUSE] --move ACTIVO: cursor y BOTONES reales (se sueltan al salir).")

    mouse = VirtualMouse()
    buttons = FingerButtons()
    flow = FlowSensor()
    print("[MOUSE] movimiento por FLUJO OPTICO. Puño=mover, levantar indice=IZQ, "
          "sacar medio=DER, mano plana=congelar.")

    tracker = HandTracker()
    cap = open_camera()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = orient(frame)
            now = time.perf_counter()
            feat, res = tracker.process(frame)
            draw(frame, res)
            h, w = frame.shape[:2]

            # flujo optico: delta sub-pixel SOLO de la piel de la mano (mascara)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mask = hand_mask(res, w, h)
            bbox = hand_bbox(res, w, h)          # solo para dibujar
            d_px = flow.delta(gray, mask)
            ext = (d_px[0] / w, d_px[1] / h) if d_px is not None else None
            info = mouse.update(res, now, ext_delta=ext)

            # botones por dedos (no mientras congelado)
            lms = _pick_hand(res, C.MOUSE_HAND)
            ev = buttons.update(lms, info["frozen"] if info else True)
            out.apply(ev)

            if bbox:
                cv2.rectangle(frame, bbox[:2], bbox[2:], (255, 200, 0), 1)
                cv2.putText(frame, f"flow pts:{flow.n_good}", (12, h - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)

            # mini-mapa del escritorio completo
            mw, mh, mx, my = 260, int(260 * mouse.vh / mouse.vw), w - 280, 20
            cv2.rectangle(frame, (mx, my), (mx + mw, my + mh), (200, 200, 200), 2)
            cv2.putText(frame, "escritorio", (mx, my - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

            if info:
                col = (0, 165, 255) if info["frozen"] else (0, 255, 0)
                dot = (mx + int(info["nx"] * mw), my + int(info["ny"] * mh))
                cv2.circle(frame, dot, 6, col, -1)
                estado = "PLANA (congelado)" if info["frozen"] else "moviendo"
                cv2.putText(frame,
                            f"{estado}  recto:{info['straight']:.2f}  "
                            f"izq(lift):{ev['lift']:+.2f}  der:{ev['mid']:.2f}",
                            (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
                if not info["frozen"]:
                    out.move(info["sx"], info["sy"])
            else:
                cv2.putText(frame, "sin mano", (12, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # indicadores de boton mantenido
            if ev["left"]:
                cv2.putText(frame, "IZQ", (12, 95), cv2.FONT_HERSHEY_SIMPLEX,
                            1.2, (0, 0, 255), 3)
            if ev["right"]:
                cv2.putText(frame, "DER", (150, 95), cv2.FONT_HERSHEY_SIMPLEX,
                            1.2, (255, 0, 0), 3)

            cv2.imshow(WIN, frame)
            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord("q")):
                break
            # cerrar con la X de la ventana tambien termina limpio
            if cv2.getWindowProperty(WIN, cv2.WND_PROP_VISIBLE) < 1:
                break
    except KeyboardInterrupt:
        pass
    finally:
        out.release_all()                   # SIEMPRE soltar botones
        cap.release()
        cv2.destroyAllWindows()
        tracker.close()


if __name__ == "__main__":
    main()
