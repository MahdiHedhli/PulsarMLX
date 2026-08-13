# PulsarMLX F017 M1-E Config-v3 Preparer Remediation Report

## Outcome

`READY FOR FRESH M1-E ATTEMPT 3 AUTHORIZATION`

Starting head: `10328e307d1905966f32ff1b1efdc7a0ca7fed67`.
Compiled runtime/tooling: `71476f0d469214c96d803ce4917c43c4562a7183`.
Authorization execution head: `32377ed50d25ba09b7147d1789b8f926ecebfe39`.

Attempts 1 and 2 remain rejected and immutable under evidence SHA-256
`346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119`
and `8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00`.

## Exact mismatch and semantic diff

The attempt-2 config declared schema `3.0.0`; the bound preparer accepted only
`2.0.0` and rejected it at its identity branch after `EXECUTION_STARTED`, but
before repository-root resolution, checkpoint open, payload read, decode,
oracle creation, or MLX context/dispatch.

| Field class | Config v2 | Config v3 | Oracle relevant | Identity only | Semantic change |
|---|---|---|---|---|---|
| Runtime | `runtime_sha` | `compiled_runtime_sha` | No | Yes | Split identity |
| Tooling | implicit/combined | `tooling_sha` | No | Yes | Explicit identity |
| Authorization | absent | `authorization_head_sha` | No | Yes | Exact later head |
| Executable | absent | `executable_identity` | No | Yes | Binary attestation |
| Repository trust | single-head assumption | `trusted_repository_identity` | No | Yes | ancestry/drift binding |
| Prior evidence | A/B/C/D + attempt 1 | adds attempt 2 | No | Yes | lineage only |
| Expert/tensors | bound | bound | Yes | No | Unchanged |
| Activation/decoder/scaffold/Tier-B | bound | bound | Yes | No | Unchanged |
| Execution counts | bound | bound | Yes | No | attempt becomes 3 |

The old preparer SHA-256 was
`841279fe5a1467f6e8deaaa0e22c59c1c2828bb67f16d5f48ad42dd198f6e224`;
the v3 preparer SHA-256 is
`f8e6f20d364d0c569875f841ec6edfc1e8e9f9997baa416b7eb8f1e409fe34e7`.
Its input contract is `f017-m1e-real-reference-preparer-input-v3`, SHA-256
`ad5768d026e5f6377e8243f4d01b50b416e50307d3bd1efd38ab437ba86709a5`.

## Independence and numerical continuity

The preparer remains Python/NumPy-only. It has no Rust FFI, MLX, candidate
subprocess, candidate decoded matrix, candidate output, or candidate metric
dependency. Identity metadata is validated but excluded from the numerical
semantic projection.

Decoder v2 (`9a92bac...`), corrected IQ3 Python/Rust/spec identities, decoded
down identity (`f919871...`), activation (`732ed2...`), final oracle
(`ae1fa8...`), final bound vector (`05273d...`), scaffold (`524724...`), and
Tier-B (`44168e...`) are unchanged. No threshold was retuned.

## Validation and authorization

- immutable attempt-3 execution config SHA-256:
  `ce451e77215b3d3f99e69e96e50af1a2f0d9b3d9b7bbe3435fcd64cbec53d9d5`
- preflight: exactly `READY_TO_EXECUTE_M1_E`; zero access/compute/consumption
- schema attacks: valid v3 accepted; downgrade/future/missing/malformed/
  duplicate/mixed/stale/substituted inputs rejected before payload open
- native synthetic M1-E: one expert, 10 deterministic repeats, 30 native
  matvec dispatches, Tier-B PASS, oracle-before-candidate PASS, lifecycle PASS,
  zero production scaffold/reference/fallback/errors
- internal review: `GO FOR M1-E ATTEMPT 3`
- adversarial review: `GO FOR M1-E ATTEMPT 3`
- authorization: `docs/architecture/reviews/f017-m1-e-attempt-3-authorization.md`
  with status `AUTHORIZED FOR EXACTLY ONE M1-E ATTEMPT 3 / NOT EXECUTED`

Real checkpoint access during remediation: `false`. Attempt 3 consumed:
`false`. M1-F remains blocked.

