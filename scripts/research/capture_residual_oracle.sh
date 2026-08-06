#!/bin/sh

# Local-only ffn_inp-0 residual capture for Feature 005.
# Uses the same pinned llama.cpp revision and model identity as Feature 002.
# Strategy: single-target capture of ffn_inp-0 (dual-ask of ffn_inp+ffn_norm
# truncates the scheduled graph before ffn_norm). Pair with the Feature 002
# ffn_norm-0 freeze for residual MoE block parity.

set -eu
umask 077

pinned_revision=b06aa774c03dbbb624e726664b714a57d1f49815
pinned_model_name=Qwen3-30B-A3B-Q8_0.gguf
pinned_model_size=32483931648
pinned_model_sha256=4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c
pinned_ffn_norm_sha256=978205a61fb31d03a8627fd5b9c9319e4c32ef7af0d3d934ccaddda9defc68a7

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
capture_source="$script_dir/llama_capture/residual_inp_capture.cpp"

usage() {
    cat <<'EOF'
Usage: scripts/research/capture_residual_oracle.sh \
  --model ABSOLUTE_EXTERNAL_FILE \
  --llama-source ABSOLUTE_PINNED_LLAMA_CPP \
  --work-dir ABSOLUTE_EXTERNAL_DIRECTORY \
  --output-dir ABSOLUTE_EXTERNAL_DIRECTORY
EOF
}

fail() {
    echo "residual oracle capture: $1" >&2
    exit 2
}

model_path=
llama_source=
work_dir=
output_dir=

while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h) usage; exit 0 ;;
        --model|--llama-source|--work-dir|--output-dir)
            option=$1; shift
            [ "$#" -gt 0 ] || fail "an option is missing its value"
            case "$option" in
                --model) model_path=$1 ;;
                --llama-source) llama_source=$1 ;;
                --work-dir) work_dir=$1 ;;
                --output-dir) output_dir=$1 ;;
            esac
            shift
            ;;
        *) fail "unknown option" ;;
    esac
done

validate_lexical_path() {
    label=$1
    candidate=$2
    [ -n "$candidate" ] || fail "$label is required"
    case "$candidate" in /*) ;; *) fail "$label must be absolute" ;; esac
    case "$candidate" in /|*//*|*/.|*/..|*/./*|*/../*|*/)
        fail "$label must be a normalized absolute path" ;;
    esac
    candidate_folded=$(printf '%s' "$candidate" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    repository_folded=$(printf '%s' "$repository_root" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    case "$candidate_folded" in
        "$repository_folded"|"$repository_folded"/*)
            fail "$label must remain outside the repository" ;;
    esac
}

reject_symlink_components() {
    label=$1
    candidate=$2
    inspected=$candidate
    while [ "$inspected" != / ]; do
        if [ -L "$inspected" ]; then
            fail "$label has a symbolic-link component"
        fi
        inspected=${inspected%/*}
        [ -n "$inspected" ] || inspected=/
    done
}

sha256_file() {
    digest=$(shasum -a 256 "$1" 2>/dev/null | awk 'NR == 1 {print $1}') || return 1
    case "$digest" in *[!0-9a-f]*|'') return 1 ;; esac
    [ "${#digest}" -eq 64 ] || return 1
    printf '%s\n' "$digest"
}

file_metadata() {
    metadata=$(stat -f '%d:%i:%z' "$1" 2>/dev/null || stat -c '%d:%i:%s' "$1" 2>/dev/null) || return 1
    printf '%s\n' "$metadata" | LC_ALL=C grep -Eq '^[0-9]+:[0-9]+:[0-9]+$' || return 1
    printf '%s\n' "$metadata"
}

file_snapshot() {
    [ -f "$1" ] && [ ! -L "$1" ] || return 1
    metadata=$(file_metadata "$1") || return 1
    digest=$(sha256_file "$1") || return 1
    printf '%s:%s\n' "$metadata" "$digest"
}

validate_lexical_path model "$model_path"
validate_lexical_path llama-source "$llama_source"
validate_lexical_path work-dir "$work_dir"
validate_lexical_path output-dir "$output_dir"
case "${model_path##*/}" in "$pinned_model_name") ;; *) fail "model filename differs" ;; esac
reject_symlink_components model "$model_path"
reject_symlink_components llama-source "$llama_source"
reject_symlink_components work-dir "$work_dir"
reject_symlink_components output-dir "$output_dir"

[ -d "$work_dir" ] && [ ! -L "$work_dir" ] || fail "work-dir unavailable"
[ ! -e "$output_dir" ] || fail "output-dir already exists"
[ -f "$capture_source" ] && [ ! -L "$capture_source" ] || fail "capture source unavailable"
[ -d "$llama_source/.git" ] || fail "pinned source checkout unavailable"
actual_revision=$(git -C "$llama_source" rev-parse HEAD)
[ "$actual_revision" = "$pinned_revision" ] || fail "pinned source revision differs"
[ -z "$(git -C "$llama_source" status --porcelain --untracked-files=normal)" ] || fail "pinned source not clean"

[ -f "$model_path" ] && [ ! -L "$model_path" ] || fail "model unavailable"
admitted_model=$(file_snapshot "$model_path") || fail "model identity unavailable"
old_ifs=$IFS
IFS=:
set -- $admitted_model
IFS=$old_ifs
model_device=$1
model_inode=$2
actual_model_size=$3
actual_model_sha256=$4
[ "$actual_model_size" = "$pinned_model_size" ] || fail "model size differs"
[ "$actual_model_sha256" = "$pinned_model_sha256" ] || fail "model sha differs"

attempt_dir=$(mktemp -d "$work_dir/residual-inp-attempt.XXXXXXXX")
overlay_dir="$attempt_dir/source"
build_dir="$attempt_dir/build"
mkdir "$overlay_dir" "$build_dir"
cp "$capture_source" "$overlay_dir/residual_inp_capture.cpp"
cat >"$overlay_dir/CMakeLists.txt" <<'EOF'
cmake_minimum_required(VERSION 3.20)
project(pulsarmlx_residual_inp_capture LANGUAGES C CXX)
if(NOT IS_ABSOLUTE "${LLAMA_SOURCE_DIR}")
  message(FATAL_ERROR "LLAMA_SOURCE_DIR must be absolute")
endif()
set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(GGML_METAL OFF CACHE BOOL "" FORCE)
set(GGML_CUDA OFF CACHE BOOL "" FORCE)
set(GGML_HIP OFF CACHE BOOL "" FORCE)
set(GGML_MUSA OFF CACHE BOOL "" FORCE)
set(GGML_OPENCL OFF CACHE BOOL "" FORCE)
set(GGML_VULKAN OFF CACHE BOOL "" FORCE)
set(GGML_SYCL OFF CACHE BOOL "" FORCE)
set(GGML_RPC OFF CACHE BOOL "" FORCE)
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_COMMON OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(LLAMA_BUILD_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory("${LLAMA_SOURCE_DIR}" llama.cpp-build EXCLUDE_FROM_ALL)
add_executable(pulsarmlx-residual-inp-capture residual_inp_capture.cpp)
target_compile_features(pulsarmlx-residual-inp-capture PRIVATE cxx_std_17)
target_link_libraries(pulsarmlx-residual-inp-capture PRIVATE llama)
set_target_properties(pulsarmlx-residual-inp-capture PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
EOF

cmake_tool=$(command -v cmake)
"$cmake_tool" -S "$overlay_dir" -B "$build_dir" \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_SOURCE_DIR="$llama_source" \
    -DGGML_METAL=OFF -DGGML_CUDA=OFF \
    >"$attempt_dir/configure.log" 2>&1 || fail "configure failed"
"$cmake_tool" --build "$build_dir" --config Release --target pulsarmlx-residual-inp-capture --parallel 1 \
    >"$attempt_dir/build.log" 2>&1 || fail "build failed"

capture_helper="$build_dir/bin/pulsarmlx-residual-inp-capture"
[ -x "$capture_helper" ] || fail "helper unavailable"

capture_once() {
    attempt_id=$1
    GGML_SCHED_DEBUG=1 "$capture_helper" \
        --model "$model_path" \
        --model-device "$model_device" \
        --model-inode "$model_inode" \
        --model-size "$pinned_model_size" \
        --model-sha256 "$pinned_model_sha256" \
        --capture-output "$attempt_dir/residual-$attempt_id.f32le" \
        --record-output "$attempt_dir/capture-$attempt_id.json" \
        >"$attempt_dir/capture-$attempt_id.stdout" \
        2>"$attempt_dir/capture-$attempt_id.stderr" || fail "capture $attempt_id failed"
}

capture_once a
capture_once b

residual_a_sha=$(sha256_file "$attempt_dir/residual-a.f32le")
residual_b_sha=$(sha256_file "$attempt_dir/residual-b.f32le")
[ "$residual_a_sha" = "$residual_b_sha" ] || fail "independent residual captures differ"

mkdir "$output_dir"
cp "$attempt_dir/residual-a.f32le" "$output_dir/ffn_inp-0.f32le"
cp "$attempt_dir/capture-a.json" "$output_dir/capture-record-a.json"
cp "$attempt_dir/capture-b.json" "$output_dir/capture-record-b.json"
# Note expected ffn_norm freeze identity for pairing
cat >"$output_dir/capture-summary.json" <<EOF
{
  "feature_id": "005-moe-block",
  "source_revision": "$pinned_revision",
  "capture_strategy": "single_target_ffn_inp_plus_f002_ffn_norm_freeze",
  "residual_sha256": "$residual_a_sha",
  "ffn_norm_freeze_sha256": "$pinned_ffn_norm_sha256",
  "independent_captures": 2,
  "shape": [2, 2048],
  "dtype": "float32_little_endian",
  "direct_token_ids": [0, 1],
  "positions": [0, 1]
}
EOF

echo "residual oracle capture: installed ffn_inp-0 under $output_dir"
echo "residual_sha256=$residual_a_sha"
echo "pair_with_f002_ffn_norm_sha256=$pinned_ffn_norm_sha256"
