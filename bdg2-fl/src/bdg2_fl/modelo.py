import torch
from torch import nn

from .config import BATCH, LR, OCULTAS


def novo_modelo(n_entradas, seed):
    torch.manual_seed(seed)
    return nn.Sequential(
        nn.Linear(n_entradas, OCULTAS), nn.ReLU(),
        nn.Linear(OCULTAS, OCULTAS), nn.ReLU(),
        nn.Linear(OCULTAS, 1),
    )


def treinar(modelo, X, y, epocas, gerador):
    """Treino local simples: Adam novo a cada chamada (o estado do otimizador não é
    compartilhado entre rodadas nem entre clientes)."""
    opt = torch.optim.Adam(modelo.parameters(), lr=LR)
    lossf = nn.MSELoss()
    modelo.train()
    n = len(X)
    for _ in range(epocas):
        perm = torch.randperm(n, generator=gerador)
        for i in range(0, n, BATCH):
            j = perm[i:i + BATCH]
            opt.zero_grad()
            lossf(modelo(X[j]), y[j]).backward()
            opt.step()
    return modelo


@torch.no_grad()
def prever(modelo, X):
    modelo.eval()
    return torch.cat([modelo(X[i:i + 65536]) for i in range(0, len(X), 65536)])


@torch.no_grad()
def mse(modelo, X, y):
    return float(((prever(modelo, X) - y) ** 2).mean())
