"""Modelo pequeño: GRU bidireccional sobre la ventana de landmarks.

Entrada:  (batch, WINDOW, FEATURE_DIM)
Salida:   (batch, num_classes)  logits

Pocos parametros (~200k). Entrena en minutos en CPU.
"""
import torch
import torch.nn as nn

import config as C


class KeyGRU(nn.Module):
    def __init__(self, num_classes):
        super().__init__()
        self.gru = nn.GRU(
            input_size=C.FEATURE_DIM,
            hidden_size=C.HIDDEN,
            num_layers=C.LAYERS,
            batch_first=True,
            dropout=C.DROPOUT if C.LAYERS > 1 else 0.0,
            bidirectional=True,
        )
        self.head = nn.Sequential(
            nn.LayerNorm(C.HIDDEN * 2),
            nn.Dropout(C.DROPOUT),
            nn.Linear(C.HIDDEN * 2, num_classes),
        )

    def forward(self, x):
        out, _ = self.gru(x)          # (B, W, 2H)
        center = out[:, C.CENTER, :]  # estado en el frame central
        return self.head(center)


def save(model, classes, path):
    torch.save({"state_dict": model.state_dict(), "classes": classes}, path)


def load(path, device="cpu"):
    ckpt = torch.load(path, map_location=device)
    classes = ckpt["classes"]
    model = KeyGRU(len(classes))
    model.load_state_dict(ckpt["state_dict"])
    model.to(device).eval()
    return model, classes


# =========================================================================
# Modelo multi-experto: un mini-GRU por dedo, cada uno ve SOLO sus landmarks.
# =========================================================================
from src.fingers import build_experts  # noqa: E402


class FingerExpert(nn.Module):
    def __init__(self, in_dim, n_local):
        super().__init__()
        self.gru = nn.GRU(
            input_size=in_dim,
            hidden_size=C.FINGER_HIDDEN,
            num_layers=C.FINGER_LAYERS,
            batch_first=True,
            dropout=C.FINGER_DROPOUT if C.FINGER_LAYERS > 1 else 0.0,
            bidirectional=True,
        )
        self.head = nn.Sequential(
            nn.LayerNorm(C.FINGER_HIDDEN * 2),
            nn.Dropout(C.FINGER_DROPOUT),
            nn.Linear(C.FINGER_HIDDEN * 2, n_local),
        )

    def forward(self, x):
        out, _ = self.gru(x)
        return self.head(out[:, C.CENTER, :])


class MultiFingerModel(nn.Module):
    def __init__(self, experts, classes):
        super().__init__()
        self.classes = list(classes)
        self.experts_meta = experts
        self.nets = nn.ModuleList(
            [FingerExpert(len(m["indices"]), len(m["local_classes"])) for m in experts]
        )
        for i, m in enumerate(experts):
            self.register_buffer(f"idx_{i}", torch.tensor(m["indices"], dtype=torch.long))

    def expert_logits(self, i, x):
        idx = getattr(self, f"idx_{i}")
        return self.nets[i](x.index_select(2, idx))

    def forward(self, x):
        return [self.expert_logits(i, x) for i in range(len(self.nets))]

    def scores(self, x):
        """Combina los expertos en un vector de puntuaciones sobre TODAS las clases.
        Cada tecla toma la prob de SU experto; la columna 'none' (0) queda a 0."""
        B = x.shape[0]
        score = torch.zeros(B, len(self.classes), device=x.device)
        for i, m in enumerate(self.experts_meta):
            p = torch.softmax(self.expert_logits(i, x), 1)   # (B, n_local)
            for li in range(1, len(m["local_classes"])):
                g = m["local_to_global"][li]
                score[:, g] = torch.maximum(score[:, g], p[:, li])
        return score


def save_fingers(model, path):
    torch.save({
        "classes": model.classes,
        "experts": [{"hand": m["hand"], "finger": m["finger"], "keys": m["keys"]}
                    for m in model.experts_meta],
        "state_dict": model.state_dict(),
    }, path)


def load_fingers(path, device="cpu"):
    ckpt = torch.load(path, map_location=device)
    classes = ckpt["classes"]
    experts = build_experts(classes)   # indices se reconstruyen desde config
    saved = [(e["hand"], e["finger"], tuple(e["keys"])) for e in ckpt["experts"]]
    rebuilt = [(e["hand"], e["finger"], tuple(e["keys"])) for e in experts]
    if saved != rebuilt:
        raise RuntimeError("El mapeo de dedos/teclas cambio desde el entrenamiento. "
                           "Reentrena (python -m src.train).")
    model = MultiFingerModel(experts, classes)
    model.load_state_dict(ckpt["state_dict"])
    model.to(device).eval()
    return model, classes
