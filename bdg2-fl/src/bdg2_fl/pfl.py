"""FL personalizado sobre a MLP com janela achatada: fine-tuning local, FedPer e FedSA-LoRA.

uv run python -m bdg2_fl.pfl --seeds 42 43 44
uv run trackio show --project bdg2-pfl      # em outro terminal: acompanha o treino ao vivo

Todos os métodos usam o mesmo orçamento de 20 épocas por cliente, igual ao FedAvg de
rodar_arquiteturas.py (10 rodadas x 2 épocas):

- FedAvg + fine-tuning: 9 rodadas de FedAvg, depois 2 épocas locais no modelo inteiro.
- FedPer: 10 rodadas; as camadas de LOCAIS_FEDPER ficam no cliente e não entram na média
  (Arivazhagan et al., 2019).
- FedSA-LoRA: 5 rodadas de FedAvg para a base; depois a base congela e cada camada linear
  ganha um adaptador de posto POSTO (W x + B A x). Em mais 5 rodadas, só A entra na média e B
  fica no cliente (Guo et al., 2025). B começa em zero, então o modelo começa igual à base.

Resultados em out/pfl/, um JSON por método e seed, com o CV(RMSE) por site e os parâmetros
enviados por rodada. O acompanhamento ao vivo usa o Trackio, que grava localmente (sem conta e
sem servidor externo); --sem-trackio desliga.
"""
import argparse
import copy
import json
import math
import time

import torch
from torch import nn

from . import arquiteturas as A
from .config import RAIZ
from .dados import construir
from .rodar_arquiteturas import avaliar

MODELO = "MLP janela achatada"
RODADAS, EPOCAS_LOCAIS = 10, 2
RODADAS_BASE_LORA = 5
POSTO = 4
# camadas lineares da MLP: mlp.rede.0 (408->64), mlp.rede.2 (64->64), mlp.rede.4 (64->1)
LOCAIS_FEDPER = {
    "FedPer (saída local)": ("mlp.rede.4.",),
    "FedPer (camada 2 e saída locais)": ("mlp.rede.2.", "mlp.rede.4."),
}
SAIDA = RAIZ / "out" / "pfl"
PROJETO = "bdg2-pfl"


class Rastreio:
    """Registra, a cada rodada, a perda de treino e a de validação (MSE em z) de cada cliente."""

    def __init__(self, ativo, metodo, seed, fontes_va):
        self.ativo, self.fontes_va = ativo, fontes_va
        self.perda_treino = {}
        if ativo:
            import trackio
            self.trackio = trackio
            trackio.init(project=PROJETO, name=f"{metodo} | seed {seed}", group=metodo,
                         config={"metodo": metodo, "seed": seed, "rodadas": RODADAS,
                                 "epocas_locais": EPOCAS_LOCAIS, "posto_lora": POSTO})

    def callback(self, site):
        """Para o treinar(): guarda a perda da última época de cada cliente."""
        if not self.ativo:
            return None
        return lambda e, perda: self.perda_treino.__setitem__(site, perda)

    def rodada(self, r, modelos, enviados):
        if not self.ativo:
            return
        val = {s: A.mse_z(modelos[s], f) for s, f in self.fontes_va.items()}
        n = {s: f.n for s, f in self.fontes_va.items()}
        m = {f"val/{s}": v for s, v in val.items()}
        m["val/total"] = sum(val[s] * n[s] for s in val) / sum(n.values())
        m |= {f"treino/{s}": v for s, v in self.perda_treino.items()}
        m["parametros_enviados"] = enviados
        self.trackio.log(m, step=r)

    def fim(self, cv):
        if self.ativo:
            self.trackio.log({f"cv_rmse/{s}": v for s, v in cv.items()}, step=RODADAS)
            self.trackio.finish()


def _media(estados, peso, chaves):
    return {k: sum(peso[s] * estados[s][k] for s in estados) for k in chaves}


def _pesos(fontes_tr):
    total = sum(f.n for f in fontes_tr.values())
    return {s: f.n / total for s, f in fontes_tr.items()}


def _n(modelo, chaves):
    return sum(v.numel() for k, v in modelo.state_dict().items() if k in chaves)


def fedavg(fontes_tr, rodadas, seed, device, g, rast):
    global_ = A.novo(MODELO, seed, device)
    peso = _pesos(fontes_tr)
    n_env = _n(global_, global_.state_dict())
    for r in range(1, rodadas + 1):
        estados = {}
        for s, f in fontes_tr.items():
            local = copy.deepcopy(global_)
            A.treinar(local, f, EPOCAS_LOCAIS, g, rast.callback(s))
            estados[s] = local.state_dict()
        global_.load_state_dict(_media(estados, peso, global_.state_dict()))
        rast.rodada(r, {s: global_ for s in fontes_tr}, n_env)
    return global_


def metodo_fedavg(fontes_tr, seed, device, g, rast):
    m = fedavg(fontes_tr, RODADAS, seed, device, g, rast)
    return {s: m for s in fontes_tr}, _n(m, m.state_dict())


def metodo_fedavg_ft(fontes_tr, seed, device, g, rast):
    global_ = fedavg(fontes_tr, RODADAS - 1, seed, device, g, rast)
    modelos = {s: A.treinar(copy.deepcopy(global_), f, EPOCAS_LOCAIS, g, rast.callback(s))
               for s, f in fontes_tr.items()}
    rast.rodada(RODADAS, modelos, 0)          # última "rodada": só treino local, sem envio
    return modelos, _n(global_, global_.state_dict())


def metodo_fedper(prefixos_locais):
    def rodar(fontes_tr, seed, device, g, rast):
        base = A.novo(MODELO, seed, device)
        compart = [k for k in base.state_dict() if not k.startswith(prefixos_locais)]
        n_env = _n(base, compart)
        modelos = {s: copy.deepcopy(base) for s in fontes_tr}    # todos começam iguais
        peso = _pesos(fontes_tr)
        global_ = {k: base.state_dict()[k].clone() for k in compart}
        for r in range(1, RODADAS + 1):
            estados = {}
            for s, f in fontes_tr.items():
                modelos[s].load_state_dict(global_, strict=False)  # recebe só a parte federada
                A.treinar(modelos[s], f, EPOCAS_LOCAIS, g, rast.callback(s))
                estados[s] = modelos[s].state_dict()
            global_ = _media(estados, peso, compart)
            for m in modelos.values():
                m.load_state_dict(global_, strict=False)
            rast.rodada(r, modelos, n_env)
        return modelos, n_env
    return rodar


class LoRALinear(nn.Module):
    def __init__(self, base, posto):
        super().__init__()
        self.base = base
        for p in self.base.parameters():
            p.requires_grad_(False)
        self.A = nn.Parameter(torch.empty(posto, base.in_features, device=base.weight.device))
        nn.init.kaiming_uniform_(self.A, a=math.sqrt(5))          # inicialização do LoRA original
        self.B = nn.Parameter(torch.zeros(base.out_features, posto, device=base.weight.device))

    def forward(self, x):
        return self.base(x) + (x @ self.A.T) @ self.B.T


def _com_lora(modelo, posto):
    m = copy.deepcopy(modelo)
    rede = m.mlp.rede
    for i, camada in enumerate(rede):
        if isinstance(camada, nn.Linear):
            rede[i] = LoRALinear(camada, posto)
    return m


def metodo_fedsa_lora(fontes_tr, seed, device, g, rast):
    base = fedavg(fontes_tr, RODADAS_BASE_LORA, seed, device, g, rast)
    torch.manual_seed(seed)
    molde = _com_lora(base, POSTO)                               # A inicial igual para todos
    chaves_a = [k for k in molde.state_dict() if k.endswith(".A")]
    n_lora = _n(molde, chaves_a)
    modelos = {s: copy.deepcopy(molde) for s in fontes_tr}
    peso = _pesos(fontes_tr)
    global_a = {k: molde.state_dict()[k].clone() for k in chaves_a}
    for r in range(RODADAS_BASE_LORA + 1, RODADAS + 1):
        estados = {}
        for s, f in fontes_tr.items():
            modelos[s].load_state_dict(global_a, strict=False)  # recebe A; B continua local
            A.treinar(modelos[s], f, EPOCAS_LOCAIS, g, rast.callback(s))
            estados[s] = modelos[s].state_dict()
        global_a = _media(estados, peso, chaves_a)
        for m in modelos.values():
            m.load_state_dict(global_a, strict=False)
        rast.rodada(r, modelos, n_lora)
    n_total = _n(base, base.state_dict())
    return modelos, {"rodadas_base": RODADAS_BASE_LORA, "por_rodada_base": n_total,
                     "rodadas_lora": RODADAS - RODADAS_BASE_LORA, "por_rodada_lora": n_lora,
                     "B_local": _n(molde, [k for k in molde.state_dict() if k.endswith(".B")])}


METODOS = {
    "FedAvg": metodo_fedavg,
    "FedAvg + fine-tuning local": metodo_fedavg_ft,
    **{nome: metodo_fedper(pref) for nome, pref in LOCAIS_FEDPER.items()},
    "FedSA-LoRA": metodo_fedsa_lora,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="+", type=int, default=[42, 43, 44])
    ap.add_argument("--metodos", nargs="+", default=list(METODOS))
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--sem-trackio", action="store_true")
    args = ap.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)

    clientes = construir()
    fontes_tr = {s: A.Fonte(c["treino"], A.JANELA, args.device) for s, c in clientes.items()}
    fontes_va = {s: A.Fonte(c["val"], A.JANELA, args.device) for s, c in clientes.items()}

    for nome in args.metodos:
        for seed in args.seeds:
            arq = SAIDA / f"{nome.replace(' ', '_').replace('+', 'mais').replace('(', '').replace(')', '')}__seed{seed}.json"
            if arq.exists():
                print("já existe:", arq.name, flush=True)
                continue
            t = time.time()
            g = torch.Generator().manual_seed(seed)
            rast = Rastreio(not args.sem_trackio, nome, seed, fontes_va)
            modelos, envio = METODOS[nome](fontes_tr, seed, args.device, g, rast)
            cv = avaliar({s: A.kwh(modelos[s], f) for s, f in fontes_va.items()}, fontes_va)
            rast.fim(cv)
            res = {"metodo": nome, "seed": seed, "cv_rmse": cv,
                   "parametros_enviados": envio, "tempo_s": time.time() - t}
            arq.write_text(json.dumps(res, indent=1, ensure_ascii=False))
            print(f"{nome} seed {seed}: {cv['Total']:.2f}  envio {envio}  "
                  f"({res['tempo_s']:.0f} s)", flush=True)


if __name__ == "__main__":
    main()
