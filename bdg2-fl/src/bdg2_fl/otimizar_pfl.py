"""Otimização dos hiperparâmetros do fine-tuning local e do FedSA-LoRA.

uv run python -m bdg2_fl.otimizar_pfl --etapa ajuste
uv run python -m bdg2_fl.otimizar_pfl --etapa teste

Protocolo
- Ajuste: treino em jan-out/2016 e validação em nov-dez/2016. 2017 não entra na escolha.
  (A normalização continua com a média e o desvio de 2016 inteiro, como em dados.py.)
- Cada configuração roda com as 3 seeds, e a escolha usa a média do CV(RMSE) total na validação.
- Busca com o Optuna (amostrador TPE), N_TENTATIVAS por método. A primeira tentativa é a
  configuração original de pfl.py, como referência. O estudo fica em out/otimizacao_pfl/optuna.db,
  então rodar de novo continua de onde parou.
- Teste: as melhores configurações são retreinadas em 2016 inteiro e avaliadas em 2017, junto
  com o FedAvg, o só local e as configurações originais de pfl.py, todos com este mesmo código.

Para economizar, o FedAvg roda uma vez por seed e guarda o modelo global de cada rodada; o
fine-tuning e o LoRA partem do estado guardado da rodada escolhida (rodadas_base).

Resultados em out/otimizacao_pfl/: optuna.db, melhores.json e teste.json.
"""
import argparse
import copy
import json
import math
import time

import numpy as np
import optuna
import torch
from torch import nn

from . import arquiteturas as A
from .config import BATCH, LR, RAIZ
from .dados import construir
from .rodar_arquiteturas import avaliar

MODELO = "MLP janela achatada"
RODADAS, EPOCAS_LOCAIS = 10, 2
SEEDS = [42, 43, 44]
MES_CORTE = 11                      # validação de ajuste: novembro e dezembro de 2016
SAIDA = RAIZ / "out" / "otimizacao_pfl"     # main() acrescenta a subpasta "<n>_sites"

# camadas lineares da MLP: mlp.rede.0 (408->64), mlp.rede.2 (64->64), mlp.rede.4 (64->1)
CAMADAS_FT = {
    "todas": ("mlp.rede.0.", "mlp.rede.2.", "mlp.rede.4."),
    "camada 2 e saída": ("mlp.rede.2.", "mlp.rede.4."),
    "saída": ("mlp.rede.4.",),
}
CAMADAS_LORA = {"todas": (0, 2, 4), "ocultas": (0, 2), "camada 1": (0,)}

N_TENTATIVAS = 60
FT_ORIGINAL = {"rodadas_base": 9, "epocas": 2, "lr": 1e-3, "camadas": "todas"}
LORA_ORIGINAL = {"rodadas_base": 5, "posto": 4, "camadas": "todas", "lr": 1e-3, "epocas": 2, "escala": 1.0}


def espaco_ft(t):
    return {"rodadas_base": t.suggest_int("rodadas_base", 1, RODADAS),
            "epocas": t.suggest_int("epocas", 1, 32, log=True),
            "lr": t.suggest_float("lr", 1e-5, 1e-2, log=True),
            "camadas": t.suggest_categorical("camadas", list(CAMADAS_FT))}


def espaco_lora(t):
    return {"rodadas_base": t.suggest_int("rodadas_base", 1, RODADAS - 1),
            "posto": t.suggest_int("posto", 1, 64, log=True),
            "camadas": t.suggest_categorical("camadas", list(CAMADAS_LORA)),
            "lr": t.suggest_float("lr", 1e-4, 3e-2, log=True),
            "epocas": t.suggest_int("epocas", 1, 4),
            "escala": t.suggest_float("escala", 0.25, 4.0, log=True)}


# ---------------------------------------------------------------- treino

def treinar(modelo, fonte, epocas, g, lr, ao_fim_da_epoca=None):
    """Como arquiteturas.treinar, mas com lr variável e só nos parâmetros com requires_grad.

    ao_fim_da_epoca(epoca, perda_media, modelo): opcional, para registrar o treino."""
    opt = torch.optim.Adam([p for p in modelo.parameters() if p.requires_grad], lr=lr)
    lossf = nn.MSELoss()
    modelo.train()
    for e in range(epocas):
        perm = torch.randperm(fonte.n, generator=g).to(fonte.X.device)
        soma, lotes = 0.0, 0
        for i in range(0, fonte.n, BATCH):
            x, y = fonte.lote(perm[i:i + BATCH], modelo.sequencia)
            opt.zero_grad()
            perda = lossf(modelo(x), y)
            perda.backward()
            opt.step()
            if ao_fim_da_epoca:
                soma, lotes = soma + perda.item(), lotes + 1
        if ao_fim_da_epoca:
            ao_fim_da_epoca(e, soma / lotes, modelo)
            modelo.train()
    return modelo


def _cb_site(cb, s):
    """Fixa o site num callback cb(site, epoca, perda, modelo)."""
    return (lambda e, p, m: cb(s, e, p, m)) if cb else None


def _pesos(fontes):
    total = sum(f.n for f in fontes.values())
    return {s: f.n / total for s, f in fontes.items()}


def trajetoria_fedavg(fontes_tr, seed, device, ao_fim_da_rodada=None):
    """Estado global do FedAvg depois de cada rodada (índice 0 = inicialização).

    ao_fim_da_rodada(rodada, modelo_global): opcional."""
    g = torch.Generator().manual_seed(seed)
    global_ = A.novo(MODELO, seed, device)
    peso = _pesos(fontes_tr)
    estados = [copy.deepcopy(global_.state_dict())]
    for _ in range(RODADAS):
        locais = {}
        for s, f in fontes_tr.items():
            locais[s] = treinar(copy.deepcopy(global_), f, EPOCAS_LOCAIS, g, LR).state_dict()
        global_.load_state_dict({k: sum(peso[s] * locais[s][k] for s in locais) for k in locais[s]})
        estados.append(copy.deepcopy(global_.state_dict()))
        if ao_fim_da_rodada:
            ao_fim_da_rodada(len(estados) - 1, global_)
    return estados


def _base(traj, rodada, seed, device):
    m = A.novo(MODELO, seed, device)
    m.load_state_dict(traj[rodada])
    return m


def fine_tuning(traj, cfg, fontes_tr, seed, device, ao_fim_da_epoca=None):
    """ao_fim_da_epoca(site, epoca, perda, modelo): opcional."""
    base = _base(traj, cfg["rodadas_base"], seed, device)
    for k, p in base.named_parameters():
        p.requires_grad_(k.startswith(CAMADAS_FT[cfg["camadas"]]))
    g = torch.Generator().manual_seed(seed + 1000)
    modelos = {s: treinar(copy.deepcopy(base), f, cfg["epocas"], g, cfg["lr"], _cb_site(ao_fim_da_epoca, s))
               for s, f in fontes_tr.items()}
    envio = {"rodadas": cfg["rodadas_base"], "por_rodada": A.n_parametros(base)}
    return modelos, envio


class LoRALinear(nn.Module):
    """W x + escala * B A x, com W congelado (Hu et al., 2022)."""

    def __init__(self, base, posto, escala):
        super().__init__()
        self.base, self.escala = base, escala
        dev = base.weight.device
        self.A = nn.Parameter(torch.empty(posto, base.in_features, device=dev))
        nn.init.kaiming_uniform_(self.A, a=math.sqrt(5))
        self.B = nn.Parameter(torch.zeros(base.out_features, posto, device=dev))

    def forward(self, x):
        return self.base(x) + self.escala * ((x @ self.A.T) @ self.B.T)


def fedsa_lora(traj, cfg, fontes_tr, seed, device):
    """A entra na média, B fica no cliente (Guo et al., 2025)."""
    molde = _base(traj, cfg["rodadas_base"], seed, device)
    torch.manual_seed(seed)
    for i in CAMADAS_LORA[cfg["camadas"]]:
        molde.mlp.rede[i] = LoRALinear(molde.mlp.rede[i], cfg["posto"], cfg["escala"])
    for k, p in molde.named_parameters():
        p.requires_grad_(k.endswith((".A", ".B")))
    chaves_a = [k for k in molde.state_dict() if k.endswith(".A")]
    modelos = {s: copy.deepcopy(molde) for s in fontes_tr}
    peso = _pesos(fontes_tr)
    global_a = {k: molde.state_dict()[k].clone() for k in chaves_a}
    g = torch.Generator().manual_seed(seed + 1000)
    for _ in range(RODADAS - cfg["rodadas_base"]):
        estados = {}
        for s, f in fontes_tr.items():
            modelos[s].load_state_dict(global_a, strict=False)
            treinar(modelos[s], f, cfg["epocas"], g, cfg["lr"])
            estados[s] = modelos[s].state_dict()
        global_a = {k: sum(peso[s] * estados[s][k] for s in estados) for k in chaves_a}
        for m in modelos.values():
            m.load_state_dict(global_a, strict=False)
    sd = molde.state_dict()
    envio = {"rodadas_base": cfg["rodadas_base"], "por_rodada_base": A.n_parametros(_base(traj, 0, seed, device)),
             "rodadas_lora": RODADAS - cfg["rodadas_base"],
             "por_rodada_lora": sum(sd[k].numel() for k in chaves_a),
             "B_local": sum(v.numel() for k, v in sd.items() if k.endswith(".B"))}
    return modelos, envio


def so_local(fontes_tr, seed, device, epocas=RODADAS * EPOCAS_LOCAIS, ao_fim_da_epoca=None):
    """ao_fim_da_epoca(site, epoca, perda, modelo): opcional."""
    out = {}
    for s, f in fontes_tr.items():
        g = torch.Generator().manual_seed(seed)
        out[s] = treinar(A.novo(MODELO, seed, device), f, epocas, g, LR, _cb_site(ao_fim_da_epoca, s))
    return out


def envio_total(envio):
    if "por_rodada_lora" in envio:
        return envio["rodadas_base"] * envio["por_rodada_base"] + envio["rodadas_lora"] * envio["por_rodada_lora"]
    return envio["rodadas"] * envio["por_rodada"]


# ---------------------------------------------------------------- ajuste

def otimizar(nome, metodo, espaco, original, trajs, tr, va, device):
    """Minimiza a média do CV(RMSE) total nas 3 seeds; guarda as notas por seed e o envio."""
    def objetivo(t):
        cfg, notas = espaco(t), []
        for seed in SEEDS:
            modelos, envio = metodo(trajs[seed], cfg, tr, seed, device)
            notas.append(avaliar({s: A.kwh(modelos[s], f) for s, f in va.items()}, va)["Total"])
        t.set_user_attr("por_seed", notas)
        t.set_user_attr("envio_total", envio_total(envio))
        return float(np.mean(notas))

    estudo = optuna.create_study(study_name=nome, storage=f"sqlite:///{SAIDA / 'optuna.db'}",
                                 load_if_exists=True, sampler=optuna.samplers.TPESampler(seed=0))
    if not estudo.trials:
        estudo.enqueue_trial(original)
    feitas = sum(t.state == optuna.trial.TrialState.COMPLETE for t in estudo.trials)
    estudo.optimize(objetivo, n_trials=max(N_TENTATIVAS - feitas, 0))
    return estudo.best_params


def _fontes(clientes, parte, device, corte=None):
    out = {}
    for s, c in clientes.items():
        df = c[parte]
        if corte == "treino":
            df = df[df["ts"].dt.month < MES_CORTE]
        elif corte == "val":
            df = df[df["ts"].dt.month >= MES_CORTE]
        out[s] = A.Fonte(df, A.JANELA, device)
    return out


def etapa_ajuste(clientes, device):
    tr = _fontes(clientes, "treino", device, "treino")
    va = _fontes(clientes, "treino", device, "val")
    print({s: (tr[s].n, va[s].n) for s in tr}, flush=True)
    t = time.time()
    trajs = {seed: trajetoria_fedavg(tr, seed, device) for seed in SEEDS}
    print(f"trajetórias do FedAvg: {time.time() - t:.0f} s", flush=True)

    ref = []
    for seed in SEEDS:
        m = _base(trajs[seed], RODADAS, seed, device)
        ref.append(avaliar({s: A.kwh(m, f) for s, f in va.items()}, va)["Total"])
    print(f"FedAvg na validação de ajuste: {np.mean(ref):.3f} ± {np.std(ref):.3f}", flush=True)

    melhor_ft = otimizar("ft", fine_tuning, espaco_ft, FT_ORIGINAL, trajs, tr, va, device)
    print("melhor fine-tuning:", melhor_ft, flush=True)
    melhor_lora = otimizar("lora", fedsa_lora, espaco_lora, LORA_ORIGINAL, trajs, tr, va, device)
    print("melhor LoRA:", melhor_lora, flush=True)
    (SAIDA / "melhores.json").write_text(json.dumps(
        {"fedavg_val_ajuste": ref, "ft": melhor_ft, "lora": melhor_lora}, indent=1, ensure_ascii=False))


def etapa_teste(clientes, device):
    melhores = json.loads((SAIDA / "melhores.json").read_text())
    tr = _fontes(clientes, "treino", device)
    va = _fontes(clientes, "val", device)
    metodos = {
        "FedAvg": None,
        "Só local": None,
        "Fine-tuning (original)": (fine_tuning, FT_ORIGINAL),
        "Fine-tuning (otimizado)": (fine_tuning, melhores["ft"]),
        "FedSA-LoRA (original)": (fedsa_lora, LORA_ORIGINAL),
        "FedSA-LoRA (otimizado)": (fedsa_lora, melhores["lora"]),
    }
    res = {nome: {"cv": [], "envio": None} for nome in metodos}
    for seed in SEEDS:
        traj = trajetoria_fedavg(tr, seed, device)
        for nome, m in metodos.items():
            if nome == "FedAvg":
                g = _base(traj, RODADAS, seed, device)
                modelos, envio = {s: g for s in tr}, {"rodadas": RODADAS, "por_rodada": A.n_parametros(g)}
            elif nome == "Só local":
                modelos, envio = so_local(tr, seed, device), {"rodadas": 0, "por_rodada": 0}
            else:
                modelos, envio = m[0](traj, m[1], tr, seed, device)
            cv = avaliar({s: A.kwh(modelos[s], f) for s, f in va.items()}, va)
            res[nome]["cv"].append(cv)
            res[nome]["envio"] = envio | {"total": envio_total(envio)}
            print(f"seed {seed} {nome}: {cv['Total']:.2f}", flush=True)
    res["configuracoes"] = melhores
    (SAIDA / "teste.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))

    print("\nCV(RMSE) em 2017 (média ± desvio de 3 seeds)")
    sites = [s for s in res["FedAvg"]["cv"][0] if s != "Total"]
    print(f"{'método':26s} {'Total':>13s} " + " ".join(f"{s:>6s}" for s in sites) + "   envio")
    for nome in metodos:
        tot = [c["Total"] for c in res[nome]["cv"]]
        por = " ".join(f"{np.mean([c[s] for c in res[nome]['cv']]):6.2f}" for s in sites)
        print(f"{nome:26s} {np.mean(tot):6.2f} ± {np.std(tot):.2f} {por}   {res[nome]['envio']['total']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etapa", choices=["ajuste", "teste"], required=True)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()
    global SAIDA
    clientes = construir()
    SAIDA = SAIDA / f"{len(clientes)}_sites"
    SAIDA.mkdir(parents=True, exist_ok=True)
    print("sites:", list(clientes), flush=True)
    (etapa_ajuste if args.etapa == "ajuste" else etapa_teste)(clientes, args.device)


if __name__ == "__main__":
    main()
