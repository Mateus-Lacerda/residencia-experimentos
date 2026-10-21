#include <Wire.h>

void setup() {
  Wire.begin(21, 22); // SDA, SCL
  Serial.begin(115200);
  delay(1000);
  Serial.println("Escaneando I2C...");
}

void loop() {
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print("Dispositivo encontrado em 0x");
      Serial.println(addr, HEX);
    }
  }
  delay(3000);
}
