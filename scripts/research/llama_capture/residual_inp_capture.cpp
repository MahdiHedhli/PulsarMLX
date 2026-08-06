// PulsarMLX Feature 005: pinned CPU-only ffn_inp-0 residual capture helper.
//
// This source is compiled only inside an external, exact-revision llama.cpp
// checkout.  The no-header branch intentionally remains buildable so fixture
// CI can syntax-check this committed source without acquiring third-party
// sources.  It cannot produce a capture.

#if defined(__has_include)
#  if __has_include("llama.h") && __has_include("ggml.h") && __has_include("ggml-backend.h")
#    define PULSARMLX_HAS_PINNED_LLAMA_HEADERS 1
#  endif
#endif

#ifndef PULSARMLX_HAS_PINNED_LLAMA_HEADERS

#include <cstdio>

int main() {
    std::fputs(
        "residual-inp capture: unavailable: pinned llama.cpp headers are required\n",
        stderr);
    return 2;
}

#else

#include "ggml-backend.h"
#include "ggml.h"
#include "llama.h"

#if defined(GGML_USE_CUDA) || defined(GGML_USE_HIP) || defined(GGML_USE_METAL) || \
    defined(GGML_USE_MUSA) || defined(GGML_USE_OPENCL) || defined(GGML_USE_SYCL) || \
    defined(GGML_USE_VULKAN)
#error "router_capture.cpp must be built by the frozen CPU-only configuration"
#endif

#include <cmath>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <limits>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {

constexpr std::string_view kPinnedRevision =
    "b06aa774c03dbbb624e726664b714a57d1f49815";
constexpr std::string_view kModelFilename = "Qwen3-30B-A3B-Q8_0.gguf";
constexpr std::uintmax_t kModelSize = 32483931648ULL;
constexpr std::string_view kModelSha256 =
    "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c";
constexpr std::string_view kTargetName = "ffn_inp-0";
constexpr std::size_t kRows = 2;
constexpr std::size_t kHiddenWidth = 2048;
constexpr std::size_t kFloatCount = kRows * kHiddenWidth;
constexpr std::size_t kByteCount = kFloatCount * sizeof(float);
constexpr std::size_t kMaximumLaterNodes = 8;
constexpr std::string_view kSchedulerTraceBegin =
    "PULSARMLX_SCHED_TRACE_BEGIN_V1";
constexpr std::string_view kSchedulerTraceEnd =
    "PULSARMLX_SCHED_TRACE_END_V1";

struct Arguments {
    std::filesystem::path model;
    std::filesystem::path capture_output;
    std::filesystem::path record_output;
    std::uintmax_t model_device = 0;
    std::uintmax_t model_inode = 0;
    std::uintmax_t model_size = 0;
    std::string model_sha256;
    bool has_model_device = false;
    bool has_model_inode = false;
    bool has_model_size = false;
};

struct ModelIdentity {
    std::uintmax_t device = 0;
    std::uintmax_t inode = 0;
    std::uintmax_t size = 0;
};

struct CaptureState {
    std::vector<float> values = std::vector<float>(kFloatCount);
    std::size_t target_ask_count = 0;
    std::size_t target_observation_count = 0;
    std::size_t abort_callback_call_count = 0;
    std::size_t abort_callback_calls_after_target = 0;
    std::size_t abort_callback_true_count = 0;
    bool target_complete = false;
    bool callback_returned_false = false;
    bool abort_guard_armed = false;
    bool overflowed_trace = false;
    std::vector<std::string> nodes_after_target;
};

int fail(const char * message) {
    std::fprintf(stderr, "residual-inp capture: %s\n", message);
    return 2;
}

bool host_is_little_endian() {
    const std::uint16_t value = 1;
    return *reinterpret_cast<const std::uint8_t *>(&value) == 1;
}

bool path_is_safe_absolute(const std::filesystem::path & path) {
    if (!path.is_absolute() || path.empty() || path.lexically_normal() != path) {
        return false;
    }
    std::filesystem::path current;
    for (const auto & component : path) {
        current /= component;
        std::error_code error;
        const auto status = std::filesystem::symlink_status(current, error);
        if (!error && std::filesystem::is_symlink(status)) {
            return false;
        }
    }
    return true;
}

bool parse_uintmax(const char * text, std::uintmax_t & result) {
    if (text == nullptr || *text == '\0' || *text == '-') {
        return false;
    }
    errno = 0;
    char * end = nullptr;
    const std::uintmax_t parsed = std::strtoull(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0') {
        return false;
    }
    result = parsed;
    return true;
}

bool parse_arguments(int argc, char ** argv, Arguments & result) {
    if (argc == 2 && (std::strcmp(argv[1], "--help") == 0 ||
                      std::strcmp(argv[1], "-h") == 0)) {
        std::fputs(
            "Usage: pulsarmlx-residual-inp-capture --model ABSOLUTE_FILE "
            "--model-device UINT --model-inode UINT --model-size UINT "
            "--model-sha256 HEX --capture-output ABSOLUTE_FILE "
            "--record-output ABSOLUTE_FILE\n",
            stdout);
        std::exit(0);
    }
    for (int index = 1; index < argc; index += 2) {
        if (index + 1 >= argc) {
            return false;
        }
        const std::string_view option(argv[index]);
        const std::filesystem::path value(argv[index + 1]);
        if (option == "--model") {
            if (!result.model.empty()) {
                return false;
            }
            result.model = value;
        } else if (option == "--model-device") {
            if (result.has_model_device ||
                !parse_uintmax(argv[index + 1], result.model_device)) {
                return false;
            }
            result.has_model_device = true;
        } else if (option == "--model-inode") {
            if (result.has_model_inode ||
                !parse_uintmax(argv[index + 1], result.model_inode)) {
                return false;
            }
            result.has_model_inode = true;
        } else if (option == "--model-size") {
            if (result.has_model_size ||
                !parse_uintmax(argv[index + 1], result.model_size)) {
                return false;
            }
            result.has_model_size = true;
        } else if (option == "--model-sha256") {
            if (!result.model_sha256.empty()) {
                return false;
            }
            result.model_sha256 = argv[index + 1];
        } else if (option == "--capture-output") {
            if (!result.capture_output.empty()) {
                return false;
            }
            result.capture_output = value;
        } else if (option == "--record-output") {
            if (!result.record_output.empty()) {
                return false;
            }
            result.record_output = value;
        } else {
            return false;
        }
    }
    return !result.model.empty() && !result.capture_output.empty() &&
           !result.record_output.empty() && result.has_model_device &&
           result.has_model_inode && result.has_model_size &&
           result.model_sha256 == kModelSha256;
}

bool inspect_model_identity(
    const std::filesystem::path & path,
    ModelIdentity & identity) {
    struct stat metadata {};
    if (::lstat(path.c_str(), &metadata) != 0 || !S_ISREG(metadata.st_mode) ||
        metadata.st_size < 0) {
        return false;
    }
    identity.device = static_cast<std::uintmax_t>(metadata.st_dev);
    identity.inode = static_cast<std::uintmax_t>(metadata.st_ino);
    identity.size = static_cast<std::uintmax_t>(metadata.st_size);
    return true;
}

bool model_identity_matches(
    const ModelIdentity & identity,
    const Arguments & arguments) {
    return identity.device == arguments.model_device &&
           identity.inode == arguments.model_inode &&
           identity.size == arguments.model_size &&
           identity.size == kModelSize;
}

bool write_exclusive(
    const std::filesystem::path & destination,
    const void * data,
    std::size_t byte_count) {
    const int descriptor = ::open(
        destination.c_str(),
        O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW,
        S_IRUSR | S_IWUSR);
    if (descriptor < 0) {
        return false;
    }
    const auto * cursor = static_cast<const std::uint8_t *>(data);
    std::size_t remaining = byte_count;
    bool passed = true;
    while (remaining > 0) {
        const ssize_t written = ::write(descriptor, cursor, remaining);
        if (written < 0 && errno == EINTR) {
            continue;
        }
        if (written <= 0) {
            passed = false;
            break;
        }
        cursor += static_cast<std::size_t>(written);
        remaining -= static_cast<std::size_t>(written);
    }
    if (passed && ::fsync(descriptor) != 0) {
        passed = false;
    }
    if (::close(descriptor) != 0) {
        passed = false;
    }
    return passed;
}

bool capture_abort_callback(void * user_data) {
    auto * state = static_cast<CaptureState *>(user_data);
    ++state->abort_callback_call_count;
    if (!state->abort_guard_armed) {
        return false;
    }
    ++state->abort_callback_calls_after_target;
    ++state->abort_callback_true_count;
    return true;
}

bool capture_eval_callback(ggml_tensor * tensor, bool ask, void * user_data) {
    auto * state = static_cast<CaptureState *>(user_data);
    const char * raw_name = tensor == nullptr ? nullptr : tensor->name;
    const std::string_view name = raw_name == nullptr ? std::string_view() : raw_name;

    if (state->target_complete) {
        if (state->nodes_after_target.size() < kMaximumLaterNodes) {
            state->nodes_after_target.emplace_back(name);
        } else {
            state->overflowed_trace = true;
        }
        return false;
    }
    if (name != kTargetName) {
        return false;
    }
    if (ask) {
        ++state->target_ask_count;
        return true;
    }

    ++state->target_observation_count;
    if (tensor->type != GGML_TYPE_F32 ||
        tensor->ne[0] != static_cast<std::int64_t>(kHiddenWidth) ||
        tensor->ne[1] != static_cast<std::int64_t>(kRows) ||
        tensor->ne[2] != 1 || tensor->ne[3] != 1 ||
        ggml_nelements(tensor) != static_cast<std::int64_t>(kFloatCount) ||
        ggml_nbytes(tensor) != kByteCount || tensor->buffer == nullptr) {
        state->callback_returned_false = true;
        state->abort_guard_armed = true;
        return false;
    }

    // The scheduler invokes this non-ask callback only after the requested
    // tensor is complete.  backend_tensor_get synchronizes the CPU value into
    // the bounded owned buffer before cancellation is armed.
    ggml_backend_tensor_get(tensor, state->values.data(), 0, kByteCount);
    state->target_complete = true;
    state->callback_returned_false = true;
    state->abort_guard_armed = true;
    return false;
}

std::string json_quoted(std::string_view value) {
    static constexpr char kHex[] = "0123456789abcdef";
    std::string result;
    result.reserve(value.size() + 2);
    result.push_back('"');
    for (const unsigned char byte : value) {
        switch (byte) {
            case '"': result += "\\\""; break;
            case '\\': result += "\\\\"; break;
            case '\b': result += "\\b"; break;
            case '\f': result += "\\f"; break;
            case '\n': result += "\\n"; break;
            case '\r': result += "\\r"; break;
            case '\t': result += "\\t"; break;
            default:
                if (byte < 0x20U) {
                    result += "\\u00";
                    result.push_back(kHex[(byte >> 4U) & 0x0fU]);
                    result.push_back(kHex[byte & 0x0fU]);
                } else {
                    result.push_back(static_cast<char>(byte));
                }
                break;
        }
    }
    result.push_back('"');
    return result;
}

std::string capture_record_json(
    const CaptureState & state,
    int decode_status,
    const ModelIdentity & model_identity) {
    // Hashes are intentionally computed by the separately committed Python
    // oracle from the exact f32le bytes.  The C++ helper records only the
    // frozen input/callback contract and observed cancellation state.
    std::string result;
    result.reserve(1400);
    result += "{\n";
    result += "  \"source_revision\": \"" + std::string(kPinnedRevision) + "\",\n";
    result += "  \"capture_node\": \"ffn_inp-0\",\n";
    result += "  \"shape\": [2, 2048],\n";
    result += "  \"dtype\": \"float32_little_endian\",\n";
    result += "  \"direct_token_ids\": [0, 1],\n";
    result += "  \"positions\": [0, 1],\n";
    result += "  \"context\": 2,\n";
    result += "  \"batch\": 2,\n";
    result += "  \"ubatch\": 2,\n";
    result += "  \"threads\": 1,\n";
    result += "  \"input_adapter\": \"direct_token_ids_v1\",\n";
    result += "  \"tokenizer\": \"not_used_direct_token_ids\",\n";
    result += "  \"canonical_byte_length\": 16384,\n";
    result += "  \"model_identity\": {\n";
    result += "    \"device\": " + std::to_string(model_identity.device) + ",\n";
    result += "    \"inode\": " + std::to_string(model_identity.inode) + ",\n";
    result += "    \"size_bytes\": " + std::to_string(model_identity.size) + ",\n";
    result += "    \"sha256\": \"" + std::string(kModelSha256) + "\",\n";
    result += "    \"pre_post_match\": true\n";
    result += "  },\n";
    result += "  \"decode_status\": " + std::to_string(decode_status) + ",\n";
    result += "  \"cancellation\": {\n";
    result += "    \"backend\": \"cpu\",\n";
    result += "    \"scheduler_trace_format\": "
              "\"ggml_sched_debug_marker_v1\",\n";
    result += "    \"target\": \"ffn_inp-0\",\n";
    result += "    \"target_ask_count\": " +
              std::to_string(state.target_ask_count) + ",\n";
    result += "    \"target_observation_count\": " +
              std::to_string(state.target_observation_count) + ",\n";
    result += std::string("    \"target_complete\": ") +
              (state.target_complete ? "true" : "false") + ",\n";
    result += std::string("    \"callback_returned_false\": ") +
              (state.callback_returned_false ? "true" : "false") + ",\n";
    result += std::string("    \"abort_guard_armed\": ") +
              (state.abort_guard_armed ? "true" : "false") + ",\n";
    result += "    \"abort_callback_call_count\": " +
              std::to_string(state.abort_callback_call_count) + ",\n";
    result += "    \"abort_callback_calls_after_target\": " +
              std::to_string(state.abort_callback_calls_after_target) + ",\n";
    result += "    \"abort_callback_true_count\": " +
              std::to_string(state.abort_callback_true_count) + ",\n";
    result += "    \"nodes_after_target\": [";
    for (std::size_t index = 0; index < state.nodes_after_target.size(); ++index) {
        if (index != 0) {
            result += ", ";
        }
        result += json_quoted(state.nodes_after_target[index]);
    }
    result += "]\n";
    result += "  }\n";
    result += "}\n";
    return result;
}

bool rows_are_distinct(const std::vector<float> & values) {
    return std::memcmp(
               values.data(),
               values.data() + kHiddenWidth,
               kHiddenWidth * sizeof(float)) != 0;
}

} // namespace

int main(int argc, char ** argv) {
    Arguments arguments;
    if (!parse_arguments(argc, argv, arguments)) {
        return fail("usage error");
    }
    if (!host_is_little_endian()) {
        return fail("little-endian host is required");
    }
    const char * scheduler_debug = std::getenv("GGML_SCHED_DEBUG");
    if (scheduler_debug == nullptr || std::strcmp(scheduler_debug, "1") != 0) {
        return fail("GGML_SCHED_DEBUG=1 is required for the capture proof");
    }
    if (!path_is_safe_absolute(arguments.model) ||
        !path_is_safe_absolute(arguments.capture_output) ||
        !path_is_safe_absolute(arguments.record_output) ||
        arguments.model == arguments.capture_output ||
        arguments.model == arguments.record_output ||
        arguments.capture_output == arguments.record_output) {
        return fail("an input or output path is unsafe");
    }
    if (arguments.model.filename().string() != std::string(kModelFilename)) {
        return fail("model filename differs from the admitted identity");
    }
    ModelIdentity model_identity_before;
    if (!inspect_model_identity(arguments.model, model_identity_before) ||
        !model_identity_matches(model_identity_before, arguments)) {
        return fail("model file identity is unavailable");
    }
    if (std::filesystem::exists(arguments.capture_output) ||
        std::filesystem::exists(arguments.record_output)) {
        return fail("an append-only output already exists");
    }

    llama_backend_init();
    llama_model_params model_parameters = llama_model_default_params();
    model_parameters.n_gpu_layers = 0;
    model_parameters.split_mode = LLAMA_SPLIT_MODE_NONE;
    model_parameters.main_gpu = 0;
    model_parameters.tensor_split = nullptr;
    model_parameters.load_mode = LLAMA_LOAD_MODE_MMAP;
    model_parameters.check_tensors = true;

    llama_model * model = llama_model_load_from_file(arguments.model.c_str(), model_parameters);
    if (model == nullptr) {
        llama_backend_free();
        return fail("CPU-only model load failed");
    }
    const llama_vocab * vocab = llama_model_get_vocab(model);
    if (vocab == nullptr || llama_vocab_n_tokens(vocab) <= 1) {
        llama_model_free(model);
        llama_backend_free();
        return fail("direct token IDs are outside the observed vocabulary");
    }

    CaptureState capture;
    llama_context_params context_parameters = llama_context_default_params();
    context_parameters.n_ctx = 2;
    context_parameters.n_batch = 2;
    context_parameters.n_ubatch = 2;
    context_parameters.n_seq_max = 1;
    context_parameters.n_threads = 1;
    context_parameters.n_threads_batch = 1;
    context_parameters.embeddings = false;
    context_parameters.offload_kqv = false;
    context_parameters.op_offload = false;
    context_parameters.flash_attn_type = LLAMA_FLASH_ATTN_TYPE_DISABLED;
    context_parameters.cb_eval = capture_eval_callback;
    context_parameters.cb_eval_user_data = &capture;
    context_parameters.abort_callback = capture_abort_callback;
    context_parameters.abort_callback_data = &capture;

    llama_context * context = llama_init_from_model(model, context_parameters);
    if (context == nullptr) {
        llama_model_free(model);
        llama_backend_free();
        return fail("CPU-only context creation failed");
    }

    llama_batch batch = llama_batch_init(2, 0, 1);
    batch.n_tokens = 2;
    for (int index = 0; index < 2; ++index) {
        batch.token[index] = static_cast<llama_token>(index);
        batch.pos[index] = index;
        batch.n_seq_id[index] = 1;
        batch.seq_id[index][0] = 0;
        batch.logits[index] = 0;
    }
    std::fprintf(stderr, "%.*s\n", static_cast<int>(kSchedulerTraceBegin.size()),
                 kSchedulerTraceBegin.data());
    std::fflush(stderr);
    const int decode_status = llama_decode(context, batch);
    std::fprintf(stderr, "%.*s\n", static_cast<int>(kSchedulerTraceEnd.size()),
                 kSchedulerTraceEnd.data());
    std::fflush(stderr);
    llama_batch_free(batch);

    llama_free(context);
    llama_model_free(model);
    llama_backend_free();

    ModelIdentity model_identity_after;
    if (!inspect_model_identity(arguments.model, model_identity_after) ||
        !model_identity_matches(model_identity_after, arguments) ||
        model_identity_after.device != model_identity_before.device ||
        model_identity_after.inode != model_identity_before.inode ||
        model_identity_after.size != model_identity_before.size) {
        return fail("model file identity changed during capture");
    }

    if (decode_status != 0 || !capture.target_complete ||
        !capture.callback_returned_false || !capture.abort_guard_armed ||
        capture.abort_callback_call_count == 0 ||
        capture.abort_callback_calls_after_target != 0 ||
        capture.abort_callback_true_count != 0 ||
        capture.target_ask_count != 1 ||
        capture.target_observation_count != 1 || capture.overflowed_trace ||
        !capture.nodes_after_target.empty()) {
        return fail("ffn_inp-0 cancellation proof is incomplete");
    }
    for (float value : capture.values) {
        if (!std::isfinite(value)) {
            return fail("captured ffn_inp-0 contains a non-finite value");
        }
    }
    if (!rows_are_distinct(capture.values)) {
        return fail("captured ffn_inp-0 rows are identical");
    }

    if (!write_exclusive(
            arguments.capture_output,
            capture.values.data(),
            kByteCount)) {
        return fail("bounded capture output cannot be installed");
    }
    const std::string record = capture_record_json(
        capture,
        decode_status,
        model_identity_before);
    if (record.size() > 4096 || !write_exclusive(
                                  arguments.record_output,
                                  record.data(),
                                  record.size())) {
        return fail("bounded capture record cannot be installed");
    }

    std::fputs("residual capture: captured one bounded CPU ffn_inp-0 value\n", stdout);
    return 0;
}

#endif
