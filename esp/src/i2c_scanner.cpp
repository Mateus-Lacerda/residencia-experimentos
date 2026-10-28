#include <Arduino.h>
#include <Wire.h>

void setup() {
  Serial.begin(115200);
  delay(1000);
  Wire.begin(21, 22);
  Serial.println("Scanner I2C iniciado");
}

void loop() {
  Serial.println("Varrendo barramento I2C...");
  uint8_t found = 0;

  for (uint8_t address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    uint8_t error = Wire.endTransmission();

    if (error == 0) {
      Serial.printf("Dispositivo encontrado em 0x%02X\n", address);
      found++;
    }
  }

  if (found == 0) {
    Serial.println("Nenhum dispositivo encontrado.");
  } else {
    Serial.printf("Total: %d dispositivo(s)\n", found);
  }

  delay(3000);
}
