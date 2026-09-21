#include <mlx/c/mlx.h>

#include <array>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <unordered_map>

namespace {

struct NativeFreeObserver {
    std::mutex mutex;
    std::unordered_map<void *, int> live;
    std::array<uint64_t, 4> created{};
    std::array<uint64_t, 4> freed{};
    uint64_t duplicate_free_attempts = 0;
    uint64_t origin_mismatches = 0;
};

NativeFreeObserver observer;

bool valid_origin(int origin) { return origin >= 1 && origin <= 3; }

}  // namespace

extern "C" {

int pulsar_mlx_native_stream_observe_create(mlx_stream stream, int origin) {
    if (stream.ctx == nullptr || !valid_origin(origin)) {
        return -1;
    }
    std::lock_guard<std::mutex> guard(observer.mutex);
    if (observer.live.find(stream.ctx) != observer.live.end()) {
        return -2;
    }
    observer.live.emplace(stream.ctx, origin);
    observer.created[static_cast<size_t>(origin)] += 1;
    return 0;
}

// This is the sole native stream-deallocation boundary used by the F017 MLX
// bridge. The observation is in a separate translation unit from logical
// ownership accounting and is recorded only after the real MLX symbol returns.
int pulsar_mlx_native_stream_free(mlx_stream stream, int origin) {
    if (stream.ctx == nullptr || !valid_origin(origin)) {
        return -1;
    }
    {
        std::lock_guard<std::mutex> guard(observer.mutex);
        auto found = observer.live.find(stream.ctx);
        if (found == observer.live.end()) {
            observer.duplicate_free_attempts += 1;
            return -2;
        }
        if (found->second != origin) {
            observer.origin_mismatches += 1;
            return -3;
        }
    }

    mlx_stream_free(stream);

    std::lock_guard<std::mutex> guard(observer.mutex);
    auto found = observer.live.find(stream.ctx);
    if (found == observer.live.end() || found->second != origin) {
        return -4;
    }
    observer.live.erase(found);
    observer.freed[static_cast<size_t>(origin)] += 1;
    return 0;
}

// Exercises duplicate-free detection without invoking MLX on an already-freed
// handle. A second request must be observed and rejected before deallocation.
int pulsar_mlx_native_stream_probe_duplicate(mlx_stream stream, int origin) {
    if (stream.ctx == nullptr || !valid_origin(origin)) {
        return -1;
    }
    std::lock_guard<std::mutex> guard(observer.mutex);
    auto found = observer.live.find(stream.ctx);
    if (found == observer.live.end()) {
        observer.duplicate_free_attempts += 1;
        return -2;
    }
    return 0;
}

int pulsar_mlx_native_stream_observer_snapshot(
    uint64_t *default_cpu_created,
    uint64_t *default_cpu_freed,
    uint64_t *default_gpu_created,
    uint64_t *default_gpu_freed,
    uint64_t *owned_created,
    uint64_t *owned_freed,
    uint64_t *live_handles,
    uint64_t *duplicate_free_attempts,
    uint64_t *origin_mismatches) {
    if (default_cpu_created == nullptr || default_cpu_freed == nullptr ||
        default_gpu_created == nullptr || default_gpu_freed == nullptr ||
        owned_created == nullptr || owned_freed == nullptr ||
        live_handles == nullptr || duplicate_free_attempts == nullptr ||
        origin_mismatches == nullptr) {
        return -1;
    }
    std::lock_guard<std::mutex> guard(observer.mutex);
    *default_cpu_created = observer.created[1];
    *default_cpu_freed = observer.freed[1];
    *default_gpu_created = observer.created[2];
    *default_gpu_freed = observer.freed[2];
    *owned_created = observer.created[3];
    *owned_freed = observer.freed[3];
    *live_handles = static_cast<uint64_t>(observer.live.size());
    *duplicate_free_attempts = observer.duplicate_free_attempts;
    *origin_mismatches = observer.origin_mismatches;
    return 0;
}

}
