"""Captura, ao mesmo tempo e pelo mesmo tanto de tempo, o Serial (corrente/potência
do INA219) e o UDP (pacotes do raw_imu.cpp ou kalman_fusion.cpp) do ESP32, cada um
no seu próprio CSV.

Uso:
    python3 power_logger.py --mode raw --duration 60 \
        --serial-port /dev/cu.usbserial-0001 --udp-port 5005 \
        --out-power raw_power.csv --out-packets raw_packets.csv

    python3 power_logger.py --mode kalman --duration 60 \
        --serial-port /dev/cu.usbserial-0001 --udp-port 5005 \
        --out-power kalman_power.csv --out-packets kalman_packets.csv

Depende de pyserial (`pip install pyserial`); o resto é biblioteca padrão.
"""

import argparse
import csv
import socket
import struct
import threading
import time

import serial

PACKET_FORMATS = {
    "raw": {
        "struct": "<ffffff",
        "fields": ["ax", "ay", "az", "gx", "gy", "gz"],
    },
    "kalman": {
        "struct": "<ff",
        "fields": ["pitch", "roll"],
    },
    "fall": {
        "struct": "<Lf",
        "fields": ["timestamp_ms", "magnitude_g"],
    },
}


def read_serial_power(ser, deadline, out_path, counters):
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["recv_timestamp", "esp_timestamp", "current_mA", "power_mW"])

        start = time.monotonic()
        while time.monotonic() < deadline:
            line = ser.readline().decode(errors="ignore").strip()
            if not line:
                continue

            parts = line.split(";")
            if len(parts) != 3:
                continue  # linha de boot/conexão WiFi, ou o cabeçalho

            try:
                esp_ts = int(parts[0])
                current_mA = float(parts[1])
                power_mW = float(parts[2])
            except ValueError:
                continue

            recv_time = time.monotonic() - start
            writer.writerow([f"{recv_time:.4f}", esp_ts, current_mA, power_mW])
            counters["power_samples"] += 1


def read_udp_packets(sock, deadline, packet_struct, fields, out_path, counters):
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["recv_timestamp", "packet_size_bytes"] + fields)

        start = time.monotonic()
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            sock.settimeout(max(remaining, 0.01))
            try:
                data, _addr = sock.recvfrom(1024)
            except socket.timeout:
                continue

            recv_time = time.monotonic() - start
            counters["total_bytes"] += len(data)

            if len(data) != packet_struct.size:
                continue

            values = packet_struct.unpack(data)
            writer.writerow([f"{recv_time:.4f}", len(data), *values])
            counters["packets"] += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=PACKET_FORMATS.keys(), required=True)
    parser.add_argument("--duration", type=float, required=True, help="duração em segundos")
    parser.add_argument("--serial-port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--udp-port", type=int, default=5005)
    parser.add_argument("--out-power", required=True)
    parser.add_argument("--out-packets", required=True)
    args = parser.parse_args()

    fmt = PACKET_FORMATS[args.mode]
    packet_struct = struct.Struct(fmt["struct"])

    ser = serial.Serial(args.serial_port, args.baud, timeout=0.5)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.udp_port))

    counters = {"power_samples": 0, "packets": 0, "total_bytes": 0}

    print(f"Capturando por {args.duration}s (modo '{args.mode}')...")
    deadline = time.monotonic() + args.duration

    t_serial = threading.Thread(
        target=read_serial_power, args=(ser, deadline, args.out_power, counters)
    )
    t_udp = threading.Thread(
        target=read_udp_packets,
        args=(sock, deadline, packet_struct, fmt["fields"], args.out_packets, counters),
    )

    t_serial.start()
    t_udp.start()
    t_serial.join()
    t_udp.join()

    ser.close()
    sock.close()

    print(f"\nAmostras de corrente/potência: {counters['power_samples']}")
    print(f"Pacotes recebidos: {counters['packets']}")
    print(f"Total de bytes recebidos: {counters['total_bytes']}")
    print(f"Gravado em {args.out_power} e {args.out_packets}")


if __name__ == "__main__":
    main()
