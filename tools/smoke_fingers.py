"""Prueba de humo del modelo multi-experto SIN camara.

Fabrica datos donde la firma de cada tecla se inyecta SOLO en los landmarks de su
dedo. Si el modelo aprende, el recorte por dedo (fingers.py) esta bien conectado.

    python -m tools.smoke_fingers
"""
import numpy as np
import torch

import config as C
from src.dataset import build_label_maps, _windows_from_session
from src.fingers import build_experts, finger_indices, FINGER_MAP
from src.model import MultiFingerModel, save_fingers, load_fingers


def make_synth(n_frames=6000, seed=0):
    rng = np.random.default_rng(seed)
    keys = [k for k in C.TARGET_KEYS if k in FINGER_MAP]
    # firma por tecla, colocada en los indices de features de SU dedo
    sigs = {}
    for k in keys:
        hand, finger = FINGER_MAP[k]
        idx = np.array(finger_indices(hand, finger))
        v = np.zeros(C.FEATURE_DIM, np.float32)
        v[idx] = rng.normal(0, 1, len(idx)).astype(np.float32)
        sigs[k] = v

    feats = rng.normal(0, 0.05, (n_frames, C.FEATURE_DIM)).astype(np.float32)
    labels = [C.NONE_LABEL] * n_frames
    i = C.WINDOW
    while i < n_frames - C.WINDOW:
        if rng.random() < 0.15:
            k = keys[rng.integers(len(keys))]
            feats[i] += sigs[k]
            labels[i] = k
            i += rng.integers(3, 8)
        else:
            i += 1
    return feats, labels


def main():
    torch.manual_seed(0)
    classes, to_idx = build_label_maps()
    experts = build_experts(classes)
    print(f"[SMOKE] {len(experts)} expertos: " +
          ", ".join(f"{m['hand'][0]}-{m['finger']}({len(m['keys'])})" for m in experts))

    feats, labels = make_synth()
    X, y = _windows_from_session(feats, labels, to_idx)
    print(f"[SMOKE] ventanas={len(X)} con_tecla={(y != 0).sum()}")

    Xt, yt = torch.from_numpy(X), torch.from_numpy(y)
    model = MultiFingerModel(experts, classes)

    maps, crits = [], []
    for m in experts:
        mt = torch.zeros(len(classes), dtype=torch.long)
        for g, li in m["global_to_local"].items():
            mt[g] = li
        cnt = torch.bincount(mt[yt], minlength=len(m["local_classes"])).float()
        w = torch.where(cnt > 0, 1.0 / cnt, torch.zeros_like(cnt))
        w = w / w.max(); w[0] *= C.NONE_WEIGHT
        maps.append(mt); crits.append(torch.nn.CrossEntropyLoss(weight=w))

    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    dl = torch.utils.data.DataLoader(torch.utils.data.TensorDataset(Xt, yt),
                                     batch_size=128, shuffle=True)
    for ep in range(10):
        model.train()
        for xb, yb in dl:
            opt.zero_grad()
            loss = sum(crits[i](model.expert_logits(i, xb), maps[i][yb])
                       for i in range(len(experts)))
            loss.backward(); opt.step()

    model.eval()
    with torch.no_grad():
        sc = model.scores(Xt)
        pred = sc[:, 1:].argmax(1) + 1
    sel = yt != 0
    acc = float((pred[sel] == yt[sel]).float().mean())
    print(f"[SMOKE] acc_teclas={acc:.3f}")

    save_fingers(model, C.MODEL_DIR / "_smoke_fingers.pt")
    m2, c2 = load_fingers(C.MODEL_DIR / "_smoke_fingers.pt")
    (C.MODEL_DIR / "_smoke_fingers.pt").unlink()
    assert c2 == classes
    assert acc > 0.85, "los expertos no aprendieron -> revisar recorte por dedo"
    print("[SMOKE] OK: fingers -> multi-experto -> train -> save/load funcionan.")


if __name__ == "__main__":
    main()
