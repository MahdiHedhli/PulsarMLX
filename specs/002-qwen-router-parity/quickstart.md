# Validation Quickstart: Qwen3MoE Layer-0 Router Parity

**Status**: Sections 1 through 3 and the complete generated-router boundary in
Section 6 describe implemented model-free work. Every external-checkpoint
command remains gated until its implementing tasks and exact prerequisites are
committed and green. Feature 001 remains the verified real-checkpoint baseline;
no Feature 002 checkpoint result exists.

## 1. Confirm the active bounded feature

From the repository root:

```sh
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
cat .specify/feature.json
sed -n '1,360p' specs/002-qwen-router-parity/spec.md
sed -n '1,360p' specs/002-qwen-router-parity/plan.md
```

The worktree must be recoverable, Feature 001 must remain closed, and active
feature metadata must resolve to `specs/002-qwen-router-parity`.

Check Spec Kit health:

```sh
specify version
specify check
specify integration status
.specify/scripts/bash/check-prerequisites.sh --json
```

## 2. Re-establish the safe Feature 001 baseline

These commands do not access an external model:

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
PYTHONPATH=python uv run python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
```

During initial Feature 002 planning, the exact Cargo gates passed with 171
active tests, zero failures, and one ignored native smoke; the Python worker
suite passed 44 tests. Counts remain commit-scoped and future runs must report
actual results.

The current repository-wide formatting and strict-Clippy diagnostics remain
non-gates because of recorded inherited debt:

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
```

Do not sweep unrelated failures into this feature. A new Feature 002 failure is
not inherited debt.

## 3. Freeze and verify methodology before model access

The first implementation milestone creates and tests the research package:

```sh
scripts/research/setup.sh
python3 -m unittest discover -s scripts/research/tests -v
python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input fixtures/research/router-v1/evidence
python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity \
  --fixture-only
```

Before any external model access or result collection, all of these must be
implemented, green, committed, pushed, and green in fixture-only CI:

- `docs/research/EXPERIMENT_PROTOCOL.md` with frozen tolerances, timing,
  statistics, order, interference, exclusion, amendment, and stop rules;
- versioned experiment and router JSON schemas;
- semantic/privacy validator;
- raw-observation statistics tests;
- deterministic table and SVG generators plus source sidecars;
- claims and reviewer package checks; and
- valid, mutated, failed, aborted, exact-tie, near-tie, and malformed fixtures.

Do not retrofit Feature 001's heterogeneous JSON records to the new schema.

### 3.1 Capture public-safe environment and worker resources

The environment collector is model-free: it accepts a storage **directory**
role, rejects model-looking file operands, never expands a model path into
evidence, and does not import or initialize MLX. Its workload declaration is
mandatory. Use `none` only after confirming there is no material local
inference, accelerator benchmark, large build, memory-pressure job, or other
declared compute/storage workload; otherwise use the truthful category and
expect admission to be postponed.

Use a fresh external output directory for each attempt:

```sh
export PULSARMLX_ROUTER_EVIDENCE='<external-evidence>/router-experiments'
export PULSARMLX_ENVIRONMENT_EVIDENCE="$PULSARMLX_ROUTER_EVIDENCE/environment"
export PULSARMLX_ROUTER_FIXTURE_EVIDENCE="$PULSARMLX_ROUTER_EVIDENCE/generated-router.json"

mkdir -p "$PULSARMLX_ENVIRONMENT_EVIDENCE"

PYTHONPATH=python uv run python scripts/research/environment.py capture \
  --repository-root . \
  --storage-root "$PULSARMLX_ROUTER_EVIDENCE" \
  --storage-role candidate_evidence_storage \
  --storage-locator '$PULSARMLX_ROUTER_EVIDENCE' \
  --capture-phase before \
  --workload-category none \
  --benchmark-concurrency 1 \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/before.json"

# A postponed admission is retained and exits nonzero. Stop here in that case.
PULSARMLX_MODEL_GGUF='' cargo run --release -p mlx-backend \
  --bin pulsar-mlx -- validate-router-fixtures \
  --manifest fixtures/research/router-v1/manifest.json \
  --evidence "$PULSARMLX_ROUTER_FIXTURE_EVIDENCE"

PYTHONPATH=python uv run python scripts/research/environment.py extract-resources \
  --candidate "$PULSARMLX_ROUTER_FIXTURE_EVIDENCE" \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/benchmark-resources.json"

PYTHONPATH=python uv run python scripts/research/environment.py capture \
  --repository-root . \
  --storage-root "$PULSARMLX_ROUTER_EVIDENCE" \
  --storage-role candidate_evidence_storage \
  --storage-locator '$PULSARMLX_ROUTER_EVIDENCE' \
  --capture-phase after \
  --workload-category none \
  --benchmark-concurrency 1 \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/after.json"

PYTHONPATH=python uv run python scripts/research/environment.py combine \
  --before "$PULSARMLX_ENVIRONMENT_EVIDENCE/before.json" \
  --after "$PULSARMLX_ENVIRONMENT_EVIDENCE/after.json" \
  --benchmark-resources "$PULSARMLX_ENVIRONMENT_EVIDENCE/benchmark-resources.json" \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/combined.json"

PYTHONDONTWRITEBYTECODE=1 PULSARMLX_MODEL_GGUF='' \
  PYTHONPATH=python uv run python -B \
  scripts/research/validate_generated_candidate.py \
  --candidate "$PULSARMLX_ROUTER_FIXTURE_EVIDENCE" \
  --environment "$PULSARMLX_ENVIRONMENT_EVIDENCE/combined.json" \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/generated-validation.json"
```

Every file is created exclusively and atomically; retry in a fresh external
directory rather than overwriting an attempt. The combined document is an
environment/resource handoff into the experiment record, not standalone
latency, correctness, or checkpoint evidence. A passing executed record must
retain both snapshots and worker-supplied process/MLX gauges. Collector-process
RSS/CPU fields remain explicitly collector-scoped. The one- and five-minute
load averages must each be no greater than `0.75 × logical CPU count`.
The fixture command uses protocol-fixed counts and retains one model-free
single-row synthetic series with five warm-ups followed by thirty measured
evaluated/synchronized MLX GPU attempts; callers cannot select or shorten the
counts. Every attempt is compared with the committed manifest/golden output,
and the candidate remains external until T069 validates its timing contract
and regenerated statistics.
The candidate retains one bounded canonical actual output. The dedicated
validator independently recomputes its component, selected-ID, and complete
hashes; recomputes the golden comparison from the retained values rather than
trusting the producer's pass flag; proves the 35 timing/result records form a
bijection; routes the raw totals through the canonical timing projection and
Type-7 statistics helpers; and rejects any component-stage or stage-sum field.
The validation report is still generated-fixture evidence and remains external
until the real-evidence publication tasks explicitly admit a record.
The resource extractor also binds the selected backend/device, fallback,
evaluation, and synchronization facts from the validated worker records; the
combine command has no caller-controlled backend/device override.
The capture command writes a postponed snapshot and returns nonzero whenever
admission is not `admitted`; do not continue to a benchmark after that result.

## 4. Notify and admit the external model

The same immutable external checkpoint from Feature 001 is required. Do not
download another model or quantization.

Do not send the start notification or touch the checkpoint until T022, T038,
T049, T060, and T071 are pushed and green and T072 records a clean/equal
offline and resource admission. T073 is the notification gate; T074 is the
first permitted checkpoint resolve/stat/hash/open operation.

Before opening it, send and confirm the NTFY notification:

```sh
curl -fsS \
  -H 'Title: PulsarMLX Feature 002 model work starting' \
  -H 'Priority: high' \
  -d 'Please pause local inference. Router inventory/oracle/MLX validation is starting; completion or blocker notice will follow.' \
  https://ntfy.sh/Mahdi-Dev
```

Then set local-only absolute paths without writing them to committed evidence:

```sh
export PULSARMLX_MODEL_GGUF='<external-model>/Qwen3-30B-A3B-Q8_0.gguf'
export PULSARMLX_MODEL_STORAGE_ROOT='<external-model>'
PULSARMLX_ROUTER_INSPECTION='<external-evidence>/router-inspection.json'
PULSARMLX_ORACLE_WORK='<external-work>/router-oracle'
PULSARMLX_ORACLE_OUTPUT='<external-evidence>/router-oracle'
PULSARMLX_ROUTER_ORACLE='<external-evidence>/router-oracle/oracle.json'
export PULSARMLX_ROUTER_EVIDENCE='<external-evidence>/router-experiments'
export PULSARMLX_ENVIRONMENT_EVIDENCE="$PULSARMLX_ROUTER_EVIDENCE/environment"
PULSARMLX_ROUTER_FIXTURE_EVIDENCE='<external-evidence>/router-fixtures.json'
```

Recheck host admission and immutable artifact identity:

```sh
uname -m
sw_vers
df -h .
memory_pressure
stat -f '%z' "$PULSARMLX_MODEL_GGUF"
shasum -a 256 "$PULSARMLX_MODEL_GGUF"
git status --short
```

Stop unless the shell is arm64, memory pressure is normal, the source tree is
clean, and the size/hash exactly match Feature 001.

Run read-only router inspection before CPU or Apple execution:

```sh
cargo run --release -p mlx-backend --bin pulsar-mlx -- inspect-router \
  --model "$PULSARMLX_MODEL_GGUF" \
  --evidence "$PULSARMLX_ROUTER_INSPECTION"

PYTHONDONTWRITEBYTECODE=1 python3 -B \
  scripts/research/validate_router_inspection.py \
  --input "$PULSARMLX_ROUTER_INSPECTION" \
  --environment "$PULSARMLX_ENVIRONMENT_EVIDENCE/before.json" \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/router-inspection-validation.json"
```

The record must prove one exact `blk.0.ffn_gate_inp.weight`, expected GGUF
dimensions `[2048,128]`, reader shape `[128,2048]`, observed type, exact offset
and length, range SHA-256, 128 experts, top-8, full-softmax/renormalization
metadata, absent bias/correction bias, and scale 1.0. Expected F32/1,048,576
bytes remain assumptions until this command observes them.

The validator additionally requires that the inspection commit exists and is
the clean current `HEAD`, and binds the candidate to a fresh admitted
`model_storage` before snapshot. Thermal state and workload must be resolved;
an unprivileged desktop power-mode probe may remain explicitly unavailable,
but an observed low-power mode is not admitted. The validation report remains
external until a later raw-evidence publication task explicitly admits it.

## 5. Freeze the independent real CPU oracle

Before running the command, prepare these local-only prerequisites under
`$PULSARMLX_ORACLE_WORK` without placing them in the repository:

- `llama.cpp/`: a clean checkout at
  `b06aa774c03dbbb624e726664b714a57d1f49815` with the recorded upstream origin
  and MIT license; and
- `oracle-python/bin/python`: external CPython 3.12.13 with the exact bounded
  reader/cross-check dependencies `numpy==2.4.5`, `PyYAML==6.0.3`,
  `tqdm==4.67.1`, and `requests==2.32.5`.

One reproducible external-only setup is:

```sh
uv venv --python 3.12.13 "$PULSARMLX_ORACLE_WORK/oracle-python"
uv pip install \
  --python "$PULSARMLX_ORACLE_WORK/oracle-python/bin/python" \
  'numpy==2.4.5' 'PyYAML==6.0.3' 'tqdm==4.67.1' 'requests==2.32.5'
```

The capture entry point verifies the Python and all four package versions and
imports pinned `gguf-py` before the first checkpoint stat or hash. A missing or
drifted dependency therefore fails as a prerequisite rather than after costly
capture work.

The script verifies these prerequisites and does not clone, download, or
initialize them.

```sh
scripts/research/capture_router_oracle.sh \
  --model "$PULSARMLX_MODEL_GGUF" \
  --work-dir "$PULSARMLX_ORACLE_WORK" \
  --output-dir "$PULSARMLX_ORACLE_OUTPUT"
```

This must use pinned CPU-only llama.cpp to capture the actual layer-0
`ffn_norm-0` router input by directly supplying token IDs `[0,1]` at positions
`[0,1]`, with context/batch/ubatch `2`, one thread, and no tokenizer selection.
It records row 0 as `qwen3moe-layer0-router-token0-row0-v1` and rows 0–1 as
`qwen3moe-layer0-router-token0-token1-batch-v1`, proves both IDs are in the
observed vocabulary and both rows differ, and retains at most two rows or 16,384
canonical F32 bytes. It then independently uses pinned `gguf-py` plus
standalone scalar/NumPy calculations for all 128 logits, full softmax, top-8,
and selected-probability renormalization. It must not import or call the MLX
worker. The final external directory retains both complete capture byte files,
both callback records, and both sanitized marker-delimited scheduler traces.
Each retained trace is reconstructed as exact markers around one normalized CPU
split line using only parsed bounded fields; arbitrary diagnostic text and
suffixes from stderr are never retained.
All files, provenance, and the bundle manifest are completed and fsynced in a
fresh hidden sibling directory before one atomic no-replace rename makes the
requested output visible; a failed or interrupted run must leave that requested
path absent.

Stop before Apple execution if:

- the real named input cannot be captured;
- callback cancellation yields incomplete values;
- the scheduler trace does not prove one CPU-only split or shows any router or
  expert node after `ffn_norm-0`;
- two independently started `ffn_norm-0` captures have different hashes;
- scalar router output and its independent NumPy F32 cross-check disagree;
- any exact F32 probability tie occurs across real ranks eight and nine;
- any input, tensor, model, command, source, or output hash is missing; or
- the oracle was not frozen at a clean commit before Apple output.

Feature 001's prompt-derived activation may appear only as a supplementary
synthetic probe. Its 16-row `ffn_gate_exps` prefix is a different tensor and is
not router evidence.

## 6. Reproduce synthetic and malformed gates

Before the real Apple command:

```sh
cargo test -p backend --test routing_contract
cargo test -p mlx-backend --test router_contract
PYTHONPATH=python uv run python -m unittest \
  python/pulsar_mlx_worker/tests/test_router.py -v

# Explicit generated Rust-to-worker integration; still model-free.
PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend \
  --test router_worker_integration \
  real_python_worker_two_row_router_matches_committed_golden -- \
  --ignored --exact

cargo run -p mlx-backend --bin pulsar-mlx -- validate-router-fixtures \
  --manifest fixtures/research/router-v1/manifest.json \
  --evidence "$PULSARMLX_ROUTER_FIXTURE_EVIDENCE"
```

The focused tests, explicit generated integration, and retained
`validate-router-fixtures` command are implemented. The retained command is
fail-closed, labels positive MLX execution separately from host tie and
fixture-contract negative validation, preserves partial failure/abort evidence,
and keeps the external-model descriptor closed. Running these focused commands
does not locate or access an external checkpoint.

The generated 128-expert/top-8 fixture must pass exact ties, near ties,
single-row and batch evaluation, while malformed lengths, shapes, orientation,
top-k, non-finite values, short reads, and file mutation fail before an accepted
result. This remains synthetic evidence.

## 7. Run bounded real Apple correctness and timing

Only after the committed oracle, method, and fixtures pass:

```sh
export PULSARMLX_ROUTER_INTERNAL_CANDIDATE="$PULSARMLX_ROUTER_EVIDENCE/internal-orchestration.json"

PYTHONPATH=python uv run python scripts/research/environment.py capture \
  --repository-root . \
  --storage-root "$PULSARMLX_ROUTER_EVIDENCE" \
  --storage-role candidate_evidence_storage \
  --storage-locator '$PULSARMLX_ROUTER_EVIDENCE' \
  --capture-phase before \
  --workload-category none \
  --benchmark-concurrency 1 \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/before.json"

cargo run --release -p mlx-backend --bin pulsar-mlx -- validate-router \
  --model "$PULSARMLX_MODEL_GGUF" \
  --oracle "$PULSARMLX_ROUTER_ORACLE" \
  --evidence-dir "$PULSARMLX_ROUTER_EVIDENCE"

PYTHONPATH=python uv run python scripts/research/environment.py extract-resources \
  --candidate "$PULSARMLX_ROUTER_INTERNAL_CANDIDATE" \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/benchmark-resources.json"

PYTHONPATH=python uv run python scripts/research/environment.py capture \
  --repository-root . \
  --storage-root "$PULSARMLX_ROUTER_EVIDENCE" \
  --storage-role candidate_evidence_storage \
  --storage-locator '$PULSARMLX_ROUTER_EVIDENCE' \
  --capture-phase after \
  --workload-category none \
  --benchmark-concurrency 1 \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/after.json"

PYTHONPATH=python uv run python scripts/research/environment.py combine \
  --before "$PULSARMLX_ENVIRONMENT_EVIDENCE/before.json" \
  --after "$PULSARMLX_ENVIRONMENT_EVIDENCE/after.json" \
  --benchmark-resources "$PULSARMLX_ENVIRONMENT_EVIDENCE/benchmark-resources.json" \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/combined.json"
```

`extract-resources` admits the 4 MiB/100,000-node/depth-64 intake only when
the root is the exact external unvalidated Apple-MLX router orchestration
identity. Before, after, and extracted-resource inputs to `combine` retain the
smaller 1 MiB/20,000-node bound. Input reads reject links, duplicate keys,
non-finite values, parent aliases, and in-place mutation; the byte cap includes
the final newline.

Capture the after snapshot and combine the environment even when
`validate-router` returns nonzero but retains a candidate. Use a fresh external
attempt directory rather than overwriting any prior snapshot or candidate.

The command must use all 128 router rows, return full bounded logits and hashes,
match exact top-8 IDs/order, meet the frozen logit and weight tolerances, retain
ten identical measured output hashes per case and twenty total, select explicit
MLX GPU, evaluate and synchronize, and report no fallback.

The resulting file is an external internal-orchestration candidate, not yet a
public evidence record. Before publication it must be transformed without
coercion into evidence envelope `1.2.0` / router payload `1.1.0`, including the
closed `router_detail` ledger, complete correctness attempts, finalized
request/resource/lifecycle joins, application read/cache semantics, and exact
candidate/environment hashes. A pre-execution abort retains unavailable
correctness and positive supervisor duration; it never invents measurements.
An evaluated correctness stop retains the exact zero-to-nineteen measured-hash
prefix. Structurally invalid evaluated output uses
`evaluated_output_invalid`; it is not a pre-execution abort. A linked later
batch keeps its own exit code, so a later failure does not rewrite a passed
first-batch outcome.

Correctness gates timing. The command then retains separately:

- first-process read/total labeled
  `first_read_new_process_os_cache_uncontrolled`, not filesystem-cold;
- warm reused-process total;
- minimally instrumented one-sync total;
- stage-instrumented read, transfer, graph, projection, top-k, normalization,
  readback, and total observations;
- F32 dequantization as `not_applicable`, not zero;
- five warm-ups plus ten costly measurements;
- five warm-ups plus thirty inexpensive warm-compute measurements;
- one complete fresh-process replication for each minimally instrumented
  single-row and two-row major benchmark; and
- a later second batch or an explicit unavailable reason.

No stage sum is required to equal the minimally instrumented total.

## 8. Validate and publish bounded evidence

First transform the exact internal candidate into a fresh external directory.
The sanitizer reads no model or oracle path, hashes the exact candidate bytes,
recomputes public comparisons and summaries, validates all joins, and installs
the linked records atomically. Every parent component must be a real directory,
not a symbolic link.

```sh
export PULSARMLX_ROUTER_SANITIZED='<external-evidence>/router-public'

PYTHONDONTWRITEBYTECODE=1 python3 -B \
  scripts/research/sanitize_router_candidate.py \
  --candidate "$PULSARMLX_ROUTER_INTERNAL_CANDIDATE" \
  --environment "$PULSARMLX_ENVIRONMENT_EVIDENCE/combined.json" \
  --output-dir "$PULSARMLX_ROUTER_SANITIZED"

PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input "$PULSARMLX_ROUTER_SANITIZED"
PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/research/verify_package.py \
  --feature 002-qwen-router-parity \
  --candidate "$PULSARMLX_ROUTER_SANITIZED"
```

After controlled sanitization and append-only installation, validate the raw
publication, commit and push it, and record its clean raw-data commit SHA. Only
then regenerate and verify publication artifacts from that committed raw data:

```sh
python3 scripts/research/generate_tables.py \
  --raw-dir docs/research/raw/002-router-parity \
  --output-dir docs/research/tables
python3 scripts/research/generate_figures.py \
  --raw-dir docs/research/raw/002-router-parity \
  --output-dir docs/research/figures
python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity
```

Update `RESULTS.md`, `LIMITATIONS.md`, `CLAIMS_LEDGER.md`, and
`REVIEWER_INDEX.md` from actual validated records. Do not type measured numbers
into generator source.

## 9. Final gates and completion notification

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
git diff --check
```

Run the staged secret/path/identifier/model/binary/cache/large-file and
Linux/CUDA selection review before every commit and push. Confirm fixture-only
CI without an external model. Record each substantive pushed commit's actual CI
run URL and conclusion in `docs/apple-silicon/SESSION_LOG.md`; carry that update
into the next focused task-state/documentation commit. For the terminal
documentation attestation, or a documentation-only attestation required to
restore a clean/equal branch before model capture or Apple execution, report
that attestation's own CI result out of tree without creating an endless CI-log
commit cycle.

Then notify completion or the exact blocker. This terminal notification is also
required for a blocker reached before model access; in that case its body must
say that model access never began and local inference was never paused.

```sh
curl -fsS \
  -H 'Title: PulsarMLX Feature 002 complete' \
  -d 'Router feature reached its documented verified or blocked boundary. Local inference may resume; see the committed Feature 002 report.' \
  https://ntfy.sh/Mahdi-Dev
```

## Exact continuation instruction

```text
Use $speckit-implement for specs/002-qwen-router-parity after $speckit-analyze
reports no critical inconsistency. Implement only the dependency-ordered task
list. Freeze, commit, push, and confirm the publication methodology before any
external checkpoint access or timing. Notify Mahdi-Dev immediately before that
access and after completion or any terminal blocker. Stop rather than
substituting a synthetic input, changing a frozen tolerance, accepting an
expert-ID mismatch, or promoting router evidence to a deeper capability.
```

## Unsupported interpretations

Even a passing Feature 002 proves no expert MLP, routed-MoE aggregation,
attention implementation in PulsarMLX, complete transformer layer/model,
logits head, tokens, generation, serving, custom Metal, full or giant model
inference, projected tokens per second, Linux/CUDA runtime parity, or broad
Qwen/quantization compatibility.
