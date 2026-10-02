#pragma once
#include <algorithm>
#include <cmath>
#include "f020_candidate_b_table_v1.h"
#ifdef __FAST_MATH__
#error "F020 Candidate B requires no fast math"
#endif
#pragma clang fp contract(off)
// Shared by the executed bridge and compile-only Candidate B source.
// The host guard must pass in this same thread before this evaluator is called.
static inline float candidate_b(float gate, float up) {
  float g = gate < 10.0f ? gate : 10.0f;
  float scaled = g * 32.0f;
  int i = static_cast<int>(std::floor(scaled)) + 512;
  i = std::max(0, std::min(831, i));
  float x0 = static_cast<float>(i - 512) / 32.0f;
  volatile float left = F020_SILU_TABLE[i];
  volatile float difference = F020_SILU_TABLE[i + 1] - F020_SILU_TABLE[i];
  volatile float slope = difference * 32.0f;
  volatile float delta = g - x0;
  volatile float increment = slope * delta;
  volatile float interpolated = left + increment;
  volatile float clipped_up = std::max(-10.0f, std::min(10.0f, up));
  volatile float product = interpolated * clipped_up;
  return product;
}
