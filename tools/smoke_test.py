"""Prueba de humo del pipeline SIN camara ni MediaPipe.

Fabrica un dataset sintetico donde cada tecla tiene una 'firma' distinta en los
landmarks, lo guarda, entrena unas pocas epocas y comprueba que el modelo aprende.
Si esto pasa, el flujo dataset -> modelo -> train -> load funciona.

    python -m tools.smoke_test
"""
import numpy as np
import torch

import config as C
from src.dataset import build_label_maps, _windows_from_session, WindowDataset
from src.model import KeyGRU, save, load


def make_synth_session(n_frames=4000, seed=0):
    rng = np.random.default_rng(seed)
    classes, to_idx = build_label_maps()
    keys = C.TARGET_KEYS
    # firma fija por tecla en el espacio de features
    sigs = {k: rng.normal(0, 1, C.FEATURE_DIM).astype(np.float32) for k in keys}

    feats = rng.normal(0, 0.05, (n_frames, C.FEATURE_DIM)).astype(np.float32)
    labels = [C.NONE_LABEL] * n_frames
    i = C.WINDOW
    while i < n_frames - C.WINDOW:
        if rng.random() < 0.12:                 # ~12% de frames son pulsacion
            k = keys[rng.integers(len(keys))]
            feats[i] += sigs[k]                  # inyecta la firma en el frame central
            labels[i] = k
            i += rng.integers(3, 8)
        else:
            i += 1
    return feats, labels


def main():
    torch.manual_seed(0)
    classes, to_idx = build_label_maps()

    feats, labels = make_synth_session()
    X, y = _windows_from_session(feats, labels, to_idx)
    print(f"[SMOKE] ventanas={len(X)}  con_tecla={(y!=0).sum()}  clases={len(classes)}")

    ds = WindowDataset(X, y)
    dl = torch.utils.data.DataLoader(ds, batch_size=128, shuffle=True)

    model = KeyGRU(len(classes))
    counts = np.bincount(y, minlength=len(classes))
    w = np.array([1.0 / n if n else 0.0 for n in counts], np.float32)
    w /= w.max(); w[0] *= C.NONE_WEIGHT
    crit = torch.nn.CrossEntropyLoss(weight=torch.tensor(w))
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)

    for ep in range(8):
        model.train()
        for xb, yb in dl:
            opt.zero_grad(); loss = crit(model(xb), yb); loss.backward(); opt.step()

    # accuracy sobre frames con tecla
    model.eval()
    with torch.no_grad():
        pred = model(ds.X).argmax(1)
    m = ds.y != 0
    acc = float((pred[m] == ds.y[m]).float().mean())
    print(f"[SMOKE] acc_teclas={acc:.3f}")

    save(model, classes, C.MODEL_DIR / "_smoke.pt")
    m2, cls2 = load(C.MODEL_DIR / "_smoke.pt")
    assert cls2 == classes
    (C.MODEL_DIR / "_smoke.pt").unlink()
    assert acc > 0.9, "el modelo no aprendio la senal sintetica"
    print("[SMOKE] OK: dataset->modelo->train->save/load funcionan.")


if __name__ == "__main__":
    main()
