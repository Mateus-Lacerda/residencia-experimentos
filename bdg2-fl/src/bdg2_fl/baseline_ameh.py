"""GRU já treinada (FedAvg nos 11 sites, 2016) aplicada, sem retreino, ao protocolo de Ameh et al. (2026).

uv run python -m bdg2_fl.baseline_ameh

Protocolo reproduzido do código publicado pelos autores (Zenodo 10.5281/zenodo.20527682,
scripts/02_prepare_data.py e src/fedbuild/data.py):
- edificações: primary use contendo "office" ou "education", na ordem do metadata.csv, as 50
  primeiras com pelo menos 80% de leituras em electricity_cleaned.csv (2016-2017). O filtro de zona
  climática do código não age, porque o metadata do BDG2 não tem coluna de clima; saem 46 do Panther
  e 4 do Robin;
- série preenchida como no código deles: interpolação no tempo (até 6 h), depois ffill e bfill;
- divisão cronológica 70/15/15 sobre 2016-2017, depois de descartar a primeira hora (lag);
  janelas de 2 h, então os alvos começam 2 horas depois do início de cada parte;
- escala: um z-score global do alvo, ajustado no treino das primeiras 100 candidatas que passam no
  filtro de completude (é o que o código faz: candidate_ids[: 2 * n]). As métricas principais deles
  são MSE nessa escala.

O nosso modelo usa as próprias features (janela de 24 h, lags 1/24/168, clima, outros medidores),
normalizadas por edificação com a estatística de 2016, que está dentro da parte de treino deles.
Nenhum peso é ajustado: o Panther não está entre os 11 sites, então nele a previsão é zero-shot; as 4
do Robin são de um site que participou do FedAvg (em 2016; o teste deles é set-dez/2017).

Referências deles (sweep_results.csv do mesmo pacote; MSE na escala global):
isolado e centralizado foram medidos no teste, média das edificações; os federados foram medidos na
validação, na rodada de menor perda de validação.

Resultados em out/baseline_ameh/: por_edificacao.csv, resumo.csv.
"""
import numpy as np
import pandas as pd
import torch

from . import arquiteturas as A
from .config import RAIZ, RAW
from .dados import MEDIDORES_OPCIONAIS, FEATURES, _ler_medidor, clima_site, features_edificacao, tempo_calendario

SAIDA = RAIZ / "out" / "baseline_ameh"
PESOS = RAIZ / "out" / "otimizacao_ft" / "11_sites" / "GRU" / "pesos"
SEEDS = [42, 505, 11]
N_EDIF, MIN_COMPLETUDE, F_TREINO, F_VAL, PASSOS = 50, 0.80, 0.70, 0.15, 2

REFERENCIAS = {   # MSE na escala global, sweep_results.csv de Ameh et al.
    ("Ameh: isolado", "teste"): 0.006664243163977517,
    ("Ameh: centralizado", "teste"): 0.010163163496763446,
    ("Ameh: FedAvg sem DP", "val"): 1.048604814708233,
    ("Ameh: FedAvg DP ε=6,5", "val"): 0.7508342456072569,
    ("Ameh: FedProx DP ε=0,5 (melhor)", "val"): 0.6610462946817279,
}


def _preencher(s):
    return s.interpolate(method="time", limit=6).ffill().bfill()


def selecao_ameh(elec):
    meta = pd.read_csv(RAW / "metadata.csv")
    uso = meta["primaryspaceusage"].fillna("").str.lower().str.contains("office|education", regex=True)
    candidatas = [b for b in meta.loc[uso, "building_id"].astype(str) if b in elec.columns]
    completas = [b for b in candidatas if elec[b].notna().mean() >= MIN_COMPLETUDE]
    # escala global: treino das candidatas completas entre as 2N primeiras candidatas
    ys = []
    for b in candidatas[: 2 * N_EDIF]:
        if elec[b].notna().mean() < MIN_COMPLETUDE:
            continue
        y = _preencher(elec[b]).to_numpy()[1:]          # a 1ª hora sai no dropna do lag
        ys.append(y[: int(len(y) * F_TREINO)])
    ys = np.concatenate(ys)
    return completas[:N_EDIF], float(ys.mean()), float(ys.std())


def alvos(idx):
    """Horas-alvo de validação e teste no protocolo deles."""
    n = len(idx) - 1
    i_tr, i_va = int(n * F_TREINO), int(n * (F_TREINO + F_VAL))
    h = idx[1:]
    return {"val": h[i_tr + PASSOS : i_va], "teste": h[i_va + PASSOS :]}


def metricas(y, p, sd_global):
    e = p - y
    return {"mse_escala_global": float(np.mean((e / sd_global) ** 2)),
            "mse_kwh": float(np.mean(e ** 2)), "rmse_kwh": float(np.sqrt(np.mean(e ** 2))),
            "mae_kwh": float(np.mean(np.abs(e))),
            "cv_rmse": float(100 * np.sqrt(np.mean(e ** 2)) / np.mean(y))}


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    elec = _ler_medidor("electricity")
    outros = {m: _ler_medidor(m) for m in MEDIDORES_OPCIONAIS}
    clima = pd.read_csv(RAW / "weather.csv", parse_dates=["timestamp"])
    idx = elec.index
    treino = idx.year == 2016
    tempo = tempo_calendario(idx)
    edifs, mu_g, sd_g = selecao_ameh(elec)
    partes = alvos(idx)
    print(f"{len(edifs)} edificações: {pd.Series([b.split('_')[0] for b in edifs]).value_counts().to_dict()}; "
          f"escala global: média {mu_g:.1f} kWh, desvio {sd_g:.1f} kWh")
    print({p: (str(h[0]), str(h[-1]), len(h)) for p, h in partes.items()})

    globais = {s: torch.load(PESOS / f"seed{s}_global_fedavg.pt", map_location="cpu") for s in SEEDS}
    climas = {}
    linhas = []
    inicio = partes["val"][0] - pd.Timedelta(hours=A.JANELA + 1)
    for b in edifs:
        site = b.split("_")[0]
        if site not in climas:
            climas[site] = clima_site(clima, site, idx, treino)
        y = _preencher(elec[b]).to_numpy(float)
        df = features_edificacao(b, y, outros, *climas[site], tempo, idx, treino)
        df = df.dropna(subset=FEATURES + ["y", "rw_kwh"])
        df["ts"] = df.index
        fonte = A.Fonte(df[df.ts >= inicio].reset_index(drop=True), A.JANELA, "cpu")
        ts = pd.DatetimeIndex(fonte.df["ts"])
        prev = {"Persistência (t-1)": fonte.df["rw_kwh"].to_numpy()}
        for s in SEEDS:
            m = A.novo("GRU", s, "cpu")
            m.load_state_dict(globais[s])
            prev[f"GRU FedAvg 11 sites, seed {s}"] = A.kwh(m, fonte)
        real = fonte.df["y_kwh"].to_numpy()
        for parte, horas in partes.items():
            sel = ts.isin(horas)
            assert sel.sum() == len(horas), (b, parte, sel.sum(), len(horas))
            for metodo, p in prev.items():
                linhas.append({"edificacao": b, "site": site, "parte": parte, "metodo": metodo}
                              | metricas(real[sel], p[sel], sd_g))
    pe = pd.DataFrame(linhas)
    pe.to_csv(SAIDA / "por_edificacao.csv", index=False)

    # média das edificações (todas têm o mesmo número de horas, então coincide com a média ponderada)
    pe["metodo_base"] = pe.metodo.str.replace(r", seed \d+", "", regex=True)
    por_seed = pe.groupby(["parte", "metodo_base", "metodo"]).mean(numeric_only=True)
    resumo = por_seed.groupby(["parte", "metodo_base"]).agg(["mean", "std"])
    resumo.columns = [f"{a}_{b}" for a, b in resumo.columns]
    resumo = resumo.reset_index()
    resumo.to_csv(SAIDA / "resumo.csv", index=False)

    pd.set_option("display.width", 200)
    print("\nMSE na escala global (média das 50 edificações; GRU: média ± desvio de 3 seeds)")
    for (metodo, parte), v in REFERENCIAS.items():
        print(f"  {parte:5s}  {metodo:34s} {v:8.4f}")
    for _, r in resumo.iterrows():
        dp = r["mse_escala_global_std"]
        print(f"  {r.parte:5s}  {r.metodo_base:34s} {r.mse_escala_global_mean:8.4f}"
              + (f" ± {dp:.4f}" if dp == dp else "")
              + f"   CV(RMSE) {r.cv_rmse_mean:5.2f}%  RMSE {r.rmse_kwh_mean:6.2f} kWh  MAE {r.mae_kwh_mean:6.2f} kWh")


if __name__ == "__main__":
    main()
