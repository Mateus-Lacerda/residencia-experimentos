"""Fine-tuning local com hiperparâmetros escolhidos por site.

uv run python -m bdg2_fl.ft_por_site --etapa ajuste
uv run python -m bdg2_fl.ft_por_site --etapa teste

Ajuste (um estudo do Optuna por site, N_TENTATIVAS tentativas, seed SEED_AJUSTE):
- treino em jan-out/2016, validação em nov-dez/2016 do próprio site, em CV(RMSE) de kWh;
- cada tentativa escolhe a rodada do FedAvg de onde partir, o lr e as camadas, treina até
  EPOCAS_MAX épocas e mede a validação depois de cada época, inclusive na época 0 (o modelo global
  sem ajuste). A nota é o melhor ponto da curva, e a época desse ponto vai junto com a
  configuração. Se a época 0 ganhar, o site fica com o modelo global.
- a primeira tentativa de cada site é a configuração uniforme escolhida com 6 sites.

Teste: cada site usa a sua configuração e o seu número de épocas, fixos; FedAvg e fine-tuning
retreinados em 2016 inteiro, avaliados em 2017, com 3 seeds. As referências (random walk, FedAvg,
só local, fine-tuning uniforme) vêm de out/todos_sites/por_site.csv, que usa os mesmos dados e
seeds. Trackio, projeto bdg2-ft-por-site: perda de treino e CV(RMSE) do teste por época, só para
diagnóstico (a escolha já foi feita antes, na validação).
"""
import argparse
import json

import numpy as np
import optuna
import pandas as pd
import torch

from . import arquiteturas as A
from . import otimizar_pfl as O
from .config import RAIZ
from .dados import construir
from .metricas import rmse_cv

SAIDA = RAIZ / "out" / "ft_por_site"
PROJETO = "bdg2-ft-por-site"
DEVICE = "cpu"
N_TENTATIVAS = 30
SEED_AJUSTE = 42
EPOCAS_MAX = 32
FT_UNIFORME = {"rodadas_base": 10, "lr": 9.89112592334374e-05, "camadas": "todas"}


def cv(fonte, prev):
    return 100 * rmse_cv(fonte.df["y_kwh"].to_numpy(), prev)["cv_rmse"]


def ajustar(traj, cfg, f_tr, epocas, seed, f_aval=None, ao_fim_da_epoca=None):
    """Fine-tuning de um site. Devolve o modelo e, se f_aval, a curva de CV(RMSE) por época
    (índice 0 = antes de treinar)."""
    m = O._base(traj, cfg["rodadas_base"], seed, DEVICE)
    for k, p in m.named_parameters():
        p.requires_grad_(k.startswith(O.CAMADAS_FT[cfg["camadas"]]))
    curva = [cv(f_aval, A.kwh(m, f_aval))] if f_aval else []

    def cb(e, perda, modelo):
        if f_aval:
            curva.append(cv(f_aval, A.kwh(modelo, f_aval)))
        if ao_fim_da_epoca:
            ao_fim_da_epoca(e, perda, curva[-1] if curva else None)

    g = torch.Generator().manual_seed(seed + 1000)
    O.treinar(m, f_tr, epocas, g, cfg["lr"], cb if (f_aval or ao_fim_da_epoca) else None)
    return m, curva


def etapa_ajuste(clientes):
    tr = O._fontes(clientes, "treino", DEVICE, "treino")
    va = O._fontes(clientes, "treino", DEVICE, "val")
    traj = O.trajetoria_fedavg(tr, SEED_AJUSTE, DEVICE)
    escolhas = {}
    for s in tr:
        def objetivo(t):
            cfg = {"rodadas_base": t.suggest_int("rodadas_base", 1, O.RODADAS),
                   "lr": t.suggest_float("lr", 1e-5, 1e-2, log=True),
                   "camadas": t.suggest_categorical("camadas", list(O.CAMADAS_FT))}
            _, curva = ajustar(traj, cfg, tr[s], EPOCAS_MAX, SEED_AJUSTE, va[s])
            t.set_user_attr("epocas", int(np.argmin(curva)))
            t.set_user_attr("curva", curva)
            return float(min(curva))

        estudo = optuna.create_study(study_name=f"ft_{s}", storage=f"sqlite:///{SAIDA / 'optuna.db'}",
                                     load_if_exists=True, sampler=optuna.samplers.TPESampler(seed=0))
        if not estudo.trials:
            estudo.enqueue_trial(FT_UNIFORME)
        feitas = sum(t.state == optuna.trial.TrialState.COMPLETE for t in estudo.trials)
        estudo.optimize(objetivo, n_trials=max(N_TENTATIVAS - feitas, 0))
        b = estudo.best_trial
        uniforme = estudo.trials[0]
        escolhas[s] = b.params | {"epocas": b.user_attrs["epocas"], "val": b.value,
                                  "val_global": b.user_attrs["curva"][0],
                                  "val_uniforme_30": uniforme.user_attrs["curva"][30]}
        print(f"{s}: {escolhas[s]}", flush=True)
    (SAIDA / "escolhas.json").write_text(json.dumps(escolhas, indent=1, ensure_ascii=False))


def etapa_teste(clientes):
    import trackio
    escolhas = json.loads((SAIDA / "escolhas.json").read_text())
    tr = O._fontes(clientes, "treino", DEVICE)
    te = O._fontes(clientes, "val", DEVICE)          # 2017
    linhas = []
    for seed in O.SEEDS:
        traj = O.trajetoria_fedavg(tr, seed, DEVICE)
        trackio.init(project=PROJETO, name=f"FT por site | seed {seed}", group="FT por site",
                     config={"seed": seed, "escolhas": escolhas})
        prev = {}
        for s in tr:
            cfg = escolhas[s]
            m, _ = ajustar(traj, cfg, tr[s], cfg["epocas"], seed, te[s] if cfg["epocas"] else None,
                           lambda e, p, c, s=s: trackio.log({f"treino/{s}": p, f"teste_cv/{s}": c}, step=e + 1))
            prev[s] = A.kwh(m, te[s])
            linhas.append({"metodo": "FT por site", "seed": O.SEEDS.index(seed), "site": s, "cv": cv(te[s], prev[s])})
        tot = 100 * rmse_cv(np.concatenate([te[s].df["y_kwh"].to_numpy() for s in tr]),
                            np.concatenate([prev[s] for s in tr]))["cv_rmse"]
        linhas.append({"metodo": "FT por site", "seed": O.SEEDS.index(seed), "site": "Total", "cv": tot})
        trackio.log({"teste_cv/Total": tot}, step=EPOCAS_MAX)
        trackio.finish()
        print(f"seed {seed}: total {tot:.2f}", flush=True)
    novo = pd.DataFrame(linhas)
    novo.to_csv(SAIDA / "por_site.csv", index=False)

    ref = pd.read_csv(RAIZ / "out" / "todos_sites" / "por_site.csv")
    ref["metodo"] = ref["metodo"].replace({"FedAvg + fine-tuning": "FT uniforme"})
    todos = pd.concat([ref, novo])
    ordem = ["Random walk", "FedAvg", "Só local", "FT uniforme", "FT por site"]
    sites = list(tr) + ["Total"]
    media = todos.groupby(["site", "metodo"]).cv.mean().unstack()[ordem].loc[sites]
    desvio = todos.groupby(["site", "metodo"]).cv.std().unstack()[ordem].loc[sites]
    pd.set_option("display.width", 200)
    print("\nCV(RMSE) em 2017 por site (média de 3 seeds)")
    print(media.round(2).to_string())
    print("\ndesvio entre seeds")
    print(desvio.round(2).to_string())
    print("\nconfiguração por site")
    print(pd.DataFrame(escolhas).T.to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--etapa", choices=["ajuste", "teste"], required=True)
    args = ap.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    clientes = construir()
    print("sites:", {s: len(c["edificacoes"]) for s, c in clientes.items()}, flush=True)
    (etapa_ajuste if args.etapa == "ajuste" else etapa_teste)(clientes)


if __name__ == "__main__":
    main()
