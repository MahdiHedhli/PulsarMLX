# Feature 002 Experiment Protocol

**Protocol ID**: `f002-router-protocol-amendment-002`

**Protocol version**: `1.2.0`

**Supersedes**: `f002-router-protocol-amendment-001` version `1.1.0`

**Feature**: `002-qwen-router-parity`

**Order policy**: `fixed-counterbalanced-v1`

**Order seed**: `22002`

**Status**: Frozen pre-execution amendment. Read-only checkpoint inspection and
CPU-oracle publication have occurred, but no Apple/MLX real-router execution or
real-router timing measurement has occurred under this protocol.

This document freezes the correctness, timing, retention, publication, and
stop rules for the bounded Qwen3MoE layer-0 router experiment. It is executable
only with the admission gates below. It records no result and makes no claim
that the Feature 002 router implementation works.

Amendment 002 was made after immutable read-only checkpoint inspection and
independent CPU-oracle publication, but before any Apple/MLX output or real
router timing was observed. It does not change inputs, oracle values,
tolerances, attempt counts, case order, timing boundaries, or acceptance
criteria. It closes the publication representation needed to retain complete
bounded outputs, process/request/resource joins, truthful pre-execution abort
timing, and the already frozen per-process summary grouping. Amendment 001 and
the original protocol remain in Git history. Checked-in conformance fixtures
are constructed policy data, not experimental attempts or checkpoint claims.

The normative companion documents are the
[feature specification](../../specs/002-qwen-router-parity/spec.md),
[router contract](../../specs/002-qwen-router-parity/contracts/router-parity-v1.md),
[research-evidence contract](../../specs/002-qwen-router-parity/contracts/research-evidence-v1.md),
and [command contract](../../specs/002-qwen-router-parity/contracts/commands-v1.md).
If they conflict, the feature specification and contracts control and the
experiment stops until the conflict is resolved by a protocol amendment.

## 1. Hard no-model boundary

Before the acknowledged start notification, every Feature 002 operation is
fixture-only. Tasks T001 through T072 MUST NOT resolve, search for, stat, hash,
open, read, map, copy, or execute the external checkpoint or an extracted
checkpoint tensor. They also MUST NOT initialize a model path implicitly.
Setup, `--help`, schema validation, generators, publication tests, and CI run
with the model variable unset and may use only committed redistributable
fixtures.

External access remains prohibited until all of these conditions hold:

1. The methodology and all offline implementation milestones through T071 are
   committed, pushed, and green in fixture-only CI.
2. T072 confirms a clean `main`, `HEAD == origin/main`, green CI, exact local
   workspace/Python/research gates, admissible resources, and mutually distinct
   absolute external model, oracle, work, and candidate-output locations
   outside Git.
3. T073 sends the required start message to NTFY topic `Mahdi-Dev` and receives
   a successful HTTP response.

If resource admission fails, work pauses before model access and the operator
is notified that model access never began and local inference was never
paused. If the start notification fails, the experiment stops. T074 is the
first task allowed to stat or open the checkpoint. Notification is not model
admission; every identity and resource gate still applies afterward.

No command in this protocol downloads a model or a second quantization.

## 2. Frozen scope and immutable identity

The only admitted real-checkpoint operation ends after complete layer-0 router
logits, full-softmax probabilities, ordered top-8 IDs, selected probabilities,
and selected-sum-normalized weights. The requested and selected backend/device
are `apple-mlx`/`gpu`, `allow_fallback` is false, and accepted work is explicitly
evaluated and synchronized.

The checkpoint must exactly match all of these already published Feature 001
identity fields before execution:

| Field | Required value |
|---|---|
| Repository | `Qwen/Qwen3-30B-A3B-GGUF` |
| Revision | `e4d4bafdfb96a411a163846265362aceb0b9c63a` |
| Filename | `Qwen3-30B-A3B-Q8_0.gguf` |
| Size | `32,483,931,648` bytes |
| SHA-256 | `4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c` |
| Architecture | `qwen3moe` |
| License | Apache-2.0, with recorded upstream provenance |

The exact local occurrence, storage type, dimensions, orientation, offset,
length, range hash, top-k, scale, and bias facts for
`blk.0.ffn_gate_inp.weight` remain observations, not results inferred by this
protocol. Read-only inspection must prove exactly one F32 tensor with GGUF
dimensions `[2048,128]`, reader/execution weight shape `[128,2048]`, 262,144
elements, 1,048,576 encoded bytes, 128 experts, top-k 8, full-softmax followed
by selected-probability renormalization, no router/correction bias, and effective
scale 1.0. Any differing or unresolved fact is a stop condition.

The model remains an external regular read-only file. The same admitted open
file description is used through an experiment, and the complete file and
router range identities are rechecked after execution. Model bytes and
extracted router-weight bytes never enter Git.

## 3. Frozen input and case matrix

### 3.1 Direct CPU capture

The real hidden-state capture uses the pinned CPU-only oracle runtime, supplies
token IDs directly, and does not select or invoke a tokenizer. These values are
immutable in v1:

| Parameter | Required value |
|---|---|
| Token IDs | exactly `[0,1]` |
| Positions | exactly `[0,1]` |
| Input adapter | `direct_token_ids_v1` |
| Tokenizer identity | `not_used_direct_token_ids` |
| Context tokens | `2` |
| Batch tokens | `2` |
| Ubatch tokens | `2` |
| Evaluation threads | `1` |
| Capture boundary | complete synchronized `ffn_norm-0` |
| Complete shape | `[2,2048]` |
| Encoding | finite canonical IEEE-754 F32, little-endian |
| Maximum retained capture | exactly two rows; at most `16,384` bytes |

Both token IDs must be inside the checkpoint's observed vocabulary. The two
captured rows must differ byte-for-byte. Two independently started CPU-only
captures must have identical canonical hashes and must prove one CPU scheduler
split plus cancellation before any router or expert node after `ffn_norm-0`.
Failure of bounds, completeness, distinctness, repeatability, CPU-only
placement, synchronization, or cancellation stops real-fixture work. A random,
prompt-derived, or merely model-shaped vector cannot be relabeled as real.

### 3.2 Required real cases

| Case ID | Selected rows | Execution input shape | Purpose |
|---|---:|---:|---|
| `qwen3moe-layer0-router-token0-row0-v1` | `[0]` | `[1,2048]` | Required single-row correctness and major benchmark |
| `qwen3moe-layer0-router-token0-token1-batch-v1` | `[0,1]` | `[2,2048]` | Required bounded-batch correctness and major benchmark |

Every route uses all 128 experts. Complete `[N,128]` logits and full-softmax
probabilities are retained or represented by their complete canonical hashes
under the bounded-publication rule. Ranges `0..16` and `64..80` are review
summaries of the complete output, never partial router execution. Feature
001's 16-row `blk.0.ffn_gate_exps.weight` prefix is a different expert-MLP
tensor and is inapplicable to this router experiment.

Synthetic exact-cutoff-tie and representable near-tie cases, plus malformed,
truncated, overlong, wrong-orientation, invalid-top-k, dimension, and non-finite
cases, remain fixture-only evidence. They test deterministic and fail-closed
behavior but cannot satisfy either real case or support a checkpoint claim.

## 4. Correctness policy

The independent CPU oracle is frozen before any corresponding Apple output is
inspected. It uses standalone scalar F32 accumulation as canonical and a
separate NumPy F32 result as a cross-check. It imports neither MLX nor
PulsarMLX worker code. For each input row it computes, in this order:

1. all 128 bias-free F32 projection logits;
2. F32 softmax over all 128 logits;
3. exactly eight IDs ordered by probability descending and expert ID ascending
   for equal probabilities;
4. the selected full-softmax probabilities in ID rank order; and
5. those eight probabilities divided by their positive finite selected sum,
   with the admitted scale 1.0.

An exact real F32 probability tie across ranks eight and nine is a stop
condition. Lower-ID-first remains a PulsarMLX deterministic rule proven only by
the synthetic exact-tie case; it does not turn a real cutoff tie into passing
cross-runtime evidence.

All non-finite inputs, intermediates, outputs, denominators, and error metrics
are rejected. Expert IDs, uniqueness, range, and ordering require exact
equality with zero mismatches. Numeric acceptance is elementwise:

```text
abs(candidate - reference)
    <= absolute_tolerance + relative_tolerance * abs(reference)
```

| Quantity | Absolute tolerance | Relative tolerance |
|---|---:|---:|
| Complete router logits | `5e-4` | `5e-4` |
| Complete 128-way softmax probabilities | `1e-6` | `1e-6` |
| Selected pre-normalization probabilities | `1e-6` | `1e-6` |
| Normalized routing weights | `1e-6` | `1e-6` |

Relative error is `abs(candidate-reference) / abs(reference)` only for a
nonzero reference; at an exact-zero reference it is `null` with reason and the
absolute-plus-relative acceptance expression still applies. Each output kind
reports compared count, numeric mismatch count, first mismatch location and
values, maximum and mean absolute error, RMSE, and maximum meaningful relative
error. IDs additionally report ID and ordering mismatch counts. Whole-output,
`0..16`, and `64..80` metrics are mandatory.

Each real case retains exactly five labeled correctness warm-up attempts,
followed by exactly ten labeled measured correctness attempts, after admission.
The attempt role and within-role index are retained. Every one of the fifteen
attempts must independently select explicit GPU, use no fallback, evaluate and
synchronize before readback, match exact IDs/order, and pass the oracle
tolerances. A failure in any warm-up or measured attempt is retained as a
failure and stops v1.

Canonical little-endian F32 hashes for complete logits, complete probabilities,
selected probabilities, and normalized weights must be bitwise identical
across the ten measured correctness attempts. Warm-up attempts do not satisfy
the measured repeat count. Any measured difference is retained as failure and
stops v1; tolerances are not widened.

An unsuccessful gate publishes the exact completed measured prefix, which may
contain zero through nineteen hashes across the ordered two-case experiment.
Its `deterministic_repeat_count` equals that prefix exactly; it is never padded
to ten or twenty. A complete passing or post-run-interference record contains
exactly ten identical measured hashes for each case and twenty total. If an
evaluated result is structurally invalid before a numerical comparison can be
formed, correctness uses the distinct `evaluated_output_invalid` unavailable
source; it cannot be relabeled as a pre-execution abort.

Both the single-row and two-row correctness gates complete before any timing
series begins. Timing observations do not retroactively satisfy either
independent correctness gate.

## 5. Benchmark matrix and execution order

### 5.1 Exact major benchmarks

There are exactly two major benchmarks:

| Benchmark ID | Real case | Primary timing boundary | Mode | Primary count | Required clean-process replication |
|---|---|---|---|---|---|
| `f002-major-single-row-minimal-v1` | `qwen3moe-layer0-router-token0-row0-v1` | evaluated projection through selected-probability normalization | `minimally_instrumented` | 5 retained warm-ups + 30 retained warm measurements | Repeat the complete 5+30 series in a separately started clean worker |
| `f002-major-two-row-minimal-v1` | `qwen3moe-layer0-router-token0-token1-batch-v1` | evaluated projection through selected-probability normalization | `minimally_instrumented` | 5 retained warm-ups + 30 retained warm measurements | Repeat the complete 5+30 series in a separately started clean worker |

No stage-instrumented series, load/read series, synthetic microbenchmark, or
end-to-end command is an additional major benchmark. A clean-process
replication starts a worker that has not participated in another benchmark,
rechecks identity/device/resource admission, records its first-read observation
under the required condition label, then repeats the entire major series.

### 5.2 Other admitted timing series

- Costly real checkpoint I/O, construction/transfer, or end-to-end series use
  at least 5 retained warm-ups followed by 10 retained measurements.
- Inexpensive warm compute and synthetic microbenchmark series use at least 5
  retained warm-ups followed by 30 retained measurements.
- A first-process condition is one predeclared cohort of exactly 10 separate
  series. Every series runs in a distinct fresh process and contains exactly 0
  warm-ups followed by exactly 1 first-read measurement with its own
  process-replication ID and required process/cache label. A process or series
  may never claim ten first reads. Independently proved controlled-cold
  behavior uses the same 10-series, 0+1 structure. Starting a process alone
  never proves a cold filesystem.
- Stage-instrumented real diagnostics use at least 5 retained warm-ups and 10
  retained measurements, remain separate from major totals, and cannot be
  promoted as a third major benchmark.

Only the dedicated fresh-process `0+1` cohorts label their one request
`first_read_new_process_os_cache_uncontrolled`. The persistent costly, primary,
stage, and clean-major workers label their complete `5+N` series `warm`: their
first request is a retained warm-up, not a separately claimed first-read
measurement. No series is labeled `cold`, `cold filesystem`, or
`controlled_cold` unless an independently reviewed cache-control method is
added by protocol amendment.

Recorded process-replication IDs are correlation evidence, not proof that the
required processes were actually spawned and shut down. T083 connects each
series identity to the execution adapter's observed spawn, one first-read
measurement, and shutdown lifecycle. Until that live command step succeeds,
the schema and orchestration checks establish only the planned evidence
structure and MUST NOT be described as a real first-process result.

### 5.3 Frozen order

Order is recorded for every observation. Batch 1 uses this fixed sequence:

1. five labeled single-row correctness warm-up attempts followed by ten labeled
   measured attempts;
2. five labeled two-row correctness warm-up attempts followed by ten labeled
   measured attempts;
3. the ten-series primary fresh-process `0+1` cohort for the first case in the
   batch's costly order;
4. the single-row and two-row costly real series, in batch order;
5. the single-row and two-row minimally instrumented primary major series, in
   batch order;
6. the single-row and two-row stage-instrumented diagnostic series, in batch
   order; and
7. for each case in clean-major order, its ten-series fresh-process `0+1`
   cohort immediately followed by that case's separate clean-major `5+30`
   replication.

Items 1 and 2 are complete gates: no first-process cohort or other timing work
starts before both pass. At each first-process condition encountered later in
the schedule, its ten one-measurement series are collected at that position;
expanding the condition into distinct fresh processes does not change the
single-row/two-row ordering above.

Each batch serializes one flat `raw_observations` ledger in append order. The
ledger includes correctness attempts plus every observation from accepted or
rejected timing series, assigns contiguous global indices, and repeats the
batch, case, and process identities needed to interpret the referenced raw
record. The separate correctness, first-process, costly, major, and diagnostic
arrays retain full typed detail but do not independently prove execution order.

Both public batch records retain the complete captured input selection
`selected_rows: [0, 1]`. `router_detail.batch_order` is derived from the first
correctness case in the ordered ledger: the linked source is
`single_row_first`, and its counterbalanced target is `two_row_first`.

The stored order seed is `22002`; it identifies this frozen schedule and is not
used for unrecorded ad-hoc shuffling. A later second independent batch is
required when feasible and reverses the single-row/two-row order within each
paired step to counterbalance case-order effects. The second batch receives a
new batch ID and process replication IDs. If it cannot be collected, evidence
must give a bounded unavailable reason and every related claim must state that
between-batch variation was not measured. Results from the two batches are
never silently pooled.

## 6. Timing boundaries and synchronization

Durations come from `time.perf_counter_ns()` or an equivalently monotonic,
high-resolution source and are stored as positive integer nanoseconds. An MLX
interval ends only after the declared outputs are evaluated and
`mx.synchronize(mx.gpu)` completes. Scheduling time is not execution time.

The worker clock is identified as `perf_counter_ns`. The supervising Rust
command separately identifies request-window durations as `rust_std_instant`.
Those clock domains are never subtracted from or silently merged with one
another. A request that aborts before worker evaluation retains its positive
supervisor-observed end-to-end request duration, records
`total_evaluated_router` as `unavailable`, and records F32 dequantization as
`not_applicable`. It must not fabricate a worker duration or claim evaluation.

`request_sent` records whether the supervisor handed the request to an admitted
worker; it is independent of whether a valid evaluated result returned. Three
pre-evaluation abort lifecycles are retained distinctly. A worker spawn failure
has `request_sent: false`, a `spawn started`/`spawn failed` lifecycle, and a
fallback request window enclosing that failed lifecycle. An admitted-request
timestamp failure after spawn has `request_sent: false`, exact failure
code/stage `internal_worker_error`/`request_observation`, and an owned `spawn
started`/`spawn passed`/eventual `shutdown` lifecycle; its fallback UTC window
is not treated as a lifecycle bound. A worker or protocol failure after request
submission has `request_sent: true`, an owned lifecycle, and a request window
inside it even though `evaluated` and `synchronized` remain false. All three
retain `aborted` status and failure evidence without output, memory gauges,
application tensor bytes, or cache-read claims.

Each real result also records application-level positional router-tensor bytes
returned and the cache outcome. The only admitted pairs are `1,048,576` bytes
with `read_and_cached`, or zero bytes with `cache_hit`. Every passing costly
force-read result must use the former pair; every cache-hit result uses the
latter. These fields describe bytes returned to the application and its
validated in-process cache, not physical device I/O, cache eviction, or proof
of a cold filesystem. The public detail binds this meaning with the exact
constant `application_positional_read_not_physical_disk_io`.

For non-force-read work, the first successful access in each worker uses
`read_and_cached` with exactly 1,048,576 bytes and later successful accesses in
that worker use `cache_hit` with zero bytes. Memory evidence forbids a summed
total, requires MLX peak bytes to be no lower than active bytes when both are
available, couples process-footprint bytes with their stable source, and uses a
stable pressure label; passing rows require admitted `normal` pressure.

Every experiment represents each boundary as `observed` with its exact duration
or `unavailable`/`not_applicable` with a bounded reason:

| Boundary | Protocol treatment |
|---|---|
| Complete checkpoint identity/hash and environment admission | Outside router-operation timing |
| Exact positional tensor read | Separate file-I/O observation |
| Storage validation and F32 decode | Separate host observation; dequantization is `not_applicable`, never zero |
| Host-to-MLX construction/transfer | Separate only when technically separable |
| Graph construction | Separate only when technically separable |
| Compilation or first evaluation | Separate when distinguishable; never merged silently with warm work |
| Projection | Evaluated/synchronized in stage mode |
| Top-k selection | Evaluated/synchronized in stage mode |
| Selected-probability normalization | Evaluated/synchronized in stage mode |
| Projection-through-normalization total | Primary minimal boundary with one final evaluation/synchronization |
| Synchronized readback | Separate when observable |
| End-to-end router command | Explicitly labeled secondary boundary |

`minimally_instrumented` uses the fewest barriers needed to evaluate all final
outputs and is the only major total-latency mode. `stage_instrumented` forces
intermediate evaluation/synchronization and is diagnostic. The two modes have
separate raw observations and summaries. Stage values are not summed into the
minimal total and no equality between the stage sum and minimal total is
claimed. An unavailable or inseparable phase is never recorded as duration
zero.

Summaries are grouped independently by source commit, experiment, case, batch,
process replication, condition, instrumentation mode, timing boundary,
requested/selected device, and materially different load, power, or thermal
state. Incompatible groups are never pooled.

### 6.1 Bounded complete-detail publication

Every external-checkpoint envelope carries one closed `router_detail` object
with the sanitizer-attested SHA-256 of its preserved external candidate and an
independently recomputable canonical SHA-256 of its paired public environment
evidence. Because the original candidate remains outside Git,
`source_candidate_sha256` is rechecked against it during T086 sanitization and
is not reconstructible from public bytes alone. The detail retains the complete ordered observation ledger; both
case outputs from the independent oracle; every Apple correctness attempt;
complete canonical logits, full probabilities, selected IDs, selected
probabilities, and normalized weights or an explicit unavailable value on an
aborted pre-execution attempt; whole-output and required `0..16`/`64..80`
comparisons; every timing-series membership list; worker lifecycle events;
supervisor request windows; and result resource records.

Canonical numeric arrays are bounded by the two frozen case shapes and are
hashed from little-endian F32 or unsigned-32 bytes. An output hash without the
corresponding bounded values is insufficient for a passing external record.
Observation IDs are the exact join key across the flat ledger, correctness or
timing detail, request window, and resource record. The validator rejects
missing, duplicate, reordered, or orphaned joins and any mismatch between
values and hashes. This representation adds reviewability; it does not add a
new measurement, tolerance, or acceptance rule.

The top-level correctness summary is recomputed from every retained detailed
logits comparison (counts and weighted error statistics), while ID/order counts
come from the corresponding complete output comparisons. A stopped prefix may
therefore project one case; a complete record projects both. It cannot
contradict the retained detail or invent metrics when no valid output exists.

Each timing-series record distinguishes planned warm-up/measurement counts from
attempted counts and the retained observation count. A stopped series retains
the exact attempted prefix; it never pads an incomplete `5+N` plan with
unattempted IDs. A closed nullable `terminal_failure` records orchestration,
post-request identity, shutdown, observed post-run interference, or an
unavailable post-run environment admission that occurs without fabricating a
failed request observation. Top-level failures are the ordered union of raw
request failures and that terminal failure.

If every request passes but the after snapshot reports material interference,
the envelope is `blocked`, keeps the complete raw/detail ledger, uses terminal
phase `environment_interference`, and publishes neither capabilities nor
statistical summaries. It is not passing performance evidence.

If every request passes but the after snapshot is unavailable, the envelope is
also `blocked`, keeps the complete raw/detail ledger, uses the distinct terminal
phase `environment_admission_unavailable`, and publishes neither capabilities
nor statistical summaries. Its combined environment admission is `postponed`,
not `observed_interference`; it is not passing performance evidence and cannot
be relabeled as observed interference.

A linked later-batch record shares immutable command arguments and build facts,
but its per-record process exit status remains outcome evidence rather than an
immutable identity field. This permits a passed first batch to link truthfully
to a failed later batch without coercing either exit code.

The canonical public envelope and the complete internal candidate (sorted
keys, two-space indentation where applicable, trailing newline, UTF-8) MUST
each be no larger than 4 MiB. The runtime, sanitizer, and publication
validators admit at most 100,000 JSON nodes at depth 64. One
node means one JSON container or scalar value; object keys are excluded from
the node count but remain subject to privacy and field-name validation.

## 7. Statistics

Raw integer nanoseconds are the source of truth. Warm-ups, failures, aborts,
and excluded observations are retained but do not enter the successful
measurement summary. For every compatible successful measurement group,
publish sample count, arithmetic mean, sample standard deviation, minimum,
maximum, p5, p25, median/p50, p75, p95, and coefficient of variation.

For sorted samples `x[0] ... x[n-1]`, percentiles use Hyndman-Fan Type 7:

```text
h = (n - 1) * p
j = floor(h)
g = h - j
Q(p) = x[j] + g * (x[min(j + 1, n - 1)] - x[j])
```

The mean is `sum(x) / n`. Sample standard deviation uses denominator `n-1`
and is `null` with reason when `n < 2`. Coefficient of variation is sample
standard deviation divided by the mean and is `null` with reason for a zero or
undefined mean. NaN and infinity are forbidden. The validator recomputes every
summary and its exact included observation IDs from raw evidence.

The bounded generator admission limits are at least 512 summaries per record
and 1,024 plotted summary rows. These are serialization-capacity limits for
the frozen two-batch schedule, not permission to pool processes or conditions.
Every generated row derives its process-replication label from the raw
observations included by that summary rather than from the envelope's anchor
process field.

## 8. Environment, resource, and interference admission

Admission is rechecked before notified access, before CPU capture, before each
Apple batch/replication, and after each executed batch. Observations are
public-safe and include macOS/build, arm64 architecture, Apple chip, total
unified memory, CPU counts, filesystem type and available bytes without mount
path, tool/runtime versions, intended/selected device, memory pressure,
physical process footprint, MLX active/cache/peak gauges, power mode and
thermal state when observable, and a sanitized concurrent-workload category.

The collector records an explicit symbolic storage-root role and never accepts
the checkpoint file as a storage operand. Before and after snapshots remain
separate and are bound to worker-supplied benchmark process/MLX gauges; the
collector's own short-lived process gauges are labeled as collector-only.
Selected backend/device evidence comes from the evaluated worker result, not
from the environment collector.

The existing conservative
[Feature 001 memory budget](../validation/models/qwen3-30b-a3b-q8_0-memory-budget.json)
remains the minimum checkpoint gate: fresh available disk is at least
`134,761,081,856` bytes; total unified memory satisfies the recorded
`42,949,672,960`-byte physical admission requirement, including the mandatory
`34,359,738,368`-byte system headroom reserve; and system memory pressure is
observable and `normal`. Feature 002 does not borrow from that reserve. Any new
external oracle/candidate storage must fit in addition to it without aliases
or paths inside Git. A missing mandatory gauge or arithmetic overflow fails
admission rather than assuming capacity.

Power mode and thermal state are recorded before and after when observable.
An observed serious/critical thermal state, a material thermal transition,
changed power mode within a batch, or non-normal memory pressure aborts the
active batch. An unavailable non-mandatory power/thermal observation records
the attempted method and reason and prevents a claim about that property; it is
not fabricated as normal.

Local inference, another accelerator benchmark, a large build, sustained
memory-pressure work, or another deliberate compute/storage workload on the
same host is material interference. The operator is asked to pause local
inference by the required NTFY message before model access. If the pause or
resource availability cannot be established, collection is postponed and the
operator is pinged before proceeding. Process command lines, usernames, and
private paths are never captured; evidence records only a public-safe workload
category, observation method, count/state, and admission decision.

Material interference present before a batch prevents a primary clean batch.
If it begins during collection, the current attempt is retained as
failed/aborted or as a separately labeled `observed_interference` batch. It is
never merged with the primary clean summary. Different pressure, load, power,
thermal, process, cache, commit, instrumentation, case, or batch conditions are
incompatible unless this protocol explicitly groups them.

The workload category is an explicit required operator declaration; it never
defaults to `none`. As an additional conservative precommitted gate, both the
one-minute and five-minute load averages must be no greater than `0.75` times
the observed logical CPU count. A missing, negative, non-finite, or higher load
observation postpones the batch. This load rule cannot prove that an undeclared
GPU workload is absent, so the explicit workload declaration remains required.

## 9. Exclusion and retention policy

The v1 measured-sample exclusion policy is `retain-all-measurements-v1`:

- no successful measured observation is removed because it is slow, fast, an
  outlier, inconvenient, or changes a summary;
- warm-ups are retained and omitted from measurement summaries solely because
  their predeclared observation kind is `warmup`;
- failed and aborted attempts are retained and counted separately;
- an observation interrupted by a predefined interference/identity/resource
  stop is retained with its stable status, failure code, and condition; and
- an `excluded` status is legal only for a rule identified in a later protocol
  amendment. Any such publication must include unfiltered and filtered
  summaries and the exact excluded observation IDs.

Every attempted warm-up, measurement, first-read observation, clean-process
replication, failure, abort, and unavailable phase remains in the candidate
record. A passing record cannot omit earlier failed attempts from the same
experiment. Failed or aborted experiment IDs never transition to passed; a
retry receives a new ID.

Committed raw records, protocol versions, manifests, sidecars, and artifacts
referenced by a claim are append-only and retained for the lifetime of that
claim and repository history. Publication uses exclusive creation and atomic
installation and refuses an existing experiment ID, filename, or symlink.
Original private external candidates are preserved outside Git through
validation and stop/closeout reconciliation; their later local retention is an
operator decision. Model files, extracted weight bytes, caches, build trees,
and private logs remain external and are never publication artifacts.

## 10. Amendment policy

This file's committed SHA-256, protocol ID, and version are recorded in every
experiment. No rule changes after inspecting affected model, oracle, Apple, or
timing output. A change to a tolerance, case, input, count, timing boundary,
grouping, ordering, exclusion, resource, or acceptance rule requires:

1. preserving this protocol and every prior raw attempt;
2. a new protocol version and amendment ID;
3. a bounded rationale and list of superseded protocol/experiment IDs;
4. a clean reviewed commit before observing new affected output; and
5. new experiment IDs plus a complete rerun of every affected case from the
   beginning.

A non-semantic clarification may increment the patch version only when it
cannot change which evidence passes. It still produces a new committed hash.
An amendment never rewrites or promotes a failed historical record.

## 11. Privacy and publication boundary

Public records use repository-relative paths or symbolic placeholders such as
`$PULSARMLX_MODEL_GGUF`. They retain immutable repositories, revisions,
filenames, sizes, hashes, license references, bounded legal hidden-state values,
and reproducible commands without expanded local paths.

Public evidence rejects usernames, absolute home/model/cache/private-mount
paths, host names, serial numbers, hardware UUIDs, account identifiers, private
email identity, process command lines, credentials, authorization headers,
cookies, private keys, shell history, and environment keys or values containing
`TOKEN`, `SECRET`, `PASSWORD`, `AUTH`, `COOKIE`, or `KEY`. It also rejects model
bytes, extracted router-weight bytes, large binaries, and caches. The bounded
two-row hidden-state fixture may be published only after license/provenance,
schema, semantic, size, privacy, and staged-content validation pass.

External candidates are validated and sanitized before an append-only raw copy
is installed. Raw evidence is committed and pushed before tables, figures, or
claims are generated from its committed SHA. Generators contain no measured
constants and must reproduce outputs byte-for-byte from validated committed
raw records.

## 12. Stop conditions and required response

Stop at the deepest already verified boundary, retain a failed or aborted
attempt when safe, and do not change the oracle, tolerance, labels, or scope if
any of these occurs:

- the clean-source, CI, NTFY, checkpoint provenance/license/identity, read-only
  file, or post-execution identity gate fails;
- model access would begin before acknowledged notification;
- router occurrence, name, dimensions, orientation, type, offset, length,
  range, hash, expert count, top-k, scale, bias, or normalization cannot be
  proved exactly;
- direct token bounds, capture size, two-row distinctness, two-capture identity,
  CPU-only placement, synchronization, one-split trace, or cancellation before
  router/expert execution fails;
- the standalone oracle imports the implementation under test, scalar and
  NumPy cross-checks disagree, or a real rank-8/rank-9 F32 tie exists;
- any ID/order mismatch, tolerance failure, non-finite value, invalid weight
  sum, fallback, wrong device, missing evaluation/synchronization, or
  ten-repeat hash difference occurs;
- disk/headroom, normal memory pressure, mandatory gauges, thermal/resource
  admission, or the operator's local-inference pause is unavailable or fails;
- instrumentation changes semantics and no synchronized minimally instrumented
  total can be retained;
- schema, privacy, append-only publication, deterministic generation,
  clean-checkout reproduction, artifact linkage, or claim traceability fails;
  or
- continuing requires expert MLP execution, routed aggregation, a complete
  transformer layer/model, language-model-head output, generation, serving,
  custom Metal, a model/weight commit, destructive action, or a Linux/CUDA
  behavior change.

After T073, every terminal stop sends a best-effort blocker notification to
NTFY topic `Mahdi-Dev` stating that local inference may resume. A terminal stop
before access states that model access never began and local inference was
never paused. Notification failure is reported accurately and never authorizes
access or hides the blocker.

## 13. Claim boundary

Even a passing run under this protocol can establish only the exact bounded
router cases and timing conditions recorded. It does not establish an expert
MLP, selected-expert execution, routed-MoE aggregation, attention in
PulsarMLX, a complete transformer layer/model, language-model-head logits,
tokens, generation, serving, custom Metal, full or giant-model inference,
projected tokens per second, broad Qwen/quantization support, or Linux/CUDA
runtime parity. Until validated real evidence is committed and reproduced,
all such router capability and performance claims remain unverified.
