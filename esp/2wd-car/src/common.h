#pragma once

#include <Arduino.h>

constexpr uint8_t IN1 = 16;
constexpr uint8_t IN2 = 17;
constexpr uint8_t IN3 = 18;
constexpr uint8_t IN4 = 19;
constexpr uint8_t ENA = 25;
constexpr uint8_t ENB = 26;

constexpr uint8_t ENCODER_A = 34;
constexpr uint8_t ENCODER_B = 35;

constexpr uint8_t DRIVE_SPEED = 180; // 0-255

extern volatile uint32_t pulsesA;
extern volatile uint32_t pulsesB;

void setupMotors();
void setupEncoders();

void stopMotors();
void driveForward();
void driveBackward();
void turnLeft();
void turnRight();
