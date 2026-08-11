#include <mlx/c/mlx.h>

#include <atomic>
#include <climits>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <new>

namespace {

struct AccountingState {
    std::atomic<uint64_t> refs{1};
    std::atomic<uint64_t> callback_count{0};
    std::atomic<uint64_t> managed_created{0};
    std::atomic<uint64_t> managed_destroyed{0};
    std::atomic<uint64_t> derived_created{0};
    std::atomic<uint64_t> derived_destroyed{0};
};

struct OwnershipState {
    std::atomic<uint64_t> refs{1};
    std::atomic<uint64_t> callback_count{0};
    AccountingState *accounting = nullptr;
    OwnershipState *next = nullptr;
};

enum class StreamOrigin : uint8_t {
    None = 0,
    DefaultCpu = 1,
    DefaultGpu = 2,
    OwnedDevice = 3,
};

struct MlxContextObject {
    mlx_device device{};
    mlx_stream stream{};
    StreamOrigin stream_origin = StreamOrigin::None;
    bool stream_handle_owned = false;
    bool singleton_claimed = false;
    AccountingState *accounting = nullptr;
    OwnershipState *ownership_states = nullptr;
};

struct MlxArrayObject {
    mlx_array array{};
    MlxContextObject *context = nullptr;
    OwnershipState *ownership = nullptr;
    bool derived = false;
};

std::atomic<bool> context_active{false};
std::atomic<uint64_t> default_cpu_stream_created{0};
std::atomic<uint64_t> default_cpu_stream_freed{0};
std::atomic<uint64_t> default_gpu_stream_created{0};
std::atomic<uint64_t> default_gpu_stream_freed{0};
std::atomic<uint64_t> owned_stream_created{0};
std::atomic<uint64_t> owned_stream_freed{0};
std::atomic<bool> fail_next_after_stream_create{false};

int set_error(char *buffer, size_t capacity, const char *message) {
    if (buffer != nullptr && capacity > 0) {
        std::snprintf(buffer, capacity, "%s", message);
    }
    return -1;
}

void retain_accounting(AccountingState *accounting) {
    if (accounting != nullptr) {
        accounting->refs.fetch_add(1, std::memory_order_relaxed);
    }
}

void release_accounting(AccountingState *accounting) {
    if (accounting != nullptr &&
        accounting->refs.fetch_sub(1, std::memory_order_acq_rel) == 1) {
        delete accounting;
    }
}

void retain_ownership(OwnershipState *ownership) {
    if (ownership != nullptr) {
        ownership->refs.fetch_add(1, std::memory_order_relaxed);
    }
}

void release_ownership(OwnershipState *ownership) {
    if (ownership != nullptr &&
        ownership->refs.fetch_sub(1, std::memory_order_acq_rel) == 1) {
        release_accounting(ownership->accounting);
        delete ownership;
    }
}

void adopt_ownership(MlxContextObject *context, OwnershipState *ownership) {
    ownership->accounting = context->accounting;
    retain_accounting(ownership->accounting);
    ownership->next = context->ownership_states;
    context->ownership_states = ownership;
}

void managed_owner_released(void *payload) {
    auto *ownership = static_cast<OwnershipState *>(payload);
    if (ownership == nullptr) {
        return;
    }
    ownership->callback_count.fetch_add(1, std::memory_order_relaxed);
    if (ownership->accounting != nullptr) {
        ownership->accounting->callback_count.fetch_add(1,
                                                        std::memory_order_relaxed);
    }
    release_ownership(ownership);
}

void record_stream_created(StreamOrigin origin) {
    switch (origin) {
        case StreamOrigin::DefaultCpu:
            default_cpu_stream_created.fetch_add(1, std::memory_order_relaxed);
            break;
        case StreamOrigin::DefaultGpu:
            default_gpu_stream_created.fetch_add(1, std::memory_order_relaxed);
            break;
        case StreamOrigin::OwnedDevice:
            owned_stream_created.fetch_add(1, std::memory_order_relaxed);
            break;
        case StreamOrigin::None:
            break;
    }
}

void record_stream_freed(StreamOrigin origin) {
    switch (origin) {
        case StreamOrigin::DefaultCpu:
            default_cpu_stream_freed.fetch_add(1, std::memory_order_relaxed);
            break;
        case StreamOrigin::DefaultGpu:
            default_gpu_stream_freed.fetch_add(1, std::memory_order_relaxed);
            break;
        case StreamOrigin::OwnedDevice:
            owned_stream_freed.fetch_add(1, std::memory_order_relaxed);
            break;
        case StreamOrigin::None:
            break;
    }
}

void release_stream_handle(MlxContextObject *context) {
    if (context == nullptr || !context->stream_handle_owned ||
        context->stream.ctx == nullptr) {
        return;
    }
    mlx_stream_free(context->stream);
    record_stream_freed(context->stream_origin);
    context->stream = {};
    context->stream_handle_owned = false;
}

void restore_default_cpu_context() {
    mlx_device cpu = mlx_device_new_type(MLX_CPU, 0);
    bool available = false;
    if (cpu.ctx != nullptr && mlx_device_is_available(&available, cpu) == 0 &&
        available) {
        mlx_set_default_device(cpu);
    }
    if (cpu.ctx != nullptr) {
        mlx_device_free(cpu);
    }

    mlx_stream cpu_stream = mlx_default_cpu_stream_new();
    if (cpu_stream.ctx != nullptr) {
        record_stream_created(StreamOrigin::DefaultCpu);
        mlx_set_default_stream(cpu_stream);
        mlx_stream_free(cpu_stream);
        record_stream_freed(StreamOrigin::DefaultCpu);
    }
}

void destroy_context(MlxContextObject *context) {
    if (context == nullptr) {
        return;
    }
    restore_default_cpu_context();
    release_stream_handle(context);
    if (context->device.ctx != nullptr) {
        mlx_device_free(context->device);
    }

    OwnershipState *ownership = context->ownership_states;
    while (ownership != nullptr) {
        OwnershipState *next = ownership->next;
        release_ownership(ownership);
        ownership = next;
    }
    release_accounting(context->accounting);
    if (context->singleton_claimed) {
        context_active.store(false, std::memory_order_release);
    }
    delete context;
}

int destroy_array(MlxArrayObject *array, uint64_t *callback_count) {
    if (array == nullptr) {
        return -1;
    }
    int status = mlx_array_free(array->array);
    if (array->ownership != nullptr) {
        if (array->ownership->accounting != nullptr) {
            if (array->derived) {
                array->ownership->accounting->derived_destroyed.fetch_add(
                    1, std::memory_order_relaxed);
            } else {
                array->ownership->accounting->managed_destroyed.fetch_add(
                    1, std::memory_order_relaxed);
            }
        }
        if (callback_count != nullptr) {
            *callback_count = array->derived
                                  ? 0
                                  : array->ownership->callback_count.load(
                                        std::memory_order_acquire);
        }
        release_ownership(array->ownership);
    } else if (callback_count != nullptr) {
        *callback_count = 0;
    }
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

    bool expected = false;
    if (!context_active.compare_exchange_strong(expected, true,
                                                std::memory_order_acq_rel)) {
        return set_error(error_buffer, error_capacity,
                         "only one MLX context is supported per process");
    }

    auto *context = new (std::nothrow) MlxContextObject();
    if (context == nullptr) {
        context_active.store(false, std::memory_order_release);
        return set_error(error_buffer, error_capacity,
                         "MLX context allocation failed");
    }
    context->singleton_claimed = true;
    context->accounting = new (std::nothrow) AccountingState();
    if (context->accounting == nullptr) {
        destroy_context(context);
        return set_error(error_buffer, error_capacity,
                         "MLX accounting allocation failed");
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

    if (stream_mode == 1) {
        context->stream = mlx_stream_new_device(context->device);
        context->stream_origin = StreamOrigin::OwnedDevice;
        if (context->stream.ctx != nullptr) {
            context->stream_handle_owned = true;
            record_stream_created(context->stream_origin);
        }
        if (context->stream.ctx == nullptr ||
            mlx_set_default_stream(context->stream) != 0) {
            destroy_context(context);
            return set_error(error_buffer, error_capacity,
                             "owned MLX stream creation failed");
        }
    } else {
        context->stream_origin = device_type == MLX_CPU
                                     ? StreamOrigin::DefaultCpu
                                     : StreamOrigin::DefaultGpu;
        context->stream = device_type == MLX_CPU
                              ? mlx_default_cpu_stream_new()
                              : mlx_default_gpu_stream_new();
        if (context->stream.ctx != nullptr) {
            context->stream_handle_owned = true;
            record_stream_created(context->stream_origin);
        }
        if (context->stream.ctx == nullptr) {
            destroy_context(context);
            return set_error(error_buffer, error_capacity,
                             "default MLX stream lookup failed");
        }
    }
    if (fail_next_after_stream_create.exchange(false,
                                                std::memory_order_acq_rel)) {
        destroy_context(context);
        return set_error(error_buffer, error_capacity,
                         "injected failure after MLX stream creation");
    }
    *out_context = reinterpret_cast<PulsarMlxContext *>(context);
    return 0;
}

int pulsar_mlx_context_stream_owned(PulsarMlxContext *raw_context) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    return context != nullptr &&
                   context->stream_origin == StreamOrigin::OwnedDevice
               ? 1
               : 0;
}

void pulsar_mlx_context_destroy(PulsarMlxContext *raw_context) {
    destroy_context(reinterpret_cast<MlxContextObject *>(raw_context));
}

int pulsar_mlx_import_f32_shaped(
    PulsarMlxContext *raw_context,
    float *data,
    size_t count,
    const int *shape,
    size_t rank,
    PulsarMlxArray **out_array,
    char *error_buffer,
    size_t error_capacity) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    if (context == nullptr || data == nullptr || count == 0 ||
        count > static_cast<size_t>(INT_MAX) || shape == nullptr || rank == 0 ||
        rank > 2 || out_array == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "invalid MLX f32 import arguments");
    }
    size_t shape_count = 1;
    for (size_t dimension = 0; dimension < rank; ++dimension) {
        if (shape[dimension] <= 0 ||
            shape_count > count / static_cast<size_t>(shape[dimension])) {
            return set_error(error_buffer, error_capacity,
                             "invalid MLX f32 import shape");
        }
        shape_count *= static_cast<size_t>(shape[dimension]);
    }
    if (shape_count != count) {
        return set_error(error_buffer, error_capacity,
                         "MLX f32 import shape does not match element count");
    }

    auto *ownership = new (std::nothrow) OwnershipState();
    auto *array = new (std::nothrow) MlxArrayObject();
    if (ownership == nullptr || array == nullptr) {
        delete ownership;
        delete array;
        return set_error(error_buffer, error_capacity,
                         "MLX managed-array allocation failed");
    }
    adopt_ownership(context, ownership);
    retain_ownership(ownership);  // array wrapper reference
    retain_ownership(ownership);  // MLX callback reference

    array->ownership = ownership;
    array->context = context;
    array->array = mlx_array_new_data_managed_payload(
        data, shape, static_cast<int>(rank), MLX_FLOAT32, ownership,
        managed_owner_released);
    if (array->array.ctx == nullptr) {
        release_ownership(ownership);  // callback reference
        release_ownership(ownership);  // array wrapper reference
        delete array;
        return set_error(error_buffer, error_capacity,
                         "MLX managed-array construction failed");
    }
    context->accounting->managed_created.fetch_add(1,
                                                   std::memory_order_relaxed);
    *out_array = reinterpret_cast<PulsarMlxArray *>(array);
    return 0;
}

int pulsar_mlx_import_f32(
    PulsarMlxContext *raw_context,
    float *data,
    size_t count,
    PulsarMlxArray **out_array,
    char *error_buffer,
    size_t error_capacity) {
    if (count > static_cast<size_t>(INT_MAX)) {
        return set_error(error_buffer, error_capacity,
                         "invalid MLX f32 import arguments");
    }
    int shape[1] = {static_cast<int>(count)};
    return pulsar_mlx_import_f32_shaped(
        raw_context, data, count, shape, 1, out_array, error_buffer,
        error_capacity);
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
        source->ownership == nullptr || out_array == nullptr) {
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
    result->ownership = source->ownership;
    result->derived = true;
    retain_ownership(result->ownership);
    result->ownership->accounting->derived_created.fetch_add(
        1, std::memory_order_relaxed);
    *out_array = reinterpret_cast<PulsarMlxArray *>(result);
    return 0;
}

int pulsar_mlx_array_matvec(
    PulsarMlxContext *raw_context,
    PulsarMlxArray *raw_matrix,
    PulsarMlxArray *raw_vector,
    PulsarMlxArray **out_array,
    char *error_buffer,
    size_t error_capacity) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    auto *matrix = reinterpret_cast<MlxArrayObject *>(raw_matrix);
    auto *vector = reinterpret_cast<MlxArrayObject *>(raw_vector);
    if (context == nullptr || matrix == nullptr || vector == nullptr ||
        matrix->context != context || vector->context != context ||
        matrix->ownership == nullptr || vector->ownership == nullptr ||
        out_array == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "MLX matvec ownership mismatch");
    }
    if (mlx_array_dtype(matrix->array) != MLX_FLOAT32 ||
        mlx_array_dtype(vector->array) != MLX_FLOAT32 ||
        mlx_array_ndim(matrix->array) != 2 ||
        mlx_array_ndim(vector->array) != 1) {
        return set_error(error_buffer, error_capacity,
                         "MLX matvec requires an f32 matrix and f32 vector");
    }
    const int *matrix_shape = mlx_array_shape(matrix->array);
    const int *vector_shape = mlx_array_shape(vector->array);
    if (matrix_shape == nullptr || vector_shape == nullptr ||
        matrix_shape[1] != vector_shape[0]) {
        return set_error(error_buffer, error_capacity,
                         "MLX matvec shape mismatch");
    }

    auto *result = new (std::nothrow) MlxArrayObject();
    if (result == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "MLX matvec result allocation failed");
    }
    result->context = context;
    if (mlx_matmul(&result->array, matrix->array, vector->array,
                   context->stream) != 0 || result->array.ctx == nullptr) {
        delete result;
        return set_error(error_buffer, error_capacity,
                         "MLX matvec dispatch failed");
    }
    result->ownership = matrix->ownership;
    result->derived = true;
    retain_ownership(result->ownership);
    result->ownership->accounting->derived_created.fetch_add(
        1, std::memory_order_relaxed);
    *out_array = reinterpret_cast<PulsarMlxArray *>(result);
    return 0;
}

int pulsar_mlx_array_copy_f32(
    PulsarMlxContext *raw_context,
    PulsarMlxArray *raw_array,
    float *destination,
    size_t count,
    char *error_buffer,
    size_t error_capacity) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    auto *array = reinterpret_cast<MlxArrayObject *>(raw_array);
    if (context == nullptr || array == nullptr || array->context != context ||
        destination == nullptr || count == 0 ||
        mlx_array_dtype(array->array) != MLX_FLOAT32 ||
        mlx_array_size(array->array) != count) {
        return set_error(error_buffer, error_capacity,
                         "invalid MLX f32 copy arguments");
    }
    const float *data = mlx_array_data_float32(array->array);
    if (data == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "MLX array is not evaluated");
    }
    std::memcpy(destination, data, count * sizeof(float));
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

int pulsar_mlx_context_synchronize(
    PulsarMlxContext *raw_context,
    char *error_buffer,
    size_t error_capacity) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    if (context == nullptr || context->stream.ctx == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "invalid MLX context synchronization arguments");
    }
    if (mlx_synchronize(context->stream) != 0) {
        return set_error(error_buffer, error_capacity,
                         "MLX context synchronization failed");
    }
    return 0;
}

int pulsar_mlx_context_ownership_snapshot(
    PulsarMlxContext *raw_context,
    uint64_t *callback_count,
    uint64_t *managed_created,
    uint64_t *managed_destroyed,
    uint64_t *derived_created,
    uint64_t *derived_destroyed,
    uint64_t *derived_live,
    char *error_buffer,
    size_t error_capacity) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    if (context == nullptr || context->accounting == nullptr ||
        callback_count == nullptr || managed_created == nullptr ||
        managed_destroyed == nullptr || derived_created == nullptr ||
        derived_destroyed == nullptr || derived_live == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "invalid MLX ownership snapshot arguments");
    }
    auto *accounting = context->accounting;
    *callback_count = accounting->callback_count.load(std::memory_order_acquire);
    *managed_created = accounting->managed_created.load(std::memory_order_acquire);
    *managed_destroyed = accounting->managed_destroyed.load(std::memory_order_acquire);
    *derived_created = accounting->derived_created.load(std::memory_order_acquire);
    *derived_destroyed = accounting->derived_destroyed.load(std::memory_order_acquire);
    *derived_live = *derived_created - *derived_destroyed;
    return 0;
}

int pulsar_mlx_debug_stream_counters(
    uint64_t *default_cpu_created,
    uint64_t *default_cpu_freed,
    uint64_t *default_gpu_created,
    uint64_t *default_gpu_freed,
    uint64_t *owned_created,
    uint64_t *owned_freed,
    char *error_buffer,
    size_t error_capacity) {
    if (default_cpu_created == nullptr || default_cpu_freed == nullptr ||
        default_gpu_created == nullptr || default_gpu_freed == nullptr ||
        owned_created == nullptr || owned_freed == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "invalid MLX stream counter arguments");
    }
    *default_cpu_created =
        default_cpu_stream_created.load(std::memory_order_acquire);
    *default_cpu_freed =
        default_cpu_stream_freed.load(std::memory_order_acquire);
    *default_gpu_created =
        default_gpu_stream_created.load(std::memory_order_acquire);
    *default_gpu_freed =
        default_gpu_stream_freed.load(std::memory_order_acquire);
    *owned_created = owned_stream_created.load(std::memory_order_acquire);
    *owned_freed = owned_stream_freed.load(std::memory_order_acquire);
    return 0;
}

int pulsar_mlx_debug_context_active() {
    return context_active.load(std::memory_order_acquire) ? 1 : 0;
}

void pulsar_mlx_debug_fail_next_after_stream_create() {
    fail_next_after_stream_create.store(true, std::memory_order_release);
}

int pulsar_mlx_validate_f32_count(
    size_t count,
    char *error_buffer,
    size_t error_capacity) {
    if (count == 0 || count > static_cast<size_t>(INT_MAX)) {
        return set_error(error_buffer, error_capacity,
                         "MLX f32 shape count is outside int range");
    }
    return 0;
}

}
