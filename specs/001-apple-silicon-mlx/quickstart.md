# Validation Quickstart: Apple Silicon MLX Backend Bring-Up

**Status**: The Cargo baseline, pinned worker environment, protocol/lifecycle
tests, evaluated MLX GPU device smoke, seven tensor fixtures, and scoped Q8_0
reference operations are runnable and verified. Storage, routed-MoE, and model
commands remain implementation targets until their evidence is committed.

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

Before implementation, compare the actual results with
`docs/preflight/BASELINE_VALIDATION.md`. Record differences; never substitute
the expected 32-test count for an actual result.

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

On tested commit `4ff4301`, these ran 13 Python tests and 12 Rust fake-worker
tests with zero failures. They cover version negotiation, frame limits,
request IDs, malformed messages, stdout contamination, worker exit/timeout,
controlled shutdown, and structured errors without a model file.

## 6. Reproduce evaluated GPU execution

```sh
cargo run -p mlx-backend --bin pulsar-mlx -- device-smoke \
  --backend apple-mlx \
  --device gpu \
  --evidence docs/validation/mlx-device-smoke.json
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
  --evidence docs/validation/mlx-tensor-fixtures.json
```

On tested commit `c53f21e`, these commands pass 14 strict Q8_0 tests, 7 Rust
fixture contract tests, and 7 evaluated MLX cases. Review exact shape,
orientation, input/accumulation/output dtype, encoded byte count,
malformed-input rejection, synchronization, compared element count, maximum
absolute/relative errors, and first mismatch in
`docs/validation/mlx-tensor-fixtures.json`. Tolerances are committed in
`fixtures/mlx/manifest.json`; do not tune them after observing output.

## 8. Prove portable expert storage (planned)

```sh
cargo test -p stream positional_source
cargo test -p mlx-backend --test expert_source_contract
```

The suite must include single and split shards, exact boundaries, invalid
layouts, below/end/overflow/straddle ranges, partial reads, interruption,
truncation, batch ordering, all-or-error behavior, and owned-payload lifetime.
The inherited Linux fetcher stays selected on its existing path.

## 9. Prove a synthetic routed-MoE layer (planned)

```sh
cargo run -p mlx-backend --bin pulsar-mlx -- validate-synthetic-moe \
  --fixture fixtures/mlx/routed-moe-v1.json \
  --evidence docs/validation/synthetic-moe-v1.json
```

Require exact expert IDs and score-descending/expert-ID-ascending tie order,
finite scores, valid top-k, declared route-weight tolerance, exact expert
ranges, scalar expert computation, weighted output parity, and separate memory
gauges. Label the evidence `synthetic`.

## 10. Gate the external real-model slice (planned; no automatic download)

The current candidate is the official
`Qwen/Qwen3-30B-A3B-GGUF` Q8_0 artifact. Before any download, create a model
compatibility record with:

- immutable repository revision and exact filename;
- source and license;
- published size plus sufficient disk headroom;
- intended bounded graph depth;
- required tensor roles and quant types;
- a trusted reference runtime/version and reproducible comparison command; and
- conservative compressed, decoded, temporary, cache, and system-headroom
  budgets.

After an explicitly authorized external download, keep the artifact outside
Git and capture its actual identity:

```sh
shasum -a 256 /absolute/external/model/path/Qwen3-30B-A3B-Q8_0.gguf
stat -f '%z bytes' /absolute/external/model/path/Qwen3-30B-A3B-Q8_0.gguf
```

The path shown is illustrative and must remain outside the repository. Do not
place an access token in a command, record, or shell history. Stop if the
trusted oracle, provenance, immutable revision, checksum, tensor coverage, or
memory fit is unresolved.

Only after that gate passes, run the implemented bounded command recorded by
its task. The result may verify only its named graph depth. An intermediate
tensor does not prove end-to-end inference; that requires a validated logits or
token boundary.

## 11. Record evidence before making a claim

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

No benchmark is published until its correctness prerequisites pass. Standard
`macos-15` CI initially covers only the Cargo baseline; it does not validate
MLX or the external checkpoint until separately specified jobs actually run.

## Exact continuation instruction

Continue from the next incomplete Spec Kit task with:

```text
Use the speckit-implement skill for specs/001-apple-silicon-mlx. Start at the
first incomplete task, preserve the verified US1 evidence boundary, and do not
bypass any stop condition.
```
