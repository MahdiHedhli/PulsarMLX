// Candidate B's separately compiled synthetic activation kernel.
// The qualification driver supplies a generated header containing the frozen
// 833 f32 table; this source contains no MLX or Candidate N dependency.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>

#ifndef F020_TABLE_HEADER
#error "F020_TABLE_HEADER must name the generated frozen table header"
#endif
#include F020_TABLE_HEADER

#pragma clang fp contract(off)
static inline float candidate_b(float gate, float up) {
  float g = gate < 10.0f ? gate : 10.0f; // source-correct upper-only clamp
  float scaled = g * 32.0f;
  int i = static_cast<int>(std::floor(scaled)) + 512;
  i = std::max(0, std::min(831, i));
  float x0 = static_cast<float>(i - 512) / 32.0f;
  volatile float left = F020_SILU_TABLE[i];
  volatile float slope = (F020_SILU_TABLE[i + 1] - F020_SILU_TABLE[i]) * 32.0f;
  volatile float delta = g - x0;
  volatile float interpolated = left + slope * delta;
  volatile float clipped_up = std::max(-10.0f, std::min(10.0f, up));
  volatile float product = interpolated * clipped_up;
  return product;
}

int main() {
  // Compile-time/self-test only. Qualification invokes the same function
  // after the frozen conformance gate and records observations separately.
  volatile float result = candidate_b(0.0f, 1.0f);
  if (!std::isfinite(result)) return 2;
  std::puts("CANDIDATE_B_COMPILE_SELFTEST_PASS");
  return 0;
}
