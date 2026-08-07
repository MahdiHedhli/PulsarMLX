# Claims ledger — Feature 016 GLM-5.2

| Claim ID | Claim | Evidence | source_commit | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| F016-C00 | Qwen e2e research baseline frozen | tag `v0.2.0-qwen30b-e2e-research` | 493234a | verified | Full Qwen stack; no tok/s claim |
| F016-C01a | Disk admission passed after space clearance | `docs/validation/glm52-disk-admission.json` | 1919ffe | verified | ≥500 GiB free; projected ≥250 after |
| F016-C01b | Experiment protocol + tolerances frozen before real-weight parity | `docs/research/glm52/EXPERIMENT_PROTOCOL.md` | (this series) | verified | Methodology only |
| F016-C01c | glm-dsa KV dims frozen from shard 00001 | `docs/architecture/GLM52_CONTRACT.md` | 5ad3d10+ | provisional | Full tensor catalog pending all shards |
| F016-C02+ | Real-weight C01–C11, generation, performance | — | — | unsupported | Requires complete checkpoint identity |

## Rejected / blocked (historical)

| Claim | Status | Notes |
| --- | --- | --- |
| Disk admission 2026-08-07 first attempt | rejected | ~346 GiB free; shortfall ~154 GiB |

## Explicit non-claims

- GLM-5.2 full-model support
- Production tokens/sec
- CUDA equivalence
- M2 Max / RAID results
