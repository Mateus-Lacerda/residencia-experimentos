"""Gráficos da comparação de arquiteturas (CV(RMSE) total no teste de 2017).

uv run python -m bdg2_fl.gerar_plots

Lê os JSONs de out/arquiteturas/ e gera, na mesma pasta:
- arquiteturas_seed42.png: todas as arquiteturas na seed 42, com o random walk como referência;
- arquiteturas_3seeds.png: só as que rodaram nas 3 seeds, média ± desvio padrão.

E, a partir dos teste.json de out/otimizacao_ft/11_sites/, gera nessa pasta:
- ft_3seeds.png: FedAvg, só local e FedAvg + fine-tuning por modelo, média ± desvio padrão.

A CNN-LSTM fica de fora. São gráficos de pontos, não de barras: as diferenças são de décimos e
uma barra teria de começar do zero.
"""
import json
import statistics as st

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from .config import RAIZ
from .graficos import METODOS, MUDO, SERIES, TINTA, aplicar_estilo

PASTA = RAIZ / "out" / "arquiteturas"
EXCLUIDOS = {"CNN-LSTM"}
CENARIOS = [("centralizado", "o", 0.22), ("local", "s", 0.0), ("federado", "D", -0.22)]
PASTA_FT = RAIZ / "out" / "otimizacao_ft" / "11_sites"
MODELOS_FT = ["GRU", "LSTM", "MLP janela achatada"]
# (chave em teste.json, rótulo, cor, marcador, deslocamento)
CENARIOS_FT = [("Só local", "Só local", METODOS["local"][1], "s", 0.22),
               ("FedAvg", "FedAvg", METODOS["federado"][1], "D", 0.0),
               ("FedAvg + fine-tuning", "FedAvg + fine-tuning", SERIES[4], "^", -0.22)]


def _virgula(v, _=None):
    return f"{v:.1f}".replace(".", ",")


def carregar():
    """{modelo: [resultado de cada seed]}"""
    runs = {}
    for f in sorted(PASTA.glob("*__seed*.json")):
        d = json.loads(f.read_text())
        if d["modelo"] not in EXCLUIDOS:
            runs.setdefault(d["modelo"], []).append(d)
    return runs


def grafico(runs, titulo, arquivo, desvio, random_walk=None):
    # o melhor FedAvg fica no topo
    modelos = sorted(runs, key=lambda m: -st.mean(d["federado"]["Total"] for d in runs[m]))
    n = len(modelos)
    fig, ax = plt.subplots(figsize=(8, 0.55 * n + 1.6))
    for chave, marcador, desloc in CENARIOS:
        rotulo, cor = METODOS[chave]
        for i, m in enumerate(modelos):
            v = [d[chave]["Total"] for d in runs[m]]
            x, y = st.mean(v), i + desloc
            if desvio:
                ax.errorbar(x, y, xerr=st.stdev(v), fmt="none", ecolor=cor, elinewidth=2, capsize=4, zorder=2)
            ax.plot(x, y, marcador, ms=8, color=cor, mec="white", mew=1.5, zorder=3,
                    label=rotulo if i == 0 else None)
    if random_walk is not None:
        ax.axvline(random_walk, color=MUDO, ls="--", lw=1.2, zorder=1)
        ax.text(random_walk, n - 0.45, f"random walk {random_walk:.2f}".replace(".", ","),
                color=MUDO, ha="right", va="bottom", fontsize=9)
    ax.set_yticks(range(n), modelos)
    ax.set_ylim(-0.6, n - 0.1)
    ax.set_xlabel("CV(RMSE) total no teste (2017), % — menor é melhor")
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=10, labelcolor=TINTA)
    ax.set_title(titulo, fontsize=12, pad=26)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=9, handletextpad=0.3)
    ax.xaxis.set_major_formatter(FuncFormatter(_virgula))
    fig.tight_layout()
    fig.savefig(PASTA / arquivo, dpi=200)
    plt.close(fig)
    print(PASTA / arquivo)


def grafico_ft():
    res = {m: json.loads((PASTA_FT / m.replace(" ", "_") / "teste.json").read_text()) for m in MODELOS_FT}
    # o melhor FedAvg + fine-tuning fica no topo
    modelos = sorted(MODELOS_FT, key=lambda m: -st.mean(d["Total"] for d in res[m]["metodos"]["FedAvg + fine-tuning"]))
    n = len(modelos)
    fig, ax = plt.subplots(figsize=(8, 0.8 * n + 1.6))
    for chave, rotulo, cor, marcador, desloc in CENARIOS_FT:
        for i, m in enumerate(modelos):
            v = [d["Total"] for d in res[m]["metodos"][chave]]
            x, y = st.mean(v), i + desloc
            ax.errorbar(x, y, xerr=st.stdev(v), fmt="none", ecolor=cor, elinewidth=2, capsize=4, zorder=2)
            ax.plot(x, y, marcador, ms=8, color=cor, mec="white", mew=1.5, zorder=3,
                    label=rotulo if i == 0 else None)
    ax.set_yticks(range(n), modelos)
    ax.set_ylim(-0.6, n - 0.4)
    ax.set_xlabel("CV(RMSE) total no teste (2017), % — menor é melhor")
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=10, labelcolor=TINTA)
    ax.set_title("Fine-tuning com 3 seeds (42, 505, 11): média ± desvio padrão", fontsize=12, pad=26)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=9, handletextpad=0.3)
    ax.xaxis.set_major_formatter(FuncFormatter(_virgula))
    fig.tight_layout()
    arq = PASTA_FT / "ft_3seeds.png"
    fig.savefig(arq, dpi=200)
    plt.close(fig)
    print(arq)


def main():
    aplicar_estilo()
    runs = carregar()
    rw = json.loads((PASTA / "random_walk.json").read_text())["Total"]
    seed42 = {m: [d for d in ds if d["seed"] == 42] for m, ds in runs.items()}
    grafico(seed42, "Comparação de arquiteturas (seed 42)", "arquiteturas_seed42.png", False, rw)
    tres = {m: ds for m, ds in runs.items() if len(ds) == 3}
    grafico(tres, "Arquiteturas com 3 seeds (42, 505, 11): média ± desvio padrão",
            "arquiteturas_3seeds.png", True)
    grafico_ft()


if __name__ == "__main__":
    main()
