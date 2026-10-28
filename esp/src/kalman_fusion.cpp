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
constexpr uint32_t SAMPLE_INTERVAL_MS = 10; // 100 Hz

Adafruit_MPU6050 mpu;
Adafruit_INA219 ina219;
WiFiUDP udp;

struct KalmanFilter {
  float Q_angle = 0.001f;
  float Q_bias = 0.003f;
  float R_measure = 0.03f;

  float angle = 0.0f;
  float bias = 0.0f;
  float rate = 0.0f;

  float P[2][2] = {{0, 0}, {0, 0}};

  float update(float newAngle, float newRate, float dt) {
    rate = newRate - bias;
    angle += dt * rate;

    P[0][0] += dt * (dt * P[1][1] - P[0][1] - P[1][0] + Q_angle);
    P[0][1] -= dt * P[1][1];
    P[1][0] -= dt * P[1][1];
    P[1][1] += Q_bias * dt;

    float S = P[0][0] + R_measure;
    float K0 = P[0][0] / S;
    float K1 = P[1][0] / S;

    float y = newAngle - angle;
    angle += K0 * y;
    bias += K1 * y;

    float P00_temp = P[0][0];
    float P01_temp = P[0][1];

    P[0][0] -= K0 * P00_temp;
    P[0][1] -= K0 * P01_temp;
    P[1][0] -= K1 * P00_temp;
    P[1][1] -= K1 * P01_temp;

    return angle;
  }
};

KalmanFilter kalmanPitch;
KalmanFilter kalmanRoll;
uint32_t lastMicros = 0;

struct FusedPacket {
  float pitch, roll;
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

  lastMicros = micros();
  Serial.println("timestamp;current_mA;power_mW");
}

void loop() {
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  uint32_t now = micros();
  float dt = (now - lastMicros) / 1000000.0f;
  lastMicros = now;

  float accelPitch = atan2(a.acceleration.y, a.acceleration.z) * 180.0f / PI;
  float accelRoll = atan2(-a.acceleration.x, a.acceleration.z) * 180.0f / PI;

  float gyroPitchRate = g.gyro.x * 180.0f / PI;
  float gyroRollRate = g.gyro.y * 180.0f / PI;

  FusedPacket packet = {
    kalmanPitch.update(accelPitch, gyroPitchRate, dt),
    kalmanRoll.update(accelRoll, gyroRollRate, dt)
  };

  udp.beginPacket(UDP_TARGET_IP, UDP_PORT);
  udp.write(reinterpret_cast<uint8_t*>(&packet), sizeof(packet));
  udp.endPacket();

  float current_mA = ina219.getCurrent_mA();
  float power_mW = ina219.getPower_mW();
  Serial.printf("%lu;%.3f;%.3f\n", millis(), current_mA, power_mW);

  delay(SAMPLE_INTERVAL_MS);
}
