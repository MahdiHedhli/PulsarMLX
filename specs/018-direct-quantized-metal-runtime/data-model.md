# Data Model: Direct-Quantized Metal Runtime

## QualificationContract

- `schema_version`: immutable contract version
- `matrix_absolute_tolerance`: `0.0005`
- `matrix_relative_tolerance`: `0.0005`
- `matrix_cosine_minimum`: `0.999999`
- `matrix_norm_ratio_minimum`: `0.9995`
- `matrix_norm_ratio_maximum`: `1.0005`
- `composed_absolute_tolerance`: `0.005`
- `composed_relative_tolerance`: `0.005`
- `composed_cosine_minimum`: `0.999`
- `composed_norm_ratio_minimum`: `0.995`
- `composed_norm_ratio_maximum`: `1.005`
- `repeat_count`: deterministic validation count
- `teacher_forced_positions`: complete committed position set
- `classification`: one of the four frozen states

## PackedMatrixBinding

- `source_commit`, `source_dirty`
- `checkpoint_set_sha256`, `immutable_revision`
- `tensor_name`, `shard_role`, `tensor_offset`, `tensor_length`
- `layer`, `expert_id`, `projection_role`
- `quantization`, `rows`, `columns`, `block_weights`, `block_bytes`
- `activation_sha256`, `scalar_output_sha256`, `numpy_output_sha256`

Validation requires a clean source, exact checkpoint identity, IQ2_XXS, positive
dimensions, columns divisible by 256, and exact packed length:
`rows * (columns / 256) * 66`.

## StableSlabLease

- `slot_id`, `generation`
- `address`, `alignment`, `capacity`, `logical_length`
- `owner_state`: allocated, registered, in-flight, completed, released
- `registration_id`, `command_id`
- `teardown_status`

The owner cannot enter `released` while a registration or command lease exists.
Generation changes on slot reuse so stale handles fail.

## DirectGemvRequest

- packed matrix lease and offset
- activation f32 vector and element count
- rows, columns, row stride
- lookup-table identity
- deterministic-validation flag

## DirectGemvResult

- f32 output and hash
- device identity and pipeline identity
- zero-fallback assertion
- complete-f32-weight-materialized bytes, required to be zero
- timing buckets: read, registration, compilation, dispatch, execution,
  synchronization, total
- memory and resource observations
- command completion/error state

## KernelAttempt

- `attempt_id`, `rung`, `status`
- `source`, `matrix_binding`, `contract_version`
- reference and candidate results
- numerical metrics and classification
- raw warmup and measured samples
- setup and steady-state summaries
- failures and unsupported interpretations
- next eligible gate

## State Transitions

```text
planned -> identity_admitted -> reference_frozen -> dispatched
dispatched -> completed -> classified -> committed
dispatched -> failed
classified -> rejected
classified -> admitted_next_rung
```

Only `golden_identical` and `numerically_qualified_greedy_identical` may admit
performance advancement. `numerically_qualified_greedy_divergent` preserves
teacher-forced research evidence but cannot admit a greedy execution claim.

## Iq3DownQualification

- `contract_version`: `f018-iq3-down-v1`
- `quantization`: `IQ3_XXS`; `projection_role`: `down`
- `rows`: 6144; `columns`: 2048
- `block_weights`: 256; `block_bytes`: 98
- `packed_row_bytes`: 784; `packed_matrix_bytes`: 4,816,896
- `matrix_absolute_tolerance`: 0.00025
- `matrix_relative_tolerance`: 0.00025
- `matrix_cosine_minimum`: 0.9999995
- `matrix_norm_ratio`: `[0.99975, 1.00025]`
- exact source/checkpoint/tensor/range/packed/activation/reference identities
- strict compiler settings and distinct IQ3 pipeline identity
- direct IQ2/IQ3, explicit-reference, direct-error, fallback, and complete-f32
  materialization counts at composed boundaries
