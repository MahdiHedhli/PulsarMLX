# Validation Evidence Reviewer Index

This directory contains the committed evidence for the Apple Silicon MLX
bring-up. The JSON artifacts are authoritative; this file is a navigation and
boundary index. A `passed` result applies only to the exact input, command,
commit, platform, and execution depth in its record. Synthetic, bounded
real-model, giant-model, Linux/CUDA, serving, and performance evidence do not
imply one another.

Command references `C01` through `C42` below reproduce the exact command text
stored in the records. They are historical evidence commands, not an
instruction to rerun downloads or hardware-sensitive model work without the
recorded prerequisites and authorization.

## Primary record index

| Stable ID and kind | Recorded status | Immutable input identity | Oracle or reference | Actual result | Command refs | Artifact |
| --- | --- | --- | --- | --- | --- | --- |
| `implementation-baseline-2026-08-05` — workspace baseline | `passed` at commit `372b9dd433f61e17048e75eda9505dd65e263275` | No dedicated `input_identity` field; the input is the repository at the recorded commit | No numerical oracle field; command exit status and test assertions are the checks | Workspace check passed; workspace tests reported 32 passed and 0 failed | C01–C02 | [implementation-baseline.json](implementation-baseline.json) |
| `apple-mlx-initial-benchmark-v1` — benchmark decision | `not_run` at commit `7c16dc0fa1d92d0f7160118b97d49020d10b35a7` | No benchmark input was selected | No benchmark oracle or bound correctness prerequisite because no case was selected | Zero samples, no statistics, and no performance claim | None — explicitly not run | [benchmark-initial.json](benchmark-initial.json) |
| `linux-cuda-shared-boundary` — platform boundary | `unavailable_unverified` at commit `8abdfe0450e9cfa44ef7d6e52c58e7f58f74e4fd` | Tested commit plus upstream merge base `183a54bd707ad086ecfa380aee48142c89cd3305`; no model input | Static upstream comparison only; no Linux/CUDA runtime oracle | Linux and CUDA commands selected zero relevant tests on macOS; static source checks passed; supported Linux/CUDA execution was not run | C03–C10; N01–N05 not run | [linux-cuda-shared-boundary.json](linux-cuda-shared-boundary.json) |
| `mlx-device-smoke` — evaluated device record | `passed`, device state `evaluated`, at commit `4ff4301af56904d4125f72ebeddee60e13f706d0` | Fixture `nonsymmetric-f32-matmul-v1`, float32 shapes `[2,3] × [3,2]`, explicit `apple-mlx`/`gpu` | `hard-coded-scalar:nonsymmetric-f32-matmul-v1` | Evaluated and synchronized GPU result `[58,64,139,154]`; 4 compared, zero error, no fallback | C11–C15 | [mlx-device-smoke.json](mlx-device-smoke.json) |
| `mlx-tensor-fixtures` — fixture-set record | `passed` at commit `c53f21e7c98bfa2288690a3662c6f6e10857a685` | `mlx-tensor-fixtures-v1` in `fixtures/mlx/manifest.json` at the tested commit | Each embedded case names `committed-independent-scalar-v1` | Seven evaluated and synchronized MLX cases passed; workspace result recorded as 114 passed and 0 failed | C16–C22 | [mlx-tensor-fixtures.json](mlx-tensor-fixtures.json) |
| `qwen3-30b-a3b-q8_0-candidate-v1` — model compatibility/admission | `artifact_identity_and_required_slice_inventory_verified`; explicitly not model execution | Official `Qwen/Qwen3-30B-A3B-GGUF` revision `e4d4bafdfb96a411a163846265362aceb0b9c63a`, filename `Qwen3-30B-A3B-Q8_0.gguf`, 32,483,931,648 bytes, SHA-256 `4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c` | No output oracle in this admission record; it links the separately frozen oracle record | Public provenance, complete local identity, required metadata, tensor range, and Q8_0 role were verified; no model output was produced | C23–C28; inventory has no standalone command field | [qwen3-30b-a3b-q8_0-compatibility.json](models/qwen3-30b-a3b-q8_0-compatibility.json) |
| `qwen3-30b-a3b-q8_0-first-expert-matvec-memory-budget-v1` — admission budget | `admitted_pre_download`; the later T055 update records rechecked gates but no execution | Same immutable Qwen artifact identity and one gate-projection expert-0, rows 0–15, 2,048-column Q8_0 matvec scope | No correctness oracle; this is a conservative resource gate | Disk and unified-memory gates passed for the bounded scope only; the record did not establish runtime memory use or correctness | C29–C31 | [qwen3-30b-a3b-q8_0-memory-budget.json](models/qwen3-30b-a3b-q8_0-memory-budget.json) |
| `qwen3-30b-a3b-q8_0-blk0-gate-expert0-prefix-oracle-v1` — oracle contract | `frozen_not_executed` | Artifact SHA-256 `4ad960…743c`, tensor `blk.0.ffn_gate_exps.weight`, prompt SHA-256 `e55164…14bd`, activation SHA-256 `382179…a92e` | `ggml-org/llama.cpp` `gguf-py` at revision `b06aa774c03dbbb624e726664b714a57d1f49815`; tolerances fixed before Apple output | The oracle, deterministic input, bounded output, and comparison policy were frozen; this contract itself contains no executed result | Embedded 216-line recipe only; execution is C32 in the result record | [qwen3-30b-a3b-q8_0-oracle.json](models/qwen3-30b-a3b-q8_0-oracle.json) |
| `qwen3-30b-a3b-q8_0-blk0-gate-expert0-prefix-v1` — trusted-reference result | `passed` at commit `fc77d57b8542757c238c637718712ba99fcc2ffd` | Artifact, encoded slice, prompt, and activation hashes recorded in `input_identity` | Frozen oracle contract Git blob `fe3eed5c3bb3a86b67b06d30afe88504af420814`; oracle script SHA-256 `9ae200…8092` | 16 reference values; output SHA-256 `610357…b51`; scalar/NumPy self-check passed with zero mismatches | C32 | [qwen3-30b-a3b-q8_0-reference-result.json](models/qwen3-30b-a3b-q8_0-reference-result.json) |
| `portable-expert-source` — portable storage record | `passed` at commit `8abdfe0450e9cfa44ef7d6e52c58e7f58f74e4fd` | Deterministic ranges and temporary shard bytes encoded by the committed `positional_source` test suite; no dedicated input-ID field | Test expectations are the exact byte/range/ownership oracle | 14 portable-source tests passed; one stream library test passed; recorded workspace result was 140 passed and 0 failed | C33–C37 | [portable-expert-source.json](portable-expert-source.json) |
| `portable-expert-source-replay-v1` — independent reproduction and final story gate | Replay `passed` at commit `0cf71ba8dd4ffc66c6e49c3dfa0cd9d23dbb04a7`; final story gate `passed` at commit `e0b965233a7cd1aa111d8f061b5b125cfcb326e3` | The same committed `positional_source` test target for replay; final gate uses the recorded clean repository commit and all 13 evidence JSON documents | The source record's exact 14-test result; typed schema tests and cross-record identity assertions for the final gate | Replay: 14 passed, 0 failed, 0 ignored. Final gate: 25 typed evidence tests and 1 reference parser test passed; 171 workspace tests passed, 1 ignored, 0 failed | C43; final commands are embedded in the record | [reproduction-check.json](reproduction-check.json) |
| `qwen3-30b-a3b-q8_0-blk0-gate-expert0-prefix-v1` — bounded Apple result | `passed` at source commit `5db6bdf1069785aee8ed2682cd18110df9bbeb84` | Same artifact, prompt, activation, encoded-slice, and decoded-slice hashes as the trusted reference | `gguf-py` reference revision `b06aa774c03dbbb624e726664b714a57d1f49815`, output SHA-256 `610357…b51` | 16 MLX values; zero mismatches; max absolute error `1.6093254089355469e-6`; max relative error `1.7527402999126447e-6`; later workspace gate recorded 154 active passes and 1 ignored | C38–C41 | [qwen3-30b-a3b-q8_0-slice.json](qwen3-30b-a3b-q8_0-slice.json) |
| `synthetic-routed-moe` — synthetic routed-MoE record | `passed` at commit `8abdfe0450e9cfa44ef7d6e52c58e7f58f74e4fd` | Fixture `synthetic-routed-moe-v1` at `fixtures/mlx/routed-moe-v1.json` in the tested commit | `committed-scalar-routed-moe-v1` | 4 compared values; max absolute error `4.759696965450644e-7`; max relative error `1.1697127408636623e-7`; evaluated and synchronized on GPU | C42 | [synthetic-moe-v1.json](synthetic-moe-v1.json) |

The trusted-reference and bounded Apple rows intentionally share the same
case ID because they are the two sides of one comparison. Their record kinds
and artifact paths distinguish them.

## Embedded case index

These cases live inside the device or tensor-set records rather than in
standalone JSON files. Their exact execution commands are C13 and C20.

| Stable case ID | Operation and immutable input locator | Oracle | Actual bounded result | Artifact |
| --- | --- | --- | --- | --- |
| `nonsymmetric-f32-matmul-v1` | Embedded nonsymmetric float32 fixture at commit `4ff4301af56904d4125f72ebeddee60e13f706d0` | `hard-coded-scalar:nonsymmetric-f32-matmul-v1` | 4 values matched exactly; evaluated, synchronized, no fallback | [mlx-device-smoke.json](mlx-device-smoke.json) |
| `elementwise-fma-nonsymmetric-f32-v1` | `elementwise_fma`; `mlx-tensor-fixtures-v1` manifest at commit `c53f21e7c98bfa2288690a3662c6f6e10857a685` | `committed-independent-scalar-v1` | Passed; 6 values; max absolute/relative error 0 | [mlx-tensor-fixtures.json](mlx-tensor-fixtures.json) |
| `matmul-nonsymmetric-f32-v1` | `matmul`; same fixture set and commit | `committed-independent-scalar-v1` | Passed; 4 values; max absolute/relative error 0 | [mlx-tensor-fixtures.json](mlx-tensor-fixtures.json) |
| `embedding-gather-order-f32-v1` | `embedding_gather`; same fixture set and commit | `committed-independent-scalar-v1` | Passed; 9 values; exact comparison, max error 0 | [mlx-tensor-fixtures.json](mlx-tensor-fixtures.json) |
| `rms-norm-weighted-f32-v1` | `rms_norm`; same fixture set and commit | `committed-independent-scalar-v1` | Passed; 8 values; max absolute error `5.258477320246868e-8` | [mlx-tensor-fixtures.json](mlx-tensor-fixtures.json) |
| `residual-add-nonsymmetric-f32-v1` | `residual_add`; same fixture set and commit | `committed-independent-scalar-v1` | Passed; 6 values; max absolute/relative error 0 | [mlx-tensor-fixtures.json](mlx-tensor-fixtures.json) |
| `router-topk-tie-f32-v1` | `router_topk_softmax`; same fixture set and commit | `committed-independent-scalar-v1` | Passed; 4 weights and exact selected IDs; max absolute error `6.977297206667289e-8` | [mlx-tensor-fixtures.json](mlx-tensor-fixtures.json) |
| `q8-0-two-block-row-v1` | `q8_0_decode_dot`; same fixture set and commit | `committed-independent-scalar-v1` | Passed; 64 decoded values and one dot result; max error 0 | [mlx-tensor-fixtures.json](mlx-tensor-fixtures.json) |

## Warnings and exclusions index

| Stable ID | Recorded warnings | Recorded exclusions or claim boundary |
| --- | --- | --- |
| `implementation-baseline-2026-08-05` | Warnings are nested per command: one inherited `unused_mut` and 13 inherited macOS serve dead-code warnings | No MLX execution; no Linux/CUDA/io_uring runtime; selected engine/kernel/server targets had no runtime tests |
| `apple-mlx-initial-benchmark-v1` | The record is not benchmark evidence and cannot support a performance claim | No command, workload, samples, statistics, timing, cache/storage, memory, thermal/power, Linux/CUDA, giant-model, or serving performance result |
| `linux-cuda-shared-boundary` | Zero-test exit codes are not passes; static review is not runtime parity; Linux helpers may skip; inherited short-payload behavior remains unresolved | No supported Linux, io_uring, O_DIRECT, or CUDA execution. `cross_platform_safe` remains false |
| `mlx-device-smoke` | Inherited quant and serve warnings | No model, quantized operation, generation, serving, Linux, or CUDA execution |
| `mlx-tensor-fixtures` | Inherited quant and serve warnings | Synthetic bounded tensors only; scoped Q8_0 roles; no real model, generation, serving, benchmark, Linux, or CUDA execution |
| `qwen3-30b-a3b-q8_0-candidate-v1` | No top-level `warnings` field | Identity/inventory only. No router, full expert/layer/model, attention, tokenization, logits, generation, serving, performance, oracle execution, or Apple execution claim |
| `qwen3-30b-a3b-q8_0-first-expert-matvec-memory-budget-v1` | No top-level `warnings` field; point-in-time pressure and disk caveats are stored under `observation` | Budget/admission only; no model-run gauges, correctness, full or giant inference, serving, or performance claim |
| `qwen3-30b-a3b-q8_0-blk0-gate-expert0-prefix-oracle-v1` | No top-level `warnings` field | Frozen contract, not an executed oracle or reproducibility result; no Apple/model-depth/serving/performance claim |
| `qwen3-30b-a3b-q8_0-blk0-gate-expert0-prefix-v1` — reference | Prompt uses a transparent SHA-256 probe adapter; the reference is CPU-only | One tensor, one expert, rows 0–15 only; no Apple result before reference, routing, full graph, generation, serving, or benchmark |
| `portable-expert-source` | Empty warning list | Portable macOS source only; no inherited Linux fetcher, 32-bit allocation branch, model, MLX graph, serving, or benchmark execution |
| `portable-expert-source-replay-v1` | Empty warning list; later clean commit used with unchanged relevant source files | Portable-source replay only; no inherited Linux fetcher, 32-bit branch, MLX, model, serving, or performance execution |
| `qwen3-30b-a3b-q8_0-blk0-gate-expert0-prefix-v1` — Apple | Linux/CUDA not established; inherited workspace warnings are retained in the post-slice gate | Prompt adapter is not tokenization; no router, full expert/layer/model, attention, logits, tokens, generation, serving, benchmark, or giant-model proof |
| `synthetic-routed-moe` | Linux/CUDA not established | Synthetic float32 fixture only; no model weights, tokenizer, model loader, generation, or serving; only the recorded two-token route |

## Exact command catalog

### Workspace, Linux/CUDA boundary, and device records

```sh
# C01
cargo check --workspace --all-targets
# C02
cargo test --workspace --no-fail-fast

# C03
cargo test -p stream --test linux_uring_preservation
# C04
cargo test --release -q -p kernels -- --test-threads=1
# C05
git diff --exit-code upstream/main...8abdfe0 -- crates/engine crates/kernels crates/stream/Cargo.toml
# C06
git diff upstream/main...8abdfe0 -- crates/stream/src/lib.rs
# C07
rustc --print cfg | rg '^(target_arch|target_os|target_env|target_vendor)'
# C08
git diff --exit-code upstream/main...HEAD -- crates/engine crates/kernels crates/tokenizer crates/gguf crates/stream/Cargo.toml
# C09
git diff --name-status upstream/main...HEAD -- Cargo.toml crates/quant crates/stream crates/serve/src/main.rs crates/backend crates/mlx-backend python fixtures
# C10
git diff --name-status 8abdfe0..HEAD -- crates python fixtures Cargo.toml Cargo.lock pyproject.toml uv.lock

# C11
PYTHONPATH=python uv run python -m unittest discover -s python/pulsar_mlx_worker/tests -v
# C12
cargo test -p mlx-backend --test worker_contract
# C13
cargo run -p mlx-backend --bin pulsar-mlx -- device-smoke --backend apple-mlx --device gpu --evidence docs/validation/mlx-device-smoke.json
# C14
cargo check --workspace --all-targets
# C15
cargo test --workspace --no-fail-fast
```

Commands explicitly recorded as not run on the required environment:

```sh
# N01 — not_run_on_required_environment
cargo test -p stream --test linux_uring_preservation
# N02 — not_run_on_required_environment
cargo test --release -p kernels -- --test-threads=1
# N03 — not_run_unavailable
cargo test -p kernels -- --ignored --test-threads=1
# N04 — not_run_unavailable
scripts/check.sh
# N05 — not_run_unavailable
scripts/check.sh MODEL.gguf
```

### Tensor fixtures

```sh
# C16
cargo test -p backend
# C17
cargo test -p quant --test q8_0_reference
# C18
PYTHONPATH=python uv run python -m unittest discover -s python/pulsar_mlx_worker/tests -v
# C19
cargo test -p mlx-backend --test tensor_contract
# C20
cargo run -p mlx-backend --bin pulsar-mlx -- validate-fixtures --manifest fixtures/mlx/manifest.json --evidence docs/validation/mlx-tensor-fixtures.json
# C21
cargo check --workspace --all-targets
# C22
cargo test --workspace --no-fail-fast
```

### Qwen admission and resource records

```sh
# C23
curl -fsSL 'https://huggingface.co/api/models/Qwen/Qwen3-30B-A3B-GGUF/revision/e4d4bafdfb96a411a163846265362aceb0b9c63a?blobs=true' | jq '{id, sha, private, gated, disabled, tags, cardData: {license: .cardData.license}, gguf_architecture: .gguf.architecture, target_sibling: (.siblings[] | select(.rfilename == "Qwen3-30B-A3B-Q8_0.gguf"))}'
# C24
curl -fsSL 'https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF/raw/e4d4bafdfb96a411a163846265362aceb0b9c63a/README.md' | rg -n -C 1 'Number of Parameters|Number of Layers|Number of Experts|Activated Experts|license:'
# C25
curl -fsSL 'https://huggingface.co/Qwen/Qwen3-30B-A3B-GGUF/raw/e4d4bafdfb96a411a163846265362aceb0b9c63a/LICENSE' | sed -n '1,12p'
# C26
HF_XET_HIGH_PERFORMANCE=1 HF_HOME=<external-cache> uvx --from huggingface_hub hf download Qwen/Qwen3-30B-A3B-GGUF Qwen3-30B-A3B-Q8_0.gguf --revision e4d4bafdfb96a411a163846265362aceb0b9c63a --local-dir <external-dir>
# C27
stat -f '%N %z bytes' <external-file>/Qwen3-30B-A3B-Q8_0.gguf
# C28
shasum -a 256 <external-file>/Qwen3-30B-A3B-Q8_0.gguf

# C29
sysctl -n hw.memsize
# C30
memory_pressure -Q
# C31
df -k .
```

The compatibility record describes its read-only pinned `gguf-py` inventory
operation but does not store that operation as a standalone shell command.
The oracle contract stores an exact 216-line recipe under
`exact_reproduction`; its status is `frozen_not_executed`. The first recorded
execution of that recipe is C32.

### Trusted reference, portable source, Apple slice, and synthetic MoE

```sh
# C32
set -o pipefail
jq -j '.exact_reproduction.oracle_shell_lines | join("\n"), "\n"' \
  docs/validation/models/qwen3-30b-a3b-q8_0-oracle.json |
  env PULSARMLX_ORACLE_ROOT=<external-oracle> \
      PULSARMLX_MODEL_GGUF=<external-model>/Qwen3-30B-A3B-Q8_0.gguf \
      /bin/zsh > <external-capture>/stdout.json \
      2> <external-capture>/stderr.txt

# C33
cargo test -p stream --test positional_source
# C34
cargo check -p stream --test positional_source
# C35
cargo test -p stream --lib
# C36
cargo check --workspace --all-targets
# C37
cargo test --workspace --no-fail-fast

# C38
cargo run --release -p mlx-backend --bin pulsar-mlx -- validate-model-slice --model <external-model>/Qwen3-30B-A3B-Q8_0.gguf --evidence docs/validation/qwen3-30b-a3b-q8_0-slice.json
# C39
cargo check --workspace --all-targets
# C40
cargo test --workspace --no-fail-fast
# C41
cargo test --workspace -- --list | rg ': test$' | wc -l

# C42
cargo run -p mlx-backend --bin pulsar-mlx -- validate-synthetic-moe --fixture fixtures/mlx/routed-moe-v1.json --evidence docs/validation/synthetic-moe-v1.json

# C43
cargo test -p stream --test positional_source
```

## Schema notes

- Stable IDs come from `case_id`, `record_id`, `validation`, or embedded
  `cases[].case_id`, depending on the record generation. The source field is
  preserved rather than normalized in the JSON.
- Older workspace, device, tensor, storage, and Linux/CUDA records do not all
  contain dedicated top-level `input_identity`, `oracle_identity`,
  `actual_values_or_bounded_summary`, `warnings`, or `exclusions` fields. This
  index points to their recorded fixture IDs, tested commits, embedded
  comparisons, command results, boundary objects, and claim-policy fields; it
  does not manufacture missing schema fields.
- `frozen_not_executed`, `admitted_pre_download`, `unavailable_unverified`,
  `zero_tests`, `not_run`, and `not_run_*` remain non-success execution states
  even when an associated static check, admission gate, or correctness record
  passed.
- External model and oracle locations use committed placeholders such as
  `<external-model>` and `<external-oracle>`. No private local path is included
  here, and model weights remain outside Git.
- Full warning, failure, memory-gauge, comparison, and exclusion detail remains
  in each linked JSON artifact.
