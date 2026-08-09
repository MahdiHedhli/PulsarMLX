# GLM-5.2 Claims Ledger

| ID | Status | Claim | Source | Evidence | Reproduction | Scope and caveat |
| --- | --- | --- | --- | --- | --- | --- |
| F016-IQ2-001 | verified | NumPy IQ2_XXS decoding matched the scalar oracle at exact f32 bits for four complete real expert matrices, with a 28.15× median decode-only speedup on the recorded M1 Ultra run. | `968cfac` | `docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json` | `uv run --frozen python scripts/research/qualify_iq2_xxs_numpy.py --output docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json` | Decode boundary only; not routed-expert, MoE, layer, P1/P2, or token speedup. |

## Prior boundary summary

**Status**: C01–C11 research baseline complete; optimization ladder active
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

| Depth | status | notes |
| ---: | --- | --- |
| 1–79 | **passed** | single-token; ~5511s; final hidden L2 ~231 |

## C10 Logits

| Metric | Value |
| --- | --- |
| status | **passed** |
| argmax | 4766 |
| top-8 | [4766, 1729, 2730, 35383, 906, 387, 505, 6073] |
| note | architecture path; residual scale large |

## C11 Generation

| Prompt ID | status | sequence | seconds |
| --- | --- | --- | ---: |
| P-MIN | **passed** | `[9703, 21615, 220, 16, 13, 16, 16, 15, 15]` | ~48731 |

## Performance (MLX-only)

| Metric | status |
| --- | --- |
| TTFT / tok/s | pending (after C11) |

Figures and tables must be generated from `raw/` — never hand-hardcoded.
