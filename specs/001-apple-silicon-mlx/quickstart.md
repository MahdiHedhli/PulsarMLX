# Validation Quickstart: Apple Silicon MLX Backend Bring-Up

**Status**: The Cargo baseline, pinned worker environment, protocol/lifecycle
tests, evaluated MLX GPU device smoke, seven tensor fixtures, strict Q8_0
references, portable positional storage, synthetic routed-MoE graph, and one
exact external Qwen checkpoint prefix are runnable and verified at their
documented scopes. The initial benchmark is explicitly `not_run`; complete
model inference, giant-model execution, and production serving are unsupported.

## 1. Inspect the current source of truth

From the repository root:

```sh
pwd
cat .specify/feature.json
sed -n '1,240p' specs/001-apple-silicon-mlx/spec.md
sed -n '1,260p' specs/001-apple-silicon-mlx/plan.md
sed -n '1,320p' specs/001-apple-silicon-mlx/tasks.md
```

Spec Kit project health:

```sh
specify version
specify check
specify integration status
.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

The active feature directory is recorded in `.specify/feature.json`; no nested
Git repository is used.

## 2. Re-establish the verified Cargo baseline

These are current repository commands:

```sh
uname -m
sw_vers
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
```

The final US5 record in `docs/validation/reproduction-check.json` shows that
both commands passed from clean commit `e0b9652`. That snapshot listed 172
tests: 171 active tests passed, one native MLX smoke test was ignored by the
general workspace run, and zero failed. Treat those counts as committed
historical evidence, not a hard-coded expectation for a later commit; always
report the new actual result.

The following are diagnostic inspections, not current merge gates:

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
```

Known upstream debt is documented, but a new error caused by the current slice
must be fixed or the slice stopped.

## 3. Confirm MLX prerequisites before installation

Do this at the start of the implementation session, before modifying source:

```sh
uname -m
sw_vers -productVersion
python3 --version
python3 -c 'import platform; print(platform.machine())'
df -h .
```

Phase-one MLX support requires all of:

- native `arm64` shell and Python process on Apple Silicon;
- macOS 14 or newer;
- native CPython 3.10 or newer with a published `mlx==0.32.0` arm64 wheel; and
- enough disk and unified-memory headroom for the bounded fixture.

Stop and create a blocked validation record if a prerequisite fails. Do not
install a source build or switch silently to CPU to bypass it.

## 4. Create the pinned project environment

The project commits `pyproject.toml` and `uv.lock`. Create only a
repository-local environment:

```sh
uv sync --frozen
.venv/bin/python -c 'from importlib.metadata import version; print(version("mlx"))'
```

The printed version must be exactly `0.32.0`. `.venv/` is local state and is
not committed. Setup validation resolved CPython 3.12.13 and native
`macosx_26_0_arm64` MLX/MLX-Metal wheels; this proves reproducible packaging,
not Metal availability or evaluated GPU execution. If a later frozen sync
cannot resolve a matching arm64 wheel, stop.

Foundational backend-neutral contracts are independently runnable:

```sh
cargo test -p backend
cargo clippy -p backend --all-targets -- -D warnings
```

The implementation checkpoint passed 32 focused tests covering explicit
selection and immutable device states, checked tensor semantics, bounded
comparisons, compatibility/evidence invariants, independent memory gauges, and
correctness-gated benchmarks. These are semantic contract tests and do not
execute MLX.

## 5. Run the verified worker contract tests

```sh
PYTHONPATH=python uv run python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
cargo test -p mlx-backend --test worker_contract
```

The complete Python discovery command passed 44 tests at T060. The focused
Rust fake-worker record passed 12 tests at the US1 checkpoint. They cover
version negotiation, frame limits, request IDs, malformed messages, stdout
contamination, worker exit/timeout, controlled shutdown, and structured errors
without a model file. Later test additions may change cardinality; retain the
exact command and report its actual count.

## 6. Reproduce evaluated GPU execution

```sh
cargo run -p mlx-backend --bin pulsar-mlx -- device-smoke \
  --backend apple-mlx \
  --device gpu \
  --evidence "${TMPDIR:-/tmp}/pulsarmlx-device-smoke.json"
```

The committed record at `docs/validation/mlx-device-smoke.json` shows native
arm64 Python 3.12.13, MLX 0.32.0, Metal and one GPU, explicit `apple-mlx`/`gpu`
selection, evaluated and synchronized nonsymmetric float32 matmul, exact
oracle parity over four values, and no fallback. An import-only or CPU result
is not a pass.

Stop if the report is not `evaluated` or if the numeric assertion fails.

## 7. Reproduce verified tensor and Q8_0 semantics

```sh
cargo test -p backend
cargo test -p quant --test q8_0_reference
cargo test -p mlx-backend --test tensor_contract
cargo run -p mlx-backend --bin pulsar-mlx -- validate-fixtures \
  --manifest fixtures/mlx/manifest.json \
  --evidence "${TMPDIR:-/tmp}/pulsarmlx-tensor-fixtures.json"
```

On tested commit `c53f21e`, these commands pass 14 strict Q8_0 tests, 7 Rust
fixture contract tests, and 7 evaluated MLX cases. Review exact shape,
orientation, input/accumulation/output dtype, encoded byte count,
malformed-input rejection, synchronization, compared element count, maximum
absolute/relative errors, and first mismatch in
`docs/validation/mlx-tensor-fixtures.json`. Tolerances are committed in
`fixtures/mlx/manifest.json`; do not tune them after observing output.

## 8. Reproduce verified portable expert storage

```sh
cargo test -p stream --test positional_source
cargo check -p stream --test positional_source
cargo test -p stream --lib
```

The committed [portable-source record](../../docs/validation/portable-expert-source.json)
shows 14 positional-source tests and one stream library test passing. The suite
covers single and split shards, exact boundaries, invalid layouts,
below/end/overflow/straddle ranges, partial reads, interruption, truncation,
batch ordering, all-or-error behavior, and owned-payload lifetime. The
independent [reproduction record](../../docs/validation/reproduction-check.json)
replayed the 14-test command with matching cardinality.

This verifies the additive portable macOS source. The inherited Linux
`io_uring` fetcher remains selected by static review, but suitable Linux,
`io_uring`, `O_DIRECT`, and CUDA runtime validation was unavailable and remains
unverified.

## 9. Reproduce the verified synthetic routed-MoE layer

```sh
cargo run -p mlx-backend --bin pulsar-mlx -- validate-synthetic-moe \
  --fixture fixtures/mlx/routed-moe-v1.json \
  --evidence "${TMPDIR:-/tmp}/pulsarmlx-synthetic-moe-v1.json"
```

The committed [synthetic record](../../docs/validation/synthetic-moe-v1.json)
passed with exact split-shard expert payloads, routes `[[1,2],[3,1]]`, declared
route weights, evaluated and synchronized MLX expert work, four compared output
values, and no fallback. It enforces finite scores, valid top-k,
score-descending/expert-ID-ascending ties, exact ranges, an independent scalar
aggregate, and separate memory gauges.

This command uses generated f32 fixture weights. It does not establish Qwen
routing, Q8_0 routed experts, a real checkpoint graph, generation, serving, or
performance.

## 10. Reproduce the verified bounded real-checkpoint slice

There is no automatic downloader. Use only an explicitly authorized external
copy of the official `Qwen/Qwen3-30B-A3B-GGUF` Q8_0 artifact and keep it outside
Git. The committed admission chain consists of:

- [provenance, immutable identity, and tensor inventory](../../docs/validation/models/qwen3-30b-a3b-q8_0-compatibility.json);
- [disk and unified-memory budget](../../docs/validation/models/qwen3-30b-a3b-q8_0-memory-budget.json);
- [preselected oracle contract](../../docs/validation/models/qwen3-30b-a3b-q8_0-oracle.json);
- [executed trusted-reference result](../../docs/validation/models/qwen3-30b-a3b-q8_0-reference-result.json); and
- [executed Apple MLX result](../../docs/validation/qwen3-30b-a3b-q8_0-slice.json).

Set the variables to absolute external paths. Use a fresh evidence destination
outside Git when reproducing so the committed record is not overwritten:

```sh
PULSARMLX_MODEL_GGUF="<external-model>/Qwen3-30B-A3B-Q8_0.gguf"
PULSARMLX_INSPECT_EVIDENCE="<external-evidence>/qwen-inspection.json"
PULSARMLX_SLICE_EVIDENCE="<external-evidence>/qwen-slice.json"

stat -f '%z bytes' "$PULSARMLX_MODEL_GGUF"
shasum -a 256 "$PULSARMLX_MODEL_GGUF"

cargo run --release -p mlx-backend --bin pulsar-mlx -- inspect-model \
  --model "$PULSARMLX_MODEL_GGUF" \
  --evidence "$PULSARMLX_INSPECT_EVIDENCE"
cargo run --release -p mlx-backend --bin pulsar-mlx -- validate-model-slice \
  --model "$PULSARMLX_MODEL_GGUF" \
  --evidence "$PULSARMLX_SLICE_EVIDENCE"
```

Replace both angle-bracket placeholders before execution; do not paste them
literally into a shell. The accepted artifact is exactly 32,483,931,648 bytes
with SHA-256
`4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c`.
The command also requires a clean source worktree, normal memory pressure, the
admitted Q8_0 tensor identity, explicit MLX GPU selection, and no fallback.

Stop before execution if provenance, revision, size, checksum, tensor layout,
trusted reference, disk/unified-memory headroom, or worktree cleanliness does
not match the committed gate. Stop after execution on any identity change,
fallback, unsynchronized result, non-finite value, tolerance mismatch, or
memory-cap violation. Do not place an access token, private path, or output
weights in evidence.

The recorded Apple command read exactly 34,816 encoded bytes for one layer-0,
expert-0 gate-projection prefix, produced 16 float32 values, and matched the
pinned CPU reference with zero mismatches. It did not execute tokenization,
embeddings, routing, a complete expert or layer, attention, logits, tokens,
generation, giant-model inference, or serving.

## 11. Review evidence before making a claim

The [validation index](../../docs/validation/README.md) maps stable case IDs to
commands, immutable inputs, oracles, results, warnings, exclusions, and
artifacts. The [compatibility matrix](../../docs/apple-silicon/COMPATIBILITY.md)
keeps scalar, MLX fixture, synthetic, bounded real-checkpoint, giant-model, and
production-serving states independent.

```sh
sed -n '1,260p' docs/validation/README.md
sed -n '1,220p' docs/apple-silicon/COMPATIBILITY.md
jq '{case_id, actual_status, reason, actual_result, warnings, exclusions}' \
  docs/validation/benchmark-initial.json
```

The [benchmark record](../../docs/validation/benchmark-initial.json) is
intentionally `actual_status: not_run`: no timing command, samples, statistics,
cache/storage state, or performance measurement exists. It must not support a
latency, throughput, speedup, bandwidth, memory, thermal, or power claim. A
future benchmark needs an exact workload and linked passing correctness
prerequisite before timing.

For every completed slice:

1. save the exact command and actual sanitized result;
2. link the commit, input identity, oracle, comparison policy, warnings, and
   exclusions;
3. update the feature artifacts, session log, compatibility record, validation
   guide, and known limitations;
4. run the exact Cargo baseline again;
5. scan the staged diff for secrets, weights, private IDs, and generated data;
   and
6. make a focused test-backed commit.

The current standard `macos-15` CI workflow covers the exact Cargo baseline; it
does not validate MLX or the external checkpoint. The native device integration
test is explicit and opt-in after the frozen environment has been prepared:

```sh
cargo test -p mlx-backend --test device_smoke \
  native_device_smoke_command_emits_evaluated_evidence -- --ignored --exact
```

The ordinary workspace command still runs the device contract tests and
reports this single native-runtime test as ignored rather than treating an
absent CI-only `.venv` as a device failure.

## Exact continuation instruction

Continue from the next incomplete Spec Kit task with:

```text
Use the speckit-implement skill for specs/001-apple-silicon-mlx. Start at the
first incomplete task, preserve every verified US1-US5 scope and the explicit
not-run/unsupported boundaries, and do not bypass any stop condition.
```
