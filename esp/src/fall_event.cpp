#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_INA219.h>

constexpr char WIFI_SSID[] = "SEU_SSID";
constexpr char WIFI_PASSWORD[] = "SUA_SENHA";
constexpr char UDP_TARGET_IP[] = "0.0.0.0";
constexpr uint16_t UDP_PORT = 5005;
constexpr uint32_t SAMPLE_INTERVAL_MS = 10; // 100 Hz, mesma taxa de leitura dos outros modos

constexpr float GRAVITY_MS2 = 9.81f;
constexpr float FREE_FALL_THRESHOLD_G = 0.3f; // magnitude abaixo disso = queda livre
constexpr uint32_t EVENT_COOLDOWN_MS = 1000;  // evita disparar várias vezes na mesma queda

Adafruit_MPU6050 mpu;
Adafruit_INA219 ina219;
WiFiUDP udp;

uint32_t lastEventMs = 0;

struct FallEvent {
  uint32_t timestamp_ms;
  float magnitude_g;
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

  float magnitude_ms2 = sqrtf(
    a.acceleration.x * a.acceleration.x +
    a.acceleration.y * a.acceleration.y +
    a.acceleration.z * a.acceleration.z
  );
  float magnitude_g = magnitude_ms2 / GRAVITY_MS2;

  uint32_t now = millis();
  bool cooldownElapsed = (now - lastEventMs) >= EVENT_COOLDOWN_MS;

  if (magnitude_g < FREE_FALL_THRESHOLD_G && cooldownElapsed) {
    FallEvent event = { now, magnitude_g };

    udp.beginPacket(UDP_TARGET_IP, UDP_PORT);
    udp.write(reinterpret_cast<uint8_t*>(&event), sizeof(event));
    udp.endPacket();

    lastEventMs = now;
  }

  float current_mA = ina219.getCurrent_mA();
  float power_mW = ina219.getPower_mW();
  Serial.printf("%lu;%.3f;%.3f\n", millis(), current_mA, power_mW);

  delay(SAMPLE_INTERVAL_MS);
}
