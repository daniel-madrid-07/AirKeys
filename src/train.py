"""Entrena el modelo multi-experto por dedo a partir de los .npz grabados.

    python -m src.train

Cada dedo tiene su experto que ve SOLO sus landmarks y aprende solo sus teclas.
La perdida total = suma de la perdida de cada experto. Guarda models/fingers.pt.
"""
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split

import config as C
from src.dataset import load_all, build_label_maps
from src.fingers import build_experts
from src.model import MultiFingerModel, save_fingers


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[TRAIN] dispositivo: {device}")

    X, y, files = load_all()
    classes, _ = build_label_maps()
    experts = build_experts(classes)
    print(f"[TRAIN] {len(X)} ventanas | {len(files)} sesiones | {len(experts)} expertos")

    counts = np.bincount(y, minlength=len(classes))
    for m in experts:
        tot = sum(int(counts[classes.index(k)]) for k in m["keys"])
        det = " ".join(f"{k}:{int(counts[classes.index(k)])}" for k in m["keys"])
        print(f"    {m['hand'][0]}-{m['finger']:<6} [{tot:>5}]  {det}")

    y_t = torch.from_numpy(y)
    ds = TensorDataset(torch.from_numpy(X), y_t)
    n_val = max(1, int(len(ds) * 0.15))
    tr, val = random_split(ds, [len(ds) - n_val, n_val],
                           generator=torch.Generator().manual_seed(0))
    tl = DataLoader(tr, batch_size=C.BATCH, shuffle=True)
    vl = DataLoader(val, batch_size=C.BATCH)

    model = MultiFingerModel(experts, classes).to(device)

    # por experto: mapa global->local y pesos de clase (none rebajado)
    maps, crits = [], []
    for m in experts:
        map_t = torch.zeros(len(classes), dtype=torch.long)
        for g, li in m["global_to_local"].items():
            map_t[g] = li
        local_y = map_t[y_t]
        cnt = torch.bincount(local_y, minlength=len(m["local_classes"])).float()
        w = torch.where(cnt > 0, 1.0 / cnt, torch.zeros_like(cnt))
        if w.max() > 0:
            w /= w.max()
        w[0] *= C.NONE_WEIGHT
        maps.append(map_t.to(device))
        crits.append(nn.CrossEntropyLoss(weight=w.to(device)))

    opt = torch.optim.Adam(model.parameters(), lr=C.LR)

    best = 0.0
    for ep in range(1, C.EPOCHS + 1):
        model.train()
        for xb, yb in tl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            loss = 0.0
            for i in range(len(experts)):
                loss = loss + crits[i](model.expert_logits(i, xb), maps[i][yb])
            loss.backward()
            opt.step()

        # validacion: acierto de tecla combinando expertos (solo frames con tecla)
        model.eval()
        ok = tot = 0
        with torch.no_grad():
            for xb, yb in vl:
                xb, yb = xb.to(device), yb.to(device)
                sc = model.scores(xb)
                pred = sc[:, 1:].argmax(1) + 1     # ignora columna 'none'
                sel = yb != 0
                ok += int((pred[sel] == yb[sel]).sum())
                tot += int(sel.sum())
        acc = ok / tot if tot else 0.0
        print(f"[TRAIN] epoch {ep:02d} | acc_teclas={acc:.3f} (val {tot})")
        if acc >= best:
            best = acc
            save_fingers(model, C.MODEL_DIR / "fingers.pt")

    print(f"[TRAIN] Listo. Mejor acc_teclas={best:.3f} -> {C.MODEL_DIR / 'fingers.pt'}")


if __name__ == "__main__":
    main()
