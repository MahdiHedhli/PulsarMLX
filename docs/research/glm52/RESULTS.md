# GLM-5.2 Results

**Status**: optimization active after completed C01–C11 research baseline
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

| Prompt ID | status | generated sequence |
| --- | --- | --- |
| P-MIN | **passed** | `[21615, 220, 16, 13, 16, 16, 15, 15]` |

## Performance (MLX-only)

| Metric | status |
| --- | --- |
| exact-bit NumPy IQ2_XXS matrix decode | **passed** — 4 complete matrices, 0 f32-bit mismatches |
| matrix decode median | 0.050588 s vector vs 1.424142 s scalar; 28.15× at this boundary |
| exact-bit NumPy IQ3_XXS matrix decode | **passed** — 4 complete matrices across 4 shards, 0 f32-bit mismatches |
| IQ3_XXS matrix decode median | 0.075513 s vector vs 1.578598 s scalar; 20.90× at this boundary |
| real IQ3_XXS down-matrix load/build/matvec | **passed** — 1 vector read vs 6144 scalar reads; exact deterministic output; 0.126149 s vs 1.559883 s median total |
| complete routed expert with vector IQ2_XXS + IQ3_XXS | **passed** — independent CPU oracle 0 mismatches; exact deterministic decoder modes; 0.243532 s vs 4.378363 s median total (17.98×) |
| real matrix load/build/matvec | **passed** — 1 vector read vs 2048 scalar reads; exact deterministic output; 0.090525 s vs 1.393479 s median total |
| complete routed expert | **passed** — CPU oracle 0 mismatches; exact deterministic MLX modes; 1.706290 s vs 4.365715 s median total |
| layer-3 top-8 + shared MoE | **passed** — CPU oracle 0 mismatches; exact route/mode bits; 14.062472 s vs 36.309373 s warm median |
| complete layer 3 | **passed** — frozen attention midpoint/routes; exact mode bits; 31.687686 s vs 53.230274 s warm median |
| vectorized P1 full stack | **passed** — golden `[9703,21615]`; 6294.015 s; 228 shared-cache hits; zero fallback |
| P1 mixed-quant ranking | **passed** — 9 formats exercised; IQ3_XXS accounts for 1791.414 s / 61.78% of the quantified component sum |
| P2 / steady-state tok/s | pending; not inferred from one P1 pilot |

The IQ3_XXS decoder qualification is decode-only. The separate real down-matrix
boundary includes load, decode, contiguous-buffer verification, synchronized
MLX matrix build/eval, and matvec, but still does not establish a complete
expert, layer, P1, or P2 speedup. The subsequent complete routed-expert rung
does establish expert-boundary benefit with an independent CPU oracle, but not
top-8 MoE, layer, P1, or P2 performance. The mixed-quant inventory is generated at
[`tables/f016-p1-quant-hotspots.md`](tables/f016-p1-quant-hotspots.md) from the
committed P1 record. Figures and tables must be generated from `raw/` — never
hand-hardcoded.
