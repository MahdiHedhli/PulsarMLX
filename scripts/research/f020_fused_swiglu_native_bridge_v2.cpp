// F020 v2 batched N-vs-B bridge. It is execution-gated by design: compiling
// this translation unit and inspecting it never calls MLX-C or emits outputs.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <string>
#include <vector>

#include "mlx/c/mlx.h"
#include "f020_candidate_b_table_v1.h"

#pragma clang fp contract(off)
static inline float candidate_b(float gate, float up) {
  float g = gate < 10.0f ? gate : 10.0f;
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

struct Witness {
  uint32_t gate_bits = 0;
  uint32_t n_bits = 0;
  uint32_t b_bits = 0;
  uint64_t delta_bits = 0;
};

static inline uint32_t bits(float x) { uint32_t u; std::memcpy(&u, &x, sizeof u); return u; }
static inline double f32_to_f64(float x) { return static_cast<double>(x); }

// The reducer is deliberately upward rounded before max. Binary32 values are
// exactly representable in binary64; nextafter makes the stored bound strict
// upward even on implementations where subtraction is not exact.
static inline double upward_abs_delta(float n, float b) {
  const double d = std::fabs(f32_to_f64(n) - f32_to_f64(b));
  return std::nextafter(d, std::numeric_limits<double>::infinity());
}

static bool execution_authorized(int argc, char **argv) {
  for (int i = 1; i < argc; ++i) if (std::strcmp(argv[i], "--execute-sweep") == 0) return true;
  return false;
}

// This is the only entry point that may eventually call the exact MLX-C graph.
// The v2 qualification driver must perform manifest/source/runtime guards
// before calling it. No invocation occurs in the default static/self-test mode.
static std::string report_path(int argc, char **argv) {
  for (int i = 1; i + 1 < argc; ++i) {
    if (std::strcmp(argv[i], "--report") == 0) return argv[i + 1];
  }
  return "";
}

static uint64_t bits(double x) { uint64_t u; std::memcpy(&u, &x, sizeof u); return u; }

static int run_batch(const std::vector<uint32_t> &input_bits,
                     mlx_stream stream, Witness &worst, double &max_delta) {
  const int shape[1] = {static_cast<int>(input_bits.size())};
  std::vector<float> gate(input_bits.size());
  std::vector<float> up(input_bits.size(), 1.0f);
  std::vector<float> b(input_bits.size());
  for (size_t i = 0; i < input_bits.size(); ++i)
    std::memcpy(&gate[i], &input_bits[i], sizeof gate[i]);
  for (size_t i = 0; i < input_bits.size(); ++i) b[i] = candidate_b(gate[i], up[i]);

  mlx_array gate_a = mlx_array_new_data(gate.data(), shape, 1, MLX_FLOAT32);
  mlx_array up_a = mlx_array_new_data(up.data(), shape, 1, MLX_FLOAT32);
  mlx_array ten = mlx_array_new_float32(10.0f);
  mlx_array neg_ten = mlx_array_new_float32(-10.0f);
  mlx_array g = mlx_array_new();
  mlx_array s = mlx_array_new();
  mlx_array silu = mlx_array_new();
  mlx_array clipped = mlx_array_new();
  mlx_array h = mlx_array_new();
  int rc = 0;
  rc |= mlx_minimum(&g, gate_a, ten, stream);
  rc |= mlx_sigmoid(&s, g, stream);
  rc |= mlx_multiply(&silu, g, s, stream);
  rc |= mlx_clip(&clipped, up_a, neg_ten, ten, stream);
  rc |= mlx_multiply(&h, silu, clipped, stream);
  rc |= mlx_array_eval(h);
  rc |= mlx_synchronize(stream);
  if (!rc) {
    const float *n = mlx_array_data_float32(h);
    for (size_t i = 0; i < input_bits.size(); ++i) {
      const double d = upward_abs_delta(n[i], b[i]);
      if (d >= max_delta) {
        max_delta = d;
        worst.gate_bits = input_bits[i];
        worst.n_bits = bits(n[i]);
        worst.b_bits = bits(b[i]);
        worst.delta_bits = bits(d);
      }
    }
  }
  mlx_array_free(h); mlx_array_free(clipped); mlx_array_free(silu);
  mlx_array_free(s); mlx_array_free(g); mlx_array_free(neg_ten);
  mlx_array_free(ten); mlx_array_free(up_a); mlx_array_free(gate_a);
  return rc;
}

static int execute_sweep_v2(int argc, char **argv) {
  const char *authorized = std::getenv("F020_V2_EXECUTION_AUTHORIZED");
  if (authorized == nullptr || std::strcmp(authorized, "1") != 0) return 78;
  constexpr uint32_t batch = 1048576u;
  mlx_device device = mlx_device_new_type(MLX_GPU, 0);
  mlx_stream stream = mlx_stream_new_device(device);
  Witness worst{};
  double max_delta = 0.0;
  int rc = 0;
  const uint32_t ranges[][2] = {{0x00000000u, 0x41800000u}, {0x80000000u, 0xc1800000u}};
  for (const auto &range : ranges) {
    for (uint64_t first = range[0]; first <= range[1]; first += batch) {
      const uint64_t last = std::min<uint64_t>(range[1], first + batch - 1);
      std::vector<uint32_t> chunk;
      chunk.reserve(static_cast<size_t>(last - first + 1));
      for (uint64_t u = first; u <= last; ++u) chunk.push_back(static_cast<uint32_t>(u));
      rc |= run_batch(chunk, stream, worst, max_delta);
      if (rc) break;
      if (last == range[1]) break;
    }
    if (rc) break;
  }
  mlx_stream_free(stream); mlx_device_free(device);
  if (rc) return rc;
  const std::string path = report_path(argc, argv);
  if (path.empty()) return 64;
  std::ofstream out(path);
  if (!out) return 73;
  out << "{\"schema\":\"pulsarmlx.f020.native-bridge-v2-result/1.0.0\","
      << "\"candidate_observations\":1,\"gate_count_exhaustive\":true,"
      << "\"worst_gate_f32_bits\":\"0x" << std::hex << worst.gate_bits << "\","
      << "\"candidate_n_output_f32_bits\":\"0x" << worst.n_bits << "\","
      << "\"candidate_b_output_f32_bits\":\"0x" << worst.b_bits << "\","
      << "\"upward_delta_f64_bits\":\"0x" << worst.delta_bits << "\"}\n";
  return 0;
}

int main(int argc, char **argv) {
  if (execution_authorized(argc, argv)) return execute_sweep_v2(argc, argv);
  std::puts("F020_NATIVE_BRIDGE_V2_STATIC_ONLY");
  return 0;
}
