# GLM-5.2 Results

**Status**: partial — real-weight C01–C08 recorded; C09 ladder in progress
**Protocol**: `EXPERIMENT_PROTOCOL.md` (frozen)

## Checkpoint

| Field | Value |
| --- | --- |
| Identity file | `docs/validation/glm52-checkpoint.json` |
| Total bytes | 238458632928 |
| Tensor count | 1809 |
| Architecture | glm-dsa |

## C01 Catalog

| Metric | Value |
| --- | --- |
| Tensor count | 1809 |
| Type histogram | `{"F32": 709, "IQ2_S": 2, "IQ2_XXS": 148, "IQ3_XXS": 71, "IQ4_XS": 4, "Q2_K": 2, "Q3_K": 1, "Q4_K": 2, "Q5_K": 312, "Q6_K": 82, "Q8_0": 476}` |
| Bad offsets | 0 |
| Status | **passed** |

## C02–C08 Boundary table

| Boundary | status | max_abs (repeat) | rmse |
| --- | --- | ---: | ---: |
| C02 dense | **passed** | n/a | n/a |
| C03 router | **passed** | n/a | n/a |
| C04 expert | **passed** | 0.0 | 0.0 |
| C05 MoE | **passed** | 0.0 | 0.0 |
| C06 MLA | **passed** | 0.0 | 0.0 |
| C07 DSA | **passed** | n/a | n/a |
| C08 layer0 | **passed** | 0.0 | 0.0 |

## C09 Depth ladder

| Depth | status |
| ---: | --- |
| 1–79 | **in progress** (background single-token ladder) |

## C10 Logits

| Metric | Value |
| --- | --- |
| status | pending (after C09) |

## C11 Generation

| Prompt ID | status |
| --- | --- |
| P-MIN | pending (after C10) |

## Performance (MLX-only)

| Metric | status |
| --- | --- |
| TTFT / tok/s | pending (after C11) |

Figures and tables must be generated from `raw/` — never hand-hardcoded.
