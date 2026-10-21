#include <Arduino.h>
#include <Wire.h>
#include <VL53L1X.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

constexpr uint8_t TRIG_PIN = 5;
constexpr uint8_t ECHO_PIN = 18;
constexpr uint32_t TIMEOUT_US = 30000;
constexpr float SOUND_CM_PER_US = 0.0343f;

VL53L1X tof;
Adafruit_MPU6050 mpu;

float readSonarCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  uint32_t duration = pulseIn(ECHO_PIN, HIGH, TIMEOUT_US);
  if (duration == 0) return -1.0f;
  return duration * SOUND_CM_PER_US / 2.0f;
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);

  Wire.begin(21, 22);

  tof.setTimeout(500);
  if (!tof.init()) {
    Serial.println("Falha ao iniciar o VL53L1X");
    while (1) {}
  }
  tof.setDistanceMode(VL53L1X::Long);
  tof.setMeasurementTimingBudget(50000);
  tof.startContinuous(50);

  if (!mpu.begin()) {
    Serial.println("Falha ao iniciar o MPU6050");
    while (1) {}
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
}

void loop() {
  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  int tofMm = tof.read();
  float sonarCm = readSonarCm();

  Serial.printf("%lu;%.4f;%.4f;%.4f;%.4f;%.4f;%.4f;%d;%.1f\n",
    millis(),
    a.acceleration.x, a.acceleration.y, a.acceleration.z,
    g.gyro.x, g.gyro.y, g.gyro.z,
    tofMm,
    sonarCm);

  delay(50);
}
