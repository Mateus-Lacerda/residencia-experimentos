"""Confere os JSON de public/data contra as fontes do BDG2.

Uso: nice -n 19 uv run --project ../bdg2-fl python scripts/verificar_dados.py

Checa:
1. contagem de edificações por site = dataset/edificacoes.csv (e mesmos ids);
2. ordem dos ids igual em edificacoes.json e energia_diaria.json;
3. série horária: mesmo número de lacunas (null) que NaN no CSV, e valores iguais;
4. diário: dia null <=> 0 horas observadas; soma diária = soma das horas lidas;
5. nenhum zero foi introduzido: zeros no JSON = zeros no CSV.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
BDG2 = RAIZ.parent / "bdg2-fl"
DADOS = RAIZ / "public" / "data"


def main() -> int:
    edif = pd.read_csv(BDG2 / "dataset" / "edificacoes.csv")
    indice = json.loads((DADOS / "sites.json").read_text())
    falhas: list[str] = []

    esperado = edif.groupby("site")["edificacao"].apply(list).to_dict()
    if indice["totalEdificacoes"] != len(edif):
        falhas.append(f"sites.json: total {indice['totalEdificacoes']} != {len(edif)}")
    if sorted(s["id"] for s in indice["sites"]) != sorted(esperado):
        falhas.append("sites.json: conjunto de sites diferente")

    elet = pd.read_csv(BDG2 / "data" / "raw" / "electricity_cleaned.csv", usecols=["timestamp", *edif["edificacao"]])
    elet["timestamp"] = pd.to_datetime(elet["timestamp"])
    elet = elet.set_index("timestamp").reindex(pd.date_range("2016-01-01", "2017-12-31 23:00", freq="h"))

    print(f"{'site':8} {'edif':>5} {'json':>5} {'lacunas h':>10} {'dias null':>9}  ok")
    for s in indice["sites"]:
        site = s["id"]
        ids = esperado[site]
        meta = json.loads((DADOS / "sites" / site / "edificacoes.json").read_text())
        en = json.loads((DADOS / "sites" / site / "energia_diaria.json").read_text())
        ids_meta = [r["id"] for r in meta["edificacoes"]]
        ok = True
        if s["edificacoes"] != len(ids) or len(ids_meta) != len(ids) or set(ids_meta) != set(ids):
            falhas.append(f"{site}: contagem/ids de edificações divergem")
            ok = False
        if en["edificacoes"] != ids_meta:
            falhas.append(f"{site}: ordem de ids difere entre metadados e energia")
            ok = False
        lacunas = 0
        dias_null = 0
        for k, bid in enumerate(en["edificacoes"]):
            h = json.loads((DADOS / "sites" / site / "horario" / f"{bid}.json").read_text())
            arr = np.array([np.nan if v is None else v for v in h["kwh"]], dtype=float)
            src = elet[bid].to_numpy()
            if np.isnan(arr).sum() != np.isnan(src).sum():
                falhas.append(f"{bid}: lacunas {np.isnan(arr).sum()} no JSON vs {np.isnan(src).sum()} no CSV")
                ok = False
            if (arr == 0).sum() != (src == 0).sum():
                falhas.append(f"{bid}: zeros {(arr == 0).sum()} no JSON vs {(src == 0).sum()} no CSV")
                ok = False
            m = ~np.isnan(src)
            if not np.allclose(arr[m], src[m], atol=0.006):
                falhas.append(f"{bid}: valores horários divergem do CSV")
                ok = False
            lacunas += int(np.isnan(arr).sum())
            kwh = en["kwh"][k]
            horas = en["horas"][k]
            for d in range(en["dias"]):
                bloco = src[d * 24 : (d + 1) * 24]
                n = int((~np.isnan(bloco)).sum())
                if horas[d] != n:
                    falhas.append(f"{bid} dia {d}: horas {horas[d]} != {n}")
                    ok = False
                    break
                if n == 0:
                    dias_null += 1
                    if kwh[d] is not None:
                        falhas.append(f"{bid} dia {d}: dia sem leitura com valor {kwh[d]}")
                        ok = False
                        break
                elif kwh[d] is None or abs(kwh[d] - np.nansum(bloco)) > 0.01 + 1e-6 * abs(kwh[d]):
                    falhas.append(f"{bid} dia {d}: soma {kwh[d]} != {np.nansum(bloco)}")
                    ok = False
                    break
        print(f"{site:8} {len(ids):5d} {len(ids_meta):5d} {lacunas:10d} {dias_null:9d}  {'sim' if ok else 'NAO'}")

    if falhas:
        print(f"\n{len(falhas)} falha(s):")
        for f in falhas[:30]:
            print("  -", f)
        return 1
    print(f"\nok: {len(edif)} edificações em {len(indice['sites'])} sites; lacunas preservadas como null")
    return 0


if __name__ == "__main__":
    sys.exit(main())
