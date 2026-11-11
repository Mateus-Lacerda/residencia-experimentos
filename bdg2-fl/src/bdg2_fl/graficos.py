"""Estilo comum dos gráficos dos notebooks."""
import matplotlib as mpl

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
MUDO = "#898781"
GRADE = "#e1e0d9"
EIXO = "#c3c2b7"

# ordem fixa da paleta categórica (validada para daltonismo nos pares adjacentes)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]

METODOS = {
    "federado": ("FedAvg", SERIES[0]),
    "centralizado": ("Centralizado", SERIES[1]),
    "local": ("Só local", SERIES[2]),
    "random_walk": ("Random walk", SERIES[3]),
}

SEQ_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def cores_sites(sites):
    """Cor fixa por site, pela ordem em que os sites foram selecionados."""
    return {s: SERIES[i] for i, s in enumerate(sites)}


def aplicar_estilo():
    mpl.rcParams.update({
        "figure.facecolor": SUPERFICIE,
        "axes.facecolor": SUPERFICIE,
        "savefig.facecolor": SUPERFICIE,
        "figure.dpi": 110,
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.labelcolor": TINTA_2,
        "axes.edgecolor": EIXO,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRADE,
        "grid.linewidth": 0.6,
        "xtick.color": MUDO,
        "ytick.color": MUDO,
        "xtick.labelcolor": TINTA_2,
        "ytick.labelcolor": TINTA_2,
        "text.color": TINTA,
        "lines.linewidth": 1.6,
        "legend.frameon": False,
        "legend.fontsize": 8,
    })
