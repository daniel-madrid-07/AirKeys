"""Teclado de GAMING sin modelo: cada dedo de la mano izquierda = UNA tecla.

Dedo BAJADO (punta por debajo de su reposo) = tecla APRETADA y se mantiene mientras
siga abajo; dedo arriba = se suelta. Como mantener W para correr. No hay IA: mapeo
fijo en config.GAMING_KEYS. Reutilizado por el modo 'gaming' de src/app.py.
"""
import atexit

import config as C
from src.fingers import _hand_slot
from src.tap import finger_signal, present


class KeyOut:
    """Salida real de teclado (pynput) con anti-tecla-pegada (atexit)."""

    def __init__(self, enabled):
        self.kb = None
        self.down = set()
        if not enabled:
            return
        from pynput.keyboard import Controller, Key
        self.kb = Controller()
        self.Key = Key
        atexit.register(self.release_all)

    def _key(self, name):
        return getattr(self.Key, name) if len(name) > 1 else name

    def press(self, name):
        if self.kb and name not in self.down:
            self.kb.press(self._key(name))
            self.down.add(name)

    def release(self, name):
        if self.kb and name in self.down:
            self.kb.release(self._key(name))
            self.down.discard(name)

    def release_all(self):
        if not self.kb:
            return
        for name in list(self.down):
            try:
                self.kb.release(self._key(name))
            except Exception:
                pass
        self.down.clear()


class HeldFingerKeys:
    """Mano de gaming: dedo BAJADO = tecla mantenida. Baseline adaptativo por dedo,
    histeresis. finger_signal ya viene normalizado por tamaño de mano."""

    def __init__(self, out, hand=None):
        self.out = out
        self.slot = _hand_slot(hand or C.GAMING_HAND)
        self.keys = dict(C.GAMING_KEYS)          # finger -> nombre de tecla
        self.base = {f: None for f in self.keys}
        self.down = {f: False for f in self.keys}

    def update(self, feat):
        """Procesa un frame. Actualiza teclas mantenidas. Devuelve {finger: bool}."""
        if not present(feat, self.slot):
            for f in list(self.keys):
                if self.down[f]:
                    self.out.release(self.keys[f]); self.down[f] = False
            return dict(self.down)

        for f, key in self.keys.items():
            s = finger_signal(feat, self.slot, f)
            if self.base[f] is None:
                self.base[f] = s
            if not self.down[f]:
                # sigue el reposo mientras el dedo no este bajando
                if s < self.base[f] + C.GAMING_PRESS * 0.5:
                    a = C.GAMING_BASE_ALPHA
                    self.base[f] = (1 - a) * self.base[f] + a * s
                if s > self.base[f] + C.GAMING_PRESS:
                    self.down[f] = True
                    self.out.press(key)
            else:
                if s < self.base[f] + C.GAMING_RELEASE:
                    self.down[f] = False
                    self.out.release(key)
        return dict(self.down)

    def close(self):
        self.out.release_all()
