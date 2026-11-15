"""Teste do caminho de importação de previsões, sem gravar nada em public/data.

Uso: nice -n 19 uv run --project ../bdg2-fl python scripts/testar_previsoes.py

Cria um CSV temporário de teste (previsto = 1,1 x real em janeiro de 2016 para duas
edificações de Lamb, mais linhas inválidas), passa por ler_previsoes/diario do exportador e
confere: linhas inválidas descartadas, alinhamento horário, pareamento só nas horas com
leitura real e erro relativo de +10%. O diretório temporário é apagado no fim.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exportar_dados as ex  # noqa: E402

TMP = ex.RAIZ / ".tmp_teste_previsoes"


def main() -> int:
    edif = pd.read_csv(ex.ARQ_EDIF)
    ids = edif.loc[edif["site"] == "Lamb", "edificacao"].tolist()
    alvo = ids[:2]
    elet = pd.read_csv(ex.ARQ_ELET, usecols=["timestamp", *ids], index_col="timestamp")
    elet.index = pd.to_datetime(elet.index)
    elet = elet.reindex(ex.HORAS)
    jan = elet.loc["2016-01-01":"2016-01-31 23:00", alvo]

    linhas = []
    for b in alvo:
        for ts, v in jan[b].items():
            # previsão existe mesmo onde não há leitura real (valor arbitrário 5.0)
            linhas.append((b, ts.strftime("%Y-%m-%d %H:%M:%S"), 1.1 * v if not np.isnan(v) else 5.0))
    linhas += [("Edificacao_inexistente", "2016-01-01 00:00:00", 1.0), (alvo[0], "data ruim", 1.0), (alvo[0], "2016-01-01 00:00:00", "")]
    TMP.mkdir(exist_ok=True)
    try:
        pd.DataFrame(linhas, columns=["edificacao", "timestamp", "previsto_kwh"]).to_csv(TMP / "Lamb.csv", index=False)
        ex.DIR_PREV = TMP
        prev = ex.ler_previsoes("Lamb", ids)
        falhas = []
        if prev is None:
            print("falha: previsões não lidas")
            return 1
        if prev.shape != (len(ex.HORAS), len(ids)):
            falhas.append(f"formato {prev.shape}")
        if prev[ids[2:]].notna().any().any():
            falhas.append("edificações sem previsão receberam valores")
        e = elet[ids]
        par_prev, _ = ex.diario(prev.where(e.notna()))
        par_real, par_h = ex.diario(e.where(prev.notna()))
        for b in alvo:
            n_real = int(jan[b].notna().sum())
            if int(par_h[b].sum()) != n_real:
                falhas.append(f"{b}: horas pareadas {int(par_h[b].sum())} != {n_real}")
            erro = (par_prev[b].sum() - par_real[b].sum()) / par_real[b].sum() * 100
            if abs(erro - 10) > 1e-6:
                falhas.append(f"{b}: erro {erro:.4f}% != 10%")
            print(f"{b}: {n_real} horas pareadas, erro relativo {erro:+.2f}%")
        if falhas:
            print("falhas:", *falhas, sep="\n  - ")
            return 1
        print("ok: formato edificacao,timestamp,previsto_kwh importado e pareado corretamente")
        return 0
    finally:
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
