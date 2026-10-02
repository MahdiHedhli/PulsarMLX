#pragma once
#include <cfenv>
#include <cstdint>
#include <cstring>
#include <cmath>
#include <limits>

#ifdef __FAST_MATH__
#error "F020 gradual-underflow guard requires no fast math"
#endif

// ARM AAPCS64: RMode[23:22], FZ[24], FIZ/AH[1:0] may vary per thread.
// No instruction in this header writes FPCR or changes C rounding state.
static inline bool f020_cpu_state_supported(uint64_t fpcr, int round_mode,
                                            bool arm64) {
  constexpr uint64_t mask = (3ULL << 22) | (1ULL << 24) | 3ULL | 0x9f00ULL;
  return arm64 && (fpcr & mask) == 0 && round_mode == FE_TONEAREST;
}

static inline uint32_t f020_guard_bits(float value) {
  uint32_t result;
  std::memcpy(&result, &value, sizeof result);
  return result;
}
static inline float f020_guard_float(uint32_t value) {
  float result;
  std::memcpy(&result, &value, sizeof result);
  return result;
}

#if defined(__clang__)
#define F020_NOINLINE __attribute__((noinline))
#else
#define F020_NOINLINE
#endif
static F020_NOINLINE float f020_guard_mul(float a, float b) {
  volatile float x = a, y = b;
  volatile float z = x * y;
  return z;
}
static F020_NOINLINE float f020_guard_add(float a, float b) {
  volatile float x = a, y = b;
  volatile float z = x + y;
  return z;
}
struct F020CanaryEvidence {
  uint32_t scaled;
  uint32_t tie_even_low;
  uint32_t tie_even_high;
  uint32_t separate_underflow;
  bool negative_floor;
};
static inline bool f020_canaries_supported(const F020CanaryEvidence &e) {
  return e.scaled == 0x00000020u && e.tie_even_low == 0x3f800000u &&
      e.tie_even_high == 0x3f800002u && e.separate_underflow == 0x00000001u &&
      e.negative_floor;
}
static inline F020CanaryEvidence f020_collect_canaries() {
  const float half_ulp = f020_guard_float(0x33800000u);
  const float power = f020_guard_float(0x1a000000u); // 2^-75
  volatile float negative_tiny = f020_guard_float(0x80000020u);
  return {f020_guard_bits(f020_guard_mul(f020_guard_float(1u), 32.0f)),
          f020_guard_bits(f020_guard_add(1.0f, half_ulp)),
          f020_guard_bits(f020_guard_add(f020_guard_float(0x3f800001u), half_ulp)),
          f020_guard_bits(f020_guard_add(f020_guard_mul(power, power),
                                        f020_guard_float(1u))),
          std::floor(negative_tiny) == -1.0f};
}
static inline bool f020_check_cpu_arithmetic(uint64_t &fpcr) {
  static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559 &&
                std::numeric_limits<float>::digits == 24 &&
                std::numeric_limits<float>::min_exponent == -125 &&
                std::numeric_limits<float>::max_exponent == 128,
                "F020 requires IEEE binary32 float");
#if defined(__aarch64__) || defined(__arm64__)
  asm volatile("mrs %0, fpcr" : "=r"(fpcr));
  if (!f020_cpu_state_supported(fpcr, std::fegetround(), true)) return false;
  if (!f020_canaries_supported(f020_collect_canaries())) return false;
  uint64_t after;
  asm volatile("mrs %0, fpcr" : "=r"(after));
  return after == fpcr && f020_cpu_state_supported(after, std::fegetround(), true);
#else
  fpcr = 0;
  return false;
#endif
}
#undef F020_NOINLINE
