/*
 * F020 Slice 2B -- ABI layout assertions for the hand-written Rust FFI.
 *
 * Compiled by build.rs against the pinned MLX-C headers (0726ca92 + the four
 * hash-verified patches). The static assertions fail the build if the C-side
 * layout or an enumerator value differs from what src/bin/qualify/ffi.rs
 * declares; pulsar_f020_abi_values() reports the same numbers at run time so
 * the child compares them against its own #[repr(C)] declarations before its
 * first MLX-C call. No MLX-C function is referenced here.
 */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "mlx/c/mlx.h"

_Static_assert(sizeof(mlx_array) == sizeof(void*), "mlx_array is one pointer");
_Static_assert(offsetof(mlx_array, ctx) == 0, "mlx_array.ctx at 0");
_Static_assert(sizeof(mlx_device) == sizeof(void*), "mlx_device is one pointer");
_Static_assert(sizeof(mlx_stream) == sizeof(void*), "mlx_stream is one pointer");
_Static_assert(sizeof(mlx_string) == sizeof(void*), "mlx_string is one pointer");
_Static_assert(sizeof(mlx_device_info) == sizeof(void*), "mlx_device_info is one pointer");
_Static_assert(sizeof(mlx_dtype) == 4, "mlx_dtype is a 4-byte enum");
_Static_assert(sizeof(mlx_device_type) == 4, "mlx_device_type is a 4-byte enum");
_Static_assert(MLX_CPU == 0 && MLX_GPU == 1, "device type enumerators");
_Static_assert(MLX_BOOL == 0, "MLX_BOOL");
_Static_assert(MLX_UINT16 == 2, "MLX_UINT16");
_Static_assert(MLX_UINT32 == 3, "MLX_UINT32");
_Static_assert(MLX_FLOAT16 == 9, "MLX_FLOAT16");
_Static_assert(MLX_FLOAT32 == 10, "MLX_FLOAT32");
_Static_assert(MLX_BFLOAT16 == 12, "MLX_BFLOAT16");
_Static_assert(sizeof(bool) == 1, "C bool is one byte");
_Static_assert(sizeof(mlx_optional_int) == 8, "mlx_optional_int size");
_Static_assert(offsetof(mlx_optional_int, value) == 0, "mlx_optional_int.value");
_Static_assert(offsetof(mlx_optional_int, has_value) == 4, "mlx_optional_int.has_value");
_Static_assert(sizeof(mlx_optional_dtype) == 8, "mlx_optional_dtype size");
_Static_assert(offsetof(mlx_optional_dtype, value) == 0, "mlx_optional_dtype.value");
_Static_assert(offsetof(mlx_optional_dtype, has_value) == 4, "mlx_optional_dtype.has_value");
_Static_assert(sizeof(int) == 4, "int is 4 bytes");
_Static_assert(sizeof(size_t) == 8, "size_t is 8 bytes");

/* Order is fixed and mirrored by EXPECTED_ABI in src/bin/qualify/ffi.rs. */
int pulsar_f020_abi_values(long long* out, int capacity) {
  const long long values[] = {
      (long long)sizeof(mlx_array),
      (long long)sizeof(mlx_device),
      (long long)sizeof(mlx_stream),
      (long long)sizeof(mlx_string),
      (long long)sizeof(mlx_device_info),
      (long long)sizeof(mlx_dtype),
      (long long)sizeof(mlx_device_type),
      (long long)MLX_CPU,
      (long long)MLX_GPU,
      (long long)MLX_UINT16,
      (long long)MLX_UINT32,
      (long long)MLX_FLOAT16,
      (long long)MLX_FLOAT32,
      (long long)MLX_BFLOAT16,
      (long long)sizeof(mlx_optional_int),
      (long long)offsetof(mlx_optional_int, has_value),
      (long long)sizeof(mlx_optional_dtype),
      (long long)offsetof(mlx_optional_dtype, has_value),
  };
  const int n = (int)(sizeof(values) / sizeof(values[0]));
  if (out == NULL || capacity < n) {
    return -n;
  }
  for (int i = 0; i < n; ++i) {
    out[i] = values[i];
  }
  return n;
}
