"""Compara energia e volume de dados entre dois modos de transmissão, a partir
dos CSVs gerados pelo power_logger.py.

Uso:
    python3 plot_energy.py --a-label Raw --a-power raw_power.csv --a-packets raw_packets.csv \
        --b-label Kalman --b-power kalman_power.csv --b-packets kalman_packets.csv \
        --out energia_kalman.png

    python3 plot_energy.py --a-label Raw --a-power raw_power.csv --a-packets raw_packets.csv \
        --b-label "Evento de queda" --b-power fall_power.csv --b-packets fall_packets.csv \
        --out energia_fall.png

Depende de matplotlib (`uv run --with matplotlib plot_energy.py ...`).
"""

import argparse
import csv

import matplotlib.pyplot as plt

COLOR_A = "#2a78d6"  # categorical slot 1 (azul)
COLOR_B = "#eb6834"  # categorical slot 2 (laranja)


def read_power_csv(path):
    timestamps, currents, powers = [], [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            timestamps.append(float(row["recv_timestamp"]))
            currents.append(float(row["current_mA"]))
            powers.append(float(row["power_mW"]))
    return timestamps, currents, powers


def read_packets_csv(path):
    total_bytes = 0
    count = 0
    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            total_bytes += int(row["packet_size_bytes"])
            count += 1
    return total_bytes, count


def trapezoid_energy_mj(timestamps, powers_mw):
    energy = 0.0
    for i in range(1, len(timestamps)):
        dt = timestamps[i] - timestamps[i - 1]
        avg_p = (powers_mw[i] + powers_mw[i - 1]) / 2
        energy += avg_p * dt
    return energy  # mW * s = mJ


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-label", required=True)
    parser.add_argument("--a-power", required=True)
    parser.add_argument("--a-packets", required=True)
    parser.add_argument("--b-label", required=True)
    parser.add_argument("--b-power", required=True)
    parser.add_argument("--b-packets", required=True)
    parser.add_argument("--out", default="energia.png")
    args = parser.parse_args()

    a_t, a_i, a_p = read_power_csv(args.a_power)
    b_t, b_i, b_p = read_power_csv(args.b_power)

    a_bytes, a_count = read_packets_csv(args.a_packets)
    b_bytes, b_count = read_packets_csv(args.b_packets)

    a_energy_mj = trapezoid_energy_mj(a_t, a_p)
    b_energy_mj = trapezoid_energy_mj(b_t, b_p)

    print(f"{args.a_label}: {len(a_t)} amostras, energia {a_energy_mj:.1f} mJ, "
          f"{a_bytes} bytes em {a_count} pacotes")
    print(f"{args.b_label}: {len(b_t)} amostras, energia {b_energy_mj:.1f} mJ, "
          f"{b_bytes} bytes em {b_count} pacotes")

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
    fig.patch.set_facecolor("#fcfcfb")

    # Painel A: corrente ao longo do tempo
    ax = axes[0]
    ax.set_facecolor("#fcfcfb")
    ax.plot(a_t, a_i, color=COLOR_A, linewidth=1.5, label=args.a_label)
    ax.plot(b_t, b_i, color=COLOR_B, linewidth=1.5, label=args.b_label)
    ax.set_xlabel("Tempo (s)")
    ax.set_ylabel("Corrente (mA)")
    ax.set_title("Corrente ao longo do teste")
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", color="#e1e0d9", linewidth=0.8)

    # Painel B: energia total consumida
    ax = axes[1]
    ax.set_facecolor("#fcfcfb")
    bars = ax.bar(
        [args.a_label, args.b_label],
        [a_energy_mj, b_energy_mj],
        color=[COLOR_A, COLOR_B],
        width=0.5,
    )
    ax.set_ylabel("Energia (mJ)")
    ax.set_title("Energia total no teste")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.bar_label(bars, fmt="%.0f", padding=3)

    # Painel C: volume de dados transmitido
    ax = axes[2]
    ax.set_facecolor("#fcfcfb")
    bars = ax.bar(
        [args.a_label, args.b_label],
        [a_bytes / 1024, b_bytes / 1024],
        color=[COLOR_A, COLOR_B],
        width=0.5,
    )
    ax.set_ylabel("Dados transmitidos (KB)")
    ax.set_title("Volume de dados no teste")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.bar_label(bars, fmt="%.1f", padding=3)

    fig.tight_layout()
    fig.savefig(args.out, dpi=150, facecolor=fig.get_facecolor())
    print(f"\nGráfico salvo em {args.out}")


if __name__ == "__main__":
    main()
