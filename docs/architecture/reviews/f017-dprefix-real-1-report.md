# PulsarMLX F017 DPREFIX-REAL-1 Report

- Verdict: `DENSE-PREFIX M1-F(-1) NOT EXECUTED`
- Release and execution head: `39b6a3edd3306c46f7601c7d9cc371db11511e61`
- Attempt: `DPREFIX-REAL-1`
- Terminal class: `HOST_ADMISSION`
- Reason: `REVIEWED_CHECKPOINT_MOUNT_ABSENT`
- Orchestrator package: `4b69d8fcca3edf6edbe78e75d62d5b9558d58ac90f7d70fbae79484e017f18df`
- Config v5: `27774a11d933750cb9703a9889b5f83b88711ee27827c9d34eb585649545aadd`
- Authorization v4: `fc286651d4fa11ff43e0db926a801d24e30152509465d2d7f0510d79599e1e47`
- Candidate binary: `1a73dd4026592e21df05a82df806e52ebcb8dd0248aaffc0d8fd91c6f9e1387a`
- Oracle package: `9b00ed225acc9b299c5bd789f1b082f6a2fd90b7893913bc9f353f99ee83c89b`
- Metric engine: `cd7ca4eee855b60b6695b8ac6671d59eae2f446231f437168df0985f984ad738`
- Inventory: `c9c1540ea1cc9e69344ed9f3dcc4eb8ba1e5c15e3d55c1bccdec00eeb1db36aa`
- Prompt package: `c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff`
- Payloads: `0`; packed bytes: `0`; shard opens: `0`; positional reads: `0`
- Attempt consumed: `false`; executed: `false`; checkpoint accessed: `false`
- Ledger: `59 → 59`
- Q4/Q6 confirmations: not reached; no expected/actual comparison was made
- Oracle/candidate/repeats/Tier-B/dispatch/lifecycle/retention: not reached
- Representative M1-F0: `BLOCKED / NOT AUTHORIZED / NOT EXECUTED`
- Raw evidence: `docs/architecture/reviews/evidence/f017-dense-prefix-real-attempt-1-not-executed-host-admission-v1.json`, SHA-256 `b7abb1999f6e018cf9a41279b161d7ac84a300984f7f8960776bc5f461065c08`
- Attempt ledger successor: `docs/architecture/reviews/evidence/f017-dense-prefix-attempt-ledger-v7.json`
- Real-payload ledger: unchanged, SHA-256 `a0edafdcd0279fb28e08c69a86a9c95ddd19e013b73a1e92f7620734456a9339`
- Evidence commit and final CI: pending append-only closeout

Exact next action: independently review the committed non-execution evidence,
restore the exact reviewed checkpoint object at the bound private mount, and
issue a fresh explicit execution instruction. No retry is authorized by this
report.
