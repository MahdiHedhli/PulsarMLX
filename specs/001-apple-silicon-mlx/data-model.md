# Data Model: Apple Silicon MLX Backend Bring-Up

**Status**: Interface-level design. These records are not yet implemented.

The feature has no database. “Entities” are versioned Rust/Python protocol
values and committed Markdown or JSON evidence records. Model data and weights
remain external to Git.

## Relationships

```text
BackendSelection
        |
        v
BackendCapabilityReport ----> ValidationCase ----> EvidenceStatus
        |                           |                    |
        v                           v                    v
TensorContract ------------> ComparisonResult      Capability claim
        |                           ^
        v                           |
QuantizationCompatibility ---------+

ShardLayout --> ExpertReadRequest --> OwnedPayload --> RoutedMoeCase
                                                     |
ModelCompatibilityRecord ----------------------------+
        |
        v
BenchmarkRecord (only after all required correctness cases pass)
```

## BackendSelection

Represents an explicit user or test choice. There is no automatic substitution
between materially different backends.

| Field | Type | Validation |
| --- | --- | --- |
| `backend_id` | stable string/enum | `linux-cuda`, `apple-mlx`, or a future registered ID |
| `requested_device` | optional device selector | Required when the backend exposes multiple materially different devices |
| `allow_fallback` | boolean | Must be `false` for validation and benchmark evidence |

Invalid or unavailable selection produces a structured unsupported result; it
does not mutate the requested backend.

## BackendCapabilityReport

Captures what the runtime proved in the current process.

| Field | Type | Validation |
| --- | --- | --- |
| `schema_version` | positive integer | Exactly supported version |
| `backend_id` | string | Matches explicit selection |
| `runtime_version` | string | Exact MLX/backend version or `null` if unavailable |
| `host_arch` | string | Native architecture, not inferred from product name |
| `os_version` | string | Actual runtime value |
| `device_id` | string or `null` | Exact selected device when available |
| `device_state` | enum | `unavailable`, `available_unevaluated`, `evaluated` |
| `supported_ops` | set of operation IDs | Only operations with declared contracts |
| `supported_dtypes` | set | Explicit, never inferred from another backend |
| `supported_quantizations` | set | Must link to compatibility records |
| `exclusions` | string list | Bounded unsupported features |
| `probe_case_id` | optional ID | Required for `evaluated` |

### State transitions

```text
unavailable

available_unevaluated -- successful explicit device operation --> evaluated
          |
          +-- probe/error/tolerance failure -------------------> remains unevaluated
```

No failure transition silently changes the selected device to CPU. A report is
immutable evidence; a later probe creates a new report.

## WorkerSession

The persistent worker has an explicit state machine:

```text
starting -> negotiating -> ready_unevaluated -> ready_evaluated
   |             |                 |                   |
   +-------------+-----------------+-------------------+--> failed
                                 ready_* -> shutting_down -> stopped
```

`negotiating` validates protocol, runtime, architecture, Metal, device, and
limits. Only a passing evaluated probe permits `ready_evaluated`. Malformed or
oversized frames, timeout, EOF, version mismatch, unexpected stdout, nonzero
exit, and evaluation/parity failure have structured outcomes and invalidate the
session. Shutdown has a bounded graceful phase and records forced cleanup as an
error.

## TensorContract

Defines semantics at a backend boundary.

| Field | Type | Validation |
| --- | --- | --- |
| `operation_id` | stable string | Names one semantic operation |
| `logical_shape` | nonempty `u64[]` | Checked element-count product |
| `storage_shape` | nonempty `u64[]` | Explicit GGUF/fixture orientation |
| `layout` | enum | Named, documented physical ordering |
| `input_dtype` | enum | Backend support checked before execution |
| `accumulation_dtype` | enum | Required for reductions/matmul |
| `output_dtype` | enum | Checked against actual result |
| `encoded_byte_count` | optional `u64` | Exact for encoded/quantized inputs |
| `quantization_id` | optional ID | Required for quantized input |
| `broadcast_rule` | enum/detail | No implicit undocumented broadcasting |
| `synchronization` | enum | Defines when result is observable |
| `comparison_policy` | comparison fields | Required for every validation fixture |

Public entry points reject zero/overflowing dimensions, wrong byte counts,
unsupported layouts or dtypes, and invalid quantization blocks before
execution.

## ComparisonPolicy and ComparisonResult

| Field | Type | Validation |
| --- | --- | --- |
| `oracle_id` | immutable identity | Scalar implementation, trusted runtime, and version/commit |
| `mode` | enum | `exact`, `abs_rel`, or declared task-specific metric |
| `absolute_tolerance` | nonnegative float | Required for `abs_rel` |
| `relative_tolerance` | nonnegative float | Required for `abs_rel` |
| `non_finite_policy` | enum | Normally reject; otherwise explicit |
| `compared_count` | `u64` | Equals expected output cardinality |
| `max_absolute_error` | optional float | Recorded for numeric comparison |
| `max_relative_error` | optional float | Recorded for numeric comparison |
| `first_mismatch` | optional detail | Index, expected, actual without huge dumps |
| `passed` | boolean | Derived from policy and actual values |

A tolerance is chosen before examining the backend result. Checksums may
identify immutable arrays but do not replace numeric error evidence when
floating-point tolerance is allowed.

## QuantizationCompatibilityRecord

| Field | Type | Validation |
| --- | --- | --- |
| `quantization_id` | enum | Exact GGUF tensor type, initially Q8_0 candidate |
| `tensor_roles` | set | Explicit supported roles; no global inference |
| `block_elements` | positive integer | Exact format rule |
| `block_bytes` | positive integer | Exact encoded representation |
| `row_divisibility` | rule | Exact multiple or documented tail rule |
| `scale_dtype` | enum | Exact on-disk interpretation |
| `decode_output_dtype` | enum | Explicit |
| `matvec_accumulation_dtype` | enum | Explicit |
| `malformed_input_cases` | validation case IDs | Required before support status |
| `scalar_parity_cases` | validation case IDs | Required before MLX status |
| `mlx_parity_cases` | validation case IDs | Required before real-model use |
| `status` | enum | `planned`, `scalar_verified`, `mlx_verified`, `unsupported`, `blocked` |

Status can advance only when every case required for the next state passes.
Support for one tensor role does not imply support for all roles.

## ShardLayout

Defines an immutable logical byte space over already-opened files.

| Field | Type | Validation |
| --- | --- | --- |
| `shards` | nonempty ordered list | Each path opened once and length snapshotted |
| `base` | `u64` per shard | Strictly ascending |
| `length` | positive `u64` per shard | Taken from opened handle |
| `end` | checked `base + length` | No overflow |
| `virtual_start` | `u64` | First base; GGUF construction requires zero |
| `virtual_end` | `u64` | End of last shard |

Adjacent shards must be contiguous: `previous.end == next.base`. Duplicate,
descending, gapped, overlapping, zero-length, and overflowing layouts fail at
construction.

## ExpertReadRequest and OwnedPayload

| Field | Type | Validation |
| --- | --- | --- |
| `request_id` | stable caller ID | Unique within a batch |
| `offset` | `u64` | Absolute logical byte offset |
| `length` | positive `u64` | Checked conversion to allocation size |
| `expert_key` | optional semantic key | Model/shard space, layer, role, expert |
| `payload` | owned bytes | Exactly `length`, never partially complete |
| `source_shard` | index/identity | Exactly one validated shard |

The half-open request `[offset, offset + length)` must fall inside one shard.
Ending exactly at a shard end is valid; beginning at the next shard base is
valid; crossing by one byte is an error. Batch output preserves request order
and is all-or-error. An owned payload remains valid after the source is dropped
and is intentionally non-cloneable by default.

## RoutedMoeCase

| Field | Type | Validation |
| --- | --- | --- |
| `fixture_id` | immutable fixture identity | Small, generated, reviewable input |
| `token_count` | positive integer | Bounded |
| `expert_count` | positive integer | Matches fixture |
| `top_k` | positive integer | `top_k <= expert_count` |
| `router_scores` | tensor reference | Shape `[tokens, experts]`; finite values |
| `tie_rule` | enum | Score descending, then expert ID ascending |
| `selected_experts` | expected IDs | Exact comparison |
| `normalized_weights` | expected floats | Declared tolerance |
| `expert_ranges` | ordered requests | Deduplicated fetch plan is traceable |
| `expected_output` | tensor reference | Independent scalar oracle |

Non-finite router scores and invalid `top_k` are rejected. Repeated experts
across tokens are valid and must not change deterministic result ordering.

## ModelCompatibilityRecord

| Field | Type | Validation |
| --- | --- | --- |
| `model_id` | upstream repository ID | Exact namespace/name |
| `revision` | immutable commit hash | Branch names alone are insufficient |
| `filename` | string | Exact artifact |
| `sha256` | 64 lowercase hex | Computed after external download |
| `size_bytes` | `u64` | Actual local artifact size |
| `license` | SPDX/name plus source | Must permit intended access/use |
| `architecture` | exact metadata | Must match supported loader path |
| `tensor_inventory` | role/type/count map | Complete for attempted slice |
| `quantization_inventory` | type/count map | Each attempted role links to compatibility |
| `disk_budget` | bytes/headroom | Must fit before download |
| `memory_budget` | separate gauges | Must preserve mandatory headroom |
| `execution_depth` | enum/detail | Metadata, routed layer, named intermediate, logits, token, generation |
| `status` | enum | `candidate`, `compatible`, `verified`, `unsupported`, `blocked` |
| `evidence` | validation IDs | Required for `verified` |

The planned Qwen3-30B-A3B Q8_0 artifact remains `candidate` until its immutable
identity, local checksum, inventory, budget, and parity are actually recorded.

## ValidationCase

| Field | Type | Validation |
| --- | --- | --- |
| `case_id` | stable ID | Unique and referenced from requirements/tasks |
| `claim_scope` | string/enum | Exact capability under test |
| `commit` | full Git commit | Must contain the tested code/docs |
| `environment` | sanitized record | No private machine IDs or credentials |
| `input_identity` | fixture/model identity | Immutable and reproducible |
| `command` | exact argv/shell command | Copyable; secrets excluded |
| `oracle` | identity and policy | Required for correctness cases |
| `started_at` | timestamp | Timezone recorded |
| `actual_result` | pass/fail/blocked plus details | Expected is never substituted |
| `warnings` | list | Actual warnings retained |
| `exclusions` | list | What the case does not establish |
| `artifacts` | committed relative paths | No local-only path presented as shared evidence |

## EvidenceStatus

```text
planned -> executed_passed -> verified
   |              |
   |              +-> superseded (newer evidence, old record retained)
   +-> blocked
   +-> executed_failed
```

Only `verified` evidence may back a working capability claim. `blocked` and
`executed_failed` remain durable results, not deleted attempts.

## BenchmarkRecord

Benchmark evidence is valid only when linked correctness cases are verified.

Required fields: commit and dirty state, host/OS/architecture, runtime and
dependency versions, backend/device, immutable input identity, command and
configuration, warm-up method, sample count, statistic definition, raw or
losslessly summarized samples, timing boundaries, memory gauges, I/O/cache
state, power/thermal notes when observable, correctness prerequisite IDs,
actual result, and exclusions.

There is no pass/fail throughput target in initial bring-up. The first record
establishes a baseline; later optimization records a before/after comparison
under equivalent conditions.
