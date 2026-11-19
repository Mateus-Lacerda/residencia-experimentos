"""Vencedor (FedAvg + fine-tuning local) com todas as edificações aprovadas de cada site.

uv run python -m bdg2_fl.avaliar_todos_sites

Usa a seleção de config.py (hoje: sites com pelo menos MIN_EDIF_POR_SITE edificações, sem máximo
por site) e a configuração de fine-tuning escolhida no ajuste com 6 sites
(out/otimizacao_pfl/6_sites/melhores.json); não há novo ajuste de hiperparâmetros.
Treino em 2016, teste em 2017, 3 seeds. Compara com FedAvg, só local e random walk, por site e por
edificação. Resultados em out/todos_sites/.

Acompanhamento no Trackio, projeto bdg2-todos-sites (val = MSE em z na validação 2017):
- FedAvg: validação de cada site e total a cada rodada;
- fine-tuning e só local: perda de treino e validação de cada site a cada época.
GRADIO_ANALYTICS_ENABLED=False uv run trackio show --project bdg2-todos-sites
"""
import json
import time

import numpy as np
import pandas as pd
import trackio

from . import arquiteturas as A
from . import otimizar_pfl as O
from .config import RAIZ
from .dados import construir
from .metricas import rmse_cv

SAIDA = RAIZ / "out" / "todos_sites"
PROJETO = "bdg2-todos-sites"
DEVICE = "cpu"


def cv(real, prev):
    return 100 * rmse_cv(real, prev)["cv_rmse"]


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    cfg_ft = json.loads((RAIZ / "out" / "otimizacao_pfl" / "6_sites" / "melhores.json").read_text())["ft"]
    clientes = construir()
    tr = {s: A.Fonte(c["treino"], A.JANELA, DEVICE) for s, c in clientes.items()}
    va = {s: A.Fonte(c["val"], A.JANELA, DEVICE) for s, c in clientes.items()}
    sites = list(va)
    total = sum(f.n for f in tr.values())
    print({s: (len(clientes[s]["edificacoes"]), round(100 * tr[s].n / total, 1)) for s in sites}, flush=True)

    real = {s: va[s].df["y_kwh"].to_numpy() for s in sites}
    edif = {s: va[s].df["edif"].to_numpy() for s in sites}
    prevs = {"Random walk": [{s: va[s].df["rw_kwh"].to_numpy() for s in sites}]}
    prevs |= {m: [] for m in ("FedAvg", "Só local", "FedAvg + fine-tuning")}
    n_va = {s: va[s].n for s in sites}

    def val_global(r, modelo):
        val = {s: A.mse_z(modelo, va[s]) for s in sites}
        total = sum(val[s] * n_va[s] for s in sites) / sum(n_va.values())
        trackio.log({f"val/{s}": v for s, v in val.items()} | {"val/total": total}, step=r)

    def epoca_local(s, e, perda, modelo):
        trackio.log({f"treino/{s}": perda, f"val/{s}": A.mse_z(modelo, va[s])}, step=e + 1)

    def inicio(metodo, seed):
        trackio.init(project=PROJETO, name=f"{metodo} | seed {seed}", group=metodo,
                     config={"metodo": metodo, "seed": seed, "sites": len(sites), "ft": cfg_ft})

    for seed in O.SEEDS:
        t = time.time()
        inicio("FedAvg", seed)
        traj = O.trajetoria_fedavg(O.MODELO, tr, seed, DEVICE, val_global)
        trackio.finish()
        g = O._base(O.MODELO, traj, O.RODADAS, seed, DEVICE)
        prevs["FedAvg"].append({s: A.kwh(g, va[s]) for s in sites})
        inicio("FedAvg + fine-tuning", seed)
        ft, _ = O.fine_tuning(O.MODELO, traj, cfg_ft, tr, seed, DEVICE, epoca_local)
        trackio.finish()
        prevs["FedAvg + fine-tuning"].append({s: A.kwh(ft[s], va[s]) for s in sites})
        inicio("Só local", seed)
        loc = O.so_local(O.MODELO, tr, seed, DEVICE, ao_fim_da_epoca=epoca_local)
        trackio.finish()
        prevs["Só local"].append({s: A.kwh(loc[s], va[s]) for s in sites})
        print(f"seed {seed}: {(time.time() - t) / 60:.0f} min", flush=True)

    # por site e total (média entre seeds do CV de cada seed)
    linhas = []
    for m, lista in prevs.items():
        for i, p in enumerate(lista):
            for s in sites:
                linhas.append({"metodo": m, "seed": i, "site": s, "cv": cv(real[s], p[s])})
            linhas.append({"metodo": m, "seed": i, "site": "Total",
                           "cv": cv(np.concatenate([real[s] for s in sites]), np.concatenate([p[s] for s in sites]))})
    por_site = pd.DataFrame(linhas)
    por_site.to_csv(SAIDA / "por_site.csv", index=False)

    # por edificação: CV de cada seed; a média entre seeds é feita na leitura
    linhas = []
    for m, lista in prevs.items():
        for i, p in enumerate(lista):
            for s in sites:
                for b in np.unique(edif[s]):
                    k = edif[s] == b
                    linhas.append({"metodo": m, "seed": i, "site": s, "edif": b, "cv": cv(real[s][k], p[s][k])})
    por_edif = pd.DataFrame(linhas)
    por_edif.to_csv(SAIDA / "por_edificacao.csv", index=False)
    (SAIDA / "config.json").write_text(json.dumps(
        {"ft": cfg_ft, "edificacoes": {s: len(clientes[s]["edificacoes"]) for s in sites},
         "peso_fedavg": {s: tr[s].n / total for s in sites}}, indent=1, ensure_ascii=False))

    pd.set_option("display.width", 200)
    media = por_site.groupby(["site", "metodo"]).cv.mean().unstack()[list(prevs)].loc[sites + ["Total"]]
    print("\nCV(RMSE) em 2017 por site (média de 3 seeds)")
    print(media.round(2).to_string())
    e = por_edif.groupby(["site", "edif", "metodo"]).cv.mean().unstack()
    print("\nFração de edificações em que o fine-tuning ganha de cada referência")
    print(pd.DataFrame({r: (e["FedAvg + fine-tuning"] < e[r]).groupby("site").mean()
                        for r in ("Random walk", "FedAvg", "Só local")}).round(2).to_string())


if __name__ == "__main__":
    main()
