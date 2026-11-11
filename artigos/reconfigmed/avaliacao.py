"""Uma execução da avaliação final: python avaliacao.py <split> <config> <seed> --csv ... --out ...

Repete o preparo do eda.ipynb (features da Tabela 1, splits, normalização, janelas, clientes)
e salva as probabilidades de validação e teste em <out>/<split>_<config>_<seed>.npz.
Cada execução é um processo novo, então várias podem rodar ao mesmo tempo na mesma GPU.
"""
import argparse
import copy
import json
import logging
import os
import warnings

logging.getLogger("torch.distributed.elastic.multiprocessing.redirects").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message="Secure RNG turned off")
warnings.filterwarnings("ignore", message="Full backward hook")

import numpy as np
import polars as pl
import torch
import torch.nn as nn
from opacus import PrivacyEngine
from opacus.accountants.utils import get_noise_multiplier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split
from torch.func import functional_call
from torch.utils.data import DataLoader, TensorDataset

CONFIGS = ["gb", "central", "fedavg", "atencao", "fedavg_dp", "atencao_dp", "artigo"]
FEATURES = ["SrcBytes", "DstBytes", "SrcLoad", "DstLoad", "SIntPkt", "DIntPkt", "SIntPktAct", "SrcJitter",
            "DstJitter", "sMaxPktSz", "dMaxPktSz", "sMinPktSz", "Dur", "TotPkts", "TotBytes", "Loss", "pLoss",
            "pSrcLoss", "pDstLoss", "Rate", "Load", "Temp", "SpO2", "Pulse_Rate", "SYS", "DIA", "Heart_rate",
            "Resp_Rate", "ST"]
K, L, T, GAP = 10, 100, 24, 50
DEV = torch.device("cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu")
torch.set_num_threads(1)


# ---- dados (etapas 1 a 5 e 6a do eda.ipynb)

def prepara(csv):
    df = pl.read_csv(csv, infer_schema_length=None).with_row_index()
    n = len(df)
    cat = df["Attack Category"].to_numpy()
    tr, resto = train_test_split(np.arange(n), test_size=0.30, stratify=cat, random_state=42)
    va, te = train_test_split(resto, test_size=0.50, stratify=cat[resto], random_state=42)
    split_iid = np.empty(n, dtype=object)
    split_iid[tr], split_iid[va], split_iid[te] = "train", "val", "test"
    a, b = int(0.70 * n), int(0.85 * n)
    split_ord = np.full(n, "gap", dtype=object)
    split_ord[:a - GAP] = "train"
    split_ord[a:b - GAP] = "val"
    split_ord[b:] = "test"
    df = df.with_columns(split_iid=pl.Series(split_iid), split_ord=pl.Series(split_ord))

    X_all = df.select(FEATURES).to_numpy().astype(np.float32)
    y_all = df["Label"].to_numpy().astype(np.float32)

    def separa(split):
        s = df[split].to_numpy()
        tr = s == "train"
        media, desvio = X_all[tr].mean(axis=0), X_all[tr].std(axis=0)
        desvio[desvio == 0] = 1.0
        X = (X_all - media) / desvio
        return {p: (X[s == p], y_all[s == p]) for p in ("train", "val", "test")}

    def janelas(dados, T):
        out = {}
        for p, (X, y) in dados.items():
            linhas = np.arange(len(X))[:, None] - T + 1 + np.arange(T)
            out[p] = (X[np.maximum(linhas, 0)].transpose(0, 2, 1), y)
        return out

    dados_iid, dados_ord = separa("split_iid"), separa("split_ord")
    jan_iid, jan_ord = janelas(dados_iid, 1), janelas(dados_ord, T)

    rng = np.random.default_rng(42)
    cat_tr = df.filter(pl.col("split_iid") == "train")["Attack Category"].to_numpy()
    cli_iid = np.empty(len(cat_tr), dtype=int)
    for c in np.unique(cat_tr):
        pos = rng.permutation(np.flatnonzero(cat_tr == c))
        cli_iid[pos] = np.arange(len(pos)) % K
    bloco = np.arange(len(dados_ord["train"][1])) // L
    rank = np.argsort(rng.permutation(bloco.max() + 1))
    cli_ord = (rank % K)[bloco]
    Xtr, ytr = dados_ord["train"]
    linhas = np.arange(len(Xtr))[:, None] - T + 1 + np.arange(T)
    jan_ord["train"] = (Xtr[np.maximum(linhas, (bloco * L)[:, None])].transpose(0, 2, 1), ytr)

    return {"iid": (cli_iid, jan_iid, dados_iid), "ord": (cli_ord, jan_ord, dados_ord)}


# ---- modelo e treino (etapas 5, 6b e 7a do eda.ipynb)

class LCNN(nn.Module):
    def __init__(self, n_feat):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(n_feat, n_feat, 3, padding=1, groups=n_feat),
            nn.Conv1d(n_feat, 64, 1), nn.GELU(),
            nn.GroupNorm(1, 64), nn.Dropout(0.2),
            nn.Conv1d(64, 64, 3, padding=1, groups=64),
            nn.Conv1d(64, 128, 1), nn.GELU(),
            nn.AdaptiveAvgPool1d(1), nn.Flatten(),
            nn.Linear(128, 32), nn.GELU(), nn.Linear(32, 1),
        )

    def forward(self, x):
        return self.net(x).squeeze(-1)


def loader(X, y, B, embaralha, seed=0):
    ds = TensorDataset(torch.from_numpy(X), torch.from_numpy(y))
    return DataLoader(ds, batch_size=B, shuffle=embaralha, generator=torch.Generator().manual_seed(seed))


@torch.no_grad()
def avalia(model, dl):
    model.eval()
    logits = torch.cat([model(xb.to(DEV)).cpu() for xb, _ in dl])
    y = torch.cat([yb for _, yb in dl]).numpy()
    p = torch.sigmoid(logits).numpy()
    return roc_auc_score(y, p), average_precision_score(y, p)


@torch.no_grad()
def probs(model, X):
    model.eval()
    dl = loader(X, np.zeros(len(X), dtype=np.float32), 1024, False)
    return torch.sigmoid(torch.cat([model(xb.to(DEV)).cpu() for xb, _ in dl])).numpy()


def treina_centralizado(jan, epocas=50, paciencia=10, seed=0):
    torch.manual_seed(seed)
    tr = loader(*jan["train"], 64, True, seed)
    va = loader(*jan["val"], 1024, False)
    model = LCNN(jan["train"][0].shape[1]).to(DEV)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    melhor, estado, sem_melhora = -1, None, 0
    for ep in range(epocas):
        model.train()
        for xb, yb in tr:
            xb, yb = xb.to(DEV), yb.to(DEV)
            opt.zero_grad()
            nn.functional.binary_cross_entropy_with_logits(model(xb), yb).backward()
            opt.step()
        auprc = avalia(model, va)[1]
        if auprc > melhor + 1e-3:
            melhor, sem_melhora = auprc, 0
            estado = {k: v.clone() for k, v in model.state_dict().items()}
        else:
            sem_melhora += 1
            if sem_melhora >= paciencia:
                break
    model.load_state_dict(estado)
    return model, ep + 1


def treina_local(modelo_global, dl, E, lr, engine=None, sigma=None, C=1.0):
    model = copy.deepcopy(modelo_global).to(DEV)
    model.train()
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    if engine is not None:
        model, opt, dl = engine.make_private(module=model, optimizer=opt, data_loader=dl,
                                             noise_multiplier=sigma, max_grad_norm=C)
    perdas = []
    for _ in range(E):
        for xb, yb in dl:
            xb, yb = xb.to(DEV), yb.to(DEV)
            opt.zero_grad()
            perda = nn.functional.binary_cross_entropy_with_logits(model(xb), yb)
            perda.backward()
            opt.step()
            perdas.append(perda.item())
    estado = {k.removeprefix("_module."): v.detach().to(DEV) for k, v in model.state_dict().items()}
    return estado, float(np.mean(perdas))


def fedavg(modelo, estados, perdas, n):
    return {k: sum(nk / sum(n) * e[k] for nk, e in zip(n, estados)) for k in estados[0]}


def metade(X, y, qual):
    m = (np.arange(len(y)) // 100) % 2 == qual
    return X[m], y[m]


def federado(jan, cli, sigma=None, rodadas=80, E=2, B=64, lr=1e-3, paciencia=10, seed=0, delta=1e-5,
             agrega=fedavg):
    torch.manual_seed(seed)
    Xtr, ytr = jan["train"]
    dls = [loader(Xtr[cli == k], ytr[cli == k], B, True, seed) for k in range(K)]
    va = loader(*metade(*jan["val"], 1), 1024, False)
    n = [len(dl.dataset) for dl in dls]
    engines = [PrivacyEngine(accountant="rdp") if sigma else None for _ in dls]
    modelo = LCNN(Xtr.shape[1]).to(DEV)
    melhor, sem_melhora, eps = -1, 0, 0.0
    for t in range(rodadas):
        locais = [treina_local(modelo, dl, E, lr, eng, sigma) for dl, eng in zip(dls, engines)]
        estados, perdas = [e for e, _ in locais], [p for _, p in locais]
        modelo.load_state_dict(agrega(modelo, estados, perdas, n))
        if sigma:
            eps = max(eng.get_epsilon(delta) for eng in engines)
        auprc = avalia(modelo, va)[1]
        if auprc > melhor + 1e-3:
            melhor, sem_melhora = auprc, 0
            estado, r_melhor, eps_melhor = {k: v.clone() for k, v in modelo.state_dict().items()}, t + 1, eps
        else:
            sem_melhora += 1
            if sem_melhora >= paciencia:
                break
    modelo.load_state_dict(estado)
    return {"rodadas": t + 1, "melhor": r_melhor, "eps": eps_melhor, "modelo": modelo}


def sigma_para(eps_alvo, n_min, B=64, E=2, rodadas=80, delta=1e-5):
    passos = int(np.ceil(n_min / B))
    return get_noise_multiplier(target_epsilon=eps_alvo, target_delta=delta, sample_rate=1 / passos,
                                steps=rodadas * E * passos, accountant="rdp")


class Atencao(nn.Module):
    def __init__(self, beta=4.0, zera_saida=True):
        super().__init__()
        self.g = nn.Sequential(nn.Linear(4, 64), nn.Tanh(), nn.Linear(64, 1))
        if zera_saida:
            nn.init.zeros_(self.g[2].weight)
            nn.init.zeros_(self.g[2].bias)
        self.beta = beta

    def forward(self, h):
        return torch.softmax(self.beta * self.g(h).squeeze(-1), dim=0)


class AgregaAtencao:
    def __init__(self, jan, treinar=True, passos=5, lr=1e-2, W=3, seed=0):
        torch.manual_seed(seed)
        self.att = Atencao(zera_saida=treinar).to(DEV)
        self.opt = torch.optim.Adam(self.att.parameters(), lr=lr)
        self.treinar, self.passos, self.W = treinar, passos, W
        Xa, ya = metade(*jan["val"], 0)
        self.Xa, self.ya = torch.from_numpy(Xa).to(DEV), torch.from_numpy(ya).to(DEV)
        self.hist_perda, self.alphas = None, []

    def estado(self, modelo, estados, perdas, n):
        g = modelo.state_dict()
        delta = torch.stack([torch.cat([(e[k] - g[k]).flatten() for k in g]) for e in estados])
        media = delta.mean(dim=0)
        rho = ((delta - media).norm(dim=1) / media.norm()).cpu().tolist()
        if self.hist_perda is None:
            self.hist_perda = [[] for _ in estados]
        for h, p in zip(self.hist_perda, perdas):
            h.append(p)
        F = [float(np.mean(h[-self.W:])) for h in self.hist_perda]
        dF = [h[-1] - h[-2] if len(h) > 1 else 0.0 for h in self.hist_perda]
        return torch.tensor([[np.log(nk), f, d, r] for nk, f, d, r in zip(n, F, dF, rho)],
                            dtype=torch.float32, device=DEV)

    def __call__(self, modelo, estados, perdas, n):
        h = self.estado(modelo, estados, perdas, n)
        mistura = lambda a: {k: sum(ak * e[k] for ak, e in zip(a, estados)) for k in estados[0]}
        if self.treinar:
            modelo.eval()
            for _ in range(self.passos):
                logits = functional_call(modelo, mistura(self.att(h)), (self.Xa,))
                perda = nn.functional.binary_cross_entropy_with_logits(logits, self.ya)
                self.opt.zero_grad()
                perda.backward()
                self.opt.step()
        with torch.no_grad():
            alpha = self.att(h)
        self.alphas.append(alpha.cpu().numpy())
        return mistura(alpha)


# ---- uma execução (célula 8a do eda.ipynb)

def roda(cenarios, split, cfg, seed, out, rodadas=80):
    cli, jan, dados = cenarios[split]
    meta = {}
    if cfg == "gb":
        m = HistGradientBoostingClassifier(random_state=seed).fit(*dados["train"])
        pv, pt = m.predict_proba(dados["val"][0])[:, 1], m.predict_proba(dados["test"][0])[:, 1]
    elif cfg == "central":
        model, ep = treina_centralizado(jan, seed=seed)
        pv, pt = probs(model, jan["val"][0]), probs(model, jan["test"][0])
        meta["epocas"] = ep
    else:
        s5 = sigma_para(5.0, np.bincount(cli).min())
        kw = {"fedavg": dict(),
              "atencao": dict(agrega=AgregaAtencao(jan, seed=seed)),
              "fedavg_dp": dict(sigma=s5, lr=1e-2),
              "atencao_dp": dict(sigma=s5, lr=1e-2, agrega=AgregaAtencao(jan, seed=seed)),
              "artigo": dict(sigma=0.7, lr=1e-3, agrega=AgregaAtencao(jan, seed=seed))}[cfg]
        r = federado(jan, cli, seed=seed, rodadas=rodadas, **kw)
        pv, pt = probs(r["modelo"], jan["val"][0]), probs(r["modelo"], jan["test"][0])
        meta = {"rodadas": r["rodadas"], "melhor": r["melhor"], "eps": r["eps"], "sigma": kw.get("sigma")}
    np.savez(f"{out}/{split}_{cfg}_{seed}.npz", val=pv, test=pt)
    json.dump(meta, open(f"{out}/{split}_{cfg}_{seed}.json", "w"))
    print(split, cfg, seed, meta, round(roc_auc_score(jan["test"][1], pt), 3), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("split", choices=["ord", "iid"])
    ap.add_argument("config", choices=CONFIGS)
    ap.add_argument("seed", type=int)
    ap.add_argument("--csv", default="_local/data/wustl-ehms-2020_with_attacks_categories.csv")
    ap.add_argument("--out", default="_local/data/avaliacao")
    ap.add_argument("--rodadas", type=int, default=80)  # só para testes rápidos
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    roda(prepara(a.csv), a.split, a.config, a.seed, a.out, a.rodadas)
