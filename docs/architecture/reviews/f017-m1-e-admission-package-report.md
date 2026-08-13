# PulsarMLX F017 M1-E Admission Package Report

## Outcome

`READY FOR FRESH M1-E AUTHORIZATION`

Starting head was `d70090d0cacdf9c103e8ffb08e319a16026596ba`.
The runtime boundary is `466770362e3066fa5fd9827ec1f454e03afe3006`,
tooling/test boundary is `3387bb6d4508eb04e672dc6194da2855ba72f072`,
and reviewed package head is
`f3a7ba8f3a7eb52dbf48c6929e23835e5c18eeea`.

M1-D remains immutably accepted at evidence SHA-256
`dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c`.
No unexplained runtime drift follows the new runtime boundary.

## Expert boundary and payload budget

Layer 3/expert 15 (`blk.3.expert.15`) was selected before M1-E payload or
candidate observation. Gate/up are IQ2_XXS logical 2048 x 6144 matrices;
down is an IQ3_XXS logical 6144 x 2048 matrix. Their exact names, shapes,
shard-2 offsets, lengths, row packing, and catalog identities are frozen in
the handoff. The maximum budget is three payloads, one shard open, three
positional reads, and 11,304,960 compressed bytes.

## Input, oracle, scaffold, and numerics

The independent input contains 6,144 canonical little-endian f32 elements,
PCG64 seed 17017005. Its artifact/payload hashes are
`a5946ba6f07d4be7c13da28549a0585b90a4ca8fa3824f52d2afd0f0b582f5c8`
and `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`.
The generator and independent real-reference preparer hashes are
`c797e5200bd126a42b1303c2c06d7ef5bbad11738241cbd9f54e014a49a0a77e`
and `1276a2818b9dceaa9e2029461df82d81776d6d8f76f3b3c6033cd903e7b318b6`.

The exact scaffold and composed expert Tier-B hashes are
`52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38`
and `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2`.
The contract composes gate/up matvec, frozen SiLU/product, and down-matvec
error without candidate fitting. The explicit cancellation, dynamic-range,
near-zero, signed-zero/subnormal, SiLU-edge, near-overflow, and simultaneous
upstream-error stress suite passed without retuning.

## Execution and evidence controls

The immutable execution config SHA-256 is
`7f69550bfd7ccd5e820f23d2bcce7f0e287d2c2bfc5f1ae2adb59ec5467b0a1b`.
Its config-only preflight returned `READY_TO_EXECUTE_M1_E`, was repeatable,
created no attempt/evidence/oracle/payload artifact, and did not consume the
attempt. Consumption begins only after preflight, production admission,
config revalidation, and the `EXECUTION_STARTED` transition.

One conceptual expert requires gate/up/down per repeat: 10 repeats and 30
native matvec dispatches. All four per-repeat stage hashes must be identical.
Production scaffold/reference/fallback/backend errors must be zero. Lifecycle
and ownership must fully reconcile before PASS.

The canonical checkpoint-free native integration passed from a relocated
private package and unrelated cwd through the same config-only path. Failure
injection covered wrong expert/tensor/name/shape/quantization, all three
truncations, second expert/router access, wrong input, stale/order-invalid
oracle, intermediate divergence with matching final output, dispatch/fallback,
lifecycle, consumed attempt, and post-preflight config mutation. M1-D
fixture, native integration, repeat, oracle, path, and immutable-config
regressions remain green.

## Reviews, CI, and authorization

- internal implementation: `GO FOR ONE M1-E REAL EXPERT`
- independent adversarial: `GO FOR ONE M1-E REAL EXPERT`
- package-head CI `31656082515`: workspace baseline and pinned Apple-native
  qualification green, including 6 Python, 5 contract/isolation, 3 numerical,
  and 4 native M1-E tests with zero ignored
- handoff SHA-256:
  `2325f9b2964b5c1120864fbaa4d3fda875f8d263154d783bf02b6ad47e78e531`
- fresh authorization:
  `docs/architecture/reviews/f017-m1-e-fresh-authorization.md`

M1-E was not executed and no real gate/up/down payload was accessed during
this sprint. M1-F, T017-141, P1/P2/golden-eight, and Feature 018 remain
blocked. The exact next action is one explicit M1-E execution from the bound
immutable config, followed by a mandatory stop and evidence review.
