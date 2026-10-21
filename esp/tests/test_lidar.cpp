#include <Arduino.h>
#include <Wire.h>
#include <VL53L1X.h>

VL53L1X sensor;

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  sensor.setTimeout(500);
  if (!sensor.init()) {
    Serial.println("Falha ao iniciar o VL53L1X");
    while (1) {}
  }
  sensor.setDistanceMode(VL53L1X::Long);
  sensor.setMeasurementTimingBudget(50000);
  sensor.startContinuous(50);
}

void loop() {
  int distancia = sensor.read();
  Serial.print(distancia);
  Serial.println(" mm");
  if (sensor.timeoutOccurred()) {
    Serial.println("Timeout!");
  }
}
