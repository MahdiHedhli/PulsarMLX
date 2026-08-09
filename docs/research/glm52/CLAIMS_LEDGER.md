# GLM-5.2 Claims Ledger

| ID | Status | Claim | Source | Evidence | Reproduction | Scope and caveat |
| --- | --- | --- | --- | --- | --- | --- |
| F016-IQ2-001 | verified | NumPy IQ2_XXS decoding matched the scalar oracle at exact f32 bits for four complete real expert matrices, with a 28.15× median decode-only speedup on the recorded M1 Ultra run. | `968cfac` | `docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json` | `uv run --frozen python scripts/research/qualify_iq2_xxs_numpy.py --output docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json` | Decode boundary only; not routed-expert, MoE, layer, P1/P2, or token speedup. |
| F016-MATRIX-001 | verified | The vector mode used one complete read and produced exact deterministic MLX matvec output for one real IQ2_XXS expert matrix, with a 15.39× median total-before-cleanup improvement over the scalar-reference mode. | `d8af70b` | `docs/research/glm52/raw/f016-matrix-boundary-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_matrix_boundary.py --output docs/research/glm52/raw/f016-matrix-boundary-0001.json` | One gate matrix only; not a routed expert, MoE, layer, stack, or token result. OS page cache was uncontrolled. |
| F016-EXPERT-001 | verified | A complete real routed expert passed the independent CPU oracle and deterministic MLX cross-mode gates; vector median total was 1.706290 s versus 4.365715 s scalar reference (2.56×). | `bbbbaae` | `docs/research/glm52/raw/f016-routed-expert-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_routed_expert.py --output docs/research/glm52/raw/f016-routed-expert-0001.json` | One selected expert only; not top-8/shared MoE, layer, stack, or token speed. OS page cache was uncontrolled. |
| F016-MOE-001 | verified | Complete real layer-3 top-8 plus shared MoE passed the independent CPU oracle, exact routes, shared-cache, and deterministic MLX gates; warm vector median was 14.062472 s versus 36.309373 s scalar reference (2.58×). | `c2337db` | `docs/research/glm52/raw/f016-moe-layer3-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_moe.py --output docs/research/glm52/raw/f016-moe-layer3-0001.json` | Layer-3 MoE only; excludes attention, full layer, stack, and token performance. OS page cache was uncontrolled. |
| F016-LAYER-001 | verified | Complete real layer 3 retained the frozen attention midpoint and post-attention route, passed the architecture-reference gate, and produced exact deterministic decoder-mode output; warm vector median was 31.687686 s versus 53.230274 s scalar reference (1.68×). | `a78bc46` | `docs/research/glm52/raw/f016-layer3-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_layer.py --output docs/research/glm52/raw/f016-layer3-0001.json` | One position-0 layer only; not a stack or token result. The complete attention reference is not independent of the shared MLX dense helper. OS page cache was uncontrolled. |

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
