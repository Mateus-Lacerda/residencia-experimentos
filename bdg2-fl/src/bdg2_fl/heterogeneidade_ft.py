"""Como o FedAvg + fine-tuning de cada modelo lida com a heterogeneidade dos sites.

uv run python -m bdg2_fl.heterogeneidade_ft

Lê os teste.json de out/otimizacao_ft/11_sites/<modelo>/ (CV(RMSE) por site em 2017, 3 seeds) e os
resumos de out/heterogeneidade/ (gerados por heterogeneidade.py). Gera em out/heterogeneidade_ft/:
- por_site.csv: CV(RMSE) médio e desvio entre seeds, por modelo, método e site;
- diferencas.csv: por site, FT − FedAvg, FT − só local e FedAvg − só local (pp, médias das seeds);
- resumo.csv: por modelo e método, o total (ponderado pelos dados), a média simples dos sites,
  o desvio entre sites, o pior site e quantos sites o FT melhora em relação ao FedAvg e ao só local;
- correlacoes.csv: Spearman entre as medidas de heterogeneidade de cada site e as diferenças acima.
  Com 11 sites, |rho| precisa passar de ~0,62 para p < 0,05 (bilateral).
- ft_por_site.png: CV(RMSE) por site, FedAvg e FT de cada modelo;
- ft_ganho_vs_heterogeneidade.png: ganho do FT sobre o FedAvg contra três medidas de heterogeneidade.
"""
import json

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

from .config import RAIZ
from .graficos import MUDO, SERIES, TINTA, aplicar_estilo

ENTRADA = RAIZ / "out" / "otimizacao_ft" / "11_sites"
HET = RAIZ / "out" / "heterogeneidade"
SAIDA = RAIZ / "out" / "heterogeneidade_ft"
MODELOS = {"GRU": "GRU", "LSTM": "LSTM", "MLP_janela_achatada": "MLP janela achatada"}
CORES = dict(zip(MODELOS.values(), SERIES[:3]))
MARCADORES = dict(zip(MODELOS.values(), ["o", "s", "D"]))
FT, FA, LO = "FedAvg + fine-tuning", "FedAvg", "Só local"


def _virgula(casas):
    return FuncFormatter(lambda v, _=None: f"{v:.{casas}f}".replace(".", ","))


def carregar():
    linhas = []
    for slug, nome in MODELOS.items():
        r = json.loads((ENTRADA / slug / "teste.json").read_text())
        for metodo, por_seed in r["metodos"].items():
            for seed, d in zip(r["seeds"], por_seed):
                linhas += [{"modelo": nome, "metodo": metodo, "seed": seed, "site": s, "cv": v} for s, v in d.items()]
    return pd.DataFrame(linhas)


def heterogeneidade(sites):
    q = pd.read_csv(HET / "quantidade.csv", index_col=0)
    ro = pd.read_csv(HET / "rotulo_resumo.csv", index_col=0)
    fe = pd.read_csv(HET / "features_resumo.csv", index_col=0)
    return pd.DataFrame({
        "peso no FedAvg": q["peso_fedavg"],
        "W1 rótulo (log10 kWh)": ro["w1_log10kwh_contra_resto"],
        "W1 rótulo (z-score)": ro["w1_z_contra_resto"],
        "W1 temperatura (°C)": fe["w1_temp_c_contra_resto"],
        "W1 temperatura (z-score)": fe["w1_temp_z_contra_resto"],
    }).loc[sites]


def tabelas(df):
    por_site = df.groupby(["modelo", "metodo", "site"]).cv.agg(["mean", "std"]).reset_index()
    media = por_site.pivot_table(index="site", columns=["modelo", "metodo"], values="mean")
    sites = [s for s in media.index if s != "Total"]
    dif, resumo = {}, []
    for m in MODELOS.values():
        f, lo, ft = (media.loc[sites, (m, x)] for x in (FA, LO, FT))
        dif[m] = pd.DataFrame({"FT − FedAvg": ft - f, "FT − só local": ft - lo, "FedAvg − só local": f - lo})
        for metodo in (FA, LO, FT):
            v = media.loc[sites, (m, metodo)]
            resumo.append({"modelo": m, "metodo": metodo, "total": media.loc["Total", (m, metodo)],
                           "media_sites": v.mean(), "desvio_sites": v.std(), "pior_site": v.idxmax(),
                           "cv_pior_site": v.max(), "melhor_site": v.idxmin(), "cv_melhor_site": v.min()})
        resumo[-1] |= {"sites_ft_melhor_que_fedavg": int((ft < f).sum()),
                       "sites_ft_melhor_que_local": int((ft < lo).sum()),
                       "sites_ft_melhor_que_ambos": int(((ft < f) & (ft < lo)).sum())}
    dif = pd.concat(dif, names=["modelo", "site"])
    return por_site, media, sites, dif, pd.DataFrame(resumo)


def correlacoes(dif, het):
    linhas = []
    for m in MODELOS.values():
        d = dif.loc[m]
        for c in d.columns:
            for h in het.columns:
                linhas.append({"modelo": m, "diferenca": c, "heterogeneidade": h,
                               # Spearman = Pearson dos postos (Series.corr com spearman exige scipy)
                               "spearman": d[c].rank().corr(het[h].rank())})
    return pd.DataFrame(linhas)


def grafico_sites(media, sites):
    # ordem dos sites: do pior para o melhor FedAvg da GRU, pior no topo
    ordem = media.loc[sites, ("GRU", FA)].sort_values().index.tolist()
    n = len(ordem)
    fig, ax = plt.subplots(figsize=(8.5, 0.5 * n + 1.8))
    desloc = dict(zip(MODELOS.values(), [0.22, 0.0, -0.22]))
    for m in MODELOS.values():
        for i, s in enumerate(ordem):
            y = i + desloc[m]
            f, ft = media.loc[s, (m, FA)], media.loc[s, (m, FT)]
            ax.plot([f, ft], [y, y], color=CORES[m], lw=1.5, alpha=0.6, zorder=2)
            ax.plot(f, y, MARCADORES[m], ms=7, mfc="white", mec=CORES[m], mew=1.5, zorder=3,
                    label=f"{m}: FedAvg" if i == 0 else None)
            ax.plot(ft, y, MARCADORES[m], ms=7, color=CORES[m], mec="white", mew=1, zorder=4,
                    label=f"{m}: FedAvg + FT" if i == 0 else None)
    ax.set_yticks(range(n), ordem)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlabel("CV(RMSE) no teste (2017), média de 3 seeds, % — menor é melhor")
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=10, labelcolor=TINTA)
    ax.xaxis.set_major_formatter(_virgula(0))
    ax.set_title("FedAvg (vazado) e FedAvg + fine-tuning (cheio) por site", fontsize=12, pad=44)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=8.5, handletextpad=0.3)
    fig.tight_layout()
    fig.savefig(SAIDA / "ft_por_site.png", dpi=200)
    plt.close(fig)


def grafico_ganho(dif, het):
    eixos = ["peso no FedAvg", "W1 rótulo (log10 kWh)", "W1 temperatura (°C)"]
    fig, axs = plt.subplots(1, len(eixos), figsize=(11, 4), sharey=True)
    for ax, h in zip(axs, eixos):
        for m in MODELOS.values():
            ganho = -dif.loc[m]["FT − FedAvg"]
            ax.plot(het[h], ganho, MARCADORES[m], ms=7, color=CORES[m], mec="white", mew=1, alpha=0.9,
                    label=m if ax is axs[0] else None)
        g = -dif.xs("GRU")["FT − FedAvg"]
        for s in g.index:          # nomes dos sites, na posição da GRU
            ax.annotate(s, (het.loc[s, h], g[s]), xytext=(4, 3), textcoords="offset points",
                        fontsize=7, color=MUDO)
        ax.axhline(0, color=MUDO, lw=1, ls="--")
        ax.set_xlabel(h)
        ax.grid(axis="x")
        ax.yaxis.set_major_formatter(_virgula(1))
    axs[0].set_ylabel("ganho do FT sobre o FedAvg (pp)")
    fig.suptitle("Ganho do fine-tuning por site contra a heterogeneidade do site", x=0.01, ha="left",
                 fontsize=12, fontweight="bold")
    fig.legend(loc="upper right", ncol=3, fontsize=9, frameon=False)
    fig.tight_layout()
    fig.savefig(SAIDA / "ft_ganho_vs_heterogeneidade.png", dpi=200)
    plt.close(fig)


def main():
    SAIDA.mkdir(parents=True, exist_ok=True)
    aplicar_estilo()
    df = carregar()
    por_site, media, sites, dif, resumo = tabelas(df)
    het = heterogeneidade(sites)
    corr = correlacoes(dif, het)
    por_site.to_csv(SAIDA / "por_site.csv", index=False)
    dif.to_csv(SAIDA / "diferencas.csv")
    resumo.to_csv(SAIDA / "resumo.csv", index=False)
    corr.to_csv(SAIDA / "correlacoes.csv", index=False)
    grafico_sites(media, sites)
    grafico_ganho(dif, het)

    pd.set_option("display.width", 250, "display.max_columns", 30)
    print("CV(RMSE) por site, média de 3 seeds")
    print(media.round(2).T.to_string())
    print("\ndiferenças por site (pp)")
    print(dif.round(2).unstack("site").to_string())
    print("\nresumo")
    print(resumo.round(2).to_string(index=False))
    print("\nSpearman (|rho| > 0,62 ~ p < 0,05 com 11 sites)")
    print(corr.pivot_table(index=["diferenca", "heterogeneidade"], columns="modelo", values="spearman").round(2).to_string())


if __name__ == "__main__":
    main()
