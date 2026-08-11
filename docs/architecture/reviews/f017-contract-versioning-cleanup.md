# PulsarMLX F017 Contract Versioning Cleanup Report

## Executive result

The accepted R7/R8 numerical basis is unchanged. R9 and R10 now preserve
their original v1 contracts byte-for-byte and bind current evidence to v2
contracts that explicitly harden internal-selection divergence to a numerical
failure. This is semantic tightening, not vocabulary-only normalization.

No threshold, metric, oracle value, fixture value, candidate output, timing,
dispatch count, fallback count, or lifecycle counter changed. No numerical
experiment was rerun, and no checkpoint was accessed.

## Audit source

- starting remediation head: `dda37f97e571c32ea469fba1e4e869e9dba8d415`
- immutable numerical baseline: `a572a2d560f5bc33f823e74c3bbc95ff2b164314`
- deterministic generator:
  `scripts/research/reconcile_f017_contract_versions.py`
- machine-readable reconciliation:
  `docs/architecture/reviews/evidence/f017-contract-version-reconciliation-v2.json`

All paths in this report are repository-relative. Machine-local worktree and
home-directory paths are intentionally excluded.

## R7 amendment

R7 remains `f017-production-expert-tier-b-v1`; it did not receive a
disproportionate version bump. The explicit amendment record is:

`specs/017-rust-native-inference-runtime/contracts/production-expert-tier-b-v1-amendment-001.json`

It records the reviewer-requested vocabulary normalization:

- `scope.greedy_applicability`: `not_applicable_at_r7` -> `not_applicable`
- addition of `numerically_qualified_greedy_not_applicable` to the declared
  vocabulary

The original contract hash is
`3245631ffdd5c9807281f12ae0be33bfa070f1962a71e4b98a3b384364a7cba2`;
the amended contract hash is
`1953adbf822a21f7fa4f8d569432e747c8c43c9fd273589bec8849b57475cee2`.
The amendment declares both `thresholds_unchanged` and
`numerical_payload_unchanged`.

## R8 audit

R8 did not publish an independent numerical contract with an immutable
retuning policy. It inherits `f017-production-expert-tier-b-v1`; the prior R8
change affected result classification metadata, not a separately versioned
contract. Therefore no R8 contract version or second amendment is required.
Exact routed IDs `[7, 6, 5, 4, 3, 2, 1, 0]` remain separate architecture
evidence and are not model-token greedy identity.

## R9 v1 and v2

The original-to-mutated-v1 semantic diff contained four changes: pass
classification and applicability were vocabulary normalization;
`selection_divergence` was semantic tightening; `selection_evidence` was
metadata/provenance. There were no formatting-only changes.

Original v1 is restored byte-for-byte at:

`specs/017-rust-native-inference-runtime/contracts/production-r9-tier-b-v1.json`

Its SHA-256 is
`fe6e95d2ea2eb31184cb5617ec27727262ac132812add75933e22a376acf80a8`.
The previously mutated-in-place v1 hash at `dda37f9` was
`4ce9aa87571f8c3d8efc7451eba37003c1e1a99f20935a972d58bf300862e3ba`.

Current evidence binds to `f017-production-r9-tier-b-v2` at:

`specs/017-rust-native-inference-runtime/contracts/production-r9-tier-b-v2.json`

V2 SHA-256 is
`56dd1e9a51752045d2f01e7c964b2d13ffbee0303bd459e734d2f7d7ae7797a1`.
It changes pass/applicability vocabulary and tightens
`selection_divergence` from
`numerically_qualified_greedy_divergent` to `numerically_failed`. All numeric
thresholds and exact requirements are unchanged. The observed result
satisfies both v1 and v2, so no rerun is required.

## R10 v1 and v2

The original-to-mutated-v1 semantic diff likewise contained pass and
applicability vocabulary normalization, semantic tightening of
`routing_divergence`, and an added metadata/provenance selection-scope field.
There were no formatting-only changes.

Original v1 is restored byte-for-byte at:

`specs/017-rust-native-inference-runtime/contracts/production-r10-tier-b-v1.json`

Its SHA-256 is
`dc11769af639a207c1528ae6756a315f585a04438d5e5f5115883e0323ebd81f`.
The previously mutated-in-place v1 hash at `dda37f9` was
`736b3fe0a56bf3076da4ad4521312d9a6291380d6bd5a9bfb0b87ca618e2efb3`.

Current evidence binds to `f017-production-r10-tier-b-v2` and inherits R9 v2:

`specs/017-rust-native-inference-runtime/contracts/production-r10-tier-b-v2.json`

V2 SHA-256 is
`07f6c8556373e7eec5bf326c9aa613680567cbef1d8f3956da7955e7fef3ce75`.
It changes pass/applicability vocabulary and tightens `routing_divergence`
from `numerically_qualified_greedy_divergent` to `numerically_failed`. Numeric
thresholds, exact requirements, and the candidate output are unchanged. The
banked R10 result satisfies both versions.

## Evidence rebindings

| Boundary | Old evidence SHA-256 | New evidence SHA-256 | Binding change |
|---|---|---|---|
| R9 | `2a0fb632db94ee4d77b6d7c62472855ce3a27aa19d9a81a2bf5e5814602ead1b` | `e65e95cc626aff0a6a7cd1471acf498399567eca6e66a2abaf72bd674c658645` | R9 v1 -> R9 v2 |
| R10 | `332b1268ddc0b16b16f3183c983e0f9901f40d2bdf6cd5c7277d050e8d6e01b6` | `268b0f685a664866b73fe9195c7111734eb97d6280d31727ab76a9c69dbc8708` | R9/R10 v1 -> R9/R10 v2 |

The changed hashes are caused by contract-binding metadata only. A normalized
semantic diff excludes contract binding, classification, and greedy
applicability and proves all numerical metrics and candidate outputs are
unchanged.

## Review disposition

- R7/R8 numerical blocker: **closed**
- R9/R10 contract-version cleanup: **closed after validation and final-head CI**
- R11/R12 checkpoint-free gate: **eligible after validation and final-head CI**
- real checkpoint: **blocked**
- P1: **blocked**

The next permitted implementation work is the already prepared checkpoint-free
R11 final-output and R12 tiny end-to-end runner sprint.
