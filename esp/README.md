# esp

Firmware do ESP32, via PlatformIO.

## Comandos

```bash
# compilar
pio run

# gravar no ESP32
pio run -t upload

# abrir o monitor serial
pio device monitor
```

A porta serial está fixa em `/dev/cu.usbserial-0001` no `platformio.ini` — ajuste `upload_port`/`monitor_port` se a sua for diferente.
