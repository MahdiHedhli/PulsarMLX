# Claims ledger — Feature 016 GLM-5.2

| Claim ID | Claim | Evidence | source_commit | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| F016-C00 | Qwen e2e research baseline frozen under annotated tag | tag `v0.2.0-qwen30b-e2e-research` @ `493234a` | 493234a | verified | Full 48-layer stack, logits, greedy, short gen; no tok/s claim |
| F016-C01 | Internal SSD disk admission for GLM-5.2-UD-IQ2_XXS | [admission](../../validation/glm52-disk-admission.json) | (this commit) | **rejected / blocked** | Free ~346 GiB after safe cleanup; need 500 GiB; shortfall ~154 GiB |
| F016-C02+ | Checkpoint identity, correctness ladder, generation, performance | — | — | unsupported | Not started until C01 disk pass |

## Unsupported

- GLM-5.2 full-model support
- GLM generation
- GLM tokens/sec
- External-drive or RAID-based GLM residency for this sprint
