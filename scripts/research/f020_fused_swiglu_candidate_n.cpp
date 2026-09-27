// Candidate N exact MLX-C graph harness. This is intentionally the only
// source in this component that includes MLX-C.
#include <cmath>
#include <cstdio>
#include "mlx/c/mlx.h"

static int exact_graph(float gate, float up, float *out) {
  int shape[1] = {1};
  mlx_array gate_a = mlx_array_new_data(&gate, shape, 1, MLX_FLOAT32);
  mlx_array up_a = mlx_array_new_data(&up, shape, 1, MLX_FLOAT32);
  mlx_array ten = mlx_array_new_float32(10.0f);
  mlx_array neg_ten = mlx_array_new_float32(-10.0f);
  mlx_array g = mlx_array_new();
  mlx_array s = mlx_array_new();
  mlx_array silu = mlx_array_new();
  mlx_array clipped = mlx_array_new();
  mlx_array h = mlx_array_new();
  mlx_device device = mlx_device_new_type(MLX_GPU, 0);
  mlx_stream stream = mlx_stream_new_device(device);
  int rc = 0;
  rc |= mlx_minimum(&g, gate_a, ten, stream);
  rc |= mlx_sigmoid(&s, g, stream);
  rc |= mlx_multiply(&silu, g, s, stream);
  rc |= mlx_clip(&clipped, up_a, neg_ten, ten, stream);
  rc |= mlx_multiply(&h, silu, clipped, stream);
  rc |= mlx_array_eval(h);
  rc |= mlx_synchronize(stream);
  if (!rc) *out = *mlx_array_data_float32(h);
  mlx_array_free(h); mlx_array_free(clipped); mlx_array_free(silu);
  mlx_array_free(s); mlx_array_free(g); mlx_array_free(neg_ten);
  mlx_array_free(ten); mlx_array_free(up_a); mlx_array_free(gate_a);
  mlx_stream_free(stream);
  mlx_device_free(device);
  return rc;
}

int main() {
  float out = 0.0f;
  if (exact_graph(0.0f, 1.0f, &out) != 0 || !std::isfinite(out)) return 2;
  std::puts("CANDIDATE_N_COMPILE_SELFTEST_PASS");
  return 0;
}
