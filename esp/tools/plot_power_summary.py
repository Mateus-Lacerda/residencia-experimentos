"""Gráfico de barras comparando potência média (com desvio padrão) entre N modos,
a partir dos CSVs de potência gerados pelo power_logger.py.

Uso:
    python3 plot_power_summary.py \
        --series "Raw=raw_power.csv" \
        --series "Kalman=kalman_power.csv" \
        --series "Evento de queda=fall_power.csv" \
        --out potencia_media.png

Depende de matplotlib (`uv run --with matplotlib plot_power_summary.py ...`).
"""

import argparse
import csv
import statistics

import matplotlib.pyplot as plt

# Paleta categórica (ordem fixa, slots 1/2/3)
COLORS = ["#2a78d6", "#eb6834", "#1baf7a"]


def read_power_mw(path):
    values = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            values.append(float(row["power_mW"]))
    return values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--series", action="append", required=True,
        help='Formato "Label=caminho.csv", repetível'
    )
    parser.add_argument("--out", default="potencia_media.png")
    args = parser.parse_args()

    labels, means, stdevs = [], [], []
    for entry in args.series:
        label, path = entry.split("=", 1)
        values = read_power_mw(path)
        mean = statistics.mean(values)
        stdev = statistics.stdev(values)
        labels.append(label)
        means.append(mean)
        stdevs.append(stdev)
        print(f"{label}: {mean:.2f} ± {stdev:.2f} mW (n={len(values)})")

    colors = [COLORS[i % len(COLORS)] for i in range(len(labels))]

    fig, ax = plt.subplots(figsize=(6, 4.5))
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")

    bars = ax.bar(labels, means, yerr=stdevs, capsize=5, color=colors, width=0.5,
                   error_kw={"ecolor": "#52514e", "linewidth": 1.2})
    ax.set_ylabel("Potência média (mW)")
    ax.set_title("Potência média por modo (± desvio padrão)")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#e1e0d9", linewidth=0.8)

    for bar, mean, stdev in zip(bars, means, stdevs):
        ax.text(bar.get_x() + bar.get_width() / 2, mean + stdev + 5,
                f"{mean:.1f}±{stdev:.1f}", ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    fig.savefig(args.out, dpi=150, facecolor=fig.get_facecolor())
    print(f"\nGráfico salvo em {args.out}")


if __name__ == "__main__":
    main()
