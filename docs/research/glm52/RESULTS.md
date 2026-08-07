# GLM-5.2 Results (structured shell)

**Status**: empty shell — **no measured results** until real checkpoint runs
**Protocol**: `EXPERIMENT_PROTOCOL.md` (frozen)

## Checkpoint

| Field | Value |
| --- | --- |
| Identity file | `docs/validation/glm52-checkpoint.json` |
| Total bytes | _pending_ |
| Set SHA / per-file SHA | _pending_ |

## C01 Catalog

| Metric | Value |
| --- | --- |
| Tensor count | _pending_ |
| Type histogram | _pending_ |
| Bad offsets | _pending_ |

## C02–C08 Boundary table

| Boundary | max_abs | rmse | cosine | status |
| --- | --- | --- | --- | --- |
| C02 dense | | | | pending |
| C03 router | | | | pending |
| C04 expert | | | | pending |
| C05 MoE | | | | pending |
| C06 MLA | | | | pending |
| C07 DSA | | | | pending |
| C08 layer0 | | | | pending |

## C09 Depth ladder

| Depth | max_abs | status |
| ---: | --- | --- |
| 1 | | pending |
| 2 | | pending |
| 4 | | pending |
| 8 | | pending |
| 16 | | pending |
| 32 | | pending |
| 64 | | pending |
| 79 | | pending |

## C10 Logits

| Metric | Value |
| --- | --- |
| max_abs | pending |
| top-1 | pending |
| greedy token | pending |

## C11 Generation

| Prompt ID | Generated token IDs | Decoded (short) | status |
| --- | --- | --- | --- |
| P-MIN | | | pending |

## Performance (MLX-only)

| Metric | n | median | mean | notes |
| --- | ---: | --- | --- | --- |
| TTFT warm (s) | | | | pending |
| Decode tok/s | | | | pending |
| Prefill tok/s | | | | pending |

Figures and tables must be generated from `raw/` — never hand-hardcoded.
