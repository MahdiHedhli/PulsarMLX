# Data Model: Qwen3MoE Layer-0 Router Parity

**Status**: The v1 evidence/statistics foundation and the generated model-free
subset of the router request/result entities are implemented for committed
fixtures. The complete real `RouterExecutionResult`, external-artifact
observations, and real-checkpoint evidence remain planned; no Feature 002
real-router result exists.

Feature 002 has no database. Its entities are versioned Rust/Python protocol
values, bounded committed JSON evidence, generated publication artifacts, and
external immutable inputs. Model files and extracted tensor bytes remain
outside Git.

## Relationships

```text
FrozenProtocol ───────────────┐
                              v
EnvironmentSnapshot ──> ResearchExperiment <── CheckpointIdentity
                              |                         |
                              v                         v
                       RawObservation          RouterTensorIdentity
                              |                         |
                              v                         v
                     StatisticalSummary       HiddenStateFixture
                              |                         |
                              └────────┬────────────────┘
                                       v
                              RouterOracleResult
                                       |
                                       v
                              RouterExecutionResult
                                       |
                                       v
                              CorrectnessSummary
                                       |
                                       v
                               ClaimLedgerEntry
                                       |
                                       v
                                ArtifactManifest
```

## FrozenProtocol

Identifies the rules committed before any affected observation.

| Field | Type | Validation |
| --- | --- | --- |
| `protocol_id` | stable string | Exact registered protocol |
| `protocol_version` | semantic version | `1.2.0` for pre-execution amendment 002; amendment 001 and `1.0.0` remain in Git history |
| `path` | repository-relative path | Must resolve inside Git |
| `sha256` | 64 lowercase hex | Hash of the committed protocol file |
| `amendment_id` | optional stable string | Required after any result-informed change |
| `affected_experiment_ids` | list | Amendment cannot silently replace older results |
| `order_seed` | unsigned integer | Fixed before measurement when order can matter |
| `exclusion_rule` | structured policy | Default retains all attempts |

An amendment creates a new protocol identity. Pre-amendment records remain
distinguishable and affected experiments restart from the beginning.

## CheckpointIdentity

Reuses Feature 001's exact external artifact rather than creating a second
model-support claim.

| Field | Type | Validation |
| --- | --- | --- |
| `repository` | namespace/name | Exact `Qwen/Qwen3-30B-A3B-GGUF` |
| `revision` | full immutable commit | Exact previously admitted revision |
| `filename` | basename | Exact Q8_0 artifact |
| `size_bytes` | positive integer | Exact local and published size |
| `sha256` | 64 lowercase hex | Full local file hash |
| `license` | name and source | Must match recorded legal source |
| `architecture` | stable ID | Exact `qwen3moe` |
| `metadata` | typed key/value map | Includes embedding, expert, top-k, and routing keys |
| `external_locator` | sanitized placeholder | Never an absolute local path |

The identity is rechecked before and after every model experiment. Full-file
hash time is setup/admission, not router-operation latency.

## RouterTensorIdentity

Describes only the complete layer-0 router matrix.

| Field | Type | Validation |
| --- | --- | --- |
| `name` | string | Exact `blk.0.ffn_gate_inp.weight` |
| `semantic_role` | enum | `layer_0_router_projection` |
| `occurrence_count` | integer | Exactly one |
| `gguf_dimensions` | integer list | Expected `[2048,128]`; actual inventory is authoritative |
| `reader_shape` | integer list | Expected `[128,2048]` |
| `dtype` | stable GGUF type | Expected F32; actual inventory must prove it |
| `quantization` | enum | Expected `none_f32`; never inferred from file-level Q8_0 name |
| `absolute_offset` | nonnegative integer | Checked against file and tensor metadata |
| `encoded_length` | positive integer | Exact; expected 1,048,576 for F32 |
| `end_offset` | integer | Checked addition, no overflow, at most file length |
| `encoded_sha256` | 64 lowercase hex | Hash of the exact external range |
| `orientation_rule` | stable ID | Expert-major rows, 2,048 inputs per expert |
| `bias_tensor` | absent/present identity | Must be absent for admitted Qwen graph |
| `correction_bias` | absent/present identity | Must be absent |
| `weight_scale` | finite float | Exactly the admitted architecture value, expected 1.0 |

The Feature 001 `blk.0.ffn_gate_exps.weight` prefix is a different entity and
cannot populate any RouterTensorIdentity field.

## HiddenStateFixture

A genuine frozen router input captured from the independent CPU graph.

| Field | Type | Validation |
| --- | --- | --- |
| `fixture_id` | stable string | Unique and versioned |
| `source_checkpoint` | CheckpointIdentity reference | Exact same artifact |
| `capture_runtime` | project/revision/backend | Pinned CPU-only implementation; no MLX |
| `graph_node` | stable string | Exact `ffn_norm-0` or proven equivalent |
| `input_adapter` | stable enum | Exactly `direct_token_ids_v1` |
| `tokenizer_identity` | stable enum | Exactly `not_used_direct_token_ids` |
| `token_ids` | integer list | Exactly `[0,1]`, each proven inside observed vocabulary |
| `positions` | integer list | Exactly `[0,1]` |
| `context_tokens` / `batch_tokens` / `ubatch_tokens` | integer | Each exactly `2` |
| `evaluation_threads` | integer | Exactly `1` |
| `selected_rows` | integer list | `[0]` for the single-row case; `[0,1]` for the batch case |
| `shape` | integer list | Complete capture exactly `[2,2048]`; case view is `[1,2048]` or `[2,2048]` |
| `dtype` | enum | Canonical float32 |
| `byte_order` | enum | Little-endian |
| `values` | bounded float list or artifact ref | At most 2 rows/16,384 bytes; rows distinct; no model weights; finite only |
| `canonical_sha256` | 64 lowercase hex | Hash of canonical f32le bytes |
| `scope_warning` | string | Capture does not prove PulsarMLX attention/prior-layer execution |

A model-shaped synthetic probe uses a different fixture kind and cannot satisfy
the real-router acceptance gate.

## RouterOracleResult

Freezes independent CPU truth before Apple execution.

| Field | Type | Validation |
| --- | --- | --- |
| `oracle_id` | stable ID | Unique and versioned |
| `project` / `revision` | strings | Pinned source and full immutable revision |
| `generation_command` | sanitized exact command | No model path or credential |
| `independence_statement` | string | Must state no MLX/PulsarMLX worker import |
| `input_fixture_sha256` | SHA-256 | Exact HiddenStateFixture |
| `tensor_sha256` | SHA-256 | Exact RouterTensorIdentity |
| `logits` | row-major floats | Full `[rows,128]` values |
| `logits_f32le_sha256` | SHA-256 | Canonical full output hash |
| `full_probabilities` | row-major floats or bounded ref | Required full `[rows,128]` softmax result |
| `probabilities_f32le_sha256` | SHA-256 | Canonical complete full-softmax hash |
| `selected_expert_ids` | integers | Exact `[rows,8]` |
| `selected_probabilities` | floats | Before selected-sum renormalization |
| `normalized_weights` | floats | Exact `[rows,8]`, finite, row sums within policy |
| `output_sha256` | SHA-256 | Canonical combined result identity |
| `tie_observation` | enum/details | None, non-cutoff, or cutoff; any rank-8/rank-9 cutoff tie stops parity |

Two independently started llama.cpp captures of `ffn_norm-0` must have identical
canonical hashes and prove cancellation before router or expert execution. The
standalone scalar router computation must agree with a separate NumPy F32
cross-check before the result is frozen; no llama.cpp router node participates
in the oracle comparison.

## RouterExecutionResult

One evaluated Apple result for an immutable oracle case.

| Field | Type | Validation |
| --- | --- | --- |
| `case_id` | stable string | Exact oracle case |
| `backend` / `requested_device` | stable IDs | `apple-mlx` / `gpu` |
| `selected_device` | stable ID | Must be `gpu` |
| `evaluated` / `synchronized` | booleans | Both true |
| `fallback_used` | boolean | Must be false |
| `logits` and hash | bounded floats/SHA | Full `[rows,128]` |
| `full_probabilities` and hash | bounded floats/SHA | Full `[rows,128]` |
| `selected_expert_ids` | integer matrix | Exact `[rows,8]` |
| `selected_probabilities` | float matrix | Before renormalization |
| `normalized_weights` | float matrix | After renormalization |
| `repeat_output_hashes` | SHA list | Exact completed measured prefix; ten identical per case for completion |
| `repeat_selected_ids` | matrices or hashes | Exact completed measured prefix |
| `memory_gauges` | independent values | No invalid overlapping total |
| `runtime_identity` | version/platform fields | Exact MLX/Python/worker/device identity |

The worker response remains below the framed-protocol cap. Repetitions retain
full output once plus exact per-run hashes and IDs rather than duplicating every
float ten times.

## CorrectnessSummary

| Field | Type | Validation |
| --- | --- | --- |
| `compared_count` | integer | Exact per output kind |
| `id_mismatch_count` | integer | Must be zero for pass |
| `order_mismatch_count` | integer | Must be zero for pass |
| `numeric_mismatch_count` | integer | Must be zero outside tolerance |
| `first_mismatch` | optional bounded location | Required when any mismatch exists |
| `maximum_absolute_error` | finite float | Recomputed from raw values |
| `mean_absolute_error` | finite float | Recomputed |
| `rmse` | finite float | Recomputed |
| `maximum_relative_error` | float or reason | Zero-reference policy explicit |
| `absolute_tolerance` / `relative_tolerance` | finite floats | Match frozen protocol by value class |
| `non_finite_policy` | stable ID | Reject |
| `deterministic_repeat_count` | integer | `0..20` exact measured prefix; `20` for complete two-case evidence |
| `passed` | boolean | Derived, never hand-entered |

## EnvironmentSnapshot

All fields are public-safe. Observable fields are recorded as values;
unobservable fields use an explicit unavailable reason.

Required groups include paired before/after macOS version/build, arm64 architecture, Apple chip,
unified memory, physical/logical CPU counts, filesystem type/available bytes,
Python/MLX/Rust/Cargo versions, build profile/features, safe allowlisted
execution environment variables, power mode, thermal state, pre/post memory
pressure, and a sanitized concurrent-workload observation. Benchmark resources
separately retain worker process/MLX gauges and worker-derived backend, device,
fallback, evaluation, and synchronization facts. Usernames, serials, UUIDs,
email/account identities, process command lines, and the full environment are
forbidden.

## RawObservation

| Field | Type | Validation |
| --- | --- | --- |
| `observation_id` | stable string | Unique within experiment |
| `run_index` | nonnegative integer | Contiguous within kind/state |
| `batch_id` / `case_id` | stable strings | Match experiment |
| `observation_kind` | enum | `warmup`, `measurement`, `clean_process_replication` |
| `process_state` | enum | `fresh_process`, `reused_process` |
| `condition` | enum | `warm`, `first_read_new_process_os_cache_uncontrolled`, `controlled_cold`, or declared state |
| `instrumentation_mode` | enum | `minimally_instrumented` or `stage_instrumented` |
| `status` | enum | `passed`, `failed`, `aborted`, `excluded` |
| `durations_ns` | stage map | Positive integers or explicit not-applicable/unavailable |
| `output_sha256` | optional SHA-256 | Required after successful output |
| `correctness_passed` | optional boolean | Required for measured successful results |
| `failure` | optional bounded object | Required for failed/aborted attempts |
| `exclusion_rule_id` | optional string | Required only for predefined exclusions |

F32 router loading records dequantization as `not_applicable` with a reason,
not a fabricated zero. Stage barriers perturb laziness, so stage values never
need to sum to the minimally instrumented total.

## StatisticalSummary

Computed separately for each experiment, case, phase, process/cache state, and
instrumentation mode.

| Field | Rule |
| --- | --- |
| `sample_count` | Exact retained successful sample count |
| `minimum_ns` / `maximum_ns` | Exact integers |
| `mean_ns` | Arithmetic mean |
| `sample_standard_deviation_ns` | Denominator `n-1`; unavailable for fewer than two samples |
| `p5_ns`, `p25_ns`, `median_ns`, `p75_ns`, `p95_ns` | Hyndman-Fan Type 7 linear interpolation |
| `coefficient_of_variation` | Sample SD / mean; null plus reason for zero/undefined mean |
| `unfiltered_summary` | Always present for successful samples |
| `filtered_summary` | Present only when predefined exclusions apply |
| `excluded_observation_ids` | Exact list tied to rule ID |

## ResearchExperiment

| Field | Type | Validation |
| --- | --- | --- |
| `evidence_schema` | stable string | `pulsarmlx.research.experiment` |
| `evidence_schema_version` | semantic version | `1.2.0` for external detail; historical synthetic `1.1.0` is verified from its source commit |
| `experiment_id` | stable unique string | Append-only identifier |
| `feature_id` | stable string | `002-qwen-router-parity` |
| `evidence_scope` | optional enum | Explicit `synthetic_fixture` or `external_checkpoint`; omission is legacy fixture-only |
| `started_at_utc` / `completed_at_utc` | timestamps | UTC and ordered |
| `source_commit` | full Git SHA | Clean measured source |
| `worktree_before` / `worktree_after` | states | Only declared output may appear afterward |
| `exact_command` | structured command | Sanitized and reproducible |
| `protocol` | FrozenProtocol | Exact hash/version |
| `environment` | EnvironmentSnapshot | Complete public-safe fields |
| `model`, `tensors`, `inputs`, `oracle` | references/objects | Exact immutable identities |
| `observations` | RawObservation list | Every attempt retained |
| `summaries` | StatisticalSummary list | Recomputed from observations |
| `correctness` | CorrectnessSummary | Required before performance claim |
| `status` | state enum | Derived lifecycle state |
| `warnings`, `failures`, `unsupported_interpretations` | nonempty bounded strings | Explicit claim boundary |
| `artifacts` | repository-relative paths | Exist and hash through manifest |

State transitions are append-only:

```text
planned -> running -> passed
                   -> failed
                   -> aborted
passed  -> superseded (new protocol/result retained separately)
```

An experiment ID cannot be overwritten or reused. A failed or aborted record
cannot transition to passed; a new attempt receives a new ID.

## ClaimLedgerEntry

| Field | Validation |
| --- | --- |
| `claim_id` | Stable `F002-CNN` |
| `claim` | One bounded public statement |
| `evidence_files` | Existing committed raw/result files |
| `commit` | Clean measured source commit |
| `scope` | Exact checkpoint/tensor/case/depth |
| `status` | `verified`, `provisional`, `rejected`, or `unsupported` |
| `caveat` | Required boundary statement |

`verified` requires schema and semantic validation, passing exact-scope
correctness, committed raw evidence, clean-checkout reproduction, artifact
hashes, and no contradiction with exclusions.

## ArtifactManifest

Maps every raw record, schema, protocol, table, figure, report, fixture, and
reproduction command to its repository-relative path, SHA-256, generating
script, input hashes, and measured source commit. Generated tables and figures
must reproduce byte-for-byte from validated committed inputs.
