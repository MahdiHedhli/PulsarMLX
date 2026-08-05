# Contract: Validation, Compatibility, and Benchmark Evidence

**Status**: Implemented and validated at the bounded v1 evidence scope

## Claim rule

A capability is “verified” only when a committed validation record contains an
actual executed result for the same immutable code and input identity. Planned,
unsupported, blocked, failed, and platform-unexercised states are not synonyms
for verified. Expected results never populate actual-result fields.

## Validation record

Each record must contain:

```text
schema_version
case_id
claim_scope
commit
git_dirty_state
started_at_and_timezone
host_architecture
os_version
tool_and_dependency_versions
backend_and_selected_device
input_identity
exact_command
oracle_identity
comparison_policy
actual_status
actual_values_or_bounded_summary
warnings
failures
exclusions
artifact_paths
```

`actual_status` is one of `passed`, `failed`, `blocked`, or `not_run`. A
`not_run` case must explain why it exists and cannot back a claim.

Environment records omit credentials, environment-variable values, private
machine identifiers, serial numbers, UUIDs, full usernames in paths, and other
nonessential sensitive data. Public GitHub attribution and public model
identity are not secret.

## Correctness comparison

Before execution, define:

- the independent oracle and exact version/revision;
- identical weight, token, position, dtype, shape, and deterministic settings;
- names of compared tensors or outputs;
- exact, absolute/relative, or task-specific comparison rule;
- tolerances and non-finite policy; and
- bounded mismatch output.

After execution, record cardinality, maximum errors where applicable, first
mismatch details, and pass/fail. Never select a tolerance after viewing the
backend discrepancy.

## Compatibility matrix

Every model architecture and quantization entry records evidence separately at
these levels:

- deterministic scalar fixture;
- evaluated MLX tensor fixture;
- synthetic routed-MoE fixture;
- bounded small real-model/checkpoint slice;
- giant-model execution; and
- production serving.

Each cell is one of `planned`, `verified`, `unsupported`, or `blocked`, with a
validation record or explanation. Verification at one level does not imply the
next.

## External model identity

Before a model case runs, record the upstream repository, immutable revision,
exact filename, license source, expected and actual size, SHA-256 after local
download, architecture metadata, tensor and quantization inventory, local disk
budget, memory budgets/headroom, and intended execution depth. The model file
and access credentials remain outside Git.

If provenance, access terms, checksum, layout, supported operations, or memory
fit is uncertain, the case is `blocked` and execution stops.

## Benchmark record

A benchmark additionally records:

- prerequisite correctness validation IDs, all passed;
- exact build profile and relevant feature flags;
- warm-up method and count;
- sample count and raw or losslessly summarized samples;
- timing boundary and synchronization point;
- statistic definitions;
- input and output sizes;
- file/cache state and storage method;
- MLX active/cache/peak gauges when available;
- process footprint and system pressure when available;
- thermal and power context when observable; and
- exact exclusions and sources of uncertainty.

The initial benchmark has no required speedup threshold. It establishes a
reproducible baseline. A before/after claim uses equivalent conditions and
keeps the correct reference path available.

## Required repository updates per completed slice

The same bounded change updates:

- feature spec/plan/tasks status where applicable;
- the quickstart or validation command;
- session log with actual result;
- compatibility matrix/evidence record;
- known limitations and unsupported scope; and
- README only when the verified capability boundary changed.

Failed and blocked results are retained. Model files, raw secrets, large local
logs, and private machine details are never committed as evidence.
