#include "common.h"

constexpr unsigned long PHASE_DURATION_MS = 3000;
constexpr unsigned long PAUSE_DURATION_MS = 500;

enum class Phase { FORWARD, PAUSE_AFTER_FORWARD, BACKWARD, PAUSE_AFTER_BACKWARD };

Phase phase = Phase::FORWARD;
unsigned long phaseStartedAt = 0;
unsigned long lastPrintAt = 0;

void enterPhase(Phase next) {
  phase = next;
  phaseStartedAt = millis();
  switch (phase) {
    case Phase::FORWARD:
      driveForward();
      break;
    case Phase::BACKWARD:
      driveBackward();
      break;
    case Phase::PAUSE_AFTER_FORWARD:
    case Phase::PAUSE_AFTER_BACKWARD:
      stopMotors();
      break;
  }
}

void setup() {
  Serial.begin(115200);
  setupMotors();
  setupEncoders();
  enterPhase(Phase::FORWARD);
}

void loop() {
  unsigned long now = millis();
  unsigned long elapsed = now - phaseStartedAt;

  switch (phase) {
    case Phase::FORWARD:
      if (elapsed >= PHASE_DURATION_MS) enterPhase(Phase::PAUSE_AFTER_FORWARD);
      break;
    case Phase::PAUSE_AFTER_FORWARD:
      if (elapsed >= PAUSE_DURATION_MS) enterPhase(Phase::BACKWARD);
      break;
    case Phase::BACKWARD:
      if (elapsed >= PHASE_DURATION_MS) enterPhase(Phase::PAUSE_AFTER_BACKWARD);
      break;
    case Phase::PAUSE_AFTER_BACKWARD:
      if (elapsed >= PAUSE_DURATION_MS) enterPhase(Phase::FORWARD);
      break;
  }

  if (now - lastPrintAt >= 100) {
    lastPrintAt = now;
    Serial.printf("%lu;%d;%lu;%lu\n", now, static_cast<int>(phase), pulsesA, pulsesB);
  }
}
