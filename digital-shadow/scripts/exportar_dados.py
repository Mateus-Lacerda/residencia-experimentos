"""Exporta os dados do BDG2 para JSON estático consumido pelo Digital Shadow.

Uso (a partir de digital-shadow/):
    nice -n 19 uv run --project ../bdg2-fl python scripts/exportar_dados.py

Entradas (somente leitura):
    ../bdg2-fl/dataset/edificacoes.csv        lista das 955 edificações aprovadas
    ../bdg2-fl/data/raw/metadata.csv          metadados (chave building_id)
    ../bdg2-fl/data/raw/electricity_cleaned.csv  consumo horário em kWh
    ../bdg2-fl/data/raw/weather.csv           clima por site (opcional)
    previsoes/<Site>.csv                      previsões do modelo (opcional)

Saída: public/data/
    sites.json                                índice dos sites
    sites/<Site>/edificacoes.json             metadados (geometria é gerada no navegador)
    sites/<Site>/energia_diaria.json          energia diária por edificação + clima diário
    sites/<Site>/horario/<edificacao>.json    série horária, carregada ao selecionar

Regra central: lacuna é ausência de leitura, nunca zero. Um dia sem nenhuma hora
observada vira null; cada soma diária vem acompanhada do número de horas observadas,
para que o navegador calcule cobertura e decida o que mostrar.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
BDG2 = RAIZ.parent / "bdg2-fl"
ARQ_EDIF = BDG2 / "dataset" / "edificacoes.csv"
ARQ_META = BDG2 / "data" / "raw" / "metadata.csv"
ARQ_ELET = BDG2 / "data" / "raw" / "electricity_cleaned.csv"
ARQ_CLIMA = BDG2 / "data" / "raw" / "weather.csv"
DIR_PREV = RAIZ / "previsoes"
SAIDA = RAIZ / "public" / "data"

INICIO = pd.Timestamp("2016-01-01 00:00:00")
FIM = pd.Timestamp("2017-12-31 23:00:00")
HORAS = pd.date_range(INICIO, FIM, freq="h")
DIAS = pd.date_range(INICIO.normalize(), FIM.normalize(), freq="D")

MEDIDORES = ["chilledwater", "steam", "hotwater", "gas", "water", "irrigation", "solar"]


def limpo(v):
    """Converte valor do pandas para JSON: NaN/None -> None, numpy -> Python."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        return s if s and s.lower() not in ("nan", "none") else None
    return v


def arred(arr: np.ndarray, casas: int = 2) -> list:
    """Lista JSON com None nas posições NaN.

    Arredonda para `casas` decimais, mas um valor não nulo nunca vira 0: leituras muito
    pequenas (ex.: 0,0025 kWh em Lamb) mantêm 3 algarismos significativos.
    """
    out = []
    for x in arr:
        if np.isnan(x):
            out.append(None)
        else:
            x = float(x)
            r = round(x, casas)
            if r == 0 and x != 0:
                r = float(f"{x:.3g}")
            out.append(int(r) if r == int(r) else r)
    return out


def escrever(caminho: Path, obj) -> int:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    caminho.write_text(txt, encoding="utf-8")
    return len(txt.encode("utf-8"))


def categoria_site(usos: pd.Series) -> str:
    """Categoria da instalação inferida dos usos (proveniência: estimated)."""
    cont = usos.value_counts(normalize=True)
    dom = cont.index[0]
    if dom == "Education":
        return "Campus educacional"
    if dom == "Office":
        return "Complexo corporativo e administrativo"
    if dom == "Public services":
        return "Complexo de serviços públicos"
    if dom == "Entertainment/public assembly":
        return "Complexo de uso público e eventos"
    if dom == "Lodging/residential":
        return "Complexo residencial"
    if dom == "Healthcare":
        return "Complexo hospitalar"
    return "Complexo de uso misto"


def ler_previsoes(site: str, ids: list[str]) -> pd.DataFrame | None:
    """Lê previsoes/<site>.csv (edificacao,timestamp,previsto_kwh) se existir."""
    arq = DIR_PREV / f"{site}.csv"
    if not arq.exists():
        return None
    df = pd.read_csv(arq)
    faltando = {"edificacao", "timestamp", "previsto_kwh"} - set(df.columns)
    if faltando:
        print(f"  [aviso] {arq.name}: colunas ausentes {sorted(faltando)}; arquivo ignorado")
        return None
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["previsto_kwh"] = pd.to_numeric(df["previsto_kwh"], errors="coerce")
    n0 = len(df)
    df = df.dropna(subset=["timestamp", "previsto_kwh"])
    desconhecidas = sorted(set(df["edificacao"]) - set(ids))
    if desconhecidas:
        print(f"  [aviso] {arq.name}: {len(desconhecidas)} edificações fora do site ignoradas")
    df = df[df["edificacao"].isin(ids)]
    df = df[(df["timestamp"] >= INICIO) & (df["timestamp"] <= FIM)]
    df = df.drop_duplicates(["edificacao", "timestamp"], keep="last")
    print(f"  previsões: {len(df)} linhas válidas de {n0}")
    if df.empty:
        return None
    larga = df.pivot(index="timestamp", columns="edificacao", values="previsto_kwh")
    return larga.reindex(index=HORAS, columns=ids)


def diario(larga: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Soma diária (só horas observadas) e número de horas observadas por dia."""
    dia = larga.index.normalize()
    soma = larga.groupby(dia).sum(min_count=1)
    horas = larga.notna().groupby(dia).sum()
    return soma.reindex(DIAS), horas.reindex(DIAS).fillna(0).astype(int)


def main() -> int:
    edif = pd.read_csv(ARQ_EDIF)
    meta = pd.read_csv(ARQ_META).set_index("building_id")
    ids_todos = edif["edificacao"].tolist()
    faltam_meta = [i for i in ids_todos if i not in meta.index]
    if faltam_meta:
        print(f"[erro] {len(faltam_meta)} edificações sem metadados: {faltam_meta[:5]}")
        return 1

    print(f"lendo {ARQ_ELET.name} ({len(ids_todos)} colunas)...")
    elet = pd.read_csv(ARQ_ELET, usecols=["timestamp", *ids_todos], index_col="timestamp")
    elet.index = pd.to_datetime(elet.index)
    elet = elet.reindex(HORAS)

    clima = None
    if ARQ_CLIMA.exists():
        clima = pd.read_csv(ARQ_CLIMA, usecols=["timestamp", "site_id", "airTemperature"])
        clima["timestamp"] = pd.to_datetime(clima["timestamp"])

    indice = []
    total_bytes = 0
    for site, grupo in edif.groupby("site", sort=True):
        ids = grupo["edificacao"].tolist()
        print(f"{site}: {len(ids)} edificações")
        m = meta.loc[ids]
        g = grupo.set_index("edificacao")

        registros = []
        for bid in ids:
            r = m.loc[bid]
            registros.append(
                {
                    "id": bid,
                    "uso": limpo(r["primaryspaceusage"]),
                    "subUso": limpo(r["sub_primaryspaceusage"]),
                    "area": limpo(r["sqm"]),
                    "andares": limpo(r["numberoffloors"]),
                    "anoConstrucao": limpo(r["yearbuilt"]),
                    "ocupantes": limpo(r["occupants"]),
                    "setor": limpo(r["industry"]),
                    "subsetor": limpo(r["subindustry"]),
                    "aquecimento": limpo(r["heatingtype"]),
                    "rating": limpo(r["rating"]),
                    "energyStar": limpo(r["energystarscore"]),
                    "euiCadastro": limpo(r["eui"]),
                    "siteEui": limpo(r["site_eui"]),
                    "sourceEui": limpo(r["source_eui"]),
                    "leed": limpo(r["leed_level"]) if limpo(r["leed_level"]) != "None" else None,
                    "medidores": {k: limpo(r[k]) == "Yes" for k in MEDIDORES},
                    "preenchimento": {
                        "2016": limpo(g.loc[bid, "preenchimento_2016"]),
                        "2017": limpo(g.loc[bid, "preenchimento_2017"]),
                    },
                    "medianaKwh": {
                        "2016": limpo(g.loc[bid, "mediana_kwh_2016"]),
                        "2017": limpo(g.loc[bid, "mediana_kwh_2017"]),
                    },
                }
            )
        r0 = m.iloc[0]
        lat, lng = limpo(r0["lat"]), limpo(r0["lng"])
        info_site = {
            "id": site,
            "edificacoes": len(ids),
            "categoria": categoria_site(m["primaryspaceusage"]),
            "usoDominante": m["primaryspaceusage"].value_counts().index[0],
            "areaTotal": round(float(m["sqm"].sum()), 1),
            "timezone": limpo(r0["timezone"]),
            "lat": lat,
            "lng": lng,
        }

        e = elet[ids]
        soma, horas = diario(e)

        prev = ler_previsoes(site, ids)
        bloco_prev = None
        if prev is not None:
            p_soma, p_horas = diario(prev)
            pareado = prev.where(e.notna())
            real_pareado = e.where(prev.notna())
            pp_soma, pp_horas = diario(pareado)
            rp_soma, _ = diario(real_pareado)
            bloco_prev = {
                "kwh": [arred(p_soma[b].to_numpy()) for b in ids],
                "horas": [p_horas[b].tolist() for b in ids],
                "pareadoPrevisto": [arred(pp_soma[b].to_numpy()) for b in ids],
                "pareadoReal": [arred(rp_soma[b].to_numpy()) for b in ids],
                "pareadoHoras": [pp_horas[b].tolist() for b in ids],
            }

        bloco_clima = None
        if clima is not None:
            c = clima[clima["site_id"] == site].set_index("timestamp")["airTemperature"]
            c = c[~c.index.duplicated()].reindex(HORAS)
            if c.notna().any():
                cd = c.groupby(c.index.normalize()).mean().reindex(DIAS)
                bloco_clima = {"temperaturaMedia": arred(cd.to_numpy(), 1), "origem": "observed"}

        energia = {
            "site": site,
            "inicio": str(DIAS[0].date()),
            "dias": len(DIAS),
            "unidade": "kWh",
            "edificacoes": ids,
            "kwh": [arred(soma[b].to_numpy()) for b in ids],
            "horas": [horas[b].tolist() for b in ids],
            "previsao": bloco_prev,
            "clima": bloco_clima,
        }

        base = SAIDA / "sites" / site
        total_bytes += escrever(base / "edificacoes.json", {"site": info_site, "edificacoes": registros})
        total_bytes += escrever(base / "energia_diaria.json", energia)
        for bid in ids:
            total_bytes += escrever(
                base / "horario" / f"{bid}.json",
                {
                    "id": bid,
                    "inicio": "2016-01-01T00:00:00",
                    "horas": len(HORAS),
                    "kwh": arred(e[bid].to_numpy()),
                    "previsto": arred(prev[bid].to_numpy()) if prev is not None else None,
                },
            )
        info_site["previsoes"] = prev is not None
        indice.append(info_site)

    total_bytes += escrever(
        SAIDA / "sites.json",
        {
            "fonte": "Building Data Genome Project 2 (BDG2), eletricidade limpa",
            "periodo": {"inicio": str(DIAS[0].date()), "fim": str(DIAS[-1].date())},
            "totalEdificacoes": len(ids_todos),
            "sites": indice,
        },
    )
    print(f"ok: {len(indice)} sites, {len(ids_todos)} edificações, {total_bytes / 1e6:.1f} MB em {SAIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
