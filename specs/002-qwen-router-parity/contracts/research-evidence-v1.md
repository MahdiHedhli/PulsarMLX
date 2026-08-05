# Contract: Research Evidence v1

**Status**: Proposed; MUST be implemented, validated, and committed before the
first Feature 002 measurement

**Feature**: `002-qwen-router-parity`

## Purpose

This contract defines the first publication-oriented evidence format for
PulsarMLX. It governs correctness, timing, resource, failure, and claim records
for the bounded Qwen3MoE layer-0 router experiment. It supplements, but does not
retroactively replace or relabel, the heterogeneous `schema_version: 1`
records under `docs/validation/`.

The contract admits evidence only for the exact operation and inputs named by
the record. Router evidence never implies expert execution, routed-expert
aggregation, a complete layer or model, logits from the language-model head,
generation, serving, projected tokens per second, giant-model performance, or
Linux/CUDA runtime parity.

## Schema identity and compatibility

The authoritative machine-readable schemas MUST be committed at:

```text
schemas/research/v1/experiment.schema.json
schemas/research/v1/router-parity.schema.json
```

Every Feature 002 raw record MUST identify them with:

```json
{
  "evidence_schema": "pulsarmlx.research.experiment",
  "evidence_schema_version": "1.0.0",
  "payload_schema": "pulsarmlx.research.router-parity",
  "payload_schema_version": "1.0.0"
}
```

The router schema extends the experiment envelope; it may narrow fields but
MUST NOT weaken the envelope. Fixed objects SHOULD reject unknown fields.
Explicit architecture metadata maps may allow documented extension keys.

A breaking field, interpretation, unit, comparison, or statistics change
requires a new major schema directory. An additive optional field requires a
minor version. A clarification that cannot change accepted documents may use a
patch version. Validators MUST reject unsupported versions instead of guessing
or silently coercing them.

Protocol changes after results are observed require a new protocol version and
new experiment IDs. The original protocol and evidence remain committed and
distinguishable. A post-amendment record MUST name the superseded protocol,
amendment reason, and newly executed batch; it MUST NOT overwrite or mutate the
earlier raw record.

## Required experiment envelope

Every raw experiment document MUST contain all of the following groups. A
field that is observable only conditionally remains present as an observation
object whose status is `observed` or `unavailable`; `unavailable` requires a
bounded reason and source or attempted method.

### Record identity

- `experiment_id`: stable, unique, lowercase identifier that also determines
  the raw evidence filename;
- `feature_id`: exactly `002-qwen-router-parity` for this feature;
- `record_kind`: `correctness`, `timing`, `combined`, `failed`, or `aborted`;
- `actual_status`: `passed`, `failed`, `blocked`, or `aborted`;
- `started_at_utc` and `completed_at_utc`: UTC timestamps;
- `source_commit`: full 40-character Git commit exercised by the experiment;
- `source_worktree_before`: MUST be `clean` for evidence eligible to verify a
  claim;
- `source_worktree_after`: `clean` or `declared_evidence_outputs_only`, with
  the exact repository-relative output paths when the latter is used;
- `protocol_id`, `protocol_version`, `protocol_path`, and protocol SHA-256;
- `batch_id`, `process_replication_id`, benchmark-order policy, and deterministic
  order seed;
- exact shell, command string, argument vector, working-directory policy, exit
  code, and build profile/features; and
- repository-relative artifact paths plus their SHA-256 values where the files
  already exist when the record is finalized.

The exact command MUST remain executable from a clean checkout after supplying
the externally verified model through a documented environment variable. It
MUST use symbolic placeholders such as `$PULSARMLX_MODEL_GGUF`; it MUST NOT
embed the expanded private absolute path.

### Model, tensor, input, and oracle identity

The envelope MUST record:

- upstream model repository, immutable revision, file name, file byte length,
  complete file SHA-256, license/provenance reference, and access policy;
- architecture name and all metadata that controls the router, including
  hidden width, expert count, selected-expert count, tensor orientation,
  router normalization/weighting rule, and tie rule;
- every relevant tensor's exact name, semantic role, occurrence count,
  absolute data offset, encoded length, exclusive end offset, GGUF dimensions,
  reader shape, execution shape, dtype, quantization format and block layout,
  and encoded-byte SHA-256;
- hidden-state fixture ID, graph boundary, source/capture contract, token and
  position identity where applicable, shape, dtype, byte order, byte length,
  canonical byte SHA-256, row selection, and redistribution policy;
- CPU oracle ID, project/component, immutable source revision, version,
  generation command, input hash, output hash, canonical byte encoding, and a
  statement explaining why it is independent of the MLX implementation under
  test; and
- correctness prerequisite record IDs for timing evidence.

The CPU oracle MUST NOT import, invoke, copy output from, or otherwise delegate
to the MLX implementation under test. The oracle procedure and comparison
policy MUST be frozen before the corresponding Apple output is inspected.

### Software, hardware, and resource environment

The environment group MUST record:

- MLX, Python, Rust, Cargo, worker-protocol, and PulsarMLX versions;
- macOS product version and build, shell architecture, and selected backend and
  device;
- Apple chip model, total unified-memory capacity, and logical and physical CPU
  counts;
- storage filesystem type and available capacity at the admitted external
  model location without recording that location;
- memory pressure and process memory/resource gauges before and after the run
  where reliably observable;
- power mode and thermal state before and after when observable without
  privilege, or an explicit `unavailable` observation with reason;
- the interference/load observation method, bounded pre-run observation,
  admission decision, and any material concurrent workload; and
- every execution-affecting environment variable from a checked-in allowlist,
  represented by a safe value or symbolic placeholder.

Serial numbers, hardware UUIDs, host names, usernames, account identifiers,
full process command lines, and private mount paths are not environment facts
needed by this contract and MUST NOT be captured.

## Router-parity payload

Each correctness case in the router payload MUST contain:

- stable case and input-row IDs;
- real-checkpoint or synthetic provenance;
- complete router-logit shape and dtype;
- CPU and MLX router logits as bounded numeric arrays and their canonical
  little-endian float32 SHA-256 values; a hash-only representation is permitted
  only with an explicit size or redistribution reason and a separately linked
  local regeneration command;
- CPU and MLX complete 128-way full-softmax probabilities under the same
  bounded-array-or-hash rule, with numerical comparison metrics under the
  frozen probability tolerances;
- exactly eight selected expert IDs per real input row;
- the eight selected full-softmax probabilities before selected-sum
  renormalization;
- the eight normalized routing weights;
- the identical CPU-oracle values for every compared field;
- the score-descending, expert-ID-ascending tie rule or the separately proven
  architecture rule if checkpoint inspection establishes a different one;
- the exact architecture-correct normalization and weighting rule;
- absolute and relative tolerances selected before Apple execution;
- compared count, exact-ID mismatch count, ordering mismatch count, numerical
  mismatch count, maximum absolute error, mean absolute error, RMSE, maximum
  relative error where meaningful, first mismatch location, and pass/fail;
- non-finite input/output policy and observed non-finite count; and
- per-repetition logits, full-softmax-probability, IDs,
  selected-probability, and normalized-weight hashes for at least ten identical
  evaluated executions.

Expert IDs and ordering compare exactly. Floating-point values use the frozen
per-element rule:

```text
abs(candidate - reference) <= absolute_tolerance
                              + relative_tolerance * abs(reference)
```

The reporting denominator for relative error MUST be defined before execution.
NaN and positive or negative infinity in an admitted input, oracle output,
candidate output, normalization denominator, or error metric fail the case.
A checksum supplements but never replaces numerical comparison.

Determinism evidence MUST retain all repetition identities. If any repeated
canonical candidate hash differs, the record MUST report the numerical spread,
mark the v1 experiment failed, and trigger the documented stop condition. It
MUST NOT substitute a looser numerical-only repeatability policy after output
is observed.

## Raw observation contract

Every attempted warm-up, measured repetition, clean-process replication,
failed attempt, and aborted attempt MUST remain in `raw_observations`. Each
observation contains:

- unique observation ID, case ID, batch ID, process-replication ID, and stable
  order index;
- `observation_kind`: `warmup`, `measurement`, or
  `clean_process_replication`;
- `condition`: `warm`, `first_read_new_process_os_cache_uncontrolled`,
  `controlled_cold`, or another predeclared bounded value;
- `instrumentation_mode`: `minimally_instrumented` or `stage_instrumented`;
- start/end timestamps and monotonic duration source;
- status: `passed`, `failed`, `aborted`, or `excluded`;
- requested and selected device, `fallback_used`, `evaluated`, and
  `synchronized`;
- stage observations, output hashes, correctness outcome, and independently
  observable resource gauges;
- failure code/message for failed or aborted attempts; and
- an exclusion rule ID and reason for an excluded observation.

Warm-ups are retained but excluded from measured summaries. Failed and aborted
attempts are counted and reported separately; they are never deleted because
they lack a usable latency. Exclusion is allowed only by a rule frozen in the
protocol before measurement. Outlier magnitude alone is not an exclusion rule.
When an exclusion applies, the record MUST publish both the unfiltered and
filtered summaries, every excluded observation ID, and the rule used.

An unsuccessful top-level experiment still produces a durable failed or
aborted raw record when doing so can be completed safely. Failure evidence MUST
never be rewritten as `not_run`, omitted from the index, or promoted to a
passing claim.

## Timing boundaries

Timing MUST use a monotonic high-resolution clock with durations stored as
positive integer nanoseconds. MLX work is complete only after explicit
evaluation and device synchronization; scheduling time alone is not execution
evidence.

The timing payload MUST represent these stages as either `observed` with a
duration or `unavailable` with a bounded reason:

- setup and admission outside the primary operation;
- file I/O;
- host decode/dequantization where applicable;
- host-to-device tensor transfer where separable;
- graph construction;
- compilation or first-evaluation cost where distinguishable;
- router projection;
- top-k selection;
- normalization; and
- total evaluated router execution.

The minimally instrumented total uses the fewest synchronization points needed
to obtain the final evaluated result and is the primary total-latency measure.
Stage-instrumented timing may force intermediate synchronization and therefore
is a diagnostic breakdown, not a substitute for the minimally instrumented
total. The two modes MUST use separate observations and summaries. Stage
durations MUST NOT be summed into a claimed total when they overlap or when the
instrumentation changes evaluation/fusion semantics. If tracing overhead is
material, the record states the overhead comparison and publishes both modes.

Complete model hashing, checkpoint admission, and one-time environment capture
remain outside operation latency unless an explicitly labeled end-to-end setup
experiment includes them. A new process does not prove an uncached filesystem;
without controlled cache evidence it MUST be labeled
`first_read_new_process_os_cache_uncontrolled`, not `cold filesystem`.

## Warm-up, repetition, and batch policy

- Every warm real-checkpoint timing case uses at least five retained warm-up
  runs and at least ten retained measured repetitions.
- Every inexpensive microbenchmark uses at least five retained warm-ups and at
  least thirty retained measured repetitions.
- A condition whose purpose is first-process or controlled-cold behavior may
  declare warm-up technically inappropriate. It records zero warm-ups, the
  precommitted exception, and at least ten measured costly repetitions.
- The two major benchmarks are exactly the minimally instrumented single-row
  real router case and minimally instrumented two-row real router case. Each
  includes at least one complete clean-process replication. Stage-instrumented
  series are diagnostic and are not additional major benchmarks.
- Case order is stable. If order effects are plausible, it is deterministically
  randomized or counterbalanced with the seed retained in evidence.
- A second independent batch later in the session is required where feasible.
  If unavailable, the result and claims state that between-batch variation was
  not measured.
- Warm, first-process OS-cache-uncontrolled, controlled-cold when independently
  proved, minimally instrumented, stage-instrumented, different commits,
  different batches, and materially different thermal/load conditions are
  summarized separately. They MUST NOT be pooled silently.

The experiment admission gate checks memory pressure, storage headroom,
thermal/power observability, and other significant workload before collection.
Material interference postpones the benchmark or is retained as a separately
labeled non-clean batch; it is not merged into the primary clean summary.

## Summary statistics

All required statistics are derived from retained measured observations by one
checked-in implementation. Raw integer nanoseconds are the source of truth.
For each independently grouped timing stage and condition, publish:

- sample count `n`;
- arithmetic mean;
- sample standard deviation;
- minimum and maximum;
- p5, p25, median/p50, p75, and p95; and
- coefficient of variation.

For sorted samples `x[0] ... x[n-1]`, percentile `p` uses Hyndman-Fan type 7:

```text
h = (n - 1) * p
j = floor(h)
g = h - j
Q(p) = x[j] + g * (x[min(j + 1, n - 1)] - x[j])
```

The arithmetic mean is `sum(x) / n`. Sample standard deviation is:

```text
sqrt(sum((x - mean)^2) / (n - 1))
```

and is undefined for `n < 2`. Coefficient of variation is
`sample_standard_deviation / mean`; it is undefined for a zero mean. An
undefined value is encoded as `null` with a reason, never as zero, NaN, or
infinity. Benchmark timing samples are positive, so their admitted means are
positive.

The summary names its algorithm version and included observation IDs. The
validator recomputes every statistic from raw observations using the same
checked-in implementation and rejects missing, stale, non-finite, differently
grouped, or hand-edited summaries. Tables and figures consume validated raw
records or regenerated summaries only; reported numbers are never embedded in
generator source.

## Artifact layout and immutability

Feature 002 publication artifacts use:

```text
docs/research/raw/002-router-parity/<experiment-id>.json
docs/research/tables/<generated-table>.csv
docs/research/tables/<generated-table>.md
docs/research/figures/<generated-figure>.svg
```

Raw files are append-only. Evidence generation MUST use exclusive creation and
refuse an existing destination. A rerun, repaired capture, protocol amendment,
or changed commit receives a new experiment ID and file. Temporary writes are
installed atomically and cannot follow a symlink to the checkpoint or another
private file.

Every generated table or figure has a repository-relative provenance sidecar
or reviewer-index entry naming its generator, source raw files and SHA-256
values, generation command, and commit. Figures are generated only from
committed raw data. Generated outputs MUST be reproducible without checkpoint
access and MUST fail rather than silently skip invalid or absent input.

## Privacy and secret boundary

Public evidence MUST NOT contain:

- absolute home-directory, external-model, cache, or private mount paths;
- usernames, host names, serial numbers, hardware UUIDs, account identifiers,
  email addresses used as private identity, or private process command lines;
- GitHub, Hugging Face, NTFY, or other access tokens;
- passwords, authentication headers, cookies, private keys, shell history, or
  unredacted secret-bearing environment values;
- model bytes, extracted tensor bytes, or large generated binaries.

Environment keys containing `TOKEN`, `SECRET`, `PASSWORD`, `AUTH`, `COOKIE`,
or `KEY` are rejected rather than redacted into a nominally passing record.
Execution-relevant safe variables come from a checked-in allowlist. Path-valued
variables use symbolic placeholders while the exact external filename, byte
length, and SHA-256 preserve reproducibility.

Public upstream URLs, repository identities, revisions, file names, license
references, and cryptographic content hashes are permitted. The validator
scans nested keys and values before a record can be committed or cited.

## Claims ledger and promotion

`docs/research/CLAIMS_LEDGER.md` contains exactly one row per public claim using:

```text
| Claim | Evidence files | Commit | Scope | Status | Caveat |
```

The claim text begins with a stable identifier such as `F002-C01`. Status is
one of `verified`, `provisional`, `rejected`, or `unsupported`. The commit is
the source commit exercised by the evidence. Scope and caveat are never blank.

A claim is `verified` only when all of the following hold:

1. the raw record passes schema and semantic validation;
2. the measured source was clean and immutable;
3. exact-scope correctness and required repetitions passed;
4. the evidence is committed and indexed by repository-relative path and
   SHA-256;
5. a clean-checkout reproduction command exists and validates the same model,
   input, oracle, and output identity; and
6. the claim does not contradict any warning, exclusion, unavailable
   observation, or unsupported interpretation.

Performance claims additionally require verified correctness for the identical
semantics, dtype, quantization, dimensions, evaluated outputs, timing mode, and
cache/process condition. First-process OS-cache-uncontrolled, independently
proved controlled-cold, and warm observations are not compared as if
equivalent. Router measurements MUST NOT be extrapolated to expert, layer,
model, generation, serving, token-throughput, or giant-model performance.
Projections remain explicitly labeled and outside verified-result tables.

## Validation and failure rules

The checked-in validator MUST perform structural schema validation and semantic
recomputation. At minimum it rejects:

- missing or unknown required fields and unsupported schema versions;
- abbreviated/invalid commits or a non-clean source promoted as verified;
- mismatched model, tensor, input, protocol, oracle, or artifact hashes;
- invalid tensor offsets, lengths, dimensions, orientation, dtype, or
  quantization identity;
- private paths, identifiers, secret keys/values, or model bytes;
- duplicate experiment or observation IDs and attempts to overwrite raw data;
- zero, negative, non-integral, or non-monotonic timing evidence;
- missing evaluation/synchronization, a fallback device, or an unselected GPU;
- insufficient warm-ups, repetitions, determinism trials, or clean-process
  replications;
- omitted failed/aborted observations, undeclared exclusions, or missing
  unfiltered summaries;
- pooled incompatible conditions, batches, commits, or instrumentation modes;
- stale or incorrectly computed statistics;
- invalid correctness metrics, silently changed tolerances, non-finite values,
  or incomplete mismatch detail; and
- claim promotion beyond the exact router boundary.

Validation failures use stable bounded codes, exit nonzero, and identify the
record and field without printing private values. A validator failure prevents
table/figure generation and prevents a claim from becoming `verified`; it does
not delete the raw record. Generators similarly fail closed on missing or
invalid evidence.

## CI and local-checkpoint boundary

CI MUST exercise everything that does not require the external checkpoint:

- positive and mutation-based schema fixtures;
- semantic validation and privacy/secret rejection;
- known-vector type-7 percentile, mean, sample-standard-deviation, and
  coefficient-of-variation tests;
- summary recomputation and incompatible-group rejection;
- frozen CPU-oracle contract tests that use redistributable fixtures only;
- exact-tie, near-tie, malformed, truncated, dimension, orientation,
  invalid-`top_k`, and non-finite synthetic cases;
- failure/aborted-run retention and append-only atomic writer tests;
- deterministic regeneration of tables, figures, claims ledger, and reviewer
  index from small committed raw fixtures; and
- explicit assertions that CI did not resolve or access an external model.

CI fixture success establishes only the named schema, statistics, generator,
and synthetic correctness boundaries. Hosted-runner results MUST NOT be used as
evidence for the local machine's checkpoint correctness, latency, memory,
storage, thermal, power, or capacity.

External-checkpoint experiments are local-only and require all of these gates:

1. the protocol, schemas, validators, statistics implementation, and their
   tests are already committed and green;
2. the worktree is clean at the measured source commit;
3. the external file matches the Feature 001 immutable identity and remains
   outside Git;
4. the memory, storage, load, and no-fallback admission checks pass;
5. NTFY topic `Mahdi-Dev` is notified immediately before model access; and
6. completion or blocker notification is sent after the feature result.

The local command first writes a complete candidate package to an external
working directory. Only after schema validation, semantic validation, privacy
review, sanitization, and explicit package verification may a controlled
append-only publication step install bounded raw evidence into the declared
repository path. Model weights, caches, private logs, and expanded external
paths remain outside the repository.
