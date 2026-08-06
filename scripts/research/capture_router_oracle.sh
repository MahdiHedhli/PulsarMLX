#!/bin/sh

# Local-only orchestration for the independent Feature 002 CPU oracle.  This
# entry point consumes an operator-provided model and an already existing
# external llama.cpp checkout.  It contains no artifact-acquisition path.

set -eu
umask 077

pinned_revision=b06aa774c03dbbb624e726664b714a57d1f49815
pinned_model_name=Qwen3-30B-A3B-Q8_0.gguf
pinned_model_size=32483931648
pinned_model_sha256=4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c
pinned_python_version=3.12.13
pinned_numpy_version=2.4.5
pinned_pyyaml_version=6.0.3
pinned_tqdm_version=4.67.1
pinned_requests_version=2.32.5

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_root=$(CDPATH= cd -- "$script_dir/../.." && pwd)
capture_source="$script_dir/llama_capture/router_capture.cpp"
oracle_source="$script_dir/router_oracle.py"

usage() {
    cat <<'EOF'
Usage: scripts/research/capture_router_oracle.sh \
  --model ABSOLUTE_EXTERNAL_FILE \
  --work-dir ABSOLUTE_EXTERNAL_DIRECTORY \
  --output-dir ABSOLUTE_EXTERNAL_DIRECTORY

The work directory must already contain:
  llama.cpp/                 clean pinned source checkout
  oracle-python/bin/python   pinned CPython with NumPy, PyYAML, tqdm, requests

The command creates CPU-only build and attempt state below --work-dir and a
new append-only candidate below --output-dir. It never acquires a model or
creates a nested repository.
EOF
}

fail() {
    echo "router oracle capture: $1" >&2
    exit 2
}

model_path=
work_dir=
output_dir=

while [ "$#" -gt 0 ]; do
    case "$1" in
        --help|-h)
            usage
            exit 0
            ;;
        --model|--work-dir|--output-dir)
            option=$1
            shift
            [ "$#" -gt 0 ] || fail "an option is missing its value"
            case "$option" in
                --model) model_path=$1 ;;
                --work-dir) work_dir=$1 ;;
                --output-dir) output_dir=$1 ;;
            esac
            shift
            ;;
        *)
            fail "unknown option"
            ;;
    esac
done

validate_lexical_path() {
    label=$1
    candidate=$2
    [ -n "$candidate" ] || fail "$label is required"
    case "$candidate" in
        /*) ;;
        *) fail "$label must be absolute" ;;
    esac
    newline='
'
    case "$candidate" in
        *"$newline"*) fail "$label contains a control character" ;;
    esac
    if printf '%s' "$candidate" | LC_ALL=C grep -q '[[:cntrl:]]'; then
        fail "$label contains a control character"
    fi
    case "$candidate" in
        /|*//*|*/.|*/..|*/./*|*/../*|*/)
            fail "$label must be a normalized absolute path"
            ;;
    esac

    candidate_folded=$(printf '%s' "$candidate" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    repository_folded=$(printf '%s' "$repository_root" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    case "$candidate_folded" in
        "$repository_folded"|"$repository_folded"/*)
            fail "$label must remain outside the repository"
            ;;
    esac
}

paths_overlap() {
    first_folded=$(printf '%s' "$1" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    second_folded=$(printf '%s' "$2" | LC_ALL=C tr '[:upper:]' '[:lower:]')
    [ "$first_folded" = "$second_folded" ] && return 0
    case "$first_folded" in
        "$second_folded"/*) return 0 ;;
    esac
    case "$second_folded" in
        "$first_folded"/*) return 0 ;;
    esac
    return 1
}

require_disjoint() {
    if paths_overlap "$2" "$4"; then
        fail "$1 and $3 must not alias or contain one another"
    fi
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

validate_lexical_path model "$model_path"
validate_lexical_path work-dir "$work_dir"
validate_lexical_path output-dir "$output_dir"
require_disjoint model "$model_path" work-dir "$work_dir"
require_disjoint model "$model_path" output-dir "$output_dir"
require_disjoint work-dir "$work_dir" output-dir "$output_dir"

case "${model_path##*/}" in
    "$pinned_model_name") ;;
    *) fail "model filename differs from the admitted identity" ;;
esac

reject_symlink_components model "$model_path"
reject_symlink_components work-dir "$work_dir"
reject_symlink_components output-dir "$output_dir"

[ -d "$work_dir" ] && [ ! -L "$work_dir" ] || fail "work-dir is unavailable or unsafe"
[ ! -e "$output_dir" ] && [ ! -L "$output_dir" ] || fail "output-dir already exists or is unsafe"
[ -d "${output_dir%/*}" ] && [ ! -L "${output_dir%/*}" ] || fail "output-dir parent is unavailable or unsafe"
[ -f "$capture_source" ] && [ ! -L "$capture_source" ] || fail "capture helper source is unavailable"
[ -f "$oracle_source" ] && [ ! -L "$oracle_source" ] || fail "oracle source is unavailable"

llama_source="$work_dir/llama.cpp"
oracle_python=${PULSARMLX_ORACLE_PYTHON-"$work_dir/oracle-python/bin/python"}
validate_lexical_path llama-source "$llama_source"
validate_lexical_path oracle-python "$oracle_python"
reject_symlink_components llama-source "$llama_source"

[ -d "$llama_source/.git" ] && [ ! -L "$llama_source" ] && [ ! -L "$llama_source/.git" ] || fail "pinned source checkout is unavailable or unsafe"
[ -f "$llama_source/LICENSE" ] && [ ! -L "$llama_source/LICENSE" ] || fail "pinned source license is unavailable"
[ -x "$oracle_python" ] || fail "pinned oracle Python is unavailable"

actual_revision=$(git -C "$llama_source" rev-parse HEAD 2>/dev/null) || fail "pinned source revision cannot be read"
[ "$actual_revision" = "$pinned_revision" ] || fail "pinned source revision differs"
[ -z "$(git -C "$llama_source" status --porcelain --untracked-files=normal 2>/dev/null)" ] || fail "pinned source checkout is not clean"
source_origin=$(git -C "$llama_source" config --get remote.origin.url 2>/dev/null) || fail "pinned source origin cannot be read"
case "$source_origin" in
    https://github.com/ggml-org/llama.cpp|https://github.com/ggml-org/llama.cpp.git|git@github.com:ggml-org/llama.cpp.git|ssh://git@github.com/ggml-org/llama.cpp.git) ;;
    *) fail "pinned source origin differs" ;;
esac
LC_ALL=C grep -q '^MIT License$' "$llama_source/LICENSE" || fail "pinned source license differs"

sha256_file() {
    digest=$(shasum -a 256 "$1" 2>/dev/null | awk 'NR == 1 {print $1}') || return 1
    case "$digest" in
        *[!0-9a-f]*|'') return 1 ;;
    esac
    [ "${#digest}" -eq 64 ] || return 1
    printf '%s\n' "$digest"
}

file_metadata() {
    metadata=$(stat -f '%d:%i:%z' "$1" 2>/dev/null || stat -c '%d:%i:%s' "$1" 2>/dev/null) || return 1
    if ! printf '%s\n' "$metadata" | LC_ALL=C grep -Eq '^[0-9]+:[0-9]+:[0-9]+$'; then
        return 1
    fi
    printf '%s\n' "$metadata"
}

file_snapshot() {
    [ -f "$1" ] && [ ! -L "$1" ] || return 1
    metadata=$(file_metadata "$1") || return 1
    digest=$(sha256_file "$1") || return 1
    printf '%s:%s\n' "$metadata" "$digest"
}

verify_source_checkout() {
    [ "$(git -C "$llama_source" rev-parse HEAD 2>/dev/null)" = "$pinned_revision" ] || return 1
    [ "$(git -C "$llama_source" rev-parse 'HEAD^{tree}' 2>/dev/null)" = "$source_tree" ] || return 1
    [ -z "$(git -C "$llama_source" status --porcelain --untracked-files=all 2>/dev/null)" ] || return 1
}

source_tree=$(git -C "$llama_source" rev-parse 'HEAD^{tree}' 2>/dev/null) || fail "pinned source tree cannot be read"
verify_source_checkout || fail "pinned source changed during admission"
capture_source_sha256=$(sha256_file "$capture_source") || fail "capture helper source cannot be hashed"
oracle_source_sha256=$(sha256_file "$oracle_source") || fail "oracle source cannot be hashed"

# Fail before the first model stat/hash when the externally prepared oracle
# environment is incomplete or has drifted. gguf-py imports these declared
# runtime dependencies even though the bounded reader itself primarily uses
# NumPy; checking the complete pinned set prevents an expensive late failure.
PULSARMLX_PINNED_PYTHON_VERSION="$pinned_python_version" \
PULSARMLX_PINNED_NUMPY_VERSION="$pinned_numpy_version" \
PULSARMLX_PINNED_PYYAML_VERSION="$pinned_pyyaml_version" \
PULSARMLX_PINNED_TQDM_VERSION="$pinned_tqdm_version" \
PULSARMLX_PINNED_REQUESTS_VERSION="$pinned_requests_version" \
PYTHONPATH="$llama_source/gguf-py" \
"$oracle_python" - >/dev/null 2>&1 <<'PY' || fail "pinned oracle Python dependencies differ"
import importlib
import os
import platform

expected = {
    "numpy": os.environ["PULSARMLX_PINNED_NUMPY_VERSION"],
    "yaml": os.environ["PULSARMLX_PINNED_PYYAML_VERSION"],
    "tqdm": os.environ["PULSARMLX_PINNED_TQDM_VERSION"],
    "requests": os.environ["PULSARMLX_PINNED_REQUESTS_VERSION"],
}
if platform.python_version() != os.environ["PULSARMLX_PINNED_PYTHON_VERSION"]:
    raise SystemExit(2)
for module_name, version in expected.items():
    module = importlib.import_module(module_name)
    if str(getattr(module, "__version__", "")) != version:
        raise SystemExit(2)
gguf = importlib.import_module("gguf")
if not callable(getattr(gguf, "GGUFReader", None)):
    raise SystemExit(2)
PY

# Model I/O begins only after argument, alias, symlink, source, tool, and
# external dependency gates.
[ -f "$model_path" ] && [ ! -L "$model_path" ] && [ -r "$model_path" ] || fail "model is unavailable or unsafe"
admitted_model=$(file_snapshot "$model_path") || fail "model identity cannot be read"
old_ifs=$IFS
IFS=:
set -- $admitted_model
IFS=$old_ifs
[ "$#" -eq 4 ] || fail "model identity metadata is invalid"
model_device=$1
model_inode=$2
actual_model_size=$3
actual_model_sha256=$4
[ "$actual_model_size" = "$pinned_model_size" ] || fail "model byte size differs"
[ "$actual_model_sha256" = "$pinned_model_sha256" ] || fail "model SHA-256 differs"

attempt_dir=$(mktemp -d "$work_dir/router-capture-attempt.XXXXXXXX") || fail "external attempt state cannot be created"
reject_symlink_components generated-state "$attempt_dir"
[ -d "$attempt_dir" ] && [ ! -L "$attempt_dir" ] || fail "external attempt state is unsafe"
overlay_dir="$attempt_dir/source"
build_dir="$attempt_dir/build"
mkdir "$overlay_dir" "$build_dir" || fail "fresh attempt build directories cannot be created"

cp "$capture_source" "$overlay_dir/router_capture.cpp" || fail "capture source cannot be copied to attempt state"
cat >"$overlay_dir/CMakeLists.txt" <<'EOF'
cmake_minimum_required(VERSION 3.20)
project(pulsarmlx_router_capture LANGUAGES C CXX)

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
add_executable(pulsarmlx-router-capture router_capture.cpp)
target_compile_features(pulsarmlx-router-capture PRIVATE cxx_std_17)
target_link_libraries(pulsarmlx-router-capture PRIVATE llama)
set_target_properties(
  pulsarmlx-router-capture
  PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin"
)
EOF

overlay_source_sha256=$(sha256_file "$overlay_dir/router_capture.cpp") || fail "attempt capture source cannot be hashed"
[ "$overlay_source_sha256" = "$capture_source_sha256" ] || fail "attempt capture source differs"
cmake_lists_sha256=$(sha256_file "$overlay_dir/CMakeLists.txt") || fail "attempt CMake source cannot be hashed"

cmake_tool=$(command -v cmake 2>/dev/null) || fail "CMake is unavailable"
case "$cmake_tool" in /*) ;; *) fail "CMake path is not absolute" ;; esac
cmake_tool_sha256=$(sha256_file "$cmake_tool") || fail "CMake executable cannot be hashed"
cmake_version=$("$cmake_tool" --version 2>/dev/null | sed -n '1p')
[ -n "$cmake_version" ] || fail "CMake version cannot be read"

"$cmake_tool" -S "$overlay_dir" -B "$build_dir" \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_SOURCE_DIR="$llama_source" \
    -DGGML_METAL=OFF \
    -DGGML_CUDA=OFF \
    -DGGML_HIP=OFF \
    -DGGML_MUSA=OFF \
    -DGGML_OPENCL=OFF \
    -DGGML_VULKAN=OFF \
    -DGGML_SYCL=OFF \
    >"$attempt_dir/configure.log" 2>&1 || fail "CPU-only capture helper configuration failed"
"$cmake_tool" --build "$build_dir" --config Release --target pulsarmlx-router-capture --parallel 1 \
    >"$attempt_dir/build.log" 2>&1 || fail "CPU-only capture helper build failed"

capture_helper="$build_dir/bin/pulsarmlx-router-capture"
[ -x "$capture_helper" ] && [ ! -L "$capture_helper" ] || fail "CPU-only capture helper is unavailable"
verify_source_checkout || fail "pinned source changed during the build"
[ "$(sha256_file "$capture_source")" = "$capture_source_sha256" ] || fail "repository capture source changed during the build"
[ "$(sha256_file "$overlay_dir/router_capture.cpp")" = "$capture_source_sha256" ] || fail "attempt capture source changed during the build"

cmake_cache_sha256=$(sha256_file "$build_dir/CMakeCache.txt") || fail "CMake cache cannot be hashed"
configure_log_sha256=$(sha256_file "$attempt_dir/configure.log") || fail "configure log cannot be hashed"
build_log_sha256=$(sha256_file "$attempt_dir/build.log") || fail "build log cannot be hashed"
helper_identity=$(file_snapshot "$capture_helper") || fail "capture helper identity cannot be read"

cxx_tool=$(sed -n 's/^CMAKE_CXX_COMPILER:FILEPATH=//p' "$build_dir/CMakeCache.txt" | sed -n '1p')
[ -n "$cxx_tool" ] && [ -x "$cxx_tool" ] || fail "configured C++ compiler cannot be identified"
case "$cxx_tool" in /*) ;; *) fail "configured C++ compiler path is not absolute" ;; esac
cxx_tool_sha256=$(sha256_file "$cxx_tool") || fail "configured C++ compiler cannot be hashed"
cxx_version=$("$cxx_tool" --version 2>/dev/null | sed -n '1p')
[ -n "$cxx_version" ] || fail "configured C++ compiler version cannot be read"
build_tool=$(sed -n 's/^CMAKE_MAKE_PROGRAM:FILEPATH=//p' "$build_dir/CMakeCache.txt" | sed -n '1p')
[ -n "$build_tool" ] && [ -x "$build_tool" ] || fail "configured CMake build tool cannot be identified"
case "$build_tool" in /*) ;; *) fail "configured CMake build tool path is not absolute" ;; esac
build_tool_sha256=$(sha256_file "$build_tool") || fail "configured CMake build tool cannot be hashed"
build_tool_version=$("$build_tool" --version 2>/dev/null | sed -n '1p')
[ -n "$build_tool_version" ] || fail "configured CMake build tool version cannot be read"

capture_once() {
    attempt_id=$1
    capture_model_before=$(file_snapshot "$model_path") || fail "capture model pre-identity cannot be read"
    capture_helper_before=$(file_snapshot "$capture_helper") || fail "capture helper pre-identity cannot be read"
    [ "$capture_model_before" = "$admitted_model" ] || fail "capture model pre-identity differs"
    [ "$capture_helper_before" = "$helper_identity" ] || fail "capture helper pre-identity differs"
    GGML_SCHED_DEBUG=1 "$capture_helper" \
        --model "$model_path" \
        --model-device "$model_device" \
        --model-inode "$model_inode" \
        --model-size "$pinned_model_size" \
        --model-sha256 "$pinned_model_sha256" \
        --capture-output "$attempt_dir/capture-$attempt_id.f32le" \
        --record-output "$attempt_dir/capture-$attempt_id.json" \
        >"$attempt_dir/capture-$attempt_id.stdout" \
        2>"$attempt_dir/capture-$attempt_id.stderr" || fail "an independent CPU capture attempt failed"
    capture_model_after=$(file_snapshot "$model_path") || fail "capture model post-identity cannot be read"
    capture_helper_after=$(file_snapshot "$capture_helper") || fail "capture helper post-identity cannot be read"
    [ "$capture_model_after" = "$admitted_model" ] || fail "capture model post-identity differs"
    [ "$capture_helper_after" = "$helper_identity" ] || fail "capture helper post-identity differs"
}

capture_once a
capture_a_model_before=$capture_model_before
capture_a_model_after=$capture_model_after
capture_a_helper_before=$capture_helper_before
capture_a_helper_after=$capture_helper_after
capture_once b
capture_b_model_before=$capture_model_before
capture_b_model_after=$capture_model_after
capture_b_helper_before=$capture_helper_before
capture_b_helper_after=$capture_helper_after

verify_source_checkout || fail "pinned source changed during capture"
[ "$(sha256_file "$capture_source")" = "$capture_source_sha256" ] || fail "repository capture source changed during capture"
[ "$(sha256_file "$overlay_dir/router_capture.cpp")" = "$capture_source_sha256" ] || fail "attempt capture source changed during capture"
[ "$(file_snapshot "$capture_helper")" = "$helper_identity" ] || fail "capture helper changed during capture"

capture_provenance="$attempt_dir/capture-provenance.json"
PULSARMLX_PROVENANCE_OUTPUT="$capture_provenance" \
PULSARMLX_ADMITTED_MODEL="$admitted_model" \
PULSARMLX_CAPTURE_A_MODEL_BEFORE="$capture_a_model_before" \
PULSARMLX_CAPTURE_A_MODEL_AFTER="$capture_a_model_after" \
PULSARMLX_CAPTURE_A_HELPER_BEFORE="$capture_a_helper_before" \
PULSARMLX_CAPTURE_A_HELPER_AFTER="$capture_a_helper_after" \
PULSARMLX_CAPTURE_B_MODEL_BEFORE="$capture_b_model_before" \
PULSARMLX_CAPTURE_B_MODEL_AFTER="$capture_b_model_after" \
PULSARMLX_CAPTURE_B_HELPER_BEFORE="$capture_b_helper_before" \
PULSARMLX_CAPTURE_B_HELPER_AFTER="$capture_b_helper_after" \
PULSARMLX_SOURCE_TREE="$source_tree" \
PULSARMLX_CAPTURE_SOURCE_SHA256="$capture_source_sha256" \
PULSARMLX_OVERLAY_SOURCE_SHA256="$overlay_source_sha256" \
PULSARMLX_CMAKE_LISTS_SHA256="$cmake_lists_sha256" \
PULSARMLX_CMAKE_CACHE_SHA256="$cmake_cache_sha256" \
PULSARMLX_CONFIGURE_LOG_SHA256="$configure_log_sha256" \
PULSARMLX_BUILD_LOG_SHA256="$build_log_sha256" \
PULSARMLX_CMAKE_VERSION="$cmake_version" \
PULSARMLX_CMAKE_SHA256="$cmake_tool_sha256" \
PULSARMLX_CXX_VERSION="$cxx_version" \
PULSARMLX_CXX_SHA256="$cxx_tool_sha256" \
PULSARMLX_BUILD_TOOL_VERSION="$build_tool_version" \
PULSARMLX_BUILD_TOOL_SHA256="$build_tool_sha256" \
PULSARMLX_HELPER_IDENTITY="$helper_identity" \
"$oracle_python" - <<'PY'
import json
import os
from pathlib import Path

def identity(name):
    device, inode, size, digest = os.environ[name].split(":")
    return {
        "device": int(device),
        "inode": int(inode),
        "size_bytes": int(size),
        "sha256": digest,
    }

helper = identity("PULSARMLX_HELPER_IDENTITY")
document = {
    "schema": "pulsarmlx.research.router-capture-provenance",
    "schema_version": "1.0.0",
    "binding_strategy": "pre_post_full_sha256_plus_device_inode_size",
    "admitted_model": identity("PULSARMLX_ADMITTED_MODEL"),
    "build": {
        "attempt_scoped_fresh": True,
        "source_revision": "b06aa774c03dbbb624e726664b714a57d1f49815",
        "source_tree": os.environ["PULSARMLX_SOURCE_TREE"],
        "source_clean_before": True,
        "source_clean_after": True,
        "capture_source_repository_sha256": os.environ["PULSARMLX_CAPTURE_SOURCE_SHA256"],
        "capture_source_overlay_sha256": os.environ["PULSARMLX_OVERLAY_SOURCE_SHA256"],
        "cmake_lists_sha256": os.environ["PULSARMLX_CMAKE_LISTS_SHA256"],
        "cmake_cache_sha256": os.environ["PULSARMLX_CMAKE_CACHE_SHA256"],
        "configure_log_sha256": os.environ["PULSARMLX_CONFIGURE_LOG_SHA256"],
        "build_log_sha256": os.environ["PULSARMLX_BUILD_LOG_SHA256"],
        "configure_command": "cmake -S $ATTEMPT_SOURCE -B $ATTEMPT_BUILD -DCMAKE_BUILD_TYPE=Release -DLLAMA_SOURCE_DIR=$PINNED_LLAMA_CPP -DGGML_METAL=OFF -DGGML_CUDA=OFF -DGGML_HIP=OFF -DGGML_MUSA=OFF -DGGML_OPENCL=OFF -DGGML_VULKAN=OFF -DGGML_SYCL=OFF",
        "build_command": "cmake --build $ATTEMPT_BUILD --config Release --target pulsarmlx-router-capture --parallel 1",
        "tools": [
            {"name": "cmake", "version": os.environ["PULSARMLX_CMAKE_VERSION"], "executable_sha256": os.environ["PULSARMLX_CMAKE_SHA256"]},
            {"name": "cxx", "version": os.environ["PULSARMLX_CXX_VERSION"], "executable_sha256": os.environ["PULSARMLX_CXX_SHA256"]},
            {"name": "cmake-build-tool", "version": os.environ["PULSARMLX_BUILD_TOOL_VERSION"], "executable_sha256": os.environ["PULSARMLX_BUILD_TOOL_SHA256"]},
        ],
        "helper": helper,
    },
    "consumers": [],
}
for suffix, consumer_id in (("A", "capture-a"), ("B", "capture-b")):
    document["consumers"].append({
        "consumer_id": consumer_id,
        "model_before": identity(f"PULSARMLX_CAPTURE_{suffix}_MODEL_BEFORE"),
        "model_after": identity(f"PULSARMLX_CAPTURE_{suffix}_MODEL_AFTER"),
        "helper_before": identity(f"PULSARMLX_CAPTURE_{suffix}_HELPER_BEFORE"),
        "helper_after": identity(f"PULSARMLX_CAPTURE_{suffix}_HELPER_AFTER"),
    })
output = Path(os.environ["PULSARMLX_PROVENANCE_OUTPUT"])
with output.open("x", encoding="utf-8") as destination:
    json.dump(document, destination, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True)
    destination.write("\n")
PY
[ -f "$capture_provenance" ] && [ ! -L "$capture_provenance" ] || fail "capture provenance cannot be created"

output_parent=${output_dir%/*}
candidate_dir=$(mktemp -d "$output_parent/.pulsarmlx-router-oracle.XXXXXXXX") || fail "sibling oracle candidate cannot be created"
reject_symlink_components candidate-state "$candidate_dir"
[ -d "$candidate_dir" ] && [ ! -L "$candidate_dir" ] || fail "sibling oracle candidate is unsafe"
oracle_model_before=$(file_snapshot "$model_path") || fail "oracle model pre-identity cannot be read"
[ "$oracle_model_before" = "$admitted_model" ] || fail "oracle model pre-identity differs"
PYTHONPATH="$llama_source/gguf-py" "$oracle_python" "$oracle_source" \
    --model "$model_path" \
    --source-dir "$llama_source" \
    --capture-a "$attempt_dir/capture-a.f32le" \
    --capture-a-record "$attempt_dir/capture-a.json" \
    --capture-a-scheduler-trace "$attempt_dir/capture-a.stderr" \
    --capture-b "$attempt_dir/capture-b.f32le" \
    --capture-b-record "$attempt_dir/capture-b.json" \
    --capture-b-scheduler-trace "$attempt_dir/capture-b.stderr" \
    --capture-provenance "$capture_provenance" \
    --output "$candidate_dir/oracle.json" || fail "independent scalar oracle validation failed"
oracle_model_after=$(file_snapshot "$model_path") || fail "oracle model post-identity cannot be read"
[ "$oracle_model_after" = "$admitted_model" ] || fail "oracle model post-identity differs"
[ "$(sha256_file "$oracle_source")" = "$oracle_source_sha256" ] || fail "oracle source changed during execution"
verify_source_checkout || fail "pinned source changed during oracle execution"

execution_provenance="$candidate_dir/execution-provenance.json"
PULSARMLX_EXECUTION_OUTPUT="$execution_provenance" \
PULSARMLX_ORACLE_MODEL_BEFORE="$oracle_model_before" \
PULSARMLX_ORACLE_MODEL_AFTER="$oracle_model_after" \
PULSARMLX_ORACLE_SOURCE_SHA256="$oracle_source_sha256" \
PULSARMLX_CAPTURE_PROVENANCE_SHA256="$(sha256_file "$capture_provenance")" \
PULSARMLX_ORACLE_DOCUMENT_SHA256="$(sha256_file "$candidate_dir/oracle.json")" \
"$oracle_python" - <<'PY'
import json
import os
from pathlib import Path

def identity(name):
    device, inode, size, digest = os.environ[name].split(":")
    return {
        "device": int(device),
        "inode": int(inode),
        "size_bytes": int(size),
        "sha256": digest,
    }

document = {
    "schema": "pulsarmlx.research.router-oracle-execution-provenance",
    "schema_version": "1.0.0",
    "binding_strategy": "pre_post_full_sha256_plus_device_inode_size",
    "oracle_process_consumer": {
        "consumer_id": "oracle-process",
        "model_before": identity("PULSARMLX_ORACLE_MODEL_BEFORE"),
        "model_after": identity("PULSARMLX_ORACLE_MODEL_AFTER"),
    },
    "oracle_source_sha256": os.environ["PULSARMLX_ORACLE_SOURCE_SHA256"],
    "capture_provenance_sha256": os.environ["PULSARMLX_CAPTURE_PROVENANCE_SHA256"],
    "oracle_document_sha256": os.environ["PULSARMLX_ORACLE_DOCUMENT_SHA256"],
}
output = Path(os.environ["PULSARMLX_EXECUTION_OUTPUT"])
with output.open("x", encoding="utf-8") as destination:
    json.dump(document, destination, allow_nan=False, ensure_ascii=True, indent=2, sort_keys=True)
    destination.write("\n")
PY
[ -f "$execution_provenance" ] && [ ! -L "$execution_provenance" ] || fail "execution provenance cannot be created"

install -m 600 "$attempt_dir/capture-a.f32le" "$candidate_dir/capture-a.f32le" || fail "first bounded capture cannot be staged"
install -m 600 "$attempt_dir/capture-a.json" "$candidate_dir/capture-a.json" || fail "first capture record cannot be staged"
install -m 600 "$attempt_dir/capture-b.f32le" "$candidate_dir/capture-b.f32le" || fail "second bounded capture cannot be staged"
install -m 600 "$attempt_dir/capture-b.json" "$candidate_dir/capture-b.json" || fail "second capture record cannot be staged"
install -m 600 "$capture_provenance" "$candidate_dir/capture-provenance.json" || fail "capture provenance cannot be staged"

PYTHONPATH="$script_dir" \
PULSARMLX_TRACE_A_SOURCE="$attempt_dir/capture-a.stderr" \
PULSARMLX_TRACE_A_DESTINATION="$candidate_dir/capture-a.scheduler-trace.txt" \
PULSARMLX_TRACE_B_SOURCE="$attempt_dir/capture-b.stderr" \
PULSARMLX_TRACE_B_DESTINATION="$candidate_dir/capture-b.scheduler-trace.txt" \
"$oracle_python" - <<'PY'
import os
from pathlib import Path
from router_oracle import retain_scheduler_trace

for attempt in ("A", "B"):
    retain_scheduler_trace(
        Path(os.environ[f"PULSARMLX_TRACE_{attempt}_SOURCE"]),
        Path(os.environ[f"PULSARMLX_TRACE_{attempt}_DESTINATION"]),
    )
PY

PYTHONPATH="$script_dir" \
PULSARMLX_CANDIDATE_DIRECTORY="$candidate_dir" \
PULSARMLX_FINAL_DIRECTORY="$output_dir" \
"$oracle_python" - <<'PY'
import os
from pathlib import Path
from router_oracle import (
    publish_oracle_candidate,
    validate_oracle_candidate_bundle,
    write_oracle_candidate_manifest,
)

candidate = Path(os.environ["PULSARMLX_CANDIDATE_DIRECTORY"])
destination = Path(os.environ["PULSARMLX_FINAL_DIRECTORY"])
write_oracle_candidate_manifest(candidate)
validate_oracle_candidate_bundle(candidate)
publish_oracle_candidate(candidate, destination)
PY

[ -d "$output_dir" ] && [ ! -L "$output_dir" ] || fail "atomic oracle publication did not appear"

echo "router oracle capture: two CPU captures and one scalar oracle passed"
