"""Seleção de sites/edificações, engenharia de features e normalização.

Saída: para cada site (cliente) um dicionário com os dados de treino (2016) e validação (2017),
já normalizados, mais a média e o desvio de cada edificação para desnormalizar."""
import numpy as np
import pandas as pd

from .config import (LAGS, MAX_EDIF_POR_SITE, MEDIDORES_OPCIONAIS, MIN_MEDIANA_KWH, MIN_PREENCHIMENTO, N_SITES, RAW)

FEATURES = (
    [f"elec_lag{l}" for l in LAGS]
    + ["hora_sin", "hora_cos", "dow_sin", "dow_cos", "temp_ar", "ponto_orvalho"]
    + [f"{m}_lag1" for m in MEDIDORES_OPCIONAIS]
    + [f"tem_{m}" for m in MEDIDORES_OPCIONAIS]
)

CONTINUAS = [f"elec_lag{l}" for l in LAGS] + [f"{m}_lag1" for m in MEDIDORES_OPCIONAIS]
CLIP_Z = 10.0


def _ler_medidor(nome):
    return pd.read_csv(RAW / f"{nome}_cleaned.csv", index_col=0, parse_dates=True)


def selecionar(elec):
    """Sites com mais edificações de eletricidade bem preenchida; até MAX_EDIF por site."""
    ok16 = elec.loc["2016"].notna().mean() >= MIN_PREENCHIMENTO
    ok17 = elec.loc["2017"].notna().mean() >= MIN_PREENCHIMENTO
    # descarta medidores praticamente zerados ou que mudam de patamar entre os anos
    # (ex.: medidor que "morre" em 2017), pois o z-score de 2016 não valeria para 2017
    med16, med17 = elec.loc["2016"].median(), elec.loc["2017"].median()
    razao = med17 / med16
    estavel = (med16 >= MIN_MEDIANA_KWH) & (med17 >= MIN_MEDIANA_KWH) & razao.between(0.5, 2.0)
    boas = elec.columns[ok16 & ok17 & estavel]
    site = pd.Series(boas.str.split("_").str[0], index=boas)
    sites = site.value_counts().head(N_SITES).index.tolist()
    escolha = {}
    preench = elec[boas].notna().mean()
    for s in sites:
        cand = site[site == s].index
        # as mais completas primeiro; desempate por nome, para ser determinístico
        ordem = sorted(cand, key=lambda b: (-preench[b], b))
        escolha[s] = ordem[:MAX_EDIF_POR_SITE]
    return escolha


def _zs(x, mu, sd):
    return (x - mu) / (sd if sd > 1e-9 else 1.0)


def construir():
    elec = _ler_medidor("electricity")
    outros = {m: _ler_medidor(m) for m in MEDIDORES_OPCIONAIS}
    clima = pd.read_csv(RAW / "weather.csv", parse_dates=["timestamp"])
    escolha = selecionar(elec)
    idx = elec.index
    treino = idx.year == 2016

    hora, dow = idx.hour.values, idx.dayofweek.values
    tempo = {
        "hora_sin": np.sin(2 * np.pi * hora / 24), "hora_cos": np.cos(2 * np.pi * hora / 24),
        "dow_sin": np.sin(2 * np.pi * dow / 7), "dow_cos": np.cos(2 * np.pi * dow / 7),
    }

    clientes = {}
    for s, edifs in escolha.items():
        w = (clima[clima.site_id == s].set_index("timestamp")
             .reindex(idx)[["airTemperature", "dewTemperature"]]
             .interpolate(limit_direction="both"))
        # clima normalizado com estatística do próprio site (cada cliente só vê seus dados)
        temp = _zs(w.airTemperature.values, w.airTemperature[treino].mean(), w.airTemperature[treino].std())
        orv = _zs(w.dewTemperature.values, w.dewTemperature[treino].mean(), w.dewTemperature[treino].std())

        blocos = []
        for b in edifs:
            y = elec[b].values.astype(float)
            mu, sd = np.nanmean(y[treino]), np.nanstd(y[treino])
            yz = _zs(y, mu, sd)
            f = {f"elec_lag{l}": pd.Series(yz).shift(l).values for l in LAGS}
            f.update(tempo)
            f["temp_ar"], f["ponto_orvalho"] = temp, orv
            for m in MEDIDORES_OPCIONAIS:
                col = outros[m][b] if b in outros[m].columns else None
                tem = False
                if col is not None:
                    v = col.values.astype(float)
                    mu_m, sd_m = np.nanmean(v[treino]), np.nanstd(v[treino])
                    # presente = cobertura razoável em 2016 e sinal que varia de fato
                    tem = col.loc["2016"].notna().mean() > 0.5 and sd_m > 0.05 * max(abs(mu_m), 1.0)
                if tem:
                    lag = pd.Series(_zs(v, mu_m, sd_m)).shift(1).values
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
            blocos.append(df)
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
