// Causal guard tests: synthetic state/evidence mutations, no state writes.
#include <cassert>
#include <cstdio>
#include <initializer_list>
#include "../f020_fused_swiglu_cpu_guard_v2_4.h"
int main() {
  assert(f020_cpu_state_supported(0, FE_TONEAREST, true));
  for (uint64_t flag : {1ULL, 2ULL, 1ULL << 22, 1ULL << 23, 1ULL << 24, 1ULL << 8, 1ULL << 9,
                        1ULL << 10, 1ULL << 11, 1ULL << 12, 1ULL << 15})
    assert(!f020_cpu_state_supported(flag, FE_TONEAREST, true));
  assert(!f020_cpu_state_supported(0, FE_UPWARD, true));
  assert(!f020_cpu_state_supported(0, FE_DOWNWARD, true));
  assert(!f020_cpu_state_supported(0, FE_TOWARDZERO, true));
  assert(!f020_cpu_state_supported(0, FE_TONEAREST, false));
  F020CanaryEvidence good{32u, 0x3f800000u, 0x3f800002u, 1u, true};
  assert(f020_canaries_supported(good));
  for (int field = 0; field < 5; ++field) {
    auto bad = good;
    if (field == 0) bad.scaled = 0;
    if (field == 1) bad.tie_even_low++;
    if (field == 2) bad.tie_even_high--;
    if (field == 3) bad.separate_underflow = 2;
    if (field == 4) bad.negative_floor = false;
    assert(!f020_canaries_supported(bad));
  }
  uint64_t fpcr = 0;
  assert(f020_check_cpu_arithmetic(fpcr)); // abstract canaries only
  std::printf("F020_CPU_GUARD_UNIT_PASS fpcr=0x%016llx\n",
              static_cast<unsigned long long>(fpcr));
}
