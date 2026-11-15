"""Comparação de arquiteturas: MLPs de vários tamanhos, MLP com janela achatada e modelos
sequenciais (RNN, LSTM, GRU, CNN-LSTM).

Dois tipos de entrada:
- MLPs sem janela: só as features da hora prevista (uma linha). Do consumo passado, veem as
  defasagens de 1, 24 e 168 horas.
- MLP com janela e modelos sequenciais: as JANELA últimas horas, cada uma com as mesmas features
  (inclusive as defasagens daquela hora). Os sequenciais recebem a janela como sequência; a MLP com
  janela recebe a mesma janela achatada num vetor só. Os dois têm exatamente a mesma informação.

Todos os modelos são avaliados nas mesmas linhas: só entram linhas cujas JANELA - 1 horas
anteriores da mesma edificação também existem (sem buracos), tanto no treino quanto na validação.
"""

import copy

import numpy as np
import torch
from torch import nn

from .config import BATCH, LR
from .dados import FEATURES

JANELA = 24
OCULTAS_SEQ = 64


# ---------------------------------------------------------------- dados em janelas


class Fonte:
    """Dados de um cliente, sem janelas pré-montadas.

    Cada hora fica armazenada uma única vez. A janela de 24 horas de cada alvo é montada só na
    hora de formar o lote, buscando as linhas anteriores pelos índices."""

    def __init__(self, df, janela, device):
        df = df.sort_values(["edif", "ts"]).reset_index(drop=True)
        X = df[FEATURES].to_numpy(np.float32)
        ts = df["ts"].to_numpy("datetime64[h]").astype(np.int64)
        edif = df["edif"].to_numpy()
        # a linha i tem janela completa se as janela-1 linhas anteriores são da mesma edificação
        # e cobrem exatamente as horas i-janela+1 .. i
        ok = np.zeros(len(df), bool)
        if len(df) >= janela:
            mesmo = edif[janela - 1 :] == edif[: len(df) - janela + 1]
            contiguo = (ts[janela - 1 :] - ts[: len(df) - janela + 1]) == janela - 1
            ok[janela - 1 :] = mesmo & contiguo
        self.alvos = np.flatnonzero(ok)
        self.df = df.iloc[self.alvos].reset_index(
            drop=True
        )  # linhas avaliadas, na mesma ordem
        self.X = torch.tensor(X, device=device)
        self.y = torch.tensor(df["y"].to_numpy(np.float32), device=device).unsqueeze(1)
        self.alvos_t = torch.tensor(self.alvos, device=device)
        self.desloc = torch.arange(-janela + 1, 1, device=device)
        self.n = len(self.alvos)

    def lote(self, idx, sequencia):
        linhas = self.alvos_t[idx]
        y = self.y[linhas]
        # Modelos com janela (sequencia=True): para cada alvo, soma os deslocamentos -23..0 ao
        # índice da linha e busca as 24 linhas, da hora mais antiga para a mais recente. Sai um
        # tensor (lote, janela, features). Modelos sem janela recebem só a linha do alvo:
        # (lote, features).
        if sequencia:
            return self.X[linhas.unsqueeze(1) + self.desloc], y  # (B, janela, F)
        return self.X[linhas], y  # (B, F)


def _uniao(fontes):
    """Fonte centralizada: concatena os clientes, deslocando os índices."""
    base = copy.copy(fontes[0])
    desloc, alvos = 0, []
    for f in fontes:
        alvos.append(f.alvos_t + desloc)
        desloc += len(f.X)
    base.X = torch.cat([f.X for f in fontes])
    base.y = torch.cat([f.y for f in fontes])
    base.alvos_t = torch.cat(alvos)
    base.n = len(base.alvos_t)
    base.df = None
    return base


# ---------------------------------------------------------------- modelos


class MLP(nn.Module):
    sequencia = False

    def __init__(self, n_ent, largura=64, camadas=2):
        super().__init__()
        partes, d = [], n_ent
        for _ in range(camadas):
            partes += [nn.Linear(d, largura), nn.ReLU()]
            d = largura
        self.rede = nn.Sequential(*partes, nn.Linear(d, 1))

    def forward(self, x):
        return self.rede(x)


class RNN(nn.Module):
    sequencia = True

    def __init__(self, n_ent, ocultas=OCULTAS_SEQ, camadas=1):
        super().__init__()
        self.rnn = nn.RNN(n_ent, ocultas, num_layers=camadas, batch_first=True)
        self.saida = nn.Linear(ocultas, 1)

    def forward(self, x):
        h, _ = self.rnn(x)
        return self.saida(h[:, -1])


class LSTM(nn.Module):
    sequencia = True

    def __init__(self, n_ent, ocultas=OCULTAS_SEQ, camadas=1):
        super().__init__()
        self.lstm = nn.LSTM(n_ent, ocultas, num_layers=camadas, batch_first=True)
        self.saida = nn.Linear(ocultas, 1)

    def forward(self, x):
        h, _ = self.lstm(x)
        return self.saida(h[:, -1])


class GRU(nn.Module):
    sequencia = True

    def __init__(self, n_ent, ocultas=OCULTAS_SEQ, camadas=1):
        super().__init__()
        self.gru = nn.GRU(n_ent, ocultas, num_layers=camadas, batch_first=True)
        self.saida = nn.Linear(ocultas, 1)

    def forward(self, x):
        h, _ = self.gru(x)
        return self.saida(h[:, -1])


class CNNLSTM(nn.Module):
    """Convolução 1D sobre o tempo para extrair padrões locais, depois LSTM."""

    sequencia = True

    def __init__(self, n_ent, filtros=32, ocultas=OCULTAS_SEQ):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(n_ent, filtros, kernel_size=3, padding=1), nn.ReLU()
        )
        self.lstm = nn.LSTM(filtros, ocultas, batch_first=True)
        self.saida = nn.Linear(ocultas, 1)

    def forward(self, x):
        z = self.conv(x.transpose(1, 2)).transpose(1, 2)
        h, _ = self.lstm(z)
        return self.saida(h[:, -1])


class MLPJanela(nn.Module):
    """MLP sobre a janela, sem estrutura de tempo.

    A janela inteira vem achatada (JANELA x n_ent entradas).
    """

    sequencia = True

    def __init__(self, n_ent, largura=64, camadas=2):
        super().__init__()
        self.mlp = MLP(JANELA * n_ent, largura, camadas)

    def forward(self, x):
        return self.mlp(x.flatten(1))


MODELOS = {
    "MLP 64 (atual)": lambda n: MLP(n, 64, 2),
    "MLP 256": lambda n: MLP(n, 256, 2),
    "MLP 1024": lambda n: MLP(n, 1024, 2),
    "MLP 256 × 4 camadas": lambda n: MLP(n, 256, 4),
    "MLP janela achatada": lambda n: MLPJanela(n),
    "RNN": lambda n: RNN(n),
    "RNN 2 camadas": lambda n: RNN(n, camadas=2),
    "LSTM": lambda n: LSTM(n),
    "GRU": lambda n: GRU(n),
    "CNN-LSTM": lambda n: CNNLSTM(n),
}


def novo(nome, seed, device):
    torch.manual_seed(seed)
    return MODELOS[nome](len(FEATURES)).to(device)


def n_parametros(modelo):
    return sum(p.numel() for p in modelo.parameters())


# ---------------------------------------------------------------- treino e previsão


def treinar(modelo, fonte, epocas, gerador, ao_fim_da_epoca=None):
    """ao_fim_da_epoca(epoca, perda_media): opcional, para registrar a perda de treino."""
    opt = torch.optim.Adam(modelo.parameters(), lr=LR)
    lossf = nn.MSELoss()
    modelo.train()
    for e in range(epocas):
        perm = torch.randperm(fonte.n, generator=gerador).to(fonte.X.device)
        soma, lotes = 0.0, 0
        for i in range(0, fonte.n, BATCH):
            x, y = fonte.lote(perm[i : i + BATCH], modelo.sequencia)
            opt.zero_grad()
            perda = lossf(modelo(x), y)
            perda.backward()
            opt.step()
            if ao_fim_da_epoca:
                # acumula no próprio dispositivo: .item() a cada lote faria a CPU esperar a GPU
                soma, lotes = soma + perda.detach(), lotes + 1
        if ao_fim_da_epoca:
            ao_fim_da_epoca(e, float(soma / lotes))  # uma única cópia para a CPU por época
        modelo.train()
    return modelo


@torch.no_grad()
def mse_z(modelo, fonte):
    """MSE no espaço normalizado (z-score), nas linhas da fonte."""
    prev = torch.tensor(prever(modelo, fonte), device=fonte.X.device)
    return float(((prev - fonte.y[fonte.alvos_t].squeeze(1)) ** 2).mean())


@torch.no_grad()
def prever(modelo, fonte):
    modelo.eval()
    saida = []
    for i in range(0, fonte.n, 8192):
        idx = torch.arange(i, min(i + 8192, fonte.n), device=fonte.X.device)
        saida.append(modelo(fonte.lote(idx, modelo.sequencia)[0]))
    return torch.cat(saida).squeeze(1).cpu().numpy()


def kwh(modelo, fonte):
    return prever(modelo, fonte) * fonte.df["sd"].to_numpy() + fonte.df["mu"].to_numpy()


def centralizado(nome, fontes_tr, epocas, seed, device, ao_fim_da_epoca=None):
    g = torch.Generator().manual_seed(seed)
    return treinar(
        novo(nome, seed, device),
        _uniao(list(fontes_tr.values())),
        epocas,
        g,
        ao_fim_da_epoca,
    )


def _criar_callback(s, ao_fim_da_epoca):
    if not ao_fim_da_epoca:
        return None

    def _callback(e, p):
        return ao_fim_da_epoca(s, e, p)

    return _callback


def locais(nome, fontes_tr, epocas, seed, device, ao_fim_da_epoca=None):
    """ao_fim_da_epoca(site, epoca, perda): opcional."""
    out = {}

    for s, f in fontes_tr.items():
        g = torch.Generator().manual_seed(seed)

        cb = _criar_callback(s, ao_fim_da_epoca)
        out[s] = treinar(novo(nome, seed, device), f, epocas, g, cb)
    return out


def fedavg(
    nome, fontes_tr, rodadas, epocas_locais, seed, device, ao_fim_da_rodada=None
):
    """O mesmo FedAvg de fedavg.py (média ponderada pelo número de amostras).

    ao_fim_da_rodada(rodada, modelo_global): opcional, para registrar a validação por rodada."""
    g = torch.Generator().manual_seed(seed)
    global_ = novo(nome, seed, device)
    sites = list(fontes_tr)
    total = sum(fontes_tr[s].n for s in sites)
    peso = {s: fontes_tr[s].n / total for s in sites}
    for r in range(1, rodadas + 1):
        estados = {}
        for s in sites:
            local = copy.deepcopy(global_)
            treinar(local, fontes_tr[s], epocas_locais, g)
            estados[s] = local.state_dict()
        global_.load_state_dict(
            {k: sum(peso[s] * estados[s][k] for s in sites) for k in estados[sites[0]]}
        )
        if ao_fim_da_rodada:
            ao_fim_da_rodada(r, global_)
    return global_
