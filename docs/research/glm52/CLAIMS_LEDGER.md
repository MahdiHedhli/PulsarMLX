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
| F016-IQ3-P2-001 | verified | The vector IQ2_XXS/IQ3_XXS MLX path produced exact P2 `[9703,21615,220]` across three complete 79-layer stacks, with 228 decoded shared-cache hits in each warm stack, 456 total hits, and zero CPU fallbacks. | `d5e1cf3` | `docs/research/glm52/raw/f016-inference-p2-iq3-0001.json` | `uv run --frozen python scripts/research/glm52_inference.py --mode inference --n-new 2 --cache-gib 16 --cache-policy decoded_shared_only --decoder-mode numpy_vectorized --out docs/research/glm52/raw/f016-inference-p2-iq3-0001.json` | One clean-process P2 on one M1 Ultra. Two warm stack times do not establish steady-state throughput, long-context behavior, or the full golden-eight sequence. |
| F016-IQ3-GOLDEN8-001 | verified | The vector IQ2_XXS/IQ3_XXS MLX path produced the exact frozen full sequence `[9703,21615,220,16,13,16,16,15,15]` across nine complete 79-layer stacks, with 228 decoded shared-cache hits in every warm stack, 1824 total hits, and zero CPU fallbacks. | `1a2ca76` | `docs/research/glm52/raw/f016-inference-golden8-iq3-0001.json` | `uv run --frozen python scripts/research/glm52_inference.py --mode inference --n-new 8 --cache-gib 16 --cache-policy decoded_shared_only --decoder-mode numpy_vectorized --out docs/research/glm52/raw/f016-inference-golden8-iq3-0001.json` | One clean-process golden-eight correctness run on one M1 Ultra. The final stack advances terminal model state after token eight is selected. This does not establish steady-state throughput, long-context behavior, or production readiness. |
| F016-GOLDEN8-PROFILE-001 | verified | Eight distinct passive snapshots yielded seven monotonic one-stack warm intervals with no counter reset. Warm stacks had a 1921.882 s median; the uninstrumented residual had a 1675.492 s median and 87.18% median fraction, while expert-cache storage averaged 3.872 s or 0.20% of mean stack wall. | `1a2ca76` (execution source) | `docs/research/glm52/raw/f016-golden8-derived-profile-0001.json` | `python3 scripts/research/analyze_glm52_golden8.py --check` | One M1 Ultra golden-eight run. Per-quant deltas cover only the expert-cache path and tokens 2–8. The watcher began after cold and first warm, so cold per-quant attribution is unavailable. The material uninstrumented residual prevents selecting a first Metal kernel from this table alone. |
| F016-POSTRUN-001 | verified | Deterministic post-run calculation places token-eight selection at 16593.771926 s of recorded components (16594.122951 s wall-minus-terminal upper bound), classifies 1,353 non-expert trunk tensors, and computes 6,136,906 current read operations versus 954 logical bulk-path reads per normal short-context token plus next-token selection. | `1a2ca76` (execution) + `5e5c06d` (catalog) | `docs/research/glm52/raw/f016-golden8-post-run-calculations-0001.json`; `docs/research/glm52/raw/f016-gguf-trunk-inventory-0001.json` | `python3 scripts/research/analyze_glm52_post_run.py --check` | Calculation only: no new inference or measured speedup. The 0.351025 s runner remainder prevents treating the subtractive boundary as an exact wall timestamp. Request counts and residency budgets are logical arithmetic; cleanup cost is not isolated, allocator overhead is not modeled, and no Feature 018 kernel is selected. |
| POST-F016-TRUNK-READ-001 | verified | One bounded read per complete real trunk matrix preserved exact f32 output bits while reducing positional-read requests by 6,144x–16,384x per matrix and 6,288x across the four instrumented 2-D layer-8 MLA projections. Median boundary totals changed by only -0.445% to +0.608% for the matrices and -0.387% for MLA, so bulk reads alone did not materially improve this warm scalar-decode path. | `bf69703` | `docs/research/glm52/raw/post-f016-trunk-bulk-read-0001.json` | `PULSARMLX_GLM_GGUF=<checkpoint-root> uv run --frozen python scripts/research/benchmark_glm52_trunk_bulk.py --output docs/research/glm52/raw/post-f016-trunk-bulk-read-0001.json` | Three real matrices and one single-position MLA boundary on one M1 Ultra; OS page cache uncontrolled. Scalar decoder arithmetic and row order were unchanged. This is not a complete transformer layer, stack, token, vector-decoder, Rust, or Metal speedup. |
| POST-F016-Q5-001 | verified | Whole-matrix NumPy Q5_K decoding matched the scalar oracle at exact f32 bits for four complete real attention-output matrices across layers 3, 20, 40, and 60, with deterministic repeats and identical signed-zero counts. The recorded M1 Ultra decode-only benchmark had a 12.232673 s scalar median and 0.391463 s vector median (31.25x). | `b5ad0059` | `docs/research/glm52/raw/post-f016-q5-k-numpy-qualification-0001.json` | `PULSARMLX_GLM_GGUF=<checkpoint-root> uv run --frozen python scripts/research/qualify_q5_k_numpy.py --output docs/research/glm52/raw/post-f016-q5-k-numpy-qualification-0001.json` | Decode boundary only, four 100,663,296-weight Q5_K matrices on one M1 Ultra; OS page cache uncontrolled. Does not establish complete MLA/layer, token, Rust, or Metal speedup. |
| POST-F016-Q5-INTEGRATION-001 | verified | Exact-bit NumPy Q5_K integration reduced one complete real matrix median from 11.080288 s to 0.547885 s (20.22x) and complete layer-3 MLA median from 17.983298 s to 5.317590 s (3.38x). The MLA candidate vectorized two Q5_K projections while retaining two captured non-Q5 projections on the scalar decoder. | `f6446a07` | `docs/research/glm52/raw/post-f016-trunk-q5-integration-0001.json` | `PULSARMLX_GLM_GGUF=<checkpoint-root> uv run --frozen python scripts/research/benchmark_glm52_trunk_q5.py --output docs/research/glm52/raw/post-f016-trunk-q5-integration-0001.json` | One matrix and one single-position MLA boundary on one M1 Ultra; OS page cache uncontrolled. Per-head 3-D Q8_0 remains outside captured 2-D metrics. Not a complete layer, stack, token, Rust, or Metal speedup. |
| POST-F016-Q8-001 | verified | Whole-matrix NumPy Q8_0 decoding matched scalar-oracle f32 bits for four complete real 2-D matrices across layers 3, 20, 40, and 60, including deterministic repeats and signed-zero counts. The M1 Ultra decode-only benchmark measured 3.056227 s scalar median and 0.040342 s vector median (75.76x). | `d2454919` | `docs/research/glm52/raw/post-f016-q8-0-numpy-qualification-0001.json` | `PULSARMLX_GLM_GGUF=<checkpoint-root> uv run --frozen python scripts/research/qualify_q8_0_numpy.py --output docs/research/glm52/raw/post-f016-q8-0-numpy-qualification-0001.json` | Four complete 2-D matrices only; per-head 3-D Q8_0 is excluded. One M1 Ultra, uncontrolled OS page cache. Not complete MLA/layer, token, Rust, or Metal speedup. |

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
