"""Calibracion de teclas por VOZ: golpea una tecla en el aire y DI su letra.

    python airkeys.py calibrate-keys

Flujo:
  1. Apoya las dos manos en la mesa (posicion home) hasta calibrar.
  2. Golpea cualquier tecla imaginaria y di su nombre por el micro ("a", "jota",
     "espacio"...). El golpe y la voz se emparejan y esa posicion queda
     registrada para esa tecla.
  3. El teclado dibujado abajo se va coloreando: gris = sin muestras,
     amarillo = 1-2, verde = 3+ (suficiente). Di "borrar" para descartar la
     ultima muestra si el reconocedor se equivoco.
  4. ESC/q para salir: se ajusta el mapa (mediana robusta por tecla) y el modo
     Teclado pasa a usar TUS posiciones en vez de la rejilla ideal.

Muestras crudas -> data/kb_calib.json (acumulan entre sesiones).
Mapa ajustado   -> models/kb_map.json.

Voz: reconocedor de Windows OFFLINE (System.Speech via pythonnet) con gramatica
cerrada de ~30 palabras -> robusto. Sin microfono/reconocedor cae a modo GUIADO:
la pantalla te dice que tecla golpear.
"""
import json
import time
import winsound
from collections import deque

import cv2

import config as C
from src.camera import open_camera, orient
from src.fingers import _hand_slot
from src.hand_tracker import HandTracker, draw
from src.tap import present
from src.keyboard_geo import (GeoKeyboard, KEY_GRID, SAMPLES_PATH, MAP_PATH,
                              fit_map, save_map)

# palabra reconocida -> tecla
WORD2KEY = {
    "a": "a", "be": "b", "ce": "c", "de": "d", "e": "e", "efe": "f", "ge": "g",
    "hache": "h", "i": "i", "jota": "j", "ka": "k", "ele": "l", "eme": "m",
    "ene": "n", "o": "o", "pe": "p", "cu": "q", "erre": "r", "ese": "s",
    "te": "t", "u": "u", "uve": "v", "uve doble": "w", "equis": "x",
    "i griega": "y", "ye": "y", "zeta": "z", "espacio": "space",
    # alfabeto radiofonico: inequivoco para las letras que suenan parecido
    # (be/de/e/pe/te/ce...). Di "delta" si "de" se confunde.
    "alfa": "a", "bravo": "b", "charli": "c", "delta": "d", "eco": "e",
    "foxtrot": "f", "golf": "g", "hotel": "h", "india": "i", "julieta": "j",
    "kilo": "k", "lima": "l", "madrid": "m", "noviembre": "n", "oscar": "o",
    "papa": "p", "quebec": "q", "romeo": "r", "sierra": "s", "tango": "t",
    "uniforme": "u", "victor": "v", "whisky": "w", "yanqui": "y", "zulu": "z",
}
DELETE_WORDS = ("borrar", "borra")
GOAL = 3            # muestras por tecla para darla por calibrada
_SPEECH_DLL = (r"C:\Windows\Microsoft.NET\assembly\GAC_MSIL\System.Speech"
               r"\v4.0_4.0.0.0__31bf3856ad364e35\System.Speech.dll")


class Voice:
    """Reconocedor de Windows (offline) con gramatica cerrada. events = deque de
    (t, palabra). Lanza excepcion si no hay reconocedor/microfono."""

    def __init__(self):
        import clr
        clr.AddReference(_SPEECH_DLL)
        from System.Speech.Recognition import (SpeechRecognitionEngine,
                                               GrammarBuilder, Choices, Grammar,
                                               RecognizeMode)
        self.events = deque()
        eng = SpeechRecognitionEngine()
        gb = GrammarBuilder()
        gb.Culture = eng.RecognizerInfo.Culture
        gb.Append(Choices(list(WORD2KEY.keys()) + list(DELETE_WORDS)))
        eng.LoadGrammar(Grammar(gb))
        eng.SetInputToDefaultAudioDevice()
        eng.SpeechRecognized += self._on
        self.level_max = 0            # para detectar micro por defecto MUDO
        self.t0 = time.perf_counter()
        eng.AudioLevelUpdated += self._on_level
        eng.RecognizeAsync(RecognizeMode.Multiple)
        self.eng = eng

    @property
    def mic_dead(self):
        return (self.level_max == 0 and
                time.perf_counter() - self.t0 > 6.0)

    def _on(self, sender, e):
        if e.Result.Confidence >= C.KB_VOICE_CONF:
            self.events.append((time.perf_counter(), e.Result.Text.lower()))

    def _on_level(self, sender, e):
        self.level_max = max(self.level_max, e.AudioLevel)

    def close(self):
        try:
            self.eng.RecognizeAsyncCancel()
        except Exception:
            pass


def _load_samples():
    if SAMPLES_PATH.exists():
        try:
            d = json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))
            if isinstance(d, list):
                return d
        except Exception:
            pass
    return []


def _save_samples(samples):
    SAMPLES_PATH.write_text(json.dumps(samples, indent=0), encoding="utf-8")


# --------------------------------------------------------------- overlay
_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]


def _draw_progress(frame, counts, msg, sub):
    h, w = frame.shape[:2]
    kw, gap = 46, 6
    y0 = h - 4 * (kw // 2 + gap) - 46
    overlay = frame.copy()
    for r, row in enumerate(_ROWS):
        x0 = (w - len(row) * (kw + gap)) // 2 + r * (kw // 2)
        for i, k in enumerate(row):
            n = counts.get(k, 0)
            color = ((70, 70, 70) if n == 0 else
                     (60, 190, 230) if n < GOAL else (90, 200, 90))
            x = x0 + i * (kw + gap)
            y = y0 + r * (kw // 2 + gap) * 2 // 2 + r * (kw // 2 + gap)
            cv2.rectangle(overlay, (x, y), (x + kw, y + kw // 2 + 14), color, -1)
            cv2.putText(overlay, k.upper(), (x + kw // 3, y + kw // 2 + 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (15, 15, 15), 2)
    # barra espaciadora
    n = counts.get("space", 0)
    color = ((70, 70, 70) if n == 0 else
             (60, 190, 230) if n < GOAL else (90, 200, 90))
    sx = (w - 5 * (kw + gap)) // 2
    sy = y0 + 3 * (kw // 2 + gap + kw // 2)
    cv2.rectangle(overlay, (sx, sy), (sx + 5 * (kw + gap), sy + kw // 2), color, -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    cv2.putText(frame, msg, (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 255), 2)
    cv2.putText(frame, sub, (16, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)


def main():
    try:
        voice = Voice()
        print("[CAL] Voz OK (reconocedor de Windows, offline).")
    except Exception as e:
        voice = None
        print(f"[CAL] Sin voz ({e}); modo GUIADO: golpea la tecla que se muestre.")

    samples = _load_samples()
    counts = {}
    for s in samples:
        counts[s["key"]] = counts.get(s["key"], 0) + 1

    tracker = HandTracker()
    cap = open_camera()
    kb = GeoKeyboard(use_map=False)         # solo deteccion de strikes, sin decodificar
    pend_strikes = deque()                  # strikes sin etiqueta: (t, ev)
    last_info = ""
    guided = [k for row in _ROWS for k in row] + ["space"]
    gi = 0
    was_calibrated = False
    slot_l, slot_r = _hand_slot("Left"), _hand_slot("Right")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = orient(frame)
            now = time.perf_counter()
            feat, res = tracker.process(frame)
            draw(frame, res)

            for ev in kb.strikes(feat, now):
                pend_strikes.append((now, ev))
            while pend_strikes and now - pend_strikes[0][0] > C.KB_VOICE_PAIR_S:
                pend_strikes.popleft()

            if voice:
                while voice.events:
                    tv, word = voice.events.popleft()
                    if word in DELETE_WORDS:
                        if samples:
                            gone = samples.pop()
                            counts[gone["key"]] -= 1
                            _save_samples(samples)
                            last_info = f"borrada ultima muestra ({gone['key']})"
                            winsound.Beep(330, 120)
                        continue
                    key = WORD2KEY.get(word)
                    if not key or not pend_strikes:
                        last_info = f'oi "{word}" pero no vi golpe: golpea y habla a la vez'
                        continue
                    ts, ev = min(pend_strikes, key=lambda p: abs(p[0] - tv))
                    pend_strikes.remove((ts, ev))
                    samples.append({"key": key, **ev})
                    counts[key] = counts.get(key, 0) + 1
                    _save_samples(samples)
                    last_info = f'"{word}" -> {key.upper()}  ({counts[key]}/{GOAL})'
                    winsound.Beep(880, 70)
            else:
                # modo guiado: cada strike es la tecla mostrada
                while gi < len(guided) and counts.get(guided[gi], 0) >= GOAL:
                    gi += 1
                if gi < len(guided) and pend_strikes:
                    _, ev = pend_strikes.popleft()
                    key = guided[gi]
                    samples.append({"key": key, **ev})
                    counts[key] = counts.get(key, 0) + 1
                    _save_samples(samples)
                    last_info = f"{key.upper()}  ({counts[key]}/{GOAL})"
                    winsound.Beep(880, 70)

            calibrated = kb.calibrated
            if calibrated and not was_calibrated:
                was_calibrated = True
                winsound.Beep(660, 90)
                winsound.Beep(990, 130)
            done = sum(1 for k in guided if counts.get(k, 0) >= GOAL)
            hands_seen = present(feat, slot_l) or present(feat, slot_r)
            if not hands_seen:
                msg = "NO VEO LAS MANOS - apunta la camara a la mesa"
            elif not calibrated:
                pct = int(kb.calib_progress * 100)
                msg = f"Apoya las manos QUIETAS en la mesa (ASDF - JKL)... {pct}%"
            elif voice and voice.mic_dead:
                msg = "MICRO SIN SEÑAL: cambia la entrada por defecto en Windows (Sonido)"
            elif voice:
                msg = "Golpea una tecla y DI su letra  (\"borrar\" descarta)"
            else:
                nxt = guided[gi].upper() if gi < len(guided) else "COMPLETO"
                msg = f"Golpea: {nxt}"
            _draw_progress(frame, counts,
                           msg, f"{done}/{len(guided)} teclas listas   "
                                f"{len(samples)} muestras   ESC/q guarda y sale   "
                                f"{last_info}")

            cv2.imshow("AirKeys - calibrar teclas (ESC/q para salir)", frame)
            k = cv2.waitKey(1) & 0xFF
            if k in (27, ord("q")):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        tracker.close()
        if voice:
            voice.close()

    if samples:
        kmap = fit_map(samples)
        save_map(kmap)
        print(f"[CAL] {len(samples)} muestras -> {MAP_PATH} ({len(kmap)} teclas).")
        print("[CAL] El modo Teclado usara TUS posiciones a partir de ahora.")
    else:
        print("[CAL] Sin muestras; nada guardado.")


if __name__ == "__main__":
    main()
