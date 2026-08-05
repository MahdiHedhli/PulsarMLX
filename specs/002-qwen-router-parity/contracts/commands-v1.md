# Contract: Feature 002 Commands v1

**Status**: Offline research/package utilities, generated control-only router
execution, and lexical fail-closed command parsers are implemented. Retained
router-fixture execution, Feature 002 result publication, and every model
command remain gated until their dependency and notification gates pass.

All commands run from the repository root. External model, oracle-build, and
temporary evidence paths remain local and are represented as placeholders in
committed evidence. No command downloads the checkpoint automatically.

## Common rules

- `--help` and invalid arguments never access the model or initialize MLX.
- Model commands require an absolute external model path and reject aliases
  between model, oracle, temporary output, and committed-output locations.
- Every error is bounded, structured, and nonzero. It identifies the failing
  gate without printing private paths, environment contents, credentials, or
  model bytes.
- Result installation is atomic and refuses an existing experiment ID or
  destination. Reproduction creates a new attempt rather than overwriting a
  historical record.
- Commands never modify the checkpoint and use read-only handles inherited by
  the persistent worker only after admission.
- Full checkpoint hashing, setup, and oracle capture remain outside bounded
  router-operation timing.
- A success line states the exact bounded result and never says inference,
  layer parity, generation, serving, or tokens per second.

## Safe setup and offline validation

### Research setup

```sh
scripts/research/setup.sh
```

Creates or verifies only repository-local ignored tooling state from committed
locks. It performs no model lookup, network download, or MLX execution. Repeated
runs are idempotent.

### Schema and semantic validation

```sh
python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input docs/research/raw/002-router-parity
```

Validates schema identity, field types, semantic relationships, privacy,
repetition policies, raw/summary agreement, correctness, artifact links, and
claim boundaries. It rejects unknown schema versions and additional fields
where the schema closes an object. It never rewrites evidence.

### Publication generation

```sh
python3 scripts/research/generate_tables.py \
  --raw-dir docs/research/raw/002-router-parity \
  --output-dir docs/research/tables

python3 scripts/research/generate_figures.py \
  --raw-dir docs/research/raw/002-router-parity \
  --output-dir docs/research/figures
```

Generators validate inputs first, contain no measured constants, write
deterministic Markdown/CSV and SVG outputs, and create source sidecars with
input hashes and generator identity. Existing unexpected output fails rather
than being silently replaced.

### Complete package verification

```sh
python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity
```

Runs schema/semantic validation, recomputes statistics and correctness,
regenerates outputs in a temporary directory, compares bytes and hashes,
verifies the reviewer index and claims ledger, scans public evidence for
private values, and returns nonzero on any mismatch.

These four safe commands are required in fixture-only CI.

## External model inventory

External access begins only after T022, T038, T049, T060, and T071 are pushed
and green; T072 has re-established the clean/equal offline and resource gates;
and the T073 NTFY notification is acknowledged. T074 is the first command
permitted to resolve, stat, hash, open, or otherwise access the checkpoint.

```sh
cargo run --release -p mlx-backend --bin pulsar-mlx -- inspect-router \
  --model "$PULSARMLX_MODEL_GGUF" \
  --evidence "$PULSARMLX_ROUTER_INSPECTION"
```

The command:

1. requires a clean full source commit;
2. rechecks Feature 001's repository/revision/file/size/full SHA-256 identity;
3. validates exact typed architecture, hidden width, expert count, top-k, and
   routing metadata;
4. requires exactly one `blk.0.ffn_gate_inp.weight`;
5. records exact GGUF dimensions, reader shape, type, offset, length, end
   offset, and encoded-range SHA-256;
6. verifies absent router/correction bias and scale 1.0 behavior; and
7. writes a sanitized admission record without loading MLX or producing router
   output.

Any expected F32/type/shape assumption that differs from the file blocks the
feature until the specification and independent oracle are reassessed. The
command cannot promote inspection into execution evidence.

## Independent CPU oracle capture

```sh
scripts/research/capture_router_oracle.sh \
  --model "$PULSARMLX_MODEL_GGUF" \
  --work-dir "$PULSARMLX_ORACLE_WORK" \
  --output-dir "$PULSARMLX_ORACLE_OUTPUT"
```

The script:

- requires an operator-prepared clean external checkout of
  `ggml-org/llama.cpp` at exactly
  `b06aa774c03dbbb624e726664b714a57d1f49815`, verifies that identity, and does
  not place or initialize the checkout in this repository;
- verifies the checkout and license;
- builds the CPU-only callback helper with no Metal/GPU offload;
- directly supplies token IDs `[0,1]` at positions `[0,1]` without tokenizer
  selection, after proving both IDs are within the observed vocabulary;
- captures only the complete named `ffn_norm-0` real router input from the same
  GGUF in two independently started executions;
- freezes a two-token context/batch/ubatch, one-thread CPU placement, case IDs
  `qwen3moe-layer0-router-token0-row0-v1` and
  `qwen3moe-layer0-router-token0-token1-batch-v1`, no more than two rows or
  16,384 canonical F32 bytes, disables GPU/KQV/op offload,
  records a `GGML_SCHED_DEBUG` single-split trace, returns false after the fully
  synchronized capture, and sets a CPU abort guard against later splits;
- proves both captures are byte-identical and the callback trace contains no
  router or expert node after the target, failing the real-fixture milestone if
  that bounded cancellation cannot be established;
- proves the two captured rows are distinct and records input adapter
  `direct_token_ids_v1` plus tokenizer state `not_used_direct_token_ids`;
- independently reads the admitted F32 router tensor through pinned `gguf-py`
  and computes float32 logits, full softmax, top-8, selected probabilities, and
  renormalized weights without importing the MLX worker;
- validates the capture independently and records the standalone oracle result
  under the frozen policy;
- retains both complete 16,384-byte `capture-{a,b}.f32le` attempts, both raw
  callback records, and both bounded marker-delimited scheduler traces so the
  two independent executions remain directly reviewable. Retained traces are
  reconstructed only from the parsed split ID, CPU backend, and bounded input
  count; raw diagnostic lines, suffixes, and paths are never copied;
- assembles, rehashes, and fsyncs the complete candidate in a freshly created
  hidden sibling directory, then publishes it with an atomic no-replace
  directory rename. The requested output directory remains absent on any
  pre-publication failure or crash, and an existing destination is never
  replaced; and
- writes bounded legal fixture/oracle values, raw attempts, hashes, source
  identities, and exclusions to the external output directory.

The script fails if a real `ffn_norm-0` input cannot be captured twice with
identical hashes, cancellation before router/expert execution cannot be proved,
scalar and NumPy router calculations disagree, any exact F32 probability tie
occurs across ranks eight and nine, or any input identity changes. A synthetic
fallback is not accepted as real evidence.

## Local Apple router validation

```sh
cargo run --release -p mlx-backend --bin pulsar-mlx -- validate-router \
  --model "$PULSARMLX_MODEL_GGUF" \
  --oracle "$PULSARMLX_ROUTER_ORACLE" \
  --evidence-dir "$PULSARMLX_ROUTER_EVIDENCE"
```

The command uses protocol-fixed counts rather than caller-selected benchmark
counts:

- at least ten identical evaluated correctness repetitions per real case;
- five warm-ups plus ten costly total/load measurements;
- five warm-ups plus thirty inexpensive warm compute measurements;
- one fresh-process replication for each of the two minimally instrumented
  single-row and two-row major benchmarks, and one later second batch when
  feasible. Stage-instrumented series remain diagnostic.

It executes one complete `[rows,2048] × [2048,128]` projection, full 128-way
softmax, top-8, and selected-probability renormalization on explicit MLX GPU.
The worker forces evaluation and synchronization before stopping each admitted
timer and readback. It returns all 128 logits for the bounded batch, exact top-8
IDs/order, selected probabilities, normalized weights, per-repeat hashes,
memory gauges, raw timing observations, and no-fallback/device identity.

The Rust side independently validates every response identity, shape, count,
hash, selected-probability relationship, weight sum, repetition, timing, memory, and
oracle comparison. It rehashes the model and router range after execution.

The command returns nonzero and retains a failed/aborted attempt on any ID or
order mismatch, tolerance excess, non-finite result, hash change, fallback,
unsynchronized work, repeatability failure, resource gate, or schema failure.
It does not install passing public evidence directly; publication occurs only
after sanitization, validation, and clean-commit review.

## Synthetic and malformed fixture validation

```sh
cargo test -p backend --test routing_contract
cargo test -p mlx-backend --test router_contract
PYTHONPATH=python uv run python -m unittest \
  python/pulsar_mlx_worker/tests/test_router.py -v

cargo run -p mlx-backend --bin pulsar-mlx -- validate-router-fixtures \
  --manifest fixtures/research/router-v1/manifest.json \
  --evidence "$PULSARMLX_ROUTER_FIXTURE_EVIDENCE"
```

The focused tests already cover the generated single-row/batch seam and an
all-equal deterministic ordering case. Once T039 through T045 complete, the
retained fixture command will also cover near ties at the 8/9 boundary,
malformed cardinality/type/range/orientation, invalid top-k, non-finite values,
short reads, file mutation, and explicit evaluated GPU/no-fallback behavior.
Synthetic results remain a separate evidence level.

## Publication installation

No generated model-run file is committed until all of the following pass:

```sh
python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input "$PULSARMLX_ROUTER_EVIDENCE"

python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity \
  --candidate "$PULSARMLX_ROUTER_EVIDENCE"
```

A controlled publication step assigns stable experiment IDs, strips local
paths, copies only bounded schema-valid JSON and legal derived values, refuses
overwrites, and updates artifact hashes. The staged raw-data diff receives the
required secret, path, identifier, weight, binary, cache, and large-file scans,
then is committed and pushed. Tables and figures are regenerated only in a
subsequent commit from that committed raw-data SHA.

## Result and exit behavior

| Outcome | Process result | Evidence behavior |
| --- | --- | --- |
| Contract and experiment pass | Zero | Append-only passing record after publication review |
| Usage or path alias error | Nonzero | No model access; bounded stderr |
| Identity, inventory, resource, or environment admission failure | Nonzero | Sanitized blocked/aborted attempt retained when experiment began |
| Independent oracle failure | Nonzero | Oracle attempt retained; Apple command remains prohibited |
| Worker/protocol/runtime failure | Nonzero | Failed/aborted raw observation retained |
| Correctness, ID/order, tolerance, fallback, or determinism failure | Nonzero | Failing values/metrics retained within legal bounded evidence |
| Evidence/schema/privacy/generation failure | Nonzero | No public claim promoted; prior files remain unchanged |

Every terminal Feature 002 blocker, including one reached before external model
access, requires a best-effort NTFY message to topic `Mahdi-Dev`. A pre-access
blocker states that model access never began and local inference was never
paused. A blocker after the start notification states that local inference may
resume. Notification failure is reported accurately and does not authorize
model access or suppression of the underlying blocker.

## Explicit exclusions

No command in this contract executes or claims expert MLPs, routed-expert
aggregation, attention in PulsarMLX, a complete layer/model, logits head, token
generation, serving, custom Metal, full or giant model inference, projected
tokens per second, or Linux/CUDA runtime parity.
