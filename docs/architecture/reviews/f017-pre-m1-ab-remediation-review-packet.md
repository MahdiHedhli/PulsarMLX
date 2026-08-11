# F017 Unified Pre-M1-A/B Remediation Review Packet

> **Final isolation appendix:** the independent adversarial review returned GO,
> while the internal review identified two final checkpoint-free blockers.
> Their remediation and re-review anchors are recorded in
> [`f017-final-environment-isolation-remediation.md`](f017-final-environment-isolation-remediation.md).
> T017-161 is closed; T017-160 remains open pending the final internal GO.

## Requested disposition

Review the checkpoint-free remediation and return one of:

- `GO FOR M1-A/B STAGED INTEGRATION`
- `GO WITH REQUIRED FIXES BEFORE M1-A/B`
- `NO-GO`

A GO authorizes only a separately prompted M1-A adapter preflight. M1-B still
requires review of M1-A evidence and a separate prompt. This packet does not
authorize checkpoint access, tensor execution, M1-C, or P1.

## Reviewed boundary

- Starting source: `74cd1f3af3538dfdff0fa1343542a9ec7656c0ef`
- Branch: `feat/017-real-checkpoint-runner`
- Checkpoint accessed: false
- R7/R8 numerical basis: accepted
- R9/R10 active contracts: v2
- Feature 018 kernels: absent
- P1 command: unpublished

## Finding map

| Finding | Remediation | Implementation and test anchors |
| --- | --- | --- |
| Adversarial 1: placeholder admission | Production collection now measures memory, compression, swap, pressure, disk, load, competing processes/port 1234, and thermal/performance state. Hard gates reject unavailable or unsafe state. | `HostAdmission::collect`, `HostAdmission::validate`, `production_admission_fails_closed`, `identity_mode_requires_checkpoint_volume_telemetry` |
| Adversarial 2: check-then-open output | The final evidence target is acquired with exclusive create before updates. Atomic replacements operate only on that acquired target. | `AtomicEvidenceWriter::create`, `exclusive_create_has_one_winner_under_race`, symlink/parent/interrupted-update tests |
| Adversarial 3: PASS before teardown | Execution synchronizes and explicitly tears down; lifecycle/dispatch reconciliation runs before PASS is assigned or persisted. Teardown imbalance is `FAIL_LIFECYCLE_OWNERSHIP`. | `execute`, `Evidence::validate_success_ready`, negative PASS tests |
| Internal 1: weak environment proof | A versioned schema validates exact MLX versions/source pins, arm64, platform/toolchain metadata, installed header/library hashes, and isolated linkage. Dyld enumeration proves the two actually loaded Mach-O images and hashes them. | `ValidatedEnvironment::load`, `verify_loaded_libraries`, environment schema and match/mismatch tests |
| Internal 2: identity omitted production map | Production identity invokes `Glm52TensorMap::from_gguf`, requires 79 layers/1,809 contracts, and records map version/hash. | `verify_checkpoint_mode`, `Glm52TensorMap::contract_sha256`, map/isolation tests |
| Internal 3: ambiguous lifecycle zero | Registration, pending destruction, in-flight work, owner tokens, and generations use explicit `measured_zero`, `measured_nonzero`, `not_applicable`, or `unavailable` states. Tensor-map status separately uses `validated`. | `ObservedCounter`, `TensorMapStatus`, status validator and negative tests |
| Internal 4: hidden R12 scaffold | Production R12 no longer invokes the exact scaffold. It compares against frozen independent fixture outputs and records zero scaffold/reference dispatch. | `run_tiny_model`, R12 actual-binary test, v2 production evidence |
| Internal 5: incomplete R12 binding | R12 evidence binds exact hashes for expert v1, R9 v2, R10 v2, and R11 v1; validation rejects missing, stale, or mismatched bindings. | `r12_contract_bindings`, evidence validation tests |
| Internal 6: overstated runtime reuse | Public wording now states the literal boundary: same binary/store/adapter/semantic components, with fixture-specific `TinyRuntime` and `Glm52FixtureTensorMap`; no shared production runtime abstraction is claimed. | R11/R12 report and adversarial packet |

## Admission and environment contract

Production M1-A/B reject synthetic telemetry, a nonpositive memory floor,
available memory below the floor, urgent/critical/unavailable pressure, swap
above the reviewed negligible bound, competing inference, port 1234,
insufficient evidence disk, missing M1-B checkpoint-volume telemetry, or a hard
thermal/performance warning. M1-A has no checkpoint argument. M1-B admits only
identity/hash/header/catalog/map/tokenizer work and no tensor decode or compute.

The environment schema is
[`production-environment-v1.schema.json`](../../../specs/017-rust-native-inference-runtime/contracts/production-environment-v1.schema.json).
The canonical evidence schema is
[`canonical-runner-evidence-v1.schema.json`](../../../specs/017-rust-native-inference-runtime/contracts/canonical-runner-evidence-v1.schema.json),
currently at evidence schema version 1.3.0.

## R12 semantic diff

Historical v1 artifacts remain immutable. New v2 records were generated from
the fixed runner. Numerical metrics, token 10, routing IDs, candidate outputs,
fallback/error counts, and ownership/stream counts are unchanged. Expected
changes are schema 1.3.0, explicit lifecycle applicability, full contract
bindings, source identity, fresh timing samples, and removal of the hidden
production scaffold execution.

| Artifact | Historical SHA-256 | Remediated SHA-256 |
| --- | --- | --- |
| R12 exact | `b280ebfaacf776201d08b104efb1db6954a71a7eb7d9d74c86c2f4ae299aeb17` | `b2dc94fe3d9467b2a38fd071d4ffa0b78ba5c400ab17d78f4c069b9eb81e9cac` |
| R12 production | `87ba02df98ccba3572a8687d2e73961496449ce9a6e81ec6a62e5cedb0d6ed0f` | `182340d0054fd556bd6abaf500e93b4b396ca8e0c4b8a8f9d282eb550fae2c7f` |

The machine-readable reconciliation manifest is
[`f017-pre-m1-remediation-manifest-v1.json`](evidence/f017-pre-m1-remediation-manifest-v1.json).

## Mode isolation

M1-A (`--adapter-preflight-only`) rejects checkpoint arguments at CLI
validation, validates measured admission and the environment, verifies the
loaded libraries, runs the production adapter lifecycle, and persists PASS
only after teardown. The actual-binary test proves that a mixed checkpoint
argument is rejected before an evidence target is created.

M1-B (`--checkpoint-identity-only`) hashes/parses the declared shards and
catalog, validates architecture/tokenizer/tensor count and the complete
production map, and records zero execution/dispatch/residency state. It does
not create `MlxContext`, decode a tensor, create layer state, or execute a
projection.

## Historical and final CI

Historical run
[`31540615532`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31540615532)
passed at `74cd1f3af3538dfdff0fa1343542a9ec7656c0ef`. Both the Apple Silicon
workspace baseline and Apple MLX small-fixture validation jobs passed; the
native adapter and R7-R12 gates executed rather than satisfying the workflow
through a skip.

Remediation implementation/evidence run
[`31545411413`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31545411413)
passed at `2af41b8999cacdc4b622f1d9a5fd2512073db8bf`. The Apple Silicon workspace
baseline passed in 2m18s. The Apple MLX small-fixture validation passed in
7m28s; its pinned native adapter, canonical projection, and complete R7-R12
numerical ladder steps all executed and passed. The containing documentation
commit must also receive green final-head CI before the packet is handed to
the reviewers.

## Open tasks and admission state

- T017-140 remains open and blocks M1-C.
- T017-141 remains open and blocks the canonical P1 command.
- T017-160 remains open until the internal review reruns and returns GO.
- T017-161 is closed by the independent adversarial GO.
- M1-A/B are not executed by this remediation.
- Real checkpoint access, M1-C, and P1 remain blocked.

## Review question

Do the admission, environment/library identity, evidence, teardown, map,
mode-isolation, and R12-accounting fixes close all checkpoint-free blockers so
that a separately authorized M1-A may begin?
