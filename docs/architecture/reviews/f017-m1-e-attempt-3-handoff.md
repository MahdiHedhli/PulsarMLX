# F017 M1-E Attempt 3 Handoff

**Status: PREPARED FOR CHECKPOINT-FREE VALIDATION / NOT AUTHORIZED / NOT EXECUTED**

This handoff exists so the attempt-3 immutable-config path can be exercised
before authorization. The final authorization commit must replace this
checkpoint-free status with the exact published runtime, tooling,
authorization-head, executable, preparer, preparer-input-contract, and
execution-config identities.

## Immutable scope

- attempt: `3`
- execution-config schema: `3.0.0`
- preparer input contract: `f017-m1e-real-reference-preparer-input-v3`
- expert: `blk.3.expert.15`
- conceptual expert count: `1`
- tensor payload count: `3` (`gate`, `up`, `down` only)
- complete production repeats: `10`
- expected native matvec dispatches: `30`
- automatic retry: `false`
- mandatory stop: before M1-F

Attempts 1 and 2 remain consumed and rejected under evidence SHA-256
`346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119`
and `8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00`.

## Numerical continuity

- decoder contract v2:
  `9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84`
- activation payload:
  `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- exact scaffold:
  `52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38`
- expert Tier-B:
  `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2`
- corrected final oracle:
  `ae1fa8e468418c8f0103a772ba4cf1380ed587435ace37d527642f8f0cda5213`
- corrected final bound vector:
  `05273dc57a7c8822f0cbf988d465debf1f4010004cd10299ff6e607f9ac6a3d4`

No threshold, decoder, expert, activation, scaffold, or Tier-B semantic may
change as part of the schema-v3 preparer remediation.
