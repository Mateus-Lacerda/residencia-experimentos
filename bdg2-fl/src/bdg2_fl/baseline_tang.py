"""GRU do FedAvg nos 11 sites aplicada ao protocolo few-shot de Tang et al. (2023, Applied Energy 337:120860).

uv run python -m bdg2_fl.baseline_tang

Protocolo do artigo (seção 4.1-4.2): edificações da Flórida (no BDG2, só o site Panther) de uso
escritório, sala de aula ou pesquisa; sem buraco contínuo de mais de 48 h; período de 2016-07-15 a
2016-09-12, com 720 h (30 dias) de treino, 240 h (10 dias) de validação e 480 h (20 dias) de teste;
1 h à frente; CV = RMSE / média, por edificação, reportado como média das edificações. O artigo não
publica a lista: das que passam no filtro, eles usaram 30 (26 participantes e 4 não participantes).
Aqui entram todas as que passam, e a comparação é com a média deles.

O Panther não está entre os 11 sites, então toda edificação é "não participante" para a GRU.
A normalização (média e desvio da edificação, do clima e dos outros medidores) usa só as 720 h de
treino. As entradas usam o histórico anterior (lags até 168 h), como a janela de 24 h do artigo usa.

Cenários, nas 3 seeds do teste (42, 505, 11):
- zero-shot: o global do FedAvg (rodada 30), sem ajuste;
- FT uniforme: o fine-tuning que o servidor manda para todos (melhor.json da GRU: rodada base,
  lr, épocas, camadas) nas 720 h de treino;
- FT com parada pela validação: como no artigo (Adam lr 1e-3, a época escolhida pela perda na
  validação de 10 dias), todas as camadas, até EPOCAS_MAX épocas, partindo da mesma rodada base.

Referências (CV, fração): participantes, média das 26 (Tabela 4): proposto 0,0694, local 0,1121,
centralizado 0,0994, transferência centralizada 1 e 2: 0,0680 e 0,0685. Não participantes (Tabela 5):
proposto 0,1261 / 0,1774 / 0,0848 / 0,0723 (média 0,1152); local 0,2306 / 0,1927 / 0,1358 / 0,0782
(média 0,1593).

Resultados em out/baseline_tang/: por_edificacao.csv, resumo.csv.
"""
import json

import numpy as np
import pandas as pd
import torch

from . import arquiteturas as A
from . import otimizar_pfl as O
from .config import RAIZ, RAW
from .dados import FEATURES, MEDIDORES_OPCIONAIS, _ler_medidor, clima_site, features_edificacao, tempo_calendario

SAIDA = RAIZ / "out" / "baseline_tang"
BASE = RAIZ / "out" / "otimizacao_ft" / "11_sites" / "GRU"
SEEDS = [42, 505, 11]
INICIO, FIM = pd.Timestamp("2016-07-15 00:00"), pd.Timestamp("2016-09-12 23:00")
H_TREINO, H_VAL, H_TESTE = 720, 240, 480
USOS = {"Office", "Classroom", "Research"}
MAX_BURACO = 48
LR_TANG, EPOCAS_MAX = 1e-3, 100

REF = {"Tang: proposto, participantes (26)": 0.0694, "Tang: local, participantes": 0.1121,
       "Tang: centralizado, participantes": 0.0994,
       "Tang: proposto, não participantes (4)": float(np.mean([0.1261, 0.1774, 0.0848, 0.0723])),
       "Tang: local, não participantes": float(np.mean([0.2306, 0.1927, 0.1358, 0.0782]))}


def _maior_buraco(s):
    falta = s.isna().to_numpy()
    maior = atual = 0
    for f in falta:
        atual = atual + 1 if f else 0
        maior = max(maior, atual)
    return maior


def selecionar(elec):
    meta = pd.read_csv(RAW / "metadata.csv")
    cand = meta[(meta.site_id == "Panther") & meta.sub_primaryspaceusage.str.strip().isin(USOS)]
    ok = []
    for b in cand.building_id:
        if b not in elec.columns:      # sem medidor de eletricidade
            continue
        s = elec.loc[INICIO:FIM, b]
        if s.notna().any() and _maior_buraco(s) <= MAX_BURACO and (s.dropna() >= 0).all():
            ok.append(b)
    return ok, cand.set_index("building_id").sub_primaryspaceusage.str.strip()


def cv(y, p):
    return float(np.sqrt(np.mean((p - y) ** 2)) / np.mean(y))


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    melhor = json.loads((BASE / "melhor.json").read_text())["ft"]
    elec = _ler_medidor("electricity")
    outros = {m: _ler_medidor(m) for m in MEDIDORES_OPCIONAIS}
    clima = pd.read_csv(RAW / "weather.csv", parse_dates=["timestamp"])
    idx = elec.index
    horas = pd.date_range(INICIO, FIM, freq="h")
    partes = {"treino": horas[:H_TREINO], "val": horas[H_TREINO:H_TREINO + H_VAL],
              "teste": horas[H_TREINO + H_VAL:]}
    treino = idx.isin(partes["treino"])
    edifs, usos = selecionar(elec)
    print(f"{len(edifs)} edificações do Panther passam no filtro: {usos[edifs].value_counts().to_dict()}")
    temp, orv = clima_site(clima, "Panther", idx, treino)
    tempo = tempo_calendario(idx)
    globais = {s: torch.load(BASE / "pesos" / f"seed{s}_global_fedavg.pt", map_location="cpu") for s in SEEDS}
    bases = {s: torch.load(BASE / "pesos" / f"seed{s}_global_base_ft.pt", map_location="cpu") for s in SEEDS}

    linhas = []
    for i, b in enumerate(edifs):
        # buracos de até 48 h interpolados linearmente, como no artigo; a métrica usa só horas medidas
        y = elec[b].interpolate(limit=MAX_BURACO, limit_area="inside").to_numpy(float)
        medido = elec[b].notna().to_numpy()
        df = features_edificacao(b, y, outros, temp, orv, tempo, idx, treino)
        df["medido"] = medido
        df = df.dropna(subset=FEATURES + ["y", "rw_kwh"])
        df["ts"] = df.index
        fontes = {p: A.Fonte(df[df.ts.isin(h)].reset_index(drop=True) if p == "treino"
                             else df[(df.ts >= h[0] - pd.Timedelta(hours=A.JANELA)) & (df.ts <= h[-1])]
                             .reset_index(drop=True), A.JANELA, "cpu")
                  for p, h in partes.items()}
        # janelas de val e teste podem olhar para trás; o treino só usa alvos das 720 h
        alvo = {p: fontes[p].df.ts.isin(partes[p]).to_numpy() & fontes[p].df.medido.to_numpy() for p in ("val", "teste")}
        real = {p: fontes[p].df.y_kwh.to_numpy()[alvo[p]] for p in alvo}

        def aval(m, p):
            return cv(real[p], A.kwh(m, fontes[p])[alvo[p]])

        res = {"Persistência (t-1)": {s: cv(real["teste"], fontes["teste"].df.rw_kwh.to_numpy()[alvo["teste"]])
                                      for s in SEEDS}}
        for s in SEEDS:
            m = A.novo("GRU", s, "cpu")
            m.load_state_dict(globais[s])
            res.setdefault("GRU zero-shot", {})[s] = aval(m, "teste")

            m = A.novo("GRU", s, "cpu")
            m.load_state_dict(bases[s])
            A.liberar(m, melhor["camadas"])
            O.treinar(m, fontes["treino"], melhor["epocas"], torch.Generator().manual_seed(s + 1000), melhor["lr"])
            res.setdefault("GRU FT uniforme", {})[s] = aval(m, "teste")

            m = A.novo("GRU", s, "cpu")
            m.load_state_dict(bases[s])
            curva = [(aval(m, "val"), aval(m, "teste"))]
            O.treinar(m, fontes["treino"], EPOCAS_MAX, torch.Generator().manual_seed(s + 1000), LR_TANG,
                      lambda e, perda, mod: curva.append((aval(mod, "val"), aval(mod, "teste"))))
            e = int(np.argmin([v for v, _ in curva]))
            res.setdefault("GRU FT parada pela val.", {})[s] = curva[e][1]
            linhas.append({"edificacao": b, "uso": usos[b], "metodo": "época escolhida", "seed": s, "cv": e})
        for metodo, por_seed in res.items():
            linhas += [{"edificacao": b, "uso": usos[b], "metodo": metodo, "seed": s, "cv": v} for s, v in por_seed.items()]
        print(f"[{i + 1}/{len(edifs)}] {b}: " + "  ".join(f"{k} {np.mean(list(v.values())):.3f}" for k, v in res.items()),
              flush=True)

    pe = pd.DataFrame(linhas)
    pe.to_csv(SAIDA / "por_edificacao.csv", index=False)
    ep = pe[pe.metodo == "época escolhida"]
    pe = pe[pe.metodo != "época escolhida"]
    por_seed = pe.groupby(["metodo", "seed"]).cv.mean()           # média das edificações, por seed
    resumo = por_seed.groupby("metodo").agg(["mean", "std"])
    resumo["mediana_edif"] = pe.groupby(["metodo", "edificacao"]).cv.mean().groupby("metodo").median()
    resumo.to_csv(SAIDA / "resumo.csv")
    print("\nCV no teste de 20 dias (fração; média das edificações)")
    for k, v in REF.items():
        print(f"  {k:42s} {v:.4f}")
    for k, r in resumo.iterrows():
        print(f"  {k:42s} {r['mean']:.4f} ± {r['std']:.4f}   (mediana das edificações {r.mediana_edif:.4f})")
    print(f"\népoca escolhida pela validação: mediana {ep.cv.median():.0f}, de {ep.cv.min():.0f} a {ep.cv.max():.0f}")


if __name__ == "__main__":
    main()
