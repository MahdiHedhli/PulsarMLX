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
#include <map>
#include <iomanip>
#include <limits.h>
#include <string>
#include <vector>
#include <sys/stat.h>
#include <unistd.h>

#include <CommonCrypto/CommonDigest.h>

#include "mlx/c/mlx.h"
#include "f020_candidate_b_table_v1.h"

#ifndef F020_EXPECTED_MANIFEST_SHA256
#error "F020_EXPECTED_MANIFEST_SHA256 must be bound by the admitted driver"
#endif
#ifndef F020_EXPECTED_PUBLIC_COMMIT
#error "F020_EXPECTED_PUBLIC_COMMIT must be bound by the admitted driver"
#endif

#include "f020_fused_swiglu_candidate_b_v2.h"
#include "f020_fused_swiglu_cpu_guard_v2_4.h"

struct Witness {
  uint32_t gate_bits = 0;
  uint32_t n_bits = 0;
  uint32_t b_bits = 0;
  uint64_t delta_bits = 0;
};

struct SweepStats {
  uint64_t total_evaluated = 0;
  uint64_t batch_count = 0;
  uint64_t range_counts[2] = {0, 0};
  uint64_t anomaly_count = 0;
  uint32_t anomaly_gate_bits = 0;
  uint32_t anomaly_n_bits = 0;
  uint32_t anomaly_b_bits = 0;
  std::string anomaly_reason;
  uint64_t cpu_fpcr = 0;
  uint64_t cpu_guard_checks = 0;
};

static bool check_cpu(SweepStats &stats, uint32_t gate_bits) {
  stats.cpu_guard_checks++;
  if (f020_check_cpu_arithmetic(stats.cpu_fpcr)) return true;
  stats.anomaly_count++;
  stats.anomaly_reason = "unsupported host RN32 gradual-underflow state/canaries";
  stats.anomaly_gate_bits = gate_bits;
  return false;
}

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

static bool sha256_file(const std::string &path, std::string &hex) {
  FILE *file = std::fopen(path.c_str(), "rb");
  if (file == nullptr) return false;
  CC_SHA256_CTX ctx;
  CC_SHA256_Init(&ctx);
  unsigned char buffer[1 << 16];
  size_t n = 0;
  while ((n = std::fread(buffer, 1, sizeof buffer, file)) != 0) {
    if (CC_SHA256_Update(&ctx, buffer, static_cast<CC_LONG>(n)) != 1) {
      std::fclose(file); return false;
    }
  }
  const bool ok = std::ferror(file) == 0;
  std::fclose(file);
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  if (!ok || CC_SHA256_Final(digest, &ctx) != 1) return false;
  static const char digits[] = "0123456789abcdef";
  hex.clear(); hex.reserve(CC_SHA256_DIGEST_LENGTH * 2);
  for (unsigned char byte : digest) { hex.push_back(digits[byte >> 4]); hex.push_back(digits[byte & 15]); }
  return true;
}

static bool read_capability(const std::string &path, std::map<std::string, std::string> &cap) {
  std::ifstream in(path);
  if (!in) return false;
  std::string line;
  while (std::getline(in, line)) {
    const auto split = line.find('=');
    if (split == std::string::npos || split == 0) return false;
    const std::string key = line.substr(0, split);
    if (cap.count(key) != 0) return false;
    cap.emplace(key, line.substr(split + 1));
  }
  return in.eof() && cap.size() == 15;
}

static bool real_path(const std::string &path, std::string &out) {
  char resolved[PATH_MAX];
  if (realpath(path.c_str(), resolved) == nullptr) return false;
  out = resolved; return true;
}

static bool capability_value(const std::map<std::string, std::string> &cap,
                             const char *key, const char *expected = nullptr) {
  const auto it = cap.find(key);
  if (it == cap.end() || it->second.empty()) return false;
  return expected == nullptr || it->second == expected;
}

static bool validate_capability(int argc, char **argv) {
  std::string capability;
  for (int i = 1; i + 1 < argc; ++i)
    if (std::strcmp(argv[i], "--capability") == 0) capability = argv[i + 1];
  if (capability.empty()) return false;
  struct stat cap_stat{};
  if (lstat(capability.c_str(), &cap_stat) != 0 || !S_ISREG(cap_stat.st_mode) ||
      cap_stat.st_uid != geteuid() || (cap_stat.st_mode & 0077) != 0) return false;
  std::map<std::string, std::string> cap;
  if (!read_capability(capability, cap)) return false;
  if (!capability_value(cap, "schema", "pulsarmlx.f020.native-bridge-capability/1.0.0") ||
      !capability_value(cap, "preflight", "PASS") ||
      !capability_value(cap, "public_commit", F020_EXPECTED_PUBLIC_COMMIT) ||
      !capability_value(cap, "manifest_sha256", F020_EXPECTED_MANIFEST_SHA256) ||
      !capability_value(cap, "candidate_b_flags", "-fno-fast-math;-ffp-contract=off") ||
      !capability_value(cap, "runtime_identity_sha256") ||
      !capability_value(cap, "compiler_identity_sha256") ||
      !capability_value(cap, "disassembly_sha256") ||
      !capability_value(cap, "execution_root") ||
      !capability_value(cap, "capability_path", capability.c_str())) return false;
  std::string actual;
  if (!real_path(capability, actual) || actual != capability) return false;
  std::string root = cap.at("execution_root");
  std::string cap_parent = actual.substr(0, actual.find_last_of('/'));
  if (cap_parent != root) return false;
  if (!capability_value(cap, "manifest_path") || !sha256_file(cap.at("manifest_path"), actual) ||
      actual != cap.at("manifest_sha256")) return false;
  if (!capability_value(cap, "source_path") || !sha256_file(cap.at("source_path"), actual) ||
      actual != cap.at("bridge_source_sha256")) return false;
  if (!capability_value(cap, "bridge_path") || !real_path(argv[0], actual) || actual != cap.at("bridge_path")) return false;
  if (!sha256_file(actual, actual) || actual != cap.at("bridge_binary_sha256")) return false;
  std::string bridge_real;
  if (!real_path(cap.at("bridge_path"), bridge_real) ||
      bridge_real.substr(0, bridge_real.find_last_of('/')) != root) return false;
  if (std::remove(capability.c_str()) != 0) return false;
  return capability_value(cap, "bridge_source_sha256") && capability_value(cap, "bridge_binary_sha256");
}

struct ControlEvidence {
  uint32_t gate_bits = 0;
  uint32_t up_bits = 0;
  uint32_t n_bits = 0;
  uint32_t b_bits = 0;
  uint64_t delta_bits = 0;
};

static int run_batch(const std::vector<uint32_t> &input_bits,
                     mlx_stream stream, Witness &worst, double &max_delta, SweepStats &stats,
                     uint64_t range_index, const std::vector<float> *controlled_up = nullptr,
                     std::vector<ControlEvidence> *evidence = nullptr) {
  if (!check_cpu(stats, input_bits.empty() ? 0 : input_bits.front())) return 79;
  const int shape[1] = {static_cast<int>(input_bits.size())};
  std::vector<float> gate(input_bits.size());
  std::vector<float> up(input_bits.size(), 1.0f);
  if (controlled_up != nullptr) {
    if (controlled_up->size() != input_bits.size()) return 75;
    up = *controlled_up;
  }
  std::vector<float> b(input_bits.size());
  for (size_t i = 0; i < input_bits.size(); ++i)
    std::memcpy(&gate[i], &input_bits[i], sizeof gate[i]);
  for (size_t i = 0; i < input_bits.size(); ++i) b[i] = candidate_b(gate[i], up[i]);
  if (!check_cpu(stats, input_bits.empty() ? 0 : input_bits.front())) return 79;

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
  size_t processed = 0;
  rc |= mlx_minimum(&g, gate_a, ten, stream);
  rc |= mlx_sigmoid(&s, g, stream);
  rc |= mlx_multiply(&silu, g, s, stream);
  rc |= mlx_clip(&clipped, up_a, neg_ten, ten, stream);
  rc |= mlx_multiply(&h, silu, clipped, stream);
  rc |= mlx_array_eval(h);
  rc |= mlx_synchronize(stream);
  if (!rc && !check_cpu(stats, input_bits.empty() ? 0 : input_bits.front())) rc = 79;
  if (!rc) {
    if (mlx_array_dtype(h) != MLX_FLOAT32 || mlx_array_size(h) != input_bits.size() ||
        mlx_array_data_float32(h) == nullptr) {
      stats.anomaly_count++;
      stats.anomaly_reason = "malformed Candidate N output array";
      stats.anomaly_gate_bits = input_bits.empty() ? 0 : input_bits[0];
      rc = 75;
    }
  }
  if (!rc) {
    const float *n = mlx_array_data_float32(h);
    for (size_t i = 0; i < input_bits.size(); ++i) {
      if (!std::isfinite(n[i]) || !std::isfinite(b[i])) {
        stats.anomaly_count++;
        stats.anomaly_reason = "nonfinite Candidate N or B output";
        stats.anomaly_gate_bits = input_bits[i];
        stats.anomaly_n_bits = bits(n[i]);
        stats.anomaly_b_bits = bits(b[i]);
        rc = 75;
        break;
      }
      const double d = upward_abs_delta(n[i], b[i]);
      if (!std::isfinite(d) || std::isnan(d)) {
        stats.anomaly_count++;
        stats.anomaly_reason = "nonfinite delta";
        stats.anomaly_gate_bits = input_bits[i];
        stats.anomaly_n_bits = bits(n[i]);
        stats.anomaly_b_bits = bits(b[i]);
        rc = 75;
        break;
      }
      processed++;
      if (d >= max_delta) {
        max_delta = d;
        worst.gate_bits = input_bits[i];
        worst.n_bits = bits(n[i]);
        worst.b_bits = bits(b[i]);
        worst.delta_bits = bits(d);
      }
      if (evidence != nullptr) evidence->push_back({input_bits[i], bits(up[i]), bits(n[i]), bits(b[i]), bits(d)});
    }
  }
  mlx_array_free(h); mlx_array_free(clipped); mlx_array_free(silu);
  mlx_array_free(s); mlx_array_free(g); mlx_array_free(neg_ten);
  mlx_array_free(ten); mlx_array_free(up_a); mlx_array_free(gate_a);
  stats.total_evaluated += processed;
  stats.batch_count++;
  stats.range_counts[range_index] += processed;
  return rc;
}

static bool write_report(const std::string &path, const SweepStats &stats,
                         const Witness &worst, double max_delta, int rc) {
  if (path.empty()) return false;
  std::ofstream out(path);
  if (!out) return false;
  const uint64_t expected_positive = 0x41800000ULL + 1ULL;
  const uint64_t expected_negative = 0xc1800000ULL - 0x80000000ULL + 1ULL;
  const bool exhaustive = rc == 0 && stats.anomaly_count == 0 &&
      stats.total_evaluated == 2197815298ULL && stats.range_counts[0] == expected_positive &&
      stats.range_counts[1] == expected_negative && stats.batch_count > 0;
  out << std::dec << "{\"schema\":\"pulsarmlx.f020.native-bridge-v2-result/1.2.0\","
      << "\"candidate_observations\":" << (rc == 0 ? 1 : 0) << ","
      << "\"gate_count_exhaustive\":" << (exhaustive ? "true" : "false") << ","
      << "\"total_evaluated\":" << stats.total_evaluated << ","
      << "\"batch_count\":" << stats.batch_count << ","
      << "\"range_counts\":{"
      << "\"positive\":" << stats.range_counts[0] << ",\"negative\":" << stats.range_counts[1] << "},"
      << "\"range_endpoints\":{"
      << "\"positive_start\":\"0x00000000\",\"positive_end\":\"0x41800000\","
      << "\"negative_start\":\"0x80000000\",\"negative_end\":\"0xc1800000\"},"
      << "\"cpu_guard_checks\":" << stats.cpu_guard_checks << ",\"cpu_fpcr\":" << stats.cpu_fpcr << ","
      << "\"anomaly_count\":" << stats.anomaly_count << ",\"anomaly_reason\":\"" << stats.anomaly_reason << "\","
      << "\"anomaly_gate_f32_bits\":\"0x" << std::hex << std::setw(8) << std::setfill('0') << stats.anomaly_gate_bits << "\","
      << "\"anomaly_candidate_n_output_f32_bits\":\"0x" << std::setw(8) << stats.anomaly_n_bits << "\","
      << "\"anomaly_candidate_b_output_f32_bits\":\"0x" << std::setw(8) << stats.anomaly_b_bits << "\","
      << "\"input_gate_f32_bits\":\"0x" << std::hex << std::setw(8) << std::setfill('0') << worst.gate_bits << "\","
      << "\"candidate_n_output_f32_bits\":\"0x" << std::setw(8) << worst.n_bits << "\","
      << "\"candidate_b_output_f32_bits\":\"0x" << std::setw(8) << worst.b_bits << "\","
      << "\"upward_rounded_abs_delta_bits\":\"0x" << std::setw(16) << worst.delta_bits << "\","
      << "\"max_delta_f64_bits\":\"0x" << std::setw(16) << bits(max_delta) << "\"}\n";
  return true;
}

static int execute_sweep_v2(int argc, char **argv) {
  if (!validate_capability(argc, argv)) return 78;
  constexpr uint32_t batch = 1048576u;
  Witness worst{};
  SweepStats stats{};
  double max_delta = 0.0;
  if (!check_cpu(stats, 0)) {
    if (!write_report(report_path(argc, argv), stats, worst, max_delta, 79)) return 64;
    return 79;
  }
  mlx_device device = mlx_device_new_type(MLX_GPU, 0);
  mlx_stream stream = mlx_stream_new_device(device);
  int rc = 0;
  const uint32_t ranges[][2] = {{0x00000000u, 0x41800000u}, {0x80000000u, 0xc1800000u}};
  for (const auto &range : ranges) {
    for (uint64_t first = range[0]; first <= range[1]; first += batch) {
      const uint64_t last = std::min<uint64_t>(range[1], first + batch - 1);
      std::vector<uint32_t> chunk;
      chunk.reserve(static_cast<size_t>(last - first + 1));
      for (uint64_t u = first; u <= last; ++u) chunk.push_back(static_cast<uint32_t>(u));
      rc |= run_batch(chunk, stream, worst, max_delta, stats, range[0] == 0 ? 0 : 1);
      if (rc) break;
      if (last == range[1]) break;
    }
    if (rc) break;
  }
  mlx_stream_free(stream); mlx_device_free(device);
  const std::string path = report_path(argc, argv);
  if (!write_report(path, stats, worst, max_delta, rc)) return 64;
  if (rc) return rc;
  const bool exhaustive = stats.total_evaluated == 2197815298ULL && stats.anomaly_count == 0;
  return exhaustive ? 0 : 76;
}

static int execute_structured_v2(int argc, char **argv) {
  if (!validate_capability(argc, argv)) return 78;
  const float values[] = {-16.0f, -10.0f, -0.0f, 0.0f, 10.0f, 16.0f};
  const float ups[] = {-16.0f, -10.0f, -0.0f, 0.0f, 1.0f, 10.0f, 16.0f};
  std::vector<uint32_t> gates;
  std::vector<float> controls;
  for (float gate : values) for (float up : ups) {
    gates.push_back(bits(gate)); controls.push_back(up);
  }
  Witness worst{}; SweepStats stats{}; double max_delta = 0.0;
  std::vector<ControlEvidence> evidence;
  int rc = 79;
  if (check_cpu(stats, gates.empty() ? 0 : gates.front())) {
    mlx_device device = mlx_device_new_type(MLX_GPU, 0);
    mlx_stream stream = mlx_stream_new_device(device);
    rc = run_batch(gates, stream, worst, max_delta, stats, 0, &controls, &evidence);
    mlx_stream_free(stream); mlx_device_free(device);
  }
  const std::string path = report_path(argc, argv);
  if (path.empty()) return 64;
  std::ofstream out(path);
  if (!out) return 73;
  out << "{\"schema\":\"pulsarmlx.f020.native-bridge-v2-3-structured/1.1.0\","
      << "\"structured\":true,\"total_evaluated\":" << stats.total_evaluated
      << ",\"cpu_guard_checks\":" << stats.cpu_guard_checks << ",\"cpu_fpcr\":" << stats.cpu_fpcr
      << ",\"anomaly_count\":" << stats.anomaly_count
      << ",\"anomaly_reason\":\"" << stats.anomaly_reason << "\""
      << ",\"anomaly_gate_f32_bits\":\"0x" << std::hex << std::setw(8) << std::setfill('0') << stats.anomaly_gate_bits
      << "\",\"anomaly_candidate_n_output_f32_bits\":\"0x" << std::setw(8) << stats.anomaly_n_bits
      << "\",\"anomaly_candidate_b_output_f32_bits\":\"0x" << std::setw(8) << stats.anomaly_b_bits
      << "\",\"controls\":[";
  for (size_t i = 0; i < evidence.size(); ++i) {
    if (i) out << ',';
    out << "{\"gate_f32_bits\":\"0x" << std::hex << std::setw(8) << std::setfill('0') << evidence[i].gate_bits
        << "\",\"up_f32_bits\":\"0x" << std::setw(8) << evidence[i].up_bits
        << "\",\"candidate_n_output_f32_bits\":\"0x" << std::setw(8) << evidence[i].n_bits
        << "\",\"candidate_b_output_f32_bits\":\"0x" << std::setw(8) << evidence[i].b_bits
        << "\",\"upward_rounded_abs_delta_bits\":\"0x" << std::setw(16) << evidence[i].delta_bits << "\"}";
  }
  out << "]}\n";
  return rc;
}

int main(int argc, char **argv) {
  bool structured = false;
  for (int i = 1; i < argc; ++i) structured |= std::strcmp(argv[i], "--structured-up-controls") == 0;
  if (structured) return execute_structured_v2(argc, argv);
  if (execution_authorized(argc, argv)) return execute_sweep_v2(argc, argv);
  std::puts("F020_NATIVE_BRIDGE_V2_STATIC_ONLY");
  return 0;
}
