#include <mlx/c/mlx.h>

#include <atomic>
#include <climits>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <new>

extern "C" {
int pulsar_mlx_native_stream_observe_create(mlx_stream stream, int origin);
int pulsar_mlx_native_stream_free(mlx_stream stream, int origin);
int pulsar_mlx_native_stream_probe_duplicate(mlx_stream stream, int origin);
int pulsar_mlx_native_stream_observer_snapshot(
    uint64_t *, uint64_t *, uint64_t *, uint64_t *, uint64_t *, uint64_t *,
    uint64_t *, uint64_t *, uint64_t *);
}

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
    bool registered = false;
    uint64_t generation = 0;
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
std::atomic<uint64_t> active_generation{0};
std::atomic<uint64_t> next_generation{1};
std::atomic<uint64_t> p1_callback_count{0};
std::atomic<uint64_t> p1_managed_created{0};
std::atomic<uint64_t> p1_managed_destroyed{0};
std::atomic<uint64_t> p1_derived_created{0};
std::atomic<uint64_t> p1_derived_destroyed{0};
std::atomic<uint64_t> p1_registrations{0};
std::atomic<uint64_t> p1_teardowns{0};
std::atomic<uint64_t> p1_in_flight_work{0};
std::atomic<uint64_t> p1_stale_native_ready_generations{0};
std::atomic<uint64_t> default_cpu_stream_created{0};
std::atomic<uint64_t> default_cpu_stream_freed{0};
std::atomic<uint64_t> default_gpu_stream_created{0};
std::atomic<uint64_t> default_gpu_stream_freed{0};
std::atomic<uint64_t> owned_stream_created{0};
std::atomic<uint64_t> owned_stream_freed{0};
std::atomic<bool> fail_next_after_stream_create{false};
std::atomic<int> next_release_fault{0};
mlx_stream skipped_native_stream{};
StreamOrigin skipped_native_origin = StreamOrigin::None;
std::atomic<int> skipped_logical_origin{0};

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
    p1_callback_count.fetch_add(1, std::memory_order_relaxed);
    if (ownership->accounting != nullptr) {
        ownership->accounting->callback_count.fetch_add(1,
                                                        std::memory_order_relaxed);
    }
    release_ownership(ownership);
}

bool context_generation_is_current(MlxContextObject *context) {
    if (context != nullptr && context->generation != 0 &&
        active_generation.load(std::memory_order_acquire) == context->generation) {
        return true;
    }
    p1_stale_native_ready_generations.fetch_add(1, std::memory_order_relaxed);
    return false;
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

int observer_origin(StreamOrigin origin) {
    return static_cast<int>(origin);
}

bool observe_stream_created(mlx_stream stream, StreamOrigin origin) {
    return pulsar_mlx_native_stream_observe_create(stream,
                                                    observer_origin(origin)) == 0;
}

void release_stream_handle(MlxContextObject *context) {
    if (context == nullptr || !context->stream_handle_owned ||
        context->stream.ctx == nullptr) {
        return;
    }
    int fault = next_release_fault.exchange(0, std::memory_order_acq_rel);
    if (fault == 1) {
        skipped_native_stream = context->stream;
        skipped_native_origin = context->stream_origin;
    } else {
        int status = pulsar_mlx_native_stream_free(
            context->stream, observer_origin(context->stream_origin));
        if (status != 0) {
            std::abort();
        }
        if (fault == 3) {
            if (pulsar_mlx_native_stream_probe_duplicate(
                    context->stream, observer_origin(context->stream_origin)) != -2) {
                std::abort();
            }
        }
    }
    if (fault == 2) {
        skipped_logical_origin.store(observer_origin(context->stream_origin),
                                     std::memory_order_release);
    } else {
        record_stream_freed(context->stream_origin);
    }
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
        if (!observe_stream_created(cpu_stream, StreamOrigin::DefaultCpu)) {
            std::abort();
        }
        record_stream_created(StreamOrigin::DefaultCpu);
        mlx_set_default_stream(cpu_stream);
        if (pulsar_mlx_native_stream_free(
                cpu_stream, observer_origin(StreamOrigin::DefaultCpu)) != 0) {
            std::abort();
        }
        record_stream_freed(StreamOrigin::DefaultCpu);
    }
}

void destroy_context(MlxContextObject *context) {
    if (context == nullptr) {
        return;
    }
    if (context->stream.ctx != nullptr) {
        mlx_synchronize(context->stream);
        p1_in_flight_work.store(0, std::memory_order_release);
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
        active_generation.store(0, std::memory_order_release);
        context_active.store(false, std::memory_order_release);
    }
    if (context->registered) {
        p1_teardowns.fetch_add(1, std::memory_order_relaxed);
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
                p1_derived_destroyed.fetch_add(1, std::memory_order_relaxed);
            } else {
                array->ownership->accounting->managed_destroyed.fetch_add(
                    1, std::memory_order_relaxed);
                p1_managed_destroyed.fetch_add(1, std::memory_order_relaxed);
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

struct PulsarMlxP1AccountingSnapshot {
    uint64_t callback_count;
    uint64_t managed_created;
    uint64_t managed_destroyed;
    uint64_t derived_created;
    uint64_t derived_destroyed;
    uint64_t default_cpu_stream_created;
    uint64_t default_cpu_stream_freed;
    uint64_t default_gpu_stream_created;
    uint64_t default_gpu_stream_freed;
    uint64_t owned_stream_created;
    uint64_t owned_stream_freed;
    uint64_t native_default_cpu_stream_freed;
    uint64_t native_default_gpu_stream_freed;
    uint64_t native_owned_stream_freed;
    uint64_t native_live_stream_handles;
    uint64_t native_duplicate_free_attempts;
    uint64_t native_origin_mismatches;
    uint64_t context_active;
    uint64_t registrations;
    uint64_t teardowns;
    uint64_t in_flight_work;
    uint64_t stale_native_ready_generations;
};

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
    context->generation = next_generation.fetch_add(1, std::memory_order_acq_rel);
    active_generation.store(context->generation, std::memory_order_release);
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
            if (!observe_stream_created(context->stream, context->stream_origin)) {
                destroy_context(context);
                return set_error(error_buffer, error_capacity,
                                 "native stream observer rejected owned handle");
            }
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
            if (!observe_stream_created(context->stream, context->stream_origin)) {
                destroy_context(context);
                return set_error(error_buffer, error_capacity,
                                 "native stream observer rejected default handle");
            }
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
    context->registered = true;
    p1_registrations.fetch_add(1, std::memory_order_relaxed);
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

int pulsar_mlx_context_stream_authority(
    PulsarMlxContext *raw_context,
    int *origin,
    int *handle_owned) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    if (context == nullptr || origin == nullptr || handle_owned == nullptr) {
        return -1;
    }
    *origin = observer_origin(context->stream_origin);
    *handle_owned = context->stream_handle_owned ? 1 : 0;
    return 0;
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
    if (context == nullptr || !context_generation_is_current(context) ||
        data == nullptr || count == 0 ||
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
    adopt_ownership(context, ownership);
    retain_ownership(ownership);  // array wrapper reference
    retain_ownership(ownership);  // MLX callback reference

    int shape[1] = {static_cast<int>(count)};
    array->ownership = ownership;
    array->context = context;
    array->array = mlx_array_new_data_managed_payload(
        data, shape, 1, MLX_FLOAT32, ownership, managed_owner_released);
    if (array->array.ctx == nullptr) {
        release_ownership(ownership);  // callback reference
        release_ownership(ownership);  // array wrapper reference
        delete array;
        return set_error(error_buffer, error_capacity,
                         "MLX managed-array construction failed");
    }
    context->accounting->managed_created.fetch_add(1,
                                                   std::memory_order_relaxed);
    p1_managed_created.fetch_add(1, std::memory_order_relaxed);
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
    if (context == nullptr || !context_generation_is_current(context) ||
        array == nullptr || array->context != context) {
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
    p1_in_flight_work.store(0, std::memory_order_release);
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
    if (context == nullptr || !context_generation_is_current(context) ||
        source == nullptr || source->context != context ||
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
    p1_derived_created.fetch_add(1, std::memory_order_relaxed);
    p1_in_flight_work.fetch_add(1, std::memory_order_relaxed);
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

int pulsar_mlx_context_synchronize(
    PulsarMlxContext *raw_context,
    char *error_buffer,
    size_t error_capacity) {
    auto *context = reinterpret_cast<MlxContextObject *>(raw_context);
    if (context == nullptr || !context_generation_is_current(context) ||
        context->stream.ctx == nullptr) {
        return set_error(error_buffer, error_capacity,
                         "invalid MLX context synchronization arguments");
    }
    if (mlx_synchronize(context->stream) != 0) {
        return set_error(error_buffer, error_capacity,
                         "MLX context synchronization failed");
    }
    p1_in_flight_work.store(0, std::memory_order_release);
    return 0;
}

int pulsar_mlx_p1_accounting_snapshot(PulsarMlxP1AccountingSnapshot *out) {
    if (out == nullptr) {
        return -1;
    }
    uint64_t native_default_cpu_created = 0;
    uint64_t native_default_gpu_created = 0;
    uint64_t native_owned_created = 0;
    if (pulsar_mlx_native_stream_observer_snapshot(
            &native_default_cpu_created, &out->native_default_cpu_stream_freed,
            &native_default_gpu_created, &out->native_default_gpu_stream_freed,
            &native_owned_created, &out->native_owned_stream_freed,
            &out->native_live_stream_handles,
            &out->native_duplicate_free_attempts,
            &out->native_origin_mismatches) != 0) {
        return -2;
    }
    out->callback_count = p1_callback_count.load(std::memory_order_acquire);
    out->managed_created = p1_managed_created.load(std::memory_order_acquire);
    out->managed_destroyed = p1_managed_destroyed.load(std::memory_order_acquire);
    out->derived_created = p1_derived_created.load(std::memory_order_acquire);
    out->derived_destroyed = p1_derived_destroyed.load(std::memory_order_acquire);
    out->default_cpu_stream_created = default_cpu_stream_created.load(std::memory_order_acquire);
    out->default_cpu_stream_freed = default_cpu_stream_freed.load(std::memory_order_acquire);
    out->default_gpu_stream_created = default_gpu_stream_created.load(std::memory_order_acquire);
    out->default_gpu_stream_freed = default_gpu_stream_freed.load(std::memory_order_acquire);
    out->owned_stream_created = owned_stream_created.load(std::memory_order_acquire);
    out->owned_stream_freed = owned_stream_freed.load(std::memory_order_acquire);
    out->context_active = context_active.load(std::memory_order_acquire) ? 1 : 0;
    out->registrations = p1_registrations.load(std::memory_order_acquire);
    out->teardowns = p1_teardowns.load(std::memory_order_acquire);
    out->in_flight_work = p1_in_flight_work.load(std::memory_order_acquire);
    out->stale_native_ready_generations = p1_stale_native_ready_generations.load(std::memory_order_acquire);
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

void pulsar_mlx_debug_fail_next_after_stream_create() {
    fail_next_after_stream_create.store(true, std::memory_order_release);
}

void pulsar_mlx_debug_set_next_release_fault(int fault) {
    next_release_fault.store(fault, std::memory_order_release);
}

int pulsar_mlx_debug_cleanup_release_fault() {
    if (skipped_native_stream.ctx != nullptr) {
        int status = pulsar_mlx_native_stream_free(
            skipped_native_stream, observer_origin(skipped_native_origin));
        skipped_native_stream = {};
        skipped_native_origin = StreamOrigin::None;
        if (status != 0) {
            return status;
        }
    }
    int logical_origin = skipped_logical_origin.exchange(0,
                                                         std::memory_order_acq_rel);
    if (logical_origin != 0) {
        record_stream_freed(static_cast<StreamOrigin>(logical_origin));
    }
    return 0;
}

int pulsar_mlx_debug_native_stream_counters(
    uint64_t *default_cpu_created,
    uint64_t *default_cpu_freed,
    uint64_t *default_gpu_created,
    uint64_t *default_gpu_freed,
    uint64_t *owned_created,
    uint64_t *owned_freed,
    uint64_t *live_handles,
    uint64_t *duplicate_free_attempts,
    uint64_t *origin_mismatches) {
    return pulsar_mlx_native_stream_observer_snapshot(
        default_cpu_created, default_cpu_freed, default_gpu_created,
        default_gpu_freed, owned_created, owned_freed, live_handles,
        duplicate_free_attempts, origin_mismatches);
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
