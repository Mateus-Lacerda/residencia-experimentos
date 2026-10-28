#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_INA219.h>

constexpr char WIFI_SSID[] = "SEU_SSID";
constexpr char WIFI_PASSWORD[] = "SUA_SENHA";
constexpr char UDP_TARGET_IP[] = "0.0.0.0";
constexpr uint16_t UDP_PORT = 5005;
constexpr uint32_t SAMPLE_INTERVAL_MS = 10;

Adafruit_MPU6050 mpu;
Adafruit_INA219 ina219;
WiFiUDP udp;

struct RawPacket {
  float ax, ay, az, gx, gy, gz;
};

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Conectando ao WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
  }
  Serial.println();
  Serial.printf("Conectado, IP local: %s\n", WiFi.localIP().toString().c_str());

  if (!mpu.begin()) {
    Serial.println("Falha ao iniciar o MPU6050");
    while (1) {}
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);

  if (!ina219.begin()) {
    Serial.println("Falha ao iniciar o INA219");
    while (1) {}
  }

  Serial.println("timestamp;current_mA;power_mW");
}

void loop() {
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  RawPacket packet = {
    a.acceleration.x, a.acceleration.y, a.acceleration.z,
    g.gyro.x, g.gyro.y, g.gyro.z
  };

  udp.beginPacket(UDP_TARGET_IP, UDP_PORT);
  udp.write(reinterpret_cast<uint8_t*>(&packet), sizeof(packet));
  udp.endPacket();

  float current_mA = ina219.getCurrent_mA();
  float power_mW = ina219.getPower_mW();
  Serial.printf("%lu;%.3f;%.3f\n", millis(), current_mA, power_mW);

  delay(SAMPLE_INTERVAL_MS);
}
