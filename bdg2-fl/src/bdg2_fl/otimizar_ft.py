"""Otimização do FedAvg + fine-tuning local para uma arquitetura (MLP janela achatada, GRU ou LSTM).

uv run python -m bdg2_fl.otimizar_ft --modelo GRU --etapa ajuste --device cuda
uv run python -m bdg2_fl.otimizar_ft --modelo GRU --etapa teste --device cuda

Mesmo protocolo de otimizar_pfl.py, só com o fine-tuning, e com o modelo como argumento:
- Ajuste: treino em jan-out/2016, validação em nov-dez/2016; 2017 não entra na escolha. Optuna
  (TPE, seed 0), --tentativas configurações, cada uma avaliada nas --seeds-ajuste. As duas
  primeiras tentativas são referências: a configuração original de pfl.py e a melhor da MLP no
  estudo de 6 sites.
- Teste: a melhor configuração é retreinada em 2016 inteiro e avaliada em 2017 nas --seeds-teste,
  junto com o FedAvg e o só local, todos com este mesmo código.

As funções de treino vêm de otimizar_pfl.py e recebem o modelo como argumento. As opções de camadas
que o fine-tuning pode treinar ficam em cada classe de arquiteturas.py (GRUPOS_FT). Nos recorrentes
há uma camada só, então as opções são "todas" e "saída" (a camada linear final).

Os pesos do teste ficam salvos (state_dict) para a análise de compressibilidade: o global do FedAvg,
o modelo de cada site depois do fine-tuning e o só local de cada site, por seed.

Resultados em out/otimizacao_ft/<n>_sites/<modelo>/: optuna.db, melhor.json, teste.json, pesos/.
"""
import argparse
import json
import time

import numpy as np
import optuna
import torch

from . import otimizar_pfl as O
from . import arquiteturas as A
from .config import RAIZ
from .dados import construir
from .rodar_arquiteturas import avaliar

MELHOR_MLP_6_SITES = {"rodadas_base": 10, "epocas": 30, "lr": 9.89112592334374e-05, "camadas": "todas"}


def _slug(nome):
    return nome.replace(" ", "_")


def _cv(modelos, va):
    return avaliar({s: A.kwh(modelos[s], f) for s, f in va.items()}, va)


def etapa_ajuste(clientes, args, saida):
    tr = O._fontes(clientes, "treino", args.device, "treino")
    va = O._fontes(clientes, "treino", args.device, "val")
    t = time.time()
    trajs = {seed: O.trajetoria_fedavg(args.modelo, tr, seed, args.device) for seed in args.seeds_ajuste}
    print(f"trajetórias do FedAvg: {time.time() - t:.0f} s", flush=True)
    ref = [_cv({s: O._base(args.modelo, trajs[seed], O.RODADAS, seed, args.device) for s in tr}, va)["Total"]
           for seed in args.seeds_ajuste]
    print(f"FedAvg na validação de ajuste: {np.mean(ref):.3f}", flush=True)

    def objetivo(t):
        cfg, notas = O.espaco_ft(t, args.modelo), []
        for seed in args.seeds_ajuste:
            inicio = time.time()
            modelos, _ = O.fine_tuning(args.modelo, trajs[seed], cfg, tr, seed, args.device)
            notas.append(_cv(modelos, va)["Total"])
            t.set_user_attr("tempo_s", time.time() - inicio)
        t.set_user_attr("por_seed", notas)
        print(f"tentativa {t.number}: {np.mean(notas):.3f}  {cfg}", flush=True)
        return float(np.mean(notas))

    estudo = optuna.create_study(study_name="ft", storage=f"sqlite:///{saida / 'optuna.db'}",
                                 load_if_exists=True, sampler=optuna.samplers.TPESampler(seed=0))
    if not estudo.trials:
        estudo.enqueue_trial(O.FT_ORIGINAL)
        estudo.enqueue_trial(MELHOR_MLP_6_SITES)
    feitas = sum(t.state == optuna.trial.TrialState.COMPLETE for t in estudo.trials)
    estudo.optimize(objetivo, n_trials=max(args.tentativas - feitas, 0))
    melhor = estudo.best_params
    print("melhor:", melhor, f"{estudo.best_value:.3f}", flush=True)
    (saida / "melhor.json").write_text(json.dumps(
        {"modelo": args.modelo, "seeds_ajuste": args.seeds_ajuste, "fedavg_val_ajuste": ref,
         "ft": melhor, "val_ajuste": estudo.best_value}, indent=1, ensure_ascii=False))


def etapa_teste(clientes, args, saida):
    melhor = json.loads((saida / "melhor.json").read_text())["ft"]
    tr = O._fontes(clientes, "treino", args.device)
    va = O._fontes(clientes, "val", args.device)
    pesos = saida / "pesos"
    pesos.mkdir(exist_ok=True)
    # retoma um teste.json existente: seeds já feitas são puladas. Permite rodar uma seed por processo
    # (na T4 do Colab, com 12 GB de RAM, o processo é morto por falta de memória na 2ª seed).
    arq = saida / "teste.json"
    if arq.exists():
        res = json.loads(arq.read_text())
        res["seeds"] = [int(s) for s in res["tempo_s"]]   # só as seeds de fato concluídas
    else:
        res = {"modelo": args.modelo, "ft": melhor, "seeds": [],
               "metodos": {m: [] for m in ("FedAvg", "Só local", "FedAvg + fine-tuning")}, "tempo_s": {}}
    for seed in args.seeds_teste:
        if str(seed) in res["tempo_s"]:
            print(f"seed {seed}: já está em teste.json", flush=True)
            continue
        res["seeds"].append(seed)
        t = time.time()
        traj = O.trajetoria_fedavg(args.modelo, tr, seed, args.device)
        g = O._base(args.modelo, traj, O.RODADAS, seed, args.device)
        torch.save(g.state_dict(), pesos / f"seed{seed}_global_fedavg.pt")
        res["metodos"]["FedAvg"].append(_cv({s: g for s in tr}, va))

        ft, _ = O.fine_tuning(args.modelo, traj, melhor, tr, seed, args.device)
        torch.save({s: m.state_dict() for s, m in ft.items()}, pesos / f"seed{seed}_ft.pt")
        # o global de onde o fine-tuning partiu (pode ser uma rodada anterior à última)
        torch.save(traj[melhor["rodadas_base"]], pesos / f"seed{seed}_global_base_ft.pt")
        res["metodos"]["FedAvg + fine-tuning"].append(_cv(ft, va))

        loc = O.so_local(args.modelo, tr, seed, args.device)
        torch.save({s: m.state_dict() for s, m in loc.items()}, pesos / f"seed{seed}_local.pt")
        res["metodos"]["Só local"].append(_cv(loc, va))

        res["tempo_s"][str(seed)] = time.time() - t
        print(f"seed {seed}: " + "  ".join(f"{m} {v[-1]['Total']:.2f}" for m, v in res["metodos"].items())
              + f"  ({res['tempo_s'][str(seed)] / 60:.0f} min)", flush=True)
        arq.write_text(json.dumps(res, indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", choices=A.COM_FT, required=True)
    ap.add_argument("--etapa", choices=["ajuste", "teste", "ambas"], required=True)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--tentativas", type=int, default=20)
    ap.add_argument("--seeds-ajuste", nargs="+", type=int, default=[42])
    ap.add_argument("--seeds-teste", nargs="+", type=int, default=[42, 505, 11])
    args = ap.parse_args()
    clientes = construir()
    saida = RAIZ / "out" / "otimizacao_ft" / f"{len(clientes)}_sites" / _slug(args.modelo)
    saida.mkdir(parents=True, exist_ok=True)
    if args.etapa in ("ajuste", "ambas"):
        etapa_ajuste(clientes, args, saida)
    if args.etapa in ("teste", "ambas"):
        etapa_teste(clientes, args, saida)


if __name__ == "__main__":
    main()
