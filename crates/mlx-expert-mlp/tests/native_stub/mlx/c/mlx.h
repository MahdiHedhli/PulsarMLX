#pragma once
#include <cstddef>
extern "C" {
struct mlx_array {void *ctx;};struct mlx_device {void *ctx;};struct mlx_stream {void *ctx;};
enum mlx_dtype {MLX_FLOAT32=10};enum mlx_device_type {MLX_CPU=0,MLX_GPU=1};
mlx_device mlx_device_new();mlx_device mlx_device_new_type(mlx_device_type,int);
int mlx_device_free(mlx_device);int mlx_device_get_type(mlx_device_type*,mlx_device);
mlx_stream mlx_stream_new_device(mlx_device);int mlx_stream_get_device(mlx_device*,mlx_stream);
int mlx_stream_free(mlx_stream);int mlx_synchronize(mlx_stream);int mlx_metal_is_available(bool*);
mlx_array mlx_array_new();mlx_array mlx_array_new_data(const void*,const int*,int,mlx_dtype);
mlx_array mlx_array_new_float32(float);int mlx_array_free(mlx_array);int mlx_array_eval(mlx_array);
mlx_dtype mlx_array_dtype(mlx_array);size_t mlx_array_ndim(mlx_array);size_t mlx_array_size(mlx_array);
const int *mlx_array_shape(mlx_array);const float *mlx_array_data_float32(mlx_array);
int mlx_minimum(mlx_array*,mlx_array,mlx_array,mlx_stream);
int mlx_maximum(mlx_array*,mlx_array,mlx_array,mlx_stream);
int mlx_multiply(mlx_array*,mlx_array,mlx_array,mlx_stream);
int mlx_sigmoid(mlx_array*,mlx_array,mlx_stream);
int mlx_clip(mlx_array*,mlx_array,mlx_array,mlx_array,mlx_stream);
}
