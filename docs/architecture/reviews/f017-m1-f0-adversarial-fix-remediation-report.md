# PulsarMLX F017 M1-F0 Adversarial-Fix Remediation Report

## Outcome

The two required adversarial fixes are closed. M1-F0 remains unexecuted,
unconsumed, and unauthorized. M1-F remains unauthorized. The package is ready
for a separate adversarial delta review.

- starting SHA: `1c80f6419112f3410cdb26e3294a8610c31a9c22`
- final SHA: the documentation-only banking commit containing this report;
  resolve it directly from Git after banking
- runtime semantic boundary: `7e4c3f37049444443164964aea2fc630752d17ce`
- old recorded tooling head: `3192b31e4fe3008f0182548a45f7117948d83afd`
- exact new tooling/config content identity:
  `7d7b972ce541ca1f62fad5269283249510ff67e8`
- old config SHA-256:
  `b1adab3dc981b3baca82279d96deb9cc8dbf79176d3ee248ee354d6e9ab4366d`
- new config SHA-256:
  `444ab5d0c0c763ee6af52d8b3a8859e1edcfa17dd8609e03551a554f6cfd8a3f`

## Provenance correction

Git history proves that neither the `3192b31` nor `1c80f64` config revision
matched the tooling commit it declared. The repaired freeze pattern separates
the accepted runtime semantic boundary, exact tooling/config content commit,
future authorization head, and final documentation/evidence head. Validation
now compares every execution-controlling artifact against its bytes in the
declared tooling commit and rejects stale, parent, descendant, or unrelated
identities.

A real pinned regeneration used CPython 3.13.13, NumPy 2.4.5, PCG64, and seed
17017006. The regenerated fixture and package were byte-identical:

- fixture: `33be5f7ed93a29621b39034246a8bf088111fa4138b0966179aad94a138e63c4`
- package: `eb5693c99f73c2a95d71aec947b8a18a6c07c71dbbb460490af82b617dba9283`
- hidden: `decc4ef42e1cf5d6cbee2fe6d46f3cd29b6dd39b9bb997d1083e7a7228ed86cf`
- position: `af5570f5a1810b7af78caf4bc70a660f0df51e42baf91d4de5b2328de0e83dfc`
- MLA cache: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- DSA: `2bb5d053425b308fbef711827f82a50aa05a6cc2ae11952f3f90447ff0d27764`
- mask: `4bf5122f344554c53bde2ebb8cd2b7e3d1600ad631c385a5d7cce23c7785459a`

## Q5_K exactness

The selected qualification tensor was `blk.3.attn_output.weight`, the largest
Q5_K matrix in the M1-F0 boundary. Exactly one payload was read with packed
SHA-256 `30d37ee75f7877defe1720f6bf14f4d9b9c4151b3d164f0618e5c2bff454b084`.

The scalar oracle decoder (`ec9a679b...`) and independent pinned-upstream
vector decoder (`57d5de26...`) produced exact decoded SHA-256
`2cd327fb89256c1d4a920fff53a47994f294a67eb17e640785b616d7c9c8e5e8`
for all 100,663,296 f32 values. The implementations share no decoder calls,
MLX, Rust FFI, or candidate output. Exact equality—not tolerance—is required.

The qualification contract `m1f0-q5-k-exact-v1` has SHA-256
`06e9acf6838fbfe8bb11a653b631d126dadab37590f50cba4db9bdaf16656510`.
Its source reference, canonical serialization, real packed/decoded identities,
independence statement, and block regressions are hash-bound.

## Downstream hardening

- first-real-quantization policy SHA-256:
  `fcec2aef9d17efe4973f5561b7fc9eb2cee8428c04889c4582b133f53bc66370`
- strengthened route-schema SHA-256:
  `ad423bec7dc2513521a36e9d98758bb5718d520350bf384282e72971ba8a7add`

Any quantization family first appearing at a real F017 gate now requires
independent exact real-byte cross-qualification. Q4_K, Q6_K, and other
unqualified families remain fail-closed.

The future route artifact now binds the exact attention residual and all
preceding routing state. M1-F must carry those residual bytes/hash and, if it
recomputes attention, qualify the recomputed residual without changing the
frozen route IDs.

## Qualification

- non-consuming preflight: `READY_TO_EXECUTE_M1_F0`
- checkpoint reads during preflight: 0
- synthetic M1-F0: PASS, 10/10 deterministic, exact top-8/routing bytes
- stress suite: PASS, six families
- historical-route and expert-access rejection: PASS
- Python research tests: 463 PASS
- Rust workspace check/tests: PASS
- M1-E/M1-D and identity/loader regressions: PASS
- duplicate-key/privacy/generated-artifact gates: PASS
- Spec Kit prerequisites/checklist: PASS
- `git diff --check`: PASS
- final-head Apple-native CI: required on the banking head before handoff

Internal review verdict:

`GO FOR M1-F0 ADVERSARIAL DELTA REVIEW`

Narrow packet:

`docs/architecture/reviews/f017-m1-f0-adversarial-delta-review-packet.md`

SHA-256:

`7aead5c742095742c6a3816463c14999dfd58a0e51f6d8e03d974b2e446d1a13`

Real checkpoint payloads accessed during remediation: **1**. This was the
bounded Q5_K decoder qualification only.

- M1-F0 route discovery performed: false
- M1-F0 attempt consumed: false
- M1-F0 authorization issued: false
- M1-F authorization issued: false

Exact next action: perform the separate independent adversarial delta review.
