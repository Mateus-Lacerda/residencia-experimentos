#include <Arduino.h>

constexpr uint8_t TRIG_PIN = 5;
constexpr uint8_t ECHO_PIN = 18;
constexpr uint32_t TIMEOUT_US = 30000;
constexpr float SOUND_CM_PER_US = 0.0343f;

void setup() {
  Serial.begin(115200);
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);
}

float readDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  uint32_t duration = pulseIn(ECHO_PIN, HIGH, TIMEOUT_US);
  if (duration == 0) return -1.0f;
  return duration * SOUND_CM_PER_US / 2.0f;
}

void loop() {
  float d = readDistanceCm();
  if (d < 0) {
    Serial.println("sem eco");
  } else {
    Serial.printf("%lu ms  %.1f cm\n", millis(), d);
  }
  delay(100);
}
