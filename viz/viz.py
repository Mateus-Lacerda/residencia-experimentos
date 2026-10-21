"""Visualização simples das leituras brutas dos sensores do ESP32.

Lê do serial linhas no formato `timestamp;ax;ay;az;gx;gy;gz;tof_mm;sonar_cm`
e plota tudo em tempo real com matplotlib.

Uso: uv run --with pyserial --with matplotlib python residencia_viz.py /dev/cu.usbserial-0001
"""

import sys
from collections import deque

import matplotlib.pyplot as plt
import serial
from matplotlib.animation import FuncAnimation

FIELDS = ["ax", "ay", "az", "gx", "gy", "gz", "tof_mm", "sonar_cm"]
WINDOW = 200

port = sys.argv[1]
baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

ser = serial.Serial(port, baud, timeout=1)

history = {field: deque(maxlen=WINDOW) for field in FIELDS}

fig, axes = plt.subplots(len(FIELDS), 1, sharex=True, figsize=(8, 10))
fig.suptitle("Leituras brutas dos sensores")
lines = {}
for ax, field in zip(axes, FIELDS):
    (line,) = ax.plot([], [])
    ax.set_ylabel(field)
    lines[field] = line


def update(_frame):
    while ser.in_waiting:
        raw_line = ser.readline().decode("utf-8", errors="replace").strip()
        parts = raw_line.split(";")
        if len(parts) != 1 + len(FIELDS):
            continue
        try:
            values = [float(p) for p in parts[1:]]
        except ValueError:
            continue
        for field, value in zip(FIELDS, values):
            history[field].append(value)

    for ax, field in zip(axes, FIELDS):
        data = list(history[field])
        lines[field].set_data(range(len(data)), data)
        ax.relim()
        ax.autoscale_view()
    return list(lines.values())


ani = FuncAnimation(fig, update, interval=100, cache_frame_data=False)
plt.show()
