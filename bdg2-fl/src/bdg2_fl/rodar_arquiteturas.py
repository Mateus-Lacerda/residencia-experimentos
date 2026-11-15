"""Roda centralizado, só local e FedAvg para cada arquitetura e grava o CV(RMSE) por site.

uv run python -m bdg2_fl.rodar_arquiteturas --modelos "LSTM" "GRU" --device mps --seeds 42
uv run trackio show --project bdg2-arquiteturas   # em outro terminal: acompanha o treino ao vivo

Todas as arquiteturas usam o mesmo orçamento de passadas sobre os dados: EPOCAS no centralizado e
no só local, e RODADAS x EPOCAS_LOCAIS no FedAvg. É menor que o do treinamento.ipynb (60) porque
os modelos sequenciais são ~10x mais lentos por época.
"""
import argparse
import json
import time

import numpy as np

from . import arquiteturas as A
from .config import RAIZ
from .dados import construir
from .metricas import rmse_cv

EPOCAS = 20
RODADAS, EPOCAS_LOCAIS = 10, 2
SAIDA = RAIZ / "out" / "arquiteturas"


class _Rastreio:
    """Um run do Trackio por (modelo, seed, método), no projeto bdg2-arquiteturas."""

    def __init__(self, ativo, modelo, seed):
        self.ativo, self.modelo, self.seed = ativo, modelo, seed
        if ativo:
            import trackio
            self.trackio = trackio

    def inicio(self, metodo):
        if self.ativo:
            self.trackio.init(project="bdg2-arquiteturas", name=f"{self.modelo} | {metodo} | seed {self.seed}",
                              group=f"{self.modelo} | {metodo}",
                              config={"modelo": self.modelo, "metodo": metodo, "seed": self.seed})

    def epoca(self, montar):
        """Embrulha um callback que devolve (métricas, passo) e manda para o Trackio."""
        if not self.ativo:
            return None
        return lambda *a: self.trackio.log(*montar(*a))

    def fim(self, cv, passo):
        if self.ativo:
            self.trackio.log({f"cv_rmse/{s}": v for s, v in cv.items()}, step=passo)
            self.trackio.finish()


def avaliar(prev, fontes_va):
    sites = list(fontes_va)
    real = {s: fontes_va[s].df["y_kwh"].to_numpy() for s in sites}
    cv = {s: 100 * rmse_cv(real[s], prev[s])["cv_rmse"] for s in sites}
    cv["Total"] = 100 * rmse_cv(np.concatenate([real[s] for s in sites]),
                                np.concatenate([prev[s] for s in sites]))["cv_rmse"]
    return cv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelos", nargs="+", default=list(A.MODELOS))
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--seeds", nargs="+", type=int, default=[42])
    ap.add_argument("--so-fedavg", action="store_true", help="pula o centralizado e o só local")
    ap.add_argument("--sem-trackio", action="store_true")
    args = ap.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)

    clientes = construir()
    fontes_tr = {s: A.Fonte(c["treino"], A.JANELA, args.device) for s, c in clientes.items()}
    fontes_va = {s: A.Fonte(c["val"], A.JANELA, args.device) for s, c in clientes.items()}

    rw = avaliar({s: f.df["rw_kwh"].to_numpy() for s, f in fontes_va.items()}, fontes_va)
    (SAIDA / "random_walk.json").write_text(json.dumps(rw, indent=1))

    for nome in args.modelos:
        for seed in args.seeds:
            arq = SAIDA / f"{nome.replace(' ', '_').replace('×', 'x')}__seed{seed}.json"
            if arq.exists():
                print("já existe:", arq.name, flush=True)
                continue
            res = {"modelo": nome, "seed": seed, "device": args.device,
                   "parametros": A.n_parametros(A.novo(nome, seed, args.device)), "tempo_s": {}}
            rast = _Rastreio(not args.sem_trackio, nome, seed)
            if not args.so_fedavg:
                t = time.time()
                rast.inicio("centralizado")
                m = A.centralizado(nome, fontes_tr, EPOCAS, seed, args.device,
                                   rast.epoca(lambda e, p: ({"treino/perda": p}, e + 1)))
                res["centralizado"] = avaliar({s: A.kwh(m, f) for s, f in fontes_va.items()}, fontes_va)
                rast.fim(res["centralizado"], EPOCAS)
                res["tempo_s"]["centralizado"] = time.time() - t
                t = time.time()
                rast.inicio("local")
                ms = A.locais(nome, fontes_tr, EPOCAS, seed, args.device,
                              rast.epoca(lambda s, e, p: ({f"treino/{s}": p}, e + 1)))
                res["local"] = avaliar({s: A.kwh(ms[s], f) for s, f in fontes_va.items()}, fontes_va)
                rast.fim(res["local"], EPOCAS)
                res["tempo_s"]["local"] = time.time() - t
            t = time.time()
            rast.inicio("federado")

            def val_rodada(r, modelo):
                val = {s: A.mse_z(modelo, f) for s, f in fontes_va.items()}
                n = {s: f.n for s, f in fontes_va.items()}
                total = sum(val[s] * n[s] for s in val) / sum(n.values())
                return {f"val/{s}": v for s, v in val.items()} | {"val/total": total}, r

            m = A.fedavg(nome, fontes_tr, RODADAS, EPOCAS_LOCAIS, seed, args.device, rast.epoca(val_rodada))
            res["federado"] = avaliar({s: A.kwh(m, f) for s, f in fontes_va.items()}, fontes_va)
            rast.fim(res["federado"], RODADAS)
            res["tempo_s"]["federado"] = time.time() - t
            arq.write_text(json.dumps(res, indent=1, ensure_ascii=False))
            outros = "".join(f"  {k} {res[k]['Total']:.1f}" for k in ("centralizado", "local") if k in res)
            print(f"{nome} seed {seed}: FedAvg {res['federado']['Total']:.1f}{outros}  "
                  f"({sum(res['tempo_s'].values()) / 60:.0f} min)", flush=True)


if __name__ == "__main__":
    main()
