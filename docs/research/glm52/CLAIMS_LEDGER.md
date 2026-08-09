# GLM-5.2 Claims Ledger

| ID | Status | Claim | Source | Evidence | Reproduction | Scope and caveat |
| --- | --- | --- | --- | --- | --- | --- |
| F016-IQ2-001 | verified | NumPy IQ2_XXS decoding matched the scalar oracle at exact f32 bits for four complete real expert matrices, with a 28.15× median decode-only speedup on the recorded M1 Ultra run. | `968cfac` | `docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json` | `uv run --frozen python scripts/research/qualify_iq2_xxs_numpy.py --output docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json` | Decode boundary only; not routed-expert, MoE, layer, P1/P2, or token speedup. |
| F016-MATRIX-001 | verified | The vector mode used one complete read and produced exact deterministic MLX matvec output for one real IQ2_XXS expert matrix, with a 15.39× median total-before-cleanup improvement over the scalar-reference mode. | `d8af70b` | `docs/research/glm52/raw/f016-matrix-boundary-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_matrix_boundary.py --output docs/research/glm52/raw/f016-matrix-boundary-0001.json` | One gate matrix only; not a routed expert, MoE, layer, stack, or token result. OS page cache was uncontrolled. |
| F016-EXPERT-001 | verified | A complete real routed expert passed the independent CPU oracle and deterministic MLX cross-mode gates; vector median total was 1.706290 s versus 4.365715 s scalar reference (2.56×). | `bbbbaae` | `docs/research/glm52/raw/f016-routed-expert-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_routed_expert.py --output docs/research/glm52/raw/f016-routed-expert-0001.json` | One selected expert only; not top-8/shared MoE, layer, stack, or token speed. OS page cache was uncontrolled. |
| F016-MOE-001 | verified | Complete real layer-3 top-8 plus shared MoE passed the independent CPU oracle, exact routes, shared-cache, and deterministic MLX gates; warm vector median was 14.062472 s versus 36.309373 s scalar reference (2.58×). | `c2337db` | `docs/research/glm52/raw/f016-moe-layer3-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_moe.py --output docs/research/glm52/raw/f016-moe-layer3-0001.json` | Layer-3 MoE only; excludes attention, full layer, stack, and token performance. OS page cache was uncontrolled. |
| F016-LAYER-001 | verified | Complete real layer 3 retained the frozen attention midpoint and post-attention route, passed the architecture-reference gate, and produced exact deterministic decoder-mode output; warm vector median was 31.687686 s versus 53.230274 s scalar reference (1.68×). | `a78bc46` | `docs/research/glm52/raw/f016-layer3-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_layer.py --output docs/research/glm52/raw/f016-layer3-0001.json` | One position-0 layer only; not a stack or token result. The complete attention reference is not independent of the shared MLX dense helper. OS page cache was uncontrolled. |
| F016-P1-002 | verified | The vectorized MLX inference path produced the exact P1 golden prefix `[9703,21615]` in 6294.015 s, with 228 decoded shared-cache hits, zero evictions, and zero CPU fallbacks. | `2de160f` | `docs/research/glm52/raw/f016-inference-p1-vectorized-0001.json` | `uv run --frozen python scripts/research/glm52_inference.py --mode inference --n-new 1 --cache-gib 16 --cache-policy decoded_shared_only --decoder-mode numpy_vectorized --out docs/research/glm52/raw/f016-inference-p1-vectorized-0001.json` | One clean-process P1 pilot on one M1 Ultra. Cross-commit comparison with legacy P1 is not a controlled benchmark population. Does not establish P2, full golden-8, or steady-state token speed. |
| F016-HOTSPOT-001 | verified | The committed vectorized P1 trace exercised nine expert quantization formats. IQ3_XXS ranked first by summed recorded component time at 1791.414 s (61.78% of the quantified total), ahead of Q6_K and Q5_K. | `2de160f` (P1 source) | `docs/research/glm52/raw/f016-p1-quant-hotspot-ranking-0001.json` | `uv run --frozen python scripts/research/rank_glm52_quant_hotspots.py --check` | Derived from one clean-process P1 trace. Component sums are hotspot attribution, not an independently timed wall total or a speedup claim. Later qualification is recorded separately as F016-IQ3-001. |
| F016-IQ3-001 | verified | NumPy IQ3_XXS decoding matched the scalar oracle at exact f32 bits for four complete real down matrices across four shards, with a 20.90× median decode-only speedup on the recorded M1 Ultra run. | `be47a95` | `docs/research/glm52/raw/f016-iq3-xxs-numpy-qualification-0001.json` | `uv run --frozen python scripts/research/qualify_iq3_xxs_numpy.py --output docs/research/glm52/raw/f016-iq3-xxs-numpy-qualification-0001.json` | Decode boundary only; not routed-expert, MoE, layer, P1/P2, or token speedup. |
| F016-IQ3-MATRIX-001 | verified | One complete real IQ3_XXS down matrix used one bounded vector read, contiguous exact-bit decode, synchronized MLX GPU matrix build/eval, and matvec; vector and scalar modes produced exact deterministic output, with 0.126149 s versus 1.559883 s median total. | `15a8aa2` | `docs/research/glm52/raw/f016-iq3-matrix-boundary-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_matrix_boundary.py --projection down --output docs/research/glm52/raw/f016-iq3-matrix-boundary-0001.json` | One layer-3 expert-15 down projection with a scalar-derived SwiGLU activation; not a complete expert, MoE, layer, P1/P2, or token speedup. OS page cache was uncontrolled. |
| F016-IQ3-EXPERT-001 | verified | A complete real layer-3 routed expert used one-read IQ2_XXS gate/up and IQ3_XXS down matrices, passed the independent scalar CPU oracle with zero tolerance mismatches, and produced exact deterministic decoder-mode output; vector median was 0.243532 s versus 4.378363 s scalar (17.98×). | `a8a3d71` | `docs/research/glm52/raw/f016-routed-expert-iq3-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_routed_expert.py --output docs/research/glm52/raw/f016-routed-expert-iq3-0001.json` | One routed expert only; not top-8/shared MoE, layer, P1/P2, or token speedup. OS page cache was uncontrolled. |
| F016-IQ3-MOE-001 | verified | Complete real layer-3 top-8 plus shared MoE passed the independent CPU oracle, exact routes, shared-cache, and deterministic MLX gates after IQ3_XXS vectorization; warm vector median was 1.698580 s versus 34.964010 s scalar (20.58×). | `b675365` | `docs/research/glm52/raw/f016-moe-layer3-iq3-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_moe.py --output docs/research/glm52/raw/f016-moe-layer3-iq3-0001.json` | Layer-3 MoE only; excludes attention, full layer, P1/P2, and token performance. Warm measured samples reused three decoded shared matrices. OS page cache was uncontrolled. |
| F016-IQ3-LAYER-001 | verified | Complete real layer 3 retained the frozen attention midpoint and post-attention route after IQ3_XXS vectorization, passed the architecture-reference gate, and produced exact deterministic decoder-mode output; warm vector median was 19.391364 s versus 52.924374 s scalar (2.73×). | `a589dcf` | `docs/research/glm52/raw/f016-layer3-iq3-0001.json` | `uv run --frozen python scripts/research/benchmark_glm52_layer.py --output docs/research/glm52/raw/f016-layer3-iq3-0001.json` | One position-0 layer only; not P1/P2 or token performance. The complete attention reference is not independent of the shared MLX dense helper. OS page cache was uncontrolled. |
| F016-IQ3-P1-001 | verified | The MLX inference path with vector IQ2_XXS and IQ3_XXS produced the exact P1 golden prefix `[9703,21615]` in 4582.511 s, with 228 decoded shared-cache hits and zero CPU fallbacks. | `99751b9` | `docs/research/glm52/raw/f016-inference-p1-iq3-0001.json` | `uv run --frozen python scripts/research/glm52_inference.py --mode inference --n-new 1 --cache-gib 16 --cache-policy decoded_shared_only --decoder-mode numpy_vectorized --out docs/research/glm52/raw/f016-inference-p1-iq3-0001.json` | One clean-process P1 on one M1 Ultra. The 27.19% reduction from the prior single P1 is a cross-commit observation, not a controlled population. Does not establish P2, golden-8, or steady-state throughput. |
| F016-HOTSPOT-002 | verified | The revised P1 trace ranked Q6_K first at 468.856 s (39.55%) after IQ3_XXS fell to fourth at 101.107 s; the warm stack reused all 228 protected shared matrices and avoided 2.106 GB compressed / 11.476 GB decoded work. | `99751b9` (P1 source) | `docs/research/glm52/raw/f016-p1-iq3-quant-hotspot-ranking-0001.json` | `uv run --frozen python scripts/research/rank_glm52_quant_hotspots.py --source docs/research/glm52/raw/f016-inference-p1-iq3-0001.json --json-out docs/research/glm52/raw/f016-p1-iq3-quant-hotspot-ranking-0001.json --table-out docs/research/glm52/tables/f016-p1-iq3-quant-hotspots.md --check` | One P1 trace; component attribution is not wall time. Q6_K is the next decoder candidate, but its protected shared matrices are already resident in the warm stack. |

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
