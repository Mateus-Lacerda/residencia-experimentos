"""Fine-tuning local com hiperparâmetros escolhidos por site, para GRU, LSTM ou MLP janela achatada.

uv run python -m bdg2_fl.ft_por_site --modelo GRU --etapa ajuste --device cuda [--sites Rat Hog]
uv run python -m bdg2_fl.ft_por_site --modelo GRU --etapa teste --device cuda [--seeds-teste 42]

Ajuste (um estudo do Optuna por site, --tentativas tentativas, seed 42):
- treino em jan-out/2016, validação em nov-dez/2016 do próprio site, em CV(RMSE) de kWh;
- cada tentativa escolhe a rodada do FedAvg de onde partir, o lr e as camadas, treina até
  EPOCAS_MAX épocas e mede a validação depois de cada época, inclusive na época 0 (o modelo da
  rodada base, sem ajuste). A nota é o melhor ponto da curva, e a época desse ponto vai junto com a
  configuração. Se a época 0 ganhar, o site fica com o modelo da rodada base sem ajuste.
- a primeira tentativa de cada site é a configuração uniforme do modelo, de
  out/otimizacao_ft/<n>_sites/<modelo>/melhor.json.
- a trajetória do FedAvg do ajuste fica salva (trajetoria_ajuste.pt), para que cada site possa
  rodar num processo separado sem retreinar o FedAvg.

Teste: cada site usa a sua configuração e o seu número de épocas, fixos; FedAvg retreinado em 2016
inteiro e fine-tuning avaliado em 2017, nas mesmas seeds do teste de otimizar_ft (42, 505, 11), que
traz as referências (FedAvg, só local, fine-tuning uniforme). Retoma um teste.json existente, para
rodar uma seed por processo.

Resultados em out/ft_por_site/<n>_sites/<modelo>/: optuna.db, escolhas.json, teste.json, pesos/.
"""
import argparse
import json
import time

import numpy as np
import optuna
import torch

from . import arquiteturas as A
from . import otimizar_pfl as O
from .config import RAIZ
from .dados import construir
from .metricas import rmse_cv
from .otimizar_ft import _slug

EPOCAS_MAX = 32
SEED_AJUSTE = 42


def cv(fonte, prev):
    return 100 * rmse_cv(fonte.df["y_kwh"].to_numpy(), prev)["cv_rmse"]


def ajustar(modelo, traj, cfg, f_tr, epocas, seed, device, f_aval=None):
    """Fine-tuning de um site. Devolve o modelo e, se f_aval, a curva de CV(RMSE) por época
    (índice 0 = antes de treinar)."""
    m = A.liberar(O._base(modelo, traj, cfg["rodadas_base"], seed, device), cfg["camadas"])
    curva = [cv(f_aval, A.kwh(m, f_aval))] if f_aval else []

    def cb(e, perda, modelo):
        curva.append(cv(f_aval, A.kwh(modelo, f_aval)))

    g = torch.Generator().manual_seed(seed + 1000)
    O.treinar(m, f_tr, epocas, g, cfg["lr"], cb if f_aval else None)
    return m, curva


def etapa_ajuste(clientes, args, saida):
    tr = O._fontes(clientes, "treino", args.device, "treino")
    va = O._fontes(clientes, "treino", args.device, "val")
    arq_traj = saida / "trajetoria_ajuste.pt"
    if arq_traj.exists():
        traj = torch.load(arq_traj, map_location=args.device)
    else:
        t = time.time()
        traj = O.trajetoria_fedavg(args.modelo, tr, SEED_AJUSTE, args.device)
        torch.save(traj, arq_traj)
        print(f"trajetória do FedAvg: {time.time() - t:.0f} s", flush=True)
    uniforme = json.loads((RAIZ / "out" / "otimizacao_ft" / saida.parent.name / _slug(args.modelo)
                           / "melhor.json").read_text())["ft"]
    arq_esc = saida / "escolhas.json"
    escolhas = json.loads(arq_esc.read_text()) if arq_esc.exists() else {}
    for s in args.sites or list(tr):
        def objetivo(t):
            cfg = {"rodadas_base": t.suggest_int("rodadas_base", 1, O.RODADAS),
                   "lr": t.suggest_float("lr", 1e-5, 1e-2, log=True),
                   "camadas": t.suggest_categorical("camadas", list(A.grupos_ft(args.modelo)))}
            inicio = time.time()
            _, curva = ajustar(args.modelo, traj, cfg, tr[s], EPOCAS_MAX, SEED_AJUSTE, args.device, va[s])
            t.set_user_attr("epocas", int(np.argmin(curva)))
            t.set_user_attr("curva", curva)
            t.set_user_attr("tempo_s", time.time() - inicio)
            print(f"{s} tentativa {t.number}: {min(curva):.3f} (época {int(np.argmin(curva))}, "
                  f"{time.time() - inicio:.0f} s)  {cfg}", flush=True)
            return float(min(curva))

        estudo = optuna.create_study(study_name=f"ft_{s}", storage=f"sqlite:///{saida / 'optuna.db'}",
                                     load_if_exists=True, sampler=optuna.samplers.TPESampler(seed=0))
        if not estudo.trials:
            estudo.enqueue_trial({k: uniforme[k] for k in ("rodadas_base", "lr", "camadas")})
        feitas = sum(t.state == optuna.trial.TrialState.COMPLETE for t in estudo.trials)
        estudo.optimize(objetivo, n_trials=max(args.tentativas - feitas, 0))
        b, u = estudo.best_trial, estudo.trials[0]
        escolhas[s] = b.params | {"epocas": b.user_attrs["epocas"], "val": b.value,
                                  "val_rodada_base": b.user_attrs["curva"][0],
                                  "val_uniforme": u.user_attrs["curva"][min(uniforme["epocas"], EPOCAS_MAX)]}
        print(f"{s}: {escolhas[s]}", flush=True)
        arq_esc.write_text(json.dumps(escolhas, indent=1, ensure_ascii=False))


def etapa_teste(clientes, args, saida):
    escolhas = json.loads((saida / "escolhas.json").read_text())
    tr = O._fontes(clientes, "treino", args.device)
    te = O._fontes(clientes, "val", args.device)          # 2017
    pesos = saida / "pesos"
    pesos.mkdir(exist_ok=True)
    arq = saida / "teste.json"
    res = json.loads(arq.read_text()) if arq.exists() else {
        "modelo": args.modelo, "escolhas": escolhas, "FT por site": {}, "tempo_s": {}}
    for seed in args.seeds_teste:
        if str(seed) in res["tempo_s"]:
            print(f"seed {seed}: já está em teste.json", flush=True)
            continue
        t = time.time()
        traj = O.trajetoria_fedavg(args.modelo, tr, seed, args.device)
        prev, modelos = {}, {}
        for s in tr:
            cfg = escolhas[s]
            m, _ = ajustar(args.modelo, traj, cfg, tr[s], cfg["epocas"], seed, args.device)
            prev[s], modelos[s] = A.kwh(m, te[s]), m.state_dict()
        torch.save(modelos, pesos / f"seed{seed}_ft_por_site.pt")
        r = {s: cv(te[s], prev[s]) for s in tr}
        r["Total"] = 100 * rmse_cv(np.concatenate([te[s].df["y_kwh"].to_numpy() for s in tr]),
                                   np.concatenate([prev[s] for s in tr]))["cv_rmse"]
        res["FT por site"][str(seed)] = r
        res["tempo_s"][str(seed)] = time.time() - t
        print(f"seed {seed}: total {r['Total']:.2f}  ({res['tempo_s'][str(seed)] / 60:.0f} min)", flush=True)
        arq.write_text(json.dumps(res, indent=1, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", choices=A.COM_FT, required=True)
    ap.add_argument("--etapa", choices=["ajuste", "teste"], required=True)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--tentativas", type=int, default=30)
    ap.add_argument("--sites", nargs="+")
    ap.add_argument("--seeds-teste", nargs="+", type=int, default=[42, 505, 11])
    # pasta de saída (padrão: o nome do modelo). Outra pasta permite dividir os sites entre máquinas
    # sem uma sobrescrever o optuna.db e o escolhas.json da outra; depois as escolhas são juntadas.
    ap.add_argument("--pasta")
    args = ap.parse_args()
    clientes = construir()
    saida = RAIZ / "out" / "ft_por_site" / f"{len(clientes)}_sites" / (args.pasta or _slug(args.modelo))
    saida.mkdir(parents=True, exist_ok=True)
    (etapa_ajuste if args.etapa == "ajuste" else etapa_teste)(clientes, args, saida)


if __name__ == "__main__":
    main()
