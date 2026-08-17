# PulsarMLX F017 DPREFIX-REAL-2 Report

- Verdict: `DENSE-PREFIX M1-F(-1) REAL-2 CAPTURE REJECTED`
- Terminal class: `EVIDENCE_VALIDATION`
- Reason: `SUCCESS_PATH_RUNTIME_ACCOUNTING_MISSING`
- Release and execution head: `acab5d4347c6af25ac3acb7bfa6e7b5dbe1257e7`
- Attempt: `DPREFIX-REAL-2`; authorized, consumed, executed, checkpoint accessed, terminal, no retry
- Ledger: `99 -> 139`
- Access: one shard open, 40 positional reads, 40 payloads, `1,431,263,232` packed bytes
- All-40 packed identity gate: PASS
- Q4_K decoded identity: PASS, `e2cff562131674156704ca21b2b6e850337c2e5d8948b4dcc9f14676ecf8f2c1`
- Q6_K decoded identity: PASS, `ff26151a7997379c1713b90852fdbfd8301b36d5d89a1c3bb623b9b8f273483a`
- Packed package: 40 immutable read-only objects, `1,431,263,232` bytes; private manifest/package identity `705066830506dbebab9212948059c71e76b4535eaeb41672c9dbd62f6e9ed156`
- Candidate: `2f6a8885a17c10c7776a0d27ed6eb8e85024b03bc499885eddb905050cad17b1`; root-cause regression PASS; all 27 native shape checks completed
- Oracle: finalized and persisted before candidate; post-candidate rehash PASS
- Oracle layer-2 and layer-3 content: `541d8dbcf459b49e9b5c69ae44f919a64c2eaaefa4f6daeb7e0d13443b521aff`; private manifest `553e2d61bb6de3bf14b79b1ffb6140f4e03db75d4479debed2346e34e2ed021b`
- Oracle layer-3 state: `[6144]`, f32, 6,144 elements, canonical LE-f32
- Candidate launch: complete; repeats: 10; deterministic: true
- Numerical result: all eight real Tier-B surfaces qualified
- Runtime: 4,050 native matvecs, 4,050 synchronizations, 4,050 readbacks, 120 CPU RMSNorm operations, 30 CPU attention operations, 30 CPU activation operations, fallback 0, backend errors 0
- Actual host-copy count: `NOT_RECORDED_BY_BOUND_SUCCESS_PATH`
- Complete success-path lifecycle reconciliation: `NOT_RECORDED_BY_BOUND_SUCCESS_PATH`
- Downstream oracle-state policy: `ANALYTICAL_ROUTE_PLANNING_ONLY`
- Representative M1-F0: `NOT_AUTHORIZED_NOT_EXECUTED`

## Tier-B surfaces

| Surface | Max abs | RMSE | Cosine | Candidate non-finite | Oracle non-finite | Signed-zero mismatch | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| `embedding` | 0 | 0 | 1 | 0 | 0 | 0 | PASS |
| `layer_0_attention` | 1.862645149230957e-8 | 9.54864222243263e-10 | 0.9999999999999838 | 0 | 0 | 0 | PASS |
| `layer_0_output` | 1.043081283569336e-7 | 9.667241942750458e-9 | 0.9999999999995661 | 0 | 0 | 0 | PASS |
| `layer_1_attention` | 8.149072527885437e-9 | 1.1205402278509975e-9 | 0.9999999999993459 | 0 | 0 | 0 | PASS |
| `layer_1_output` | 7.82310962677002e-8 | 1.184088457503118e-8 | 0.9999999999992526 | 0 | 0 | 0 | PASS |
| `layer_2_attention` | 9.313225746154785e-9 | 1.1703606767833709e-9 | 0.9999999999995185 | 0 | 0 | 0 | PASS |
| `layer_2_output` | 7.450580596923828e-8 | 1.084308585452015e-8 | 0.9999999999994857 | 0 | 0 | 0 | PASS |
| `layer_3_entry` | 7.450580596923828e-8 | 1.084308585452015e-8 | 0.9999999999994857 | 0 | 0 | 0 | PASS |

## Committed evidence

- Raw evidence: `docs/architecture/reviews/evidence/f017-dense-prefix-real-attempt-2-rejected-evidence-validation-v1.json`, SHA-256 `a9708c84ebe08e9c3717cd3abbaec37c15fa06cb99d2f97d5a7dc87871e79039`
- Packed descriptor: `docs/architecture/reviews/evidence/f017-dprefix-real2-packed-package-descriptor-v1.json`, SHA-256 `ab0f1b3e4cdfe6664d6f30190a4d21dc2be30d12b2808f23b83c759ceb2b3ea8`
- Oracle descriptor: `docs/architecture/reviews/evidence/f017-dprefix-real2-oracle-retention-descriptor-v1.json`, SHA-256 `95df0d8bce380cf25ac8144f6a825015d0002dff525b35b2ab458093b8ebe336`
- Candidate descriptor: `docs/architecture/reviews/evidence/f017-dprefix-real2-candidate-retention-descriptor-v1.json`, SHA-256 `ae0c59253bd5cdac6ac4427799e2649880c124b781d65095738fcea084750cb5`
- Attempt ledger v10: `docs/architecture/reviews/evidence/f017-dense-prefix-attempt-ledger-v10.json`, SHA-256 `c24f80c316a6a45d4e91d6a9dbec288c94c5ab3e987f02d8f19ff73bee27fe98`
- Real-payload ledger: `docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json`, SHA-256 `fc32161d30373840126835e8f925179e606c792368131b06647f7cb6f50666b2`
- Real-evidence commit: `1c072ee99388e49a60392f3cc44c732a2e2a21d6`
- Evidence review: `docs/architecture/reviews/f017-dprefix-real-2-evidence-validation-rejection-review.md`, SHA-256 `d306487eb072f6df4f6276f110266b36457159ab76ca2ace2c9432e5c890693b`
- CI binding ledger SHA-256: `5a1a8b158dbdea81f3e4d79caf0d8ad79cbd99c79515525ef399528f10f345bf`
- Initial evidence-head CI: run `31979940586` -> `1c072ee99388e49a60392f3cc44c732a2e2a21d6`; workspace passed, fixture failed on stale predecessor-ledger assertions
- Final Apple-native CI: run `31980507219` -> `ac16f280856b32933c90737e5f4e1b7f19427f5e`; both required jobs passed

Exact next action: independent adversarial review of the failure evidence. Do
not reread the checkpoint. Retained packed payloads and retained oracle state
may be used only under the frozen policy and later authorization.
