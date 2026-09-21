// Public-safe Feature 017 MLX C API qualification probe.
//
// Build on an Apple host with the pinned native installation, for example:
// clang++ -std=c++17 scripts/research/f017_mlx_c_qualification.cpp \
//   -I/opt/homebrew/Cellar/mlx-c/0.6.0_2/include -L/opt/homebrew/lib \
//   -Wl,-rpath,/opt/homebrew/lib -lmlxc -lmlx -o /tmp/f017-mlx-c-qualification
// /tmp/f017-mlx-c-qualification

#include <mlx/c/mlx.h>

#include <cstdio>
#include <cstdlib>

struct OwnershipState {
  int destructor_calls = 0;
};

void record_destructor(void* payload) {
  static_cast<OwnershipState*>(payload)->destructor_calls += 1;
}

int main() {
  bool metal_available = false;
  if (mlx_metal_is_available(&metal_available) != 0) {
    return 2;
  }

  mlx_device gpu = mlx_device_new_type(MLX_GPU, 0);
  bool gpu_available = false;
  if (mlx_device_is_available(&gpu_available, gpu) != 0) {
    mlx_device_free(gpu);
    return 3;
  }
  std::printf("metal_available=%d gpu_available=%d\n",
              metal_available ? 1 : 0,
              gpu_available ? 1 : 0);
  mlx_device_free(gpu);

  float* source = nullptr;
  if (posix_memalign(reinterpret_cast<void**>(&source), 4096,
                     4 * sizeof(float)) != 0) {
    return 4;
  }
  source[0] = 1.0f;
  source[1] = 2.0f;
  source[2] = 3.0f;
  source[3] = 4.0f;

  OwnershipState ownership;
  int shape[1] = {4};
  mlx_array array = mlx_array_new_data_managed_payload(
      source, shape, 1, MLX_FLOAT32, &ownership, record_destructor);
  mlx_stream stream = mlx_default_cpu_stream_new();
  if (!array.ctx || mlx_array_eval(array) != 0 || mlx_synchronize(stream) != 0) {
    if (array.ctx) {
      mlx_array_free(array);
    }
    mlx_stream_free(stream);
    std::free(source);
    return 5;
  }

  const float* result = mlx_array_data_float32(array);
  const bool valid_result = result != nullptr;
  const bool same_pointer = result == source;
  const float first_value = result ? result[0] : -1.0f;
  const int array_status = mlx_array_free(array);
  const int stream_status = mlx_stream_free(stream);
  std::printf(
      "cpu_source=%p cpu_result=%p same_pointer=%d first=%.1f "
      "array_free=%d stream_free=%d destructor_calls=%d\n",
      static_cast<void*>(source), static_cast<const void*>(result),
      same_pointer ? 1 : 0, first_value, array_status,
      stream_status, ownership.destructor_calls);
  std::free(source);

  return valid_result && same_pointer && array_status == 0 && stream_status == 0 &&
                 ownership.destructor_calls == 1
             ? 0
             : 6;
}
