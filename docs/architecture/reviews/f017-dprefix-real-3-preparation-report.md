# PulsarMLX F017 DPREFIX-REAL-3 Preparation Report

- Starting SHA: `ea362ced6b39915c4d42bf044f1779f55b60995e`
- Final preparation SHA: `586dd64fc6cd7360614e4f79458752cbd464a488`
- REAL-2 evidence SHA: `a9708c84ebe08e9c3717cd3abbaec37c15fa06cb99d2f97d5a7dc87871e79039`
- Real-payload ledger: `139`
- REAL-2 historical classification: `NUMERICALLY_QUALIFIED / EVENT_REJECTED_FOR_EVIDENCE_COMPLETENESS`
- Host-copy root cause: `native_matvec/DispatchEvidence → RealCandidateEvidence: copy_f32 was counted only as a readback; no host-copy count or byte producer existed in candidate IPC`
- Lifecycle root cause: `native_matvec ownership_snapshot → execute_material_package: reconciliation ran locally per matvec but RealCandidateEvidence omitted the aggregate success-path lifecycle record`
- Rehearsal blind spot: `the prior synthetic route serialized SyntheticEvidence.lifecycle_reconciled=true and never exercised the production RealCandidateEvidence success IPC/banker route`
- Accounting remediation SHA: `53c9f3ff564ecf191509c30f9448c6e73bf47f2753f2f0794dd5c646c272fcda`
- Candidate identity: `5192c51d2f1a133f769937d234c1f56621aa5484385a99708dcdc7bdc784beb8`
- Replay orchestrator SHA: `5c4cbab83e3d95dbc961a4170622a451d248ddbf44e6b1ece23fcfa1535a74ad`
- Packed-package identity: `705066830506dbebab9212948059c71e76b4535eaeb41672c9dbd62f6e9ed156`
- Packed-package integrity: `PACKED PACKAGE READY FOR CHECKPOINT-FREE REPLAY`
- Packed package byte count: `1431263232`
- Decoded identity manifest SHA: `69cce66021b5e28f77d07cc80ec1358aff7df187d00aa5cd9981b08b58372e02`
- Decoded hard-gate count: `40`
- Zero-checkpoint-access contract SHA: `2c057476b4c277a2b885e0620973c4a40f9a5a4fabb9df058b9ee37fe311dcf0`
- Replay event contract SHA: `ceae09cf190d8ef7661990aaecbedbcdf1fe9c539237ddb4240dd4e4da934cbc`
- Success rehearsal: `SUCCESS-PATH TERMINAL EVIDENCE COMPLETE`
- Actual rehearsal host-copy count: `4050` (`10145280` bytes)
- Rehearsal lifecycle: `PASS`
- All-eight Tier-B rehearsal: `REAL-3 CHECKPOINT-FREE NUMERICAL REHEARSAL PASS`
- Failure-path rehearsal: `REAL-3 FAILURE PATH COMPLETE`
- Banker mutation result: `PASS`
- Checkpoint-access attack result: `REAL-3 ZERO-READ GUARANTEE STRUCTURAL`
- Fresh replay attempt ID: `DPREFIX-REAL-3`
- Config SHA: `9746f7f4a8aa86ce0770de438945272eea25843e59cb1c3c0fce6e9447dd013e`
- Authorization SHA: `62a2508489855958ce58dc71a2263b127d9b6fea0015e9349a404e1068f8b837`
- Attempt ledger SHA: `142c56fd764d44bac21759cfc3ce98cefa1913fa955cbf38eb258409e5496827`
- Ledger plan: `139 → 139`
- Checkpoint access: `0`
- Internal verdict: `GO FOR CHECKPOINT-FREE DPREFIX-REAL-3 ADVERSARIAL REVIEW`
- Adversarial packet SHA: `fa238febd8990a489c764c5a935ceae733f318559327d858bfc2aa0fbc4f6a3e`
- Final CI run/head: `31992366576 → 586dd64fc6cd7360614e4f79458752cbd464a488` (`success`; Apple jobs `95278061563`, `95278061626`)

## Exact next action

Independent adversarial review. Only `GO FOR ONE CHECKPOINT-FREE DPREFIX-REAL-3 REPLAY` may release the replay. No checkpoint read under any circumstance.
