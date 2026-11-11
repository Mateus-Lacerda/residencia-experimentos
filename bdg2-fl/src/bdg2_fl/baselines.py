import torch

from .config import EPOCAS_BASELINE, SEED
from .modelo import novo_modelo, treinar


def centralizado(dados, n_entradas):
    X = torch.cat([d["Xtr"] for d in dados.values()])
    y = torch.cat([d["ytr"] for d in dados.values()])
    g = torch.Generator().manual_seed(SEED)
    return treinar(novo_modelo(n_entradas, SEED), X, y, EPOCAS_BASELINE, g)


def locais(dados, n_entradas):
    out = {}
    for s, d in dados.items():
        g = torch.Generator().manual_seed(SEED)
        out[s] = treinar(novo_modelo(n_entradas, SEED), d["Xtr"], d["ytr"], EPOCAS_BASELINE, g)
    return out
