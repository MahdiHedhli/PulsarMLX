// Standalone Feature 017 MLX C API GPU teardown forensics.
//
// This file intentionally has no PulsarMLX runtime dependency. The parent
// process runs every lifecycle variant in a fresh child so an abort remains
// evidence instead of terminating the matrix.
//
// Build:
// clang++ -std=c++17 scripts/research/f017_mlx_c_teardown_matrix.cpp \
//   -I/opt/homebrew/Cellar/mlx-c/0.6.0_2/include -L/opt/homebrew/lib \
//   -Wl,-rpath,/opt/homebrew/lib -lmlxc -lmlx \
//   -o /tmp/f017-mlx-c-teardown-matrix
//
// Run the matrix:
// /tmp/f017-mlx-c-teardown-matrix

#include <mlx/c/mlx.h>

#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <signal.h>
#include <string>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include <vector>

namespace {

constexpr int kChildTimeoutSeconds = 5;
constexpr size_t kOutputLimit = 32 * 1024;

struct OwnershipState {
  int callback_count = 0;
  bool callback_entered = false;
  bool callback_exited = false;
};

OwnershipState* g_payload = nullptr;

void mark(const char* stage) {
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  const long long millis = static_cast<long long>(now.tv_sec) * 1000 +
                           static_cast<long long>(now.tv_nsec) / 1000000;
  std::fprintf(stdout, "MARK pid=%d t_ms=%lld stage=%s\n",
               static_cast<int>(getpid()), millis, stage);
  std::fflush(stdout);
}

void markf(const char* stage, const char* value) {
  struct timespec now;
  clock_gettime(CLOCK_MONOTONIC, &now);
  const long long millis = static_cast<long long>(now.tv_sec) * 1000 +
                           static_cast<long long>(now.tv_nsec) / 1000000;
  std::fprintf(stdout, "MARK pid=%d t_ms=%lld stage=%s value=%s\n",
               static_cast<int>(getpid()), millis, stage, value);
  std::fflush(stdout);
}

void payload_destructor(void* payload) {
  auto* state = static_cast<OwnershipState*>(payload);
  g_payload = state;
  state->callback_entered = true;
  state->callback_count += 1;
  mark("ownership_callback_entry");
  mark("ownership_callback_exit");
  state->callback_exited = true;
}

bool has(const std::string& variant, const char* text) {
  return variant.find(text) != std::string::npos;
}

bool is_gpu(const std::string& variant) {
  return has(variant, "gpu");
}

bool is_copy(const std::string& variant) {
  return has(variant, "copy");
}

bool owns_stream(const std::string& variant) {
  return has(variant, "owned-stream") || has(variant, "explicit-sync");
}

bool gets_default_stream(const std::string& variant) {
  return has(variant, "get-default-stream");
}

bool stream_first(const std::string& variant) {
  return has(variant, "stream-first");
}

bool owner_first(const std::string& variant) {
  return has(variant, "owner-first");
}

bool use_operation(const std::string& variant) {
  return has(variant, "operation") || is_copy(variant) || owns_stream(variant);
}

int cleanup_array(mlx_array* array, const char* name) {
  if (!array->ctx) {
    return 0;
  }
  std::string begin = std::string(name) + "_begin";
  std::string end = std::string(name) + "_end";
  mark(begin.c_str());
  int result = mlx_array_free(*array);
  *array = mlx_array_empty;
  mark(end.c_str());
  return result;
}

int cleanup_stream(mlx_stream* stream) {
  mark("stream_release_begin");
  int result = mlx_stream_free(*stream);
  *stream = mlx_stream_new();
  mark("stream_release_end");
  return result;
}

int cleanup_device(mlx_device* device) {
  mark("device_release_begin");
  int result = mlx_device_free(*device);
  *device = mlx_device_new();
  mark("device_release_end");
  return result;
}

int reuse_main() {
  mark("variant_reuse_begin");
  mlx_device device = mlx_device_new_type(MLX_GPU, 0);
  bool available = false;
  if (mlx_device_is_available(&available, device) != 0 || !available ||
      mlx_set_default_device(device) != 0) {
    mark("reuse_device_failed");
    mlx_device_free(device);
    return 40;
  }
  mlx_stream stream = mlx_stream_new_device(device);
  if (!stream.ctx || mlx_set_default_stream(stream) != 0) {
    mark("reuse_stream_failed");
    if (stream.ctx) {
      mlx_stream_free(stream);
    }
    mlx_device_free(device);
    return 41;
  }

  constexpr int kIterations = 10;
  int callback_total = 0;
  for (int iteration = 0; iteration < kIterations; ++iteration) {
    char iteration_name[64];
    std::snprintf(iteration_name, sizeof(iteration_name), "reuse_iteration_%d",
                  iteration);
    mark(iteration_name);
    OwnershipState ownership;
    g_payload = &ownership;
    float* source = nullptr;
    if (posix_memalign(reinterpret_cast<void**>(&source), 4096,
                       4 * sizeof(float)) != 0) {
      mark("reuse_host_allocate_failed");
      cleanup_stream(&stream);
      cleanup_device(&device);
      return 42;
    }
    source[0] = static_cast<float>(iteration + 1);
    source[1] = 2.0f;
    source[2] = 3.0f;
    source[3] = 4.0f;
    int shape[1] = {4};
    mlx_array input = mlx_array_new_data_managed_payload(
        source, shape, 1, MLX_FLOAT32, &ownership, payload_destructor);
    mlx_array result = mlx_array_empty;
    if (!input.ctx || mlx_add(&result, input, input, stream) != 0 ||
        !result.ctx || mlx_array_eval(result) != 0 ||
        mlx_synchronize(stream) != 0) {
      mark("reuse_operation_failed");
      cleanup_array(&result, "reuse_result_release");
      cleanup_array(&input, "reuse_input_release");
      std::free(source);
      cleanup_stream(&stream);
      cleanup_device(&device);
      return 43;
    }
    cleanup_array(&result, "reuse_result_release");
    cleanup_array(&input, "reuse_input_release");
    std::free(source);
    if (ownership.callback_count != 1) {
      mark("reuse_callback_count_failed");
      cleanup_stream(&stream);
      cleanup_device(&device);
      return 44;
    }
    callback_total += ownership.callback_count;
  }
  cleanup_stream(&stream);
  cleanup_device(&device);
  std::fprintf(stdout, "REUSE_SUMMARY iterations=%d callbacks=%d\n", kIterations,
               callback_total);
  std::fflush(stdout);
  return 0;
}

int child_main(const std::string& variant) {
  if (has(variant, "reuse")) {
    return reuse_main();
  }
  markf("variant", variant.c_str());
  const bool gpu = is_gpu(variant);
  const bool copy = is_copy(variant);
  OwnershipState ownership;
  g_payload = &ownership;

  mark("device_create_begin");
  mlx_device device = mlx_device_new_type(gpu ? MLX_GPU : MLX_CPU, 0);
  bool available = false;
  if (mlx_device_is_available(&available, device) != 0 || !available) {
    mark("device_unavailable");
    mlx_device_free(device);
    return 30;
  }
  mark("device_create_end");
  if (mlx_set_default_device(device) != 0) {
    mark("default_device_failed");
    mlx_device_free(device);
    return 31;
  }

  mark("stream_create_begin");
  mlx_stream stream = mlx_stream_new();
  if (gets_default_stream(variant)) {
    if (mlx_get_default_stream(&stream, device) != 0) {
      mark("stream_create_failed");
      mlx_stream_free(stream);
      mlx_device_free(device);
      return 32;
    }
  } else {
    stream = owns_stream(variant)
                 ? mlx_stream_new_device(device)
                 : (gpu ? mlx_default_gpu_stream_new()
                        : mlx_default_cpu_stream_new());
  }
  if (!stream.ctx) {
    mark("stream_create_failed");
    mlx_device_free(device);
    return 32;
  }
  if (owns_stream(variant) && mlx_set_default_stream(stream) != 0) {
    mark("default_stream_failed");
    mlx_stream_free(stream);
    mlx_device_free(device);
    return 33;
  }
  mark("stream_create_end");

  float* source = nullptr;
  mark("host_allocate");
  if (posix_memalign(reinterpret_cast<void**>(&source), 4096,
                     4 * sizeof(float)) != 0) {
    mark("host_allocate_failed");
    cleanup_stream(&stream);
    cleanup_device(&device);
    return 34;
  }
  source[0] = 1.0f;
  source[1] = 2.0f;
  source[2] = 3.0f;
  source[3] = 4.0f;
  int shape[1] = {4};

  mark("managed_import_begin");
  mlx_array input = copy
                        ? mlx_array_new_data(source, shape, 1, MLX_FLOAT32)
                        : mlx_array_new_data_managed_payload(
                              source, shape, 1, MLX_FLOAT32, &ownership,
                              payload_destructor);
  if (!input.ctx) {
    mark("array_create_failed");
    std::free(source);
    cleanup_stream(&stream);
    cleanup_device(&device);
    return 35;
  }
  mark("managed_import_end");
  if (copy) {
    mark("host_release_after_copy_import");
    std::free(source);
    source = nullptr;
  }

  mlx_array result = mlx_array_empty;
  if (use_operation(variant)) {
    mark("gpu_dispatch_begin");
    if (mlx_add(&result, input, input, stream) != 0 || !result.ctx) {
      mark("gpu_dispatch_failed");
      cleanup_array(&input, "input_release");
      if (source != nullptr) {
        std::free(source);
      }
      cleanup_stream(&stream);
      cleanup_device(&device);
      return 36;
    }
    mark("gpu_dispatch_end");
  }

  mlx_array* evaluated = result.ctx ? &result : &input;
  mark("evaluation_begin");
  if (mlx_array_eval(*evaluated) != 0) {
    mark("evaluation_failed");
    cleanup_array(&result, "result_release");
    cleanup_array(&input, "input_release");
    if (source != nullptr) {
      std::free(source);
    }
    cleanup_stream(&stream);
    cleanup_device(&device);
    return 37;
  }
  mark("evaluation_end");

  if (has(variant, "data_access")) {
    mark("data_access_begin");
    const float* data = mlx_array_data_float32(*evaluated);
    std::fprintf(stdout, "DATA pid=%d pointer=%p first=%.1f same_source=%d\n",
                 static_cast<int>(getpid()), static_cast<const void*>(data),
                 data ? data[0] : -1.0f,
                 data && source && data == source ? 1 : 0);
    std::fflush(stdout);
    mark("data_access_end");
  }

  if (has(variant, "sync") || gpu) {
    mark("synchronize_begin");
    if (mlx_synchronize(stream) != 0) {
      mark("synchronize_failed");
      return 38;
    }
    mark("synchronize_end");
  }

  if (owner_first(variant) && source != nullptr) {
    mark("host_release_before_array");
    std::free(source);
    source = nullptr;
    mark("host_release_before_array_end");
  }

  if (stream_first(variant)) {
    cleanup_stream(&stream);
  }

  if (!stream_first(variant)) {
    cleanup_array(&result, "result_release");
    cleanup_array(&input, "input_release");
  }
  if (stream_first(variant)) {
    cleanup_array(&result, "result_release");
    cleanup_array(&input, "input_release");
  }

  if (!has(variant, "keep-device")) {
    cleanup_device(&device);
  }
  if (!stream_first(variant)) {
    cleanup_stream(&stream);
  }
  if (source != nullptr) {
    mark("host_release_after_objects");
    std::free(source);
    source = nullptr;
    mark("host_release_after_objects_end");
  }
  std::fprintf(stdout, "SUMMARY pid=%d callback_count=%d callback_entered=%d callback_exited=%d\n",
               static_cast<int>(getpid()), ownership.callback_count,
               ownership.callback_entered ? 1 : 0,
               ownership.callback_exited ? 1 : 0);
  std::fflush(stdout);
  return 0;
}

struct ChildResult {
  int wait_status = -1;
  bool timed_out = false;
  std::string output;
};

ChildResult run_child(const std::string& executable, const std::string& variant) {
  int pipe_fds[2];
  if (pipe(pipe_fds) != 0) {
    return {-1, false, std::strerror(errno)};
  }
  pid_t pid = fork();
  if (pid == 0) {
    close(pipe_fds[0]);
    dup2(pipe_fds[1], STDOUT_FILENO);
    dup2(pipe_fds[1], STDERR_FILENO);
    close(pipe_fds[1]);
    execl(executable.c_str(), executable.c_str(), "--child", variant.c_str(),
          static_cast<char*>(nullptr));
    std::perror("exec");
    _exit(127);
  }
  if (pid < 0) {
    close(pipe_fds[0]);
    close(pipe_fds[1]);
    return {-1, false, std::strerror(errno)};
  }
  close(pipe_fds[1]);
  int flags = fcntl(pipe_fds[0], F_GETFL, 0);
  fcntl(pipe_fds[0], F_SETFL, flags | O_NONBLOCK);
  std::string output;
  int status = 0;
  bool reaped = false;
  bool timed_out = false;
  auto deadline = std::chrono::steady_clock::now() +
                  std::chrono::seconds(kChildTimeoutSeconds);
  while (!reaped) {
    char buffer[4096];
    for (;;) {
      ssize_t count = read(pipe_fds[0], buffer, sizeof(buffer));
      if (count <= 0) {
        break;
      }
      if (output.size() < kOutputLimit) {
        output.append(buffer, static_cast<size_t>(count));
      }
    }
    pid_t result = waitpid(pid, &status, WNOHANG);
    if (result == pid) {
      reaped = true;
      break;
    }
    if (std::chrono::steady_clock::now() >= deadline) {
      kill(pid, SIGKILL);
      waitpid(pid, &status, 0);
      timed_out = true;
      reaped = true;
      break;
    }
    usleep(10 * 1000);
  }
  char buffer[4096];
  for (;;) {
    ssize_t count = read(pipe_fds[0], buffer, sizeof(buffer));
    if (count <= 0) {
      break;
    }
    if (output.size() < kOutputLimit) {
      output.append(buffer, static_cast<size_t>(count));
    }
  }
  close(pipe_fds[0]);
  return {status, timed_out, output};
}

std::string real_executable(const char* value) {
  char resolved[PATH_MAX];
  if (realpath(value, resolved) != nullptr) {
    return resolved;
  }
  return value;
}

void print_sample(const std::string& output) {
  size_t start = output.rfind("MARK ");
  if (start == std::string::npos) {
    start = 0;
  }
  std::string sample = output.substr(start);
  if (sample.size() > 1000) {
    sample.resize(1000);
  }
  std::fprintf(stdout, "sample=%s\n", sample.c_str());
}

void parent_main(const std::string& executable) {
  const std::vector<std::pair<std::string, int>> variants = {
      {"cpu-managed-sync-array-first", 30},
      {"gpu-managed-current-data-access", 30},
      {"gpu-managed-get-default-stream-data_access", 30},
      {"gpu-managed-get-default-stream-operation", 30},
      {"gpu-managed-owned-stream-operation", 30},
      {"gpu-managed-explicit-sync-operation", 30},
      {"gpu-managed-reuse-operation", 30},
      {"gpu-managed-stream-first-operation", 30},
      {"gpu-managed-owner-first-operation", 30},
      {"gpu-managed-operation-array-first", 30},
      {"gpu-copy-backed-operation", 100},
      {"gpu-copy-backed-owned-stream-operation", 30},
  };
  mark("parent_matrix_begin");
  for (const auto& [variant, repeats] : variants) {
    int passed = 0;
    int exited_134 = 0;
    int signaled = 0;
    int other_failures = 0;
    int timeouts = 0;
    std::string first_failure;
    std::string first_pass;
    for (int iteration = 0; iteration < repeats; ++iteration) {
      ChildResult result = run_child(executable, variant);
      if (result.timed_out) {
        timeouts += 1;
      } else if (WIFEXITED(result.wait_status) && WEXITSTATUS(result.wait_status) == 0) {
        passed += 1;
        if (first_pass.empty()) {
          first_pass = result.output;
        }
      } else if (WIFEXITED(result.wait_status) && WEXITSTATUS(result.wait_status) == 134) {
        exited_134 += 1;
        if (first_failure.empty()) {
          first_failure = result.output;
        }
      } else if (WIFSIGNALED(result.wait_status)) {
        signaled += 1;
        if (first_failure.empty()) {
          first_failure = result.output;
        }
      } else {
        other_failures += 1;
        if (first_failure.empty()) {
          first_failure = result.output;
        }
      }
    }
    std::printf(
        "RESULT variant=%s repeats=%d passed=%d exit134=%d signaled=%d "
        "other_failures=%d timeouts=%d\n",
        variant.c_str(), repeats, passed, exited_134, signaled, other_failures,
        timeouts);
    if (!first_failure.empty()) {
      std::printf("FAILURE_EVIDENCE variant=%s\n", variant.c_str());
      print_sample(first_failure);
    } else if (!first_pass.empty()) {
      std::printf("PASS_EVIDENCE variant=%s\n", variant.c_str());
      print_sample(first_pass);
    }
  }
  mark("parent_matrix_end");
}

}  // namespace

int main(int argc, char** argv) {
  if (argc == 3 && std::strcmp(argv[1], "--child") == 0) {
    return child_main(argv[2]);
  }
  parent_main(real_executable(argv[0]));
  return 0;
}
