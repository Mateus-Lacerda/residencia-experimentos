"""Teste preliminar de horizonte: a GRU de 1 h à frente usada de forma recursiva até 96 h.

uv run python -m bdg2_fl.horizonte [--seed 42] [--por-site 10]

Modelo: GRU com FedAvg + fine-tuning uniforme, já treinada (out/otimizacao_ft/11_sites/GRU/pesos/
seed<seed>_ft.pt, um modelo por site). Nada é retreinado.

Previsão recursiva: a partir de uma origem t0, prevê t0, usa a previsão como lag de 1 h da hora
seguinte, e assim até t0+95. Os lags de 24 h e 168 h usam o valor medido quando caem antes de t0 e a
previsão quando caem depois. Hipóteses:
- clima: o observado (equivale a uma previsão do tempo perfeita);
- outros medidores: congelados no último valor medido antes de t0;
- calendário: conhecido.

Amostra: --por-site edificações sorteadas por site (semente fixa), origens a cada 23 h ao longo de
2017 (a hora da origem varia). Referências ingênuas: repetir o mesmo horário do último dia medido
(naive diário) e da última semana medida (naive semanal).

Métrica por horizonte h: CV(RMSE) por site, em kWh, sobre todas as origens e edificações do site;
o resumo é a média simples dos sites. Gera em out/horizonte/: por_horizonte.csv, horizonte.png,
exemplos.png.
"""
import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch

from . import arquiteturas as A
from .config import RAIZ, RAW
from .dados import (CLIP_Z, CONTINUAS, FEATURES, MEDIDORES_OPCIONAIS, _ler_medidor, clima_site,
                    features_edificacao, selecionar, tempo_calendario)
from .graficos import MUDO, SERIES, TINTA, aplicar_estilo

SAIDA = RAIZ / "out" / "horizonte"
PESOS = RAIZ / "out" / "otimizacao_ft" / "11_sites" / "GRU" / "pesos"
H = 96
MARCAS = [1, 6, 12, 24, 48, 96]
PASSO_ORIGEM = 23
HIST = 168 + 24          # lag de 168 h da primeira linha da janela de 24 h

I_LAG = {l: FEATURES.index(f"elec_lag{l}") for l in (1, 24, 168)}
I_MED = [FEATURES.index(f"{m}_lag1") for m in MEDIDORES_OPCIONAIS]
I_CONT = [FEATURES.index(c) for c in CONTINUAS]
I_FIXAS = [j for j in range(len(FEATURES)) if j not in I_LAG.values()]   # calendário, clima, medidores


@torch.no_grad()
def recursiva(modelo, X, z, origens):
    """X: (T, F) features medidas; z: (T,) consumo normalizado medido. Devolve (O, H) previsões em z."""
    O = len(origens)
    buf = np.full((O, HIST + H), np.nan, np.float32)          # z de t0-HIST .. t0+95
    for i, t0 in enumerate(origens):
        buf[i, :HIST] = z[t0 - HIST:t0]
    med = X[origens - 1][:, I_MED]                           # outros medidores congelados em t0-1
    prev = np.zeros((O, H), np.float32)
    rel = np.arange(-A.JANELA + 1, 1)                        # linhas da janela, relativas ao alvo
    for h in range(H):
        linhas = origens[:, None] + h + rel[None, :]          # (O, janela) índices absolutos
        x = X[linhas].copy()                                  # (O, janela, F)
        r_rel = h + rel                                       # posição da linha relativa a t0
        for l, j in I_LAG.items():
            pos = HIST + r_rel - l                            # índice no buf do valor de lag
            x[:, :, j] = buf[:, pos]
        depois = r_rel - 1 >= 0                               # o lag de 1 h dos medidores cai depois de t0
        for k, j in enumerate(I_MED):
            x[:, depois, j] = med[:, k][:, None]
        x[:, :, I_CONT] = np.clip(x[:, :, I_CONT], -CLIP_Z, CLIP_Z)
        p = modelo(torch.from_numpy(x)).squeeze(1).numpy()
        prev[:, h] = p
        buf[:, HIST + h] = p
    return prev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--por-site", type=int, default=10)
    args = ap.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    elec = _ler_medidor("electricity")
    outros = {m: _ler_medidor(m) for m in MEDIDORES_OPCIONAIS}
    clima = pd.read_csv(RAW / "weather.csv", parse_dates=["timestamp"])
    idx = elec.index
    treino = idx.year == 2016
    tempo = tempo_calendario(idx)
    escolha = selecionar(elec)
    ft = torch.load(PESOS / f"seed{args.seed}_ft.pt", map_location="cpu")
    rng = np.random.default_rng(0)
    t_ini = idx.get_loc(pd.Timestamp("2017-01-01"))
    t_fim = idx.get_loc(pd.Timestamp("2017-12-31 23:00")) - H + 1
    origens_todas = np.arange(t_ini, t_fim, PASSO_ORIGEM)

    linhas, exemplos = [], {}
    for s, edifs in escolha.items():
        modelo = A.novo("GRU", args.seed, "cpu")
        modelo.load_state_dict(ft[s])
        modelo.eval()
        temp, orv = clima_site(clima, s, idx, treino)
        sorteio = rng.choice(edifs, size=min(args.por_site, len(edifs)), replace=False)
        for b in sorteio:
            y = elec[b].to_numpy(float)
            df = features_edificacao(b, y, outros, temp, orv, tempo, idx, treino)
            X = df[FEATURES].to_numpy(np.float32)
            z = df["y"].to_numpy(np.float32)
            mu, sd = df["mu"].iloc[0], df["sd"].iloc[0]
            # origem válida: histórico de 168 h e janelas sem buraco (features e consumo medidos)
            ok = []
            for t0 in origens_todas:
                if np.isnan(z[t0 - HIST:t0]).any() or np.isnan(X[t0 - A.JANELA:t0 + H][:, I_FIXAS]).any():
                    continue
                ok.append(t0)
            origens = np.array(ok)
            if len(origens) == 0:
                continue
            p = recursiva(modelo, X, z, origens) * sd + mu                 # (O, H) kWh
            alvo = origens[:, None] + np.arange(H)[None, :]
            real = y[alvo]
            dia = y[origens[:, None] - 24 + (np.arange(H) % 24)[None, :]]   # último dia medido, repetido
            sem = y[origens[:, None] - 168 + (np.arange(H) % 168)[None, :]]  # última semana medida
            for nome, pr in (("GRU recursiva", p), ("Naive diário", dia), ("Naive semanal", sem)):
                for h in range(H):
                    m = ~np.isnan(real[:, h])
                    e = pr[m, h] - real[m, h]
                    linhas.append({"site": s, "edificacao": b, "metodo": nome, "h": h + 1,
                                   "n": int(m.sum()), "sse": float((e ** 2).sum()), "soma_y": float(real[m, h].sum())})
            if s not in exemplos:
                i = len(origens) // 2
                exemplos[s] = (b, idx[origens[i]], real[i], p[i], dia[i])
        print(f"{s}: {len(sorteio)} edificações", flush=True)

    d = pd.DataFrame(linhas)
    g = d.groupby(["metodo", "site", "h"])[["n", "sse", "soma_y"]].sum()
    g["cv"] = 100 * np.sqrt(g.sse / g.n) / (g.soma_y / g.n)
    g = g.reset_index()
    media = g.groupby(["metodo", "h"]).cv.mean().unstack("metodo")
    g.to_csv(SAIDA / "por_horizonte.csv", index=False)

    aplicar_estilo()
    sites = sorted(g.site.unique())
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.8), gridspec_kw={"width_ratios": [1.15, 1]})
    ax = axs[0]
    for nome, cor, ls in (("GRU recursiva", SERIES[0], "-"), ("Naive diário", SERIES[1], "--"),
                          ("Naive semanal", SERIES[2], ":")):
        ax.plot(media.index, media[nome], color=cor, lw=2, ls=ls, label=nome)
    for h in MARCAS:
        v = media.loc[h, "GRU recursiva"]
        ax.plot(h, v, "o", ms=6, color=SERIES[0], mec="white", mew=1.2, zorder=5)
        ax.annotate(f"{v:.1f}".replace(".", ","), (h, v), xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=8.5, color=TINTA)
    ax.set_xticks(MARCAS)
    ax.set_xlabel("horas à frente")
    ax.set_ylabel("CV(RMSE), média simples dos sites (%)")
    ax.set_title("Erro por horizonte (2017)", loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=9)
    ax = axs[1]
    gru = g[g.metodo == "GRU recursiva"]
    fim = {}
    for s in sites:
        v = gru[gru.site == s].set_index("h").cv
        ax.plot(v.index, v.values, color=MUDO, lw=1.1, alpha=0.8)
        fim[s] = v.iloc[-1]
    ax.plot(media.index, media["GRU recursiva"], color=SERIES[0], lw=2.2, label="média dos sites")
    # nomes na ponta das linhas, afastados para não sobrepor
    y_ant = -np.inf
    passo = (max(fim.values()) - min(fim.values())) / 22 + 0.3
    for s, v in sorted(fim.items(), key=lambda kv: kv[1]):
        y_txt = max(v, y_ant + passo)
        ax.annotate(s, (H, v), xytext=(H + 2, y_txt), textcoords="data", fontsize=7.5, color=MUDO,
                    va="center", annotation_clip=False)
        y_ant = y_txt
    ax.set_xlim(0, H + 14)
    ax.set_xticks(MARCAS)
    ax.set_xlabel("horas à frente")
    ax.set_title("GRU recursiva por site", loc="left", fontsize=11)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.suptitle(f"GRU (FedAvg + FT, seed {args.seed}) prevista de forma recursiva, "
                 f"{args.por_site} edificações por site", x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout()
    fig.savefig(SAIDA / "horizonte.png", dpi=200)
    plt.close(fig)

    n = len(exemplos)
    fig, axs = plt.subplots((n + 2) // 3, 3, figsize=(14, 2.6 * ((n + 2) // 3)), sharex=True)
    for ax, (s, (b, t0, real, p, dia)) in zip(axs.flat, sorted(exemplos.items())):
        x = np.arange(1, H + 1)
        ax.plot(x, real, color=TINTA, lw=1.4, label="medido")
        ax.plot(x, p, color=SERIES[0], lw=1.6, label="GRU recursiva")
        ax.plot(x, dia, color=SERIES[1], lw=1, ls="--", label="naive diário")
        ax.set_title(f"{b} — origem {t0:%d/%m %Hh}", fontsize=8.5, loc="left", color=MUDO)
        ax.set_xticks(MARCAS)
    for ax in list(axs.flat)[n:]:
        ax.axis("off")
    axs.flat[0].legend(frameon=False, fontsize=8)
    fig.supxlabel("horas à frente")
    fig.supylabel("kWh")
    fig.tight_layout()
    fig.savefig(SAIDA / "exemplos.png", dpi=160)
    plt.close(fig)

    print("\nCV(RMSE) %, média simples dos sites")
    print(media.loc[MARCAS].round(2).to_string())


if __name__ == "__main__":
    main()
