"""Carga los .npz grabados y construye ventanas temporales etiquetadas.

Cada muestra = ventana de WINDOW frames consecutivos.
La etiqueta de la muestra = etiqueta del frame CENTRAL.
Esto convierte el problema en clasificacion de secuencias.
"""
import glob

import numpy as np
import torch
from torch.utils.data import Dataset

import config as C


def build_label_maps():
    classes = [C.NONE_LABEL] + C.TARGET_KEYS
    to_idx = {c: i for i, c in enumerate(classes)}
    return classes, to_idx


def _windows_from_session(feats, labels, to_idx):
    n = len(feats)
    X, y = [], []
    for start in range(0, n - C.WINDOW + 1):
        center = start + C.CENTER
        lbl = labels[center]
        if lbl not in to_idx:            # tecla fuera de TARGET_KEYS -> se ignora
            continue
        X.append(feats[start:start + C.WINDOW])
        y.append(to_idx[lbl])
    if not X:
        return np.empty((0, C.WINDOW, C.FEATURE_DIM), np.float32), np.empty((0,), np.int64)
    return np.stack(X).astype(np.float32), np.array(y, np.int64)


def load_all(pattern=None):
    pattern = pattern or str(C.DATA_DIR / "*.npz")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No hay datasets en {pattern}. Graba con record_dataset.")
    _, to_idx = build_label_maps()
    Xs, ys = [], []
    for f in files:
        d = np.load(f, allow_pickle=False)
        feats = d["features"]
        labels = [s for s in d["labels"].astype(str)]
        X, y = _windows_from_session(feats, labels, to_idx)
        if len(X):
            Xs.append(X)
            ys.append(y)
    X = np.concatenate(Xs)
    y = np.concatenate(ys)
    return X, y, files


class WindowDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.from_numpy(X)
        self.y = torch.from_numpy(y)

    def __len__(self):
        return len(self.y)

    def __getitem__(self, i):
        return self.X[i], self.y[i]
