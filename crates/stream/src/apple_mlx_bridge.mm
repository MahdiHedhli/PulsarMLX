#include <mlx/c/mlx.h>

#include <climits>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <new>

namespace {

struct OwnershipState {
    uint64_t callback_count = 0;
};

struct MlxContextObject {
    mlx_device device{};
    mlx_stream stream{};
    bool stream_owned = false;
};

struct MlxArrayObject {
    mlx_array array{};
    MlxContextObject *context = nullptr;
    OwnershipState *ownership = nullptr;
};

int set_error(char *buffer, size_t capacity, const char *message) {
    if (buffer != nullptr && capacity > 0) {
        std::snprintf(buffer, capacity, "%s", message);
    }
    return -1;
}

void managed_owner_released(void *payload) {
    auto *ownership = static_cast<OwnershipState *>(payload);
    ownership->callback_count += 1;
}

void restore_default_cpu_context() {
    mlx_device cpu = mlx_device_new_type(MLX_CPU, 0);
    bool available = false;
    if (cpu.ctx != nullptr && mlx_device_is_available(&available, cpu) == 0 &&
        available) {
        mlx_set_default_device(cpu);
        mlx_device_free(cpu);
    }
    mlx_stream cpu_stream = mlx_default_cpu_stream_new();
    if (cpu_stream.ctx != nullptr) {
        mlx_set_default_stream(cpu_stream);
    }
}

void destroy_context(MlxContextObject *context) {
    if (context == nullptr) {
        return;
    }
    restore_default_cpu_context();
    if (context->stream_owned && context->stream.ctx != nullptr) {
        mlx_stream_free(context->stream);
    }
    if (context->device.ctx != nullptr) {
        mlx_device_free(context->device);
    }
    delete context;
}

int destroy_array(MlxArrayObject *array, uint64_t *callback_count) {
    if (array == nullptr) {
        return -1;
    }
    int status = mlx_array_free(array->array);
    if (callback_count != nullptr) {
        *callback_count = array->ownership == nullptr
                              ? 0
                              : array->ownership->callback_count;
    }
    delete array->ownership;
    delete array;
    return status;
}

}  // namespace

extern "C" {

typedef void PulsarMlxContext;
typedef void PulsarMlxArray;

int pulsar_mlx_context_create(
    int device_type,
    int stream_mode,
    PulsarMlxContext **out_context,
    char *error_buffer,
    size_t error_capacity) {
    if (out_context == nullptr ||
        (device_type != MLX_CPU && device_type != MLX_GPU) ||
        (stream_mode != 0 && stream_mode != 1)) {
        return set_error(error_buffer, error_capacity,
                         "invalid MLX context arguments");
    }
    auto *context = new (std::nothrow) MlxContextObject();
    if (context == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "MLX context allocation failed");
    }
    context->device = mlx_device_new_type(
        static_cast<mlx_device_type>(device_type), 0);
    bool available = false;
    if (context->device.ctx == nullptr ||
        mlx_device_is_available(&available, context->device) != 0 ||
        !available || mlx_set_default_device(context->device) != 0) {
        destroy_context(context);
        return set_error(error_buffer, error_capacity,
                         "requested MLX device unavailable");
    }

    context->stream = mlx_stream_new();
    if (stream_mode == 1) {
        context->stream = mlx_stream_new_device(context->device);
        context->stream_owned = true;
        if (context->stream.ctx == nullptr ||
            mlx_set_default_stream(context->stream) != 0) {
            destroy_context(context);
            return set_error(error_buffer, error_capacity,
                             "owned MLX stream creation failed");
        }
    } else if (mlx_get_default_stream(&context->stream, context->device) != 0 ||
               context->stream.ctx == nullptr) {
        destroy_context(context);
        return set_error(error_buffer, error_capacity,
                         "default MLX stream lookup failed");
    }
    *out_context = reinterpret_cast<PulsarMlxContext *>(context);
    return 0;
}

int pulsar_mlx_context_stream_owned(PulsarMlxContext *raw_context) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    return context != nullptr && context->stream_owned ? 1 : 0;
}

void pulsar_mlx_context_destroy(PulsarMlxContext *raw_context) {
    destroy_context(reinterpret_cast<MlxContextObject *>(raw_context));
}

int pulsar_mlx_import_f32(
    PulsarMlxContext *raw_context,
    float *data,
    size_t count,
    PulsarMlxArray **out_array,
    char *error_buffer,
    size_t error_capacity) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    if (context == nullptr || data == nullptr || count == 0 ||
        count > static_cast<size_t>(INT_MAX) || out_array == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "invalid MLX f32 import arguments");
    }
    auto *ownership = new (std::nothrow) OwnershipState();
    auto *array = new (std::nothrow) MlxArrayObject();
    if (ownership == nullptr || array == nullptr) {
        delete ownership;
        delete array;
        return set_error(error_buffer, error_capacity,
                         "MLX managed-array allocation failed");
    }
    int shape[1] = {static_cast<int>(count)};
    array->ownership = ownership;
    array->context = context;
    array->array = mlx_array_new_data_managed_payload(
        data, shape, 1, MLX_FLOAT32, ownership, managed_owner_released);
    if (array->array.ctx == nullptr) {
        delete ownership;
        delete array;
        return set_error(error_buffer, error_capacity,
                         "MLX managed-array construction failed");
    }
    *out_array = reinterpret_cast<PulsarMlxArray *>(array);
    return 0;
}

int pulsar_mlx_array_eval_sync(
    PulsarMlxContext *raw_context,
    PulsarMlxArray *raw_array,
    char *error_buffer,
    size_t error_capacity) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    auto *array = reinterpret_cast<MlxArrayObject *>(raw_array);
    if (context == nullptr || array == nullptr || array->context != context) {
        return set_error(error_buffer, error_capacity,
                         "MLX array/context ownership mismatch");
    }
    if (mlx_array_eval(array->array) != 0) {
        return set_error(error_buffer, error_capacity, "MLX array evaluation failed");
    }
    if (mlx_synchronize(context->stream) != 0) {
        return set_error(error_buffer, error_capacity,
                         "MLX submission-stream synchronization failed");
    }
    return 0;
}

int pulsar_mlx_array_add_self(
    PulsarMlxContext *raw_context,
    PulsarMlxArray *raw_array,
    PulsarMlxArray **out_array,
    char *error_buffer,
    size_t error_capacity) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    auto *source = reinterpret_cast<MlxArrayObject *>(raw_array);
    if (context == nullptr || source == nullptr || source->context != context ||
        out_array == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "MLX add ownership mismatch");
    }
    auto *result = new (std::nothrow) MlxArrayObject();
    if (result == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "MLX result allocation failed");
    }
    result->context = context;
    if (mlx_add(&result->array, source->array, source->array,
                context->stream) != 0 || result->array.ctx == nullptr) {
        delete result;
        return set_error(error_buffer, error_capacity, "MLX add dispatch failed");
    }
    *out_array = reinterpret_cast<PulsarMlxArray *>(result);
    return 0;
}

int pulsar_mlx_array_data_pointer(
    PulsarMlxArray *raw_array,
    uintptr_t *out_pointer,
    char *error_buffer,
    size_t error_capacity) {
    auto *array = reinterpret_cast<MlxArrayObject *>(raw_array);
    if (array == nullptr || out_pointer == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "invalid MLX data-pointer arguments");
    }
    const float *data = mlx_array_data_float32(array->array);
    if (data == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "MLX array is not evaluated");
    }
    *out_pointer = reinterpret_cast<uintptr_t>(data);
    return 0;
}

int pulsar_mlx_array_destroy(
    PulsarMlxArray *raw_array,
    uint64_t *callback_count,
    char *error_buffer,
    size_t error_capacity) {
    auto *array = reinterpret_cast<MlxArrayObject *>(raw_array);
    if (array == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "invalid MLX array destroy arguments");
    }
    int status = destroy_array(array, callback_count);
    if (status != 0) {
        return set_error(error_buffer, error_capacity,
                         "MLX array destruction failed");
    }
    return 0;
}

}
