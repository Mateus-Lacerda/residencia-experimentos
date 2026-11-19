"""Seleção de sites/edificações, engenharia de features e normalização.

Saída: para cada site (cliente) um dicionário com os dados de treino (2016) e validação (2017),
já normalizados, mais a média e o desvio de cada edificação para desnormalizar.

uv run python -m bdg2_fl.dados   # grava dataset/edificacoes.csv, a lista das edificações usadas"""
import numpy as np
import pandas as pd

from .config import (
    LAGS,
    MAX_EDIF_POR_SITE,
    MEDIDORES_OPCIONAIS,
    MIN_EDIF_POR_SITE,
    MIN_MEDIANA_KWH,
    MIN_PREENCHIMENTO,
    N_SITES,
    RAW,
)

FEATURES = (
    [f"elec_lag{l}" for l in LAGS]
    + ["hora_sin", "hora_cos", "dow_sin", "dow_cos", "temp_ar_lag1", "ponto_orvalho_lag1"]
    + [f"{m}_lag1" for m in MEDIDORES_OPCIONAIS]
    + [f"tem_{m}" for m in MEDIDORES_OPCIONAIS]
)

CONTINUAS = [f"elec_lag{l}" for l in LAGS] + [f"{m}_lag1" for m in MEDIDORES_OPCIONAIS]
CLIP_Z = 10.0


def _ler_medidor(nome):
    return pd.read_csv(RAW / f"{nome}_cleaned.csv", index_col=0, parse_dates=True)


def selecionar(electricity):
    """Sites com pelo menos MIN_EDIF edificações de eletricidade bem preenchida, em ordem
    decrescente de edificações aprovadas (os N_SITES primeiros, se definido); até MAX_EDIF por site."""
    # Regra 1: o medidor precisa ter leitura em pelo menos 90% das horas, em 2016 e em 2017.
    ok16 = electricity.loc["2016"].notna().mean() >= MIN_PREENCHIMENTO
    ok17 = electricity.loc["2017"].notna().mean() >= MIN_PREENCHIMENTO

    # Regra 2: a mediana horária precisa ser de pelo menos 1 kWh em cada ano (tira medidores
    # praticamente zerados).
    med16, med17 = electricity.loc["2016"].median(), electricity.loc["2017"].median()

    # Regra 3: a mediana de 2017 precisa ficar entre metade e o dobro da de 2016. Tira medidores que
    # mudam de patamar entre os anos (ex.: um medidor que "morre" em 2017), porque a normalização
    # usa as estatísticas de 2016 e não valeria para 2017.
    razao = med17 / med16
    estavel = (med16 >= MIN_MEDIANA_KWH) & (med17 >= MIN_MEDIANA_KWH) & razao.between(0.5, 2.0)

    boas = electricity.columns[ok16 & ok17 & estavel]

    # O site é o prefixo do id da edificação (ex.: "Rat" em "Rat_office_Colby").
    site = pd.Series(boas.str.split("_").str[0], index=boas)

    # Regra 4: o site entra se tiver pelo menos MIN_EDIF_POR_SITE edificações aprovadas. Os sites
    # ficam em ordem decrescente de aprovadas; se N_SITES estiver definido, entram só os primeiros.
    contagem = site.value_counts()
    sites = contagem[contagem >= MIN_EDIF_POR_SITE].index.tolist()[:N_SITES]

    # Regra 5: dentro de cada site, entram as edificações aprovadas, das mais completas para as
    # menos completas, até MAX_EDIF_POR_SITE (sem limite se for None). O desempate é pelo nome,
    # para a escolha ser sempre a mesma.
    escolha = {}
    preench = electricity[boas].notna().mean()
    for s in sites:
        cand = site[site == s].index
        ordem = sorted(cand, key=lambda b: (-preench[b], b))
        escolha[s] = ordem[:MAX_EDIF_POR_SITE]
    return escolha


def manifesto(electricity):
    """Uma linha por edificação do dataset, com os números que os critérios de seleção olham."""
    meta = pd.read_csv(RAW / "metadata.csv").set_index("building_id")
    linhas = []
    for s, edifs in selecionar(electricity).items():
        for b in edifs:
            e16, e17 = electricity.loc["2016", b], electricity.loc["2017", b]
            linhas.append({"site": s, "edificacao": b, "uso_principal": meta.at[b, "primaryspaceusage"],
                           "area_m2": meta.at[b, "sqm"],
                           "preenchimento_2016": round(e16.notna().mean(), 4),
                           "preenchimento_2017": round(e17.notna().mean(), 4),
                           "mediana_kwh_2016": round(e16.median(), 3), "mediana_kwh_2017": round(e17.median(), 3)})
    return pd.DataFrame(linhas)


def _z_score(x, mu, sd):
    return (x - mu) / (sd if sd > 1e-9 else 1.0)


def tempo_calendario(idx):
    hora, dow = idx.hour.values, idx.dayofweek.values
    return {
        "hora_sin": np.sin(2 * np.pi * hora / 24), "hora_cos": np.cos(2 * np.pi * hora / 24),
        "dow_sin": np.sin(2 * np.pi * dow / 7), "dow_cos": np.cos(2 * np.pi * dow / 7),
    }


def clima_site(clima, s, idx, treino):
    """Temperatura e ponto de orvalho do site em t-1, normalizados com a estatística do próprio site
    no período de treino (cada cliente só vê seus dados)."""
    w = (clima[clima.site_id == s].set_index("timestamp")
         .reindex(idx)[["airTemperature", "dewTemperature"]]
         .interpolate(limit_direction="both")
         .shift(1))   # clima de t-1: na hora de prever t, o clima de t ainda não foi medido
    temp = _z_score(w.airTemperature.values, w.airTemperature[treino].mean(), w.airTemperature[treino].std())
    orv = _z_score(w.dewTemperature.values, w.dewTemperature[treino].mean(), w.dewTemperature[treino].std())
    return temp, orv


def features_edificacao(b, y, outros, temp, orv, tempo, idx, treino):
    """Features, alvo normalizado e referências de uma edificação, em todas as horas de idx.
    y: série de eletricidade (kWh) da edificação; treino: máscara das horas usadas na normalização."""
    mu, sd = np.nanmean(y[treino]), np.nanstd(y[treino])
    yz = _z_score(y, mu, sd)
    f = {f"elec_lag{l}": pd.Series(yz).shift(l).values for l in LAGS}
    f.update(tempo)
    f["temp_ar_lag1"], f["ponto_orvalho_lag1"] = temp, orv
    for m in MEDIDORES_OPCIONAIS:
        col = outros[m][b] if b in outros[m].columns else None
        tem = False
        if col is not None:
            v = col.values.astype(float)
            mu_m, sd_m = np.nanmean(v[treino]), np.nanstd(v[treino])
            # presente = cobertura razoável em 2016 e sinal que varia de fato
            tem = col.loc["2016"].notna().mean() > 0.5 and sd_m > 0.05 * max(abs(mu_m), 1.0)
        if tem:
            lag = pd.Series(_z_score(v, mu_m, sd_m)).shift(1).values
            f[f"{m}_lag1"] = np.nan_to_num(lag, nan=0.0)  # buracos pontuais -> média
        else:
            f[f"{m}_lag1"] = np.zeros(len(idx))
        f[f"tem_{m}"] = np.full(len(idx), 1.0 if tem else 0.0)
    df = pd.DataFrame(f, index=idx)[FEATURES]
    # salvaguarda contra mudança de escala entre 2016 e 2017 (z-score de 2016 extrapolado)
    df[CONTINUAS] = df[CONTINUAS].clip(-CLIP_Z, CLIP_Z)
    df["y"] = yz
    df["y_kwh"] = y
    # previsão do random walk: a próxima hora repete a hora atual
    df["rw_kwh"] = pd.Series(y, index=idx).shift(1).values
    df["edif"] = b
    df["mu"], df["sd"] = mu, (sd if sd > 1e-9 else 1.0)
    return df


def construir():
    electricity = _ler_medidor("electricity")
    outros = {m: _ler_medidor(m) for m in MEDIDORES_OPCIONAIS}
    clima = pd.read_csv(RAW / "weather.csv", parse_dates=["timestamp"])
    escolha = selecionar(electricity)
    idx = electricity.index
    treino = idx.year == 2016

    # Só o calendário entra na hora prevista (t), porque é conhecido de antemão. Tudo o que vem de
    # medição (eletricidade, outros medidores e clima) entra defasado, no máximo até t-1.
    tempo = tempo_calendario(idx)

    clientes = {}
    for s, edifs in escolha.items():
        temp, orv = clima_site(clima, s, idx, treino)
        blocos = [features_edificacao(b, electricity[b].values.astype(float), outros, temp, orv, tempo, idx, treino)
                  for b in edifs]
        d = pd.concat(blocos)
        d = d.dropna(subset=FEATURES + ["y", "rw_kwh"])
        d["ts"] = d.index
        clientes[s] = {
            "edificacoes": edifs,
            "treino": d[d.index.year == 2016].reset_index(drop=True),
            "val": d[d.index.year == 2017].reset_index(drop=True),
        }
    return clientes


def tensores(df):
    import torch
    X = torch.tensor(df[FEATURES].values, dtype=torch.float32)
    y = torch.tensor(df["y"].values, dtype=torch.float32).unsqueeze(1)
    return X, y


if __name__ == "__main__":
    from .config import RAIZ
    destino = RAIZ / "dataset" / "edificacoes.csv"
    destino.parent.mkdir(exist_ok=True)
    m = manifesto(_ler_medidor("electricity"))
    m.to_csv(destino, index=False)
    print(m.groupby("site", sort=False).size().to_string(), f"\ntotal {len(m)} -> {destino}")
