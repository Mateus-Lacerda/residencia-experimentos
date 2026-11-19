"""GRU do FedAvg nos 11 sites no desenho few-shot da FedRSA (Ryu, 2026, IEEE Access 14:53618), no BDG2.

uv run python -m bdg2_fl.baseline_fedrsa

Desenho do artigo (seção IV e Tabela 8): edificações não vistas (um escritório e uma residencial do
BDG2) fazem fine-tuning com K = 5, 7 ou 14 dias de dados locais e são avaliadas nos 5 dias seguintes,
1 h à frente, em MAPE. O artigo não publica as edificações nem o período, então aqui o desenho roda
em todas as edificações de escritório e residenciais (Lodging/residential) de sites fora dos 11 do
FedAvg (Panther e Cockatoo), com pelo menos 90% de leituras em 2017 e mediana de pelo menos 1 kWh,
e em 12 janelas por edificação, começando no dia 1 de cada mês de 2017.

Em cada janela, a normalização da edificação (consumo, clima, outros medidores) usa só os K dias.
As entradas da GRU usam lags de até 168 h, que para K = 5 e 7 olham para antes do início da janela;
fica registrado como diferença do desenho do artigo.

Cenários, nas 3 seeds (42, 505, 11): zero-shot (global do FedAvg) e FT uniforme (a configuração que
o servidor manda, melhor.json da GRU) nos K dias. Persistência (t-1) como referência.

Referência (Tabela 8, MAPE %, K=5/7/14): FedRSA escritório 10,7/10,1/8,92, residencial
11,84/11,1/9,93; FedAvg com fine-tuning escritório 15,2/14,1/12,3, residencial 16,8/15,62/13,47.

Resultados em out/baseline_fedrsa/: por_janela.csv, resumo.csv.
"""
import json

import numpy as np
import pandas as pd
import torch

from . import arquiteturas as A
from . import otimizar_pfl as O
from .config import RAIZ, RAW
from .dados import FEATURES, MEDIDORES_OPCIONAIS, _ler_medidor, clima_site, features_edificacao, tempo_calendario

SAIDA = RAIZ / "out" / "baseline_fedrsa"
BASE = RAIZ / "out" / "otimizacao_ft" / "11_sites" / "GRU"
SEEDS = [42, 505, 11]
KS = [5, 7, 14]
DIAS_TESTE = 5
VISTOS = {"Rat", "Hog", "Fox", "Bull", "Eagle", "Bear", "Robin", "Wolf", "Peacock", "Gator", "Lamb"}
USOS = {"Office": "escritório", "Lodging/residential": "residencial"}
INICIOS = pd.date_range("2017-01-01", "2017-12-01", freq="MS")

REF = {("escritório", "FedRSA"): [10.7, 10.1, 8.92], ("residencial", "FedRSA"): [11.84, 11.1, 9.93],
       ("escritório", "FedAvg + FT"): [15.2, 14.1, 12.3], ("residencial", "FedAvg + FT"): [16.8, 15.62, 13.47]}


def mape(y, p):
    ok = y > 0
    return float(100 * np.mean(np.abs((p[ok] - y[ok]) / y[ok])))


def selecionar(elec):
    meta = pd.read_csv(RAW / "metadata.csv")
    c = meta[~meta.site_id.isin(VISTOS) & meta.primaryspaceusage.isin(USOS) & meta.building_id.isin(elec.columns)]
    e7 = elec.loc["2017"]
    c = c[c.building_id.map(lambda b: e7[b].notna().mean() >= 0.9 and e7[b].median() >= 1)]
    return c.set_index("building_id")[["site_id", "primaryspaceusage"]]


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    ft = json.loads((BASE / "melhor.json").read_text())["ft"]
    elec = _ler_medidor("electricity")
    outros = {m: _ler_medidor(m) for m in MEDIDORES_OPCIONAIS}
    clima = pd.read_csv(RAW / "weather.csv", parse_dates=["timestamp"])
    idx = elec.index
    tempo = tempo_calendario(idx)
    edifs = selecionar(elec)
    print(f"{len(edifs)} edificações: {edifs.groupby(['site_id', 'primaryspaceusage']).size().to_dict()}", flush=True)
    globais = {s: torch.load(BASE / "pesos" / f"seed{s}_global_fedavg.pt", map_location="cpu") for s in SEEDS}
    bases = {s: torch.load(BASE / "pesos" / f"seed{s}_global_base_ft.pt", map_location="cpu") for s in SEEDS}
    modelos = {}
    for s in SEEDS:
        modelos[s] = A.novo("GRU", s, "cpu")
        modelos[s].load_state_dict(globais[s])

    arq = SAIDA / "por_janela.csv"
    linhas = pd.read_csv(arq).to_dict("records") if arq.exists() else []
    feitas = {(r["edificacao"], r["inicio"]) for r in linhas}
    for n, (b, info) in enumerate(edifs.iterrows()):
        uso = USOS[info.primaryspaceusage]
        for ini in INICIOS:
            if (b, str(ini.date())) in feitas:
                continue
            for k in KS:
                tr_h = pd.date_range(ini, periods=24 * k, freq="h")
                te_h = pd.date_range(tr_h[-1] + pd.Timedelta(hours=1), periods=24 * DIAS_TESTE, freq="h")
                treino = idx.isin(tr_h)
                temp, orv = clima_site(clima, info.site_id, idx, treino)
                y = elec[b].to_numpy(float)
                if np.isnan(y[treino]).mean() > 0.2 or np.isnan(y[idx.isin(te_h)]).mean() > 0.2:
                    continue
                df = features_edificacao(b, y, outros, temp, orv, tempo, idx, treino)
                df = df.dropna(subset=FEATURES + ["y", "rw_kwh"])
                df["ts"] = df.index
                f_tr = A.Fonte(df[df.ts.isin(tr_h)].reset_index(drop=True), A.JANELA, "cpu")
                f_te = A.Fonte(df[(df.ts >= te_h[0] - pd.Timedelta(hours=A.JANELA)) & (df.ts <= te_h[-1])]
                               .reset_index(drop=True), A.JANELA, "cpu")
                alvo = f_te.df.ts.isin(te_h).to_numpy()
                real = f_te.df.y_kwh.to_numpy()[alvo]
                if f_tr.n < 24 or alvo.sum() < 24 * (DIAS_TESTE - 1):
                    continue
                base = {"edificacao": b, "site": info.site_id, "uso": uso, "inicio": str(ini.date()), "K": k}
                linhas.append(base | {"metodo": "Persistência (t-1)", "seed": 0,
                                      "mape": mape(real, f_te.df.rw_kwh.to_numpy()[alvo])})
                for s in SEEDS:
                    linhas.append(base | {"metodo": "GRU zero-shot", "seed": s,
                                          "mape": mape(real, A.kwh(modelos[s], f_te)[alvo])})
                    m = A.novo("GRU", s, "cpu")
                    m.load_state_dict(bases[s])
                    A.liberar(m, ft["camadas"])
                    O.treinar(m, f_tr, ft["epocas"], torch.Generator().manual_seed(s + 1000), ft["lr"])
                    linhas.append(base | {"metodo": "GRU FT uniforme", "seed": s,
                                          "mape": mape(real, A.kwh(m, f_te)[alvo])})
        pd.DataFrame(linhas).to_csv(arq, index=False)
        print(f"[{n + 1}/{len(edifs)}] {b}", flush=True)

    d = pd.DataFrame(linhas)
    # média por edificação (janelas e seeds), depois média e mediana entre edificações
    por_edif = d.groupby(["uso", "metodo", "K", "edificacao"]).mape.mean()
    resumo = por_edif.groupby(["uso", "metodo", "K"]).agg(["mean", "median", "count"]).round(2)
    resumo.to_csv(SAIDA / "resumo.csv")
    print("\nMAPE (%) no teste de 5 dias; média e mediana entre edificações (cada uma: média de janelas e seeds)")
    for (uso, met), v in REF.items():
        print(f"  {uso:12s} {'artigo: ' + met:28s} " + "  ".join(f"K={k}: {x:5.2f}" for k, x in zip(KS, v)))
    for (uso, met), g in resumo.groupby(level=[0, 1]):
        print(f"  {uso:12s} {met:28s} " + "  ".join(
            f"K={k}: {g.loc[(uso, met, k), 'mean']:5.2f} (med {g.loc[(uso, met, k), 'median']:5.2f})" for k in KS))


if __name__ == "__main__":
    main()
