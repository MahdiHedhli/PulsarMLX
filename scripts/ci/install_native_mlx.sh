#!/usr/bin/env bash
# Build the exact official MLX/MLX C sources qualified by Feature 017.
set -euo pipefail

readonly MLX_COMMIT="68cf2fddd8de5edd8ab3d926391772b2e2cedad8"
readonly MLX_C_COMMIT="0726ca922fc902c4c61ef9c27d94132be418e945"
readonly PREFIX="${1:?usage: install_native_mlx.sh INSTALL_PREFIX}"
readonly WORK_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/pulsar-native-mlx-source"

rm -rf "${WORK_ROOT}"
mkdir -p "${WORK_ROOT}" "${PREFIX}"

if ! xcrun -sdk macosx metal --version >/dev/null 2>&1; then
  xcodebuild -downloadComponent MetalToolchain
fi
xcrun -sdk macosx metal --version >/dev/null

git clone --filter=blob:none --no-checkout https://github.com/ml-explore/mlx.git "${WORK_ROOT}/mlx"
git -C "${WORK_ROOT}/mlx" checkout --detach "${MLX_COMMIT}"
test "$(git -C "${WORK_ROOT}/mlx" rev-parse HEAD)" = "${MLX_COMMIT}"

cmake -S "${WORK_ROOT}/mlx" -B "${WORK_ROOT}/mlx-build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
  -DCMAKE_INSTALL_RPATH="${PREFIX}/lib" \
  -DBUILD_SHARED_LIBS=ON \
  -DMLX_BUILD_TESTS=OFF \
  -DMLX_BUILD_EXAMPLES=OFF \
  -DMLX_BUILD_BENCHMARKS=OFF \
  -DMLX_BUILD_PYTHON_BINDINGS=OFF \
  -DMLX_BUILD_GGUF=OFF \
  -DMLX_BUILD_SAFETENSORS=OFF
cmake --build "${WORK_ROOT}/mlx-build" --target install --parallel 3

git clone --filter=blob:none --no-checkout https://github.com/ml-explore/mlx-c.git "${WORK_ROOT}/mlx-c"
git -C "${WORK_ROOT}/mlx-c" checkout --detach "${MLX_C_COMMIT}"
test "$(git -C "${WORK_ROOT}/mlx-c" rev-parse HEAD)" = "${MLX_C_COMMIT}"

# Match the official Homebrew mlx-c 0.6.0_2 recipe qualified on ColPanicM2.
while read -r commit expected_sha; do
  patch_file="${WORK_ROOT}/mlx-c-${commit}.patch"
  curl -fsSL \
    "https://github.com/ml-explore/mlx-c/commit/${commit}.patch?full_index=1" \
    -o "${patch_file}"
  printf '%s  %s\n' "${expected_sha}" "${patch_file}" | shasum -a 256 -c -
  git -C "${WORK_ROOT}/mlx-c" apply "${patch_file}"
done <<'PATCHES'
1e3c24ffebfdfbeecca054c51637fc4381d98aab 24831d5bc44b72a0fd027572a4e4eaf754ed9805ffed86185bb8dbdfb6284818
89d3454ac3f46ff68668dd9f7817c6d47650e47c 411749fd1908fdee783c3b378471603606852ce3a0ee0011ca5b66f47187b9d3
782d4712862b247a094086419ce130fd82cf3c53 4469b3ec2836efeadce98a192ae26f423cdbbd182edcd2126f4a6ef36891ce58
fba4470b89073180056c9ea46c443051375f7399 5102eafc68ea94cbe8cabb4acaa9905e17d1c92cb6a1b8c7f0f73dc863c09609
PATCHES

cmake -S "${WORK_ROOT}/mlx-c" -B "${WORK_ROOT}/mlx-c-build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX="${PREFIX}" \
  -DCMAKE_INSTALL_RPATH="${PREFIX}/lib" \
  -DCMAKE_PREFIX_PATH="${PREFIX}" \
  -DBUILD_SHARED_LIBS=ON \
  -DMLX_C_BUILD_EXAMPLES=OFF \
  -DMLX_C_USE_SYSTEM_MLX=ON
cmake --build "${WORK_ROOT}/mlx-c-build" --target install --parallel 3

test -f "${PREFIX}/include/mlx/c/mlx.h"
test -f "${PREFIX}/lib/libmlxc.dylib"
test -f "${PREFIX}/lib/libmlx.dylib"

printf 'native-mlx-prefix=%s\nmlx-commit=%s\nmlx-c-commit=%s\n' \
  "${PREFIX}" "${MLX_COMMIT}" "${MLX_C_COMMIT}"
