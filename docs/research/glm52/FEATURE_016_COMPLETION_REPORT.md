# PulsarMLX Feature 016 Completion Report

## Executive result

Feature 016 is complete. The deepest
verified boundary is one clean M1 Ultra MLX GPU execution of the exact frozen
eight-token continuation across nine complete 79-layer stacks. The run matched
`[9703,21615,220,16,13,16,16,15,15]`, retained shared-expert reuse, and recorded
zero CPU fallbacks, evictions, or admission rejections. The implementation and
report commit passed both Apple Silicon CI jobs; the task-closing reconciliation
is validated again before publication.

This is a research correctness/reuse milestone. It is not production readiness,
interactive performance, steady-state tokens per second, long-context support,
serving, a Rust-native runtime, or direct quantized Metal execution.

## Repository

- Session starting SHA: `c263d2ee9ea5a972ea066c88ca7d41168ec4e5f6`
- Golden evidence source: `1a2ca76ee2df0f518bfc9ddbaafd31500a5e6a26`
- Raw evidence commit: `540f29c85324f79315bb859a3ad7608e55ddbda6`
- Derived profile commit: `2167fc227ac4afc82a8d02883158d0c6c3a4b57d`
- Branch: `main`
- Validated implementation/report SHA: `c37807687191f2f69c2b9ad174c9fa763ce57479`
- Reconciliation SHA: the commit containing the final 44/44 task-state change;
  its exact identity and remote parity are reported in the session handoff.

## Golden-eight result

| Field | Observed result |
| --- | --- |
| Prompt / prompt token | `Hello` / `[9703]` |
| Generated tokens | `[21615,220,16,13,16,16,15,15]` |
| Full sequence | `[9703,21615,220,16,13,16,16,15,15]` |
| Complete evidence wall | 18522.659049 seconds |
| Time to first token, recorded components | 2646.649936 seconds |
| Warm stack population | n=8; median 1921.882049; mean 1916.364214; sample SD 12.887186; min 1892.661681; max 1928.536098 seconds |
| Recorded inter-token components | n=7; median 2000.487972; mean 1992.445999; sample SD 14.334507; min 1968.421771; max 2004.201347 seconds |
| Terminal state advance | 1928.536098 seconds after token eight selection; not user-visible eighth-token latency |
| Shared cache | 228 admissions after cold; 228 hits in each warm stack; 1,824 total hits |
| Avoided bytes | 16,846,159,872 compressed; 91,804,925,952 decoded |
| Resident decoded shared bytes | 11,475,615,744 |
| Fallback / eviction / rejection | 0 / 0 / 0 |
| Resource state | normal at every retained checkpoint |

## Correctness

- Exact-token gate: passed with `matches_golden_full=true`.
- Checkpoint: six-shard GLM-5.2 UD-IQ2_XXS, architecture `glm-dsa`, immutable
  revision `abc55e72527792c6e77069c99b4cb7de16fa9f23`, set SHA-256
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`.
- Execution: MLX 0.32.0 on `Device(gpu,0)`; zero CPU fallbacks.
- Shape: nine 79-layer stacks, each with 76 complete MoE routing records;
  every record contains eight routed expert IDs and one shared expert.
- Semantic validator:
  `python3 -m unittest scripts.research.tests.test_glm52_golden8_iq3_record -v`.
- Committed raw record SHA-256:
  `be4232f2bb4df103756158bfd9d7f6a807c2b332ff651b1670a98a04be5c0018`.
- The compact committed JSON is semantically identical to the terminal original
  watcher snapshot; whitespace compaction did not alter the evidence object.

## Performance

These rows are historical cross-commit observations with different scopes,
not a controlled same-binary population and not a throughput extrapolation.

| Boundary | Wall seconds | Scope |
| --- | ---: | --- |
| Research C11 | ~48730.7 | original eight-token research generation |
| Legacy P1 | 15146.448 | recovered one-token prefix |
| Vectorized P1 | 4582.511 | IQ2_XXS + IQ3_XXS, one-token prefix |
| P2 | 6552.475 | exact two-token prefix, three stacks |
| Golden eight | 18522.659 | exact eight-token continuation, nine stacks |

Across the golden run, expert-cache instrumentation recorded 64,787,546,112
storage bytes read, 2484.091670 seconds of dequantization, 219.970718 seconds
of contiguous-buffer work, 87.939649 seconds of MLX matrix build/evaluation,
72.683463 seconds of MLX matvec, and 622.220436 seconds of logits work.

## Revised hotspots

The cold prompt stack took 2569.173874 seconds. Its measured ranking was an
uninstrumented residual of 1636.635724 seconds (63.70%), expert-cache
dequantization of 836.065616 seconds, contiguous buffers of 74.588111 seconds,
matrix build of 11.018476 seconds, matvec of 8.909328 seconds, and storage of
1.956619 seconds. Cold per-quant deltas are unavailable because the watcher
started after the cold and first warm stacks; no earlier snapshot was invented.

Warm stack means ranked as follows: uninstrumented residual 1670.729513
seconds, expert-cache dequantization 206.003257, separate full-vocabulary logits
77.777555, contiguous buffers 18.172826, MLX matrix build 9.615147, MLX matvec
7.971767, and storage 3.871705. The median residual was 1675.491540 seconds and
87.18% of stack wall.

This residual is not a direct trunk or cleanup measurement; it is the layer/stack
wall not covered by the expert-cache component timers.

Seven watcher intervals covering generated tokens 2–8 were monotonic and valid
for subtraction; no reset occurred. Their per-quant ranking is explicitly
**EXPERT-CACHE PATH ONLY**: IQ2_XXS 69.672 mean component-seconds, IQ3_XXS
50.304, Q2_K 36.153, IQ4_XS 34.654, IQ2_S 33.964, Q3_K 20.391, Q5_K 0.813,
Q6_K 0.378, and Q8_0 0.014. It is not whole-token quantization cost.

## Cache

The decoded-shared-only policy admitted 228 shared slabs during the cold stack
and hit all 228 in every warm stack. It retained 11,475,615,744 decoded bytes,
avoided 16,846,159,872 compressed bytes and 91,804,925,952 decoded bytes, and
recorded zero evictions. This establishes useful reuse under this checkpoint and
sequence, not a general cache hit rate or steady-state population.

## Prefetch and storage

Warm expert-cache storage averaged 3.871705 seconds, 0.20% of mean warm stack
wall. Feature 016 therefore completes the prefetch requirement as an
evidence-backed deferral. No new prefetch mechanism or full-model experiment is
justified by this record. Any future storage change starts at a bounded matrix,
expert, MoE, or layer fixture and changes one variable at a time.

## Rust boundary

[`RUST_EXACT_DECODE_BOUNDARY.md`](../../architecture/RUST_EXACT_DECODE_BOUNDARY.md)
defines whole-slab positional reads, checkpoint identity, exact f32 bits,
mixed-quant fail-closed dispatch, ownership/alignment/lifetime, cancellation,
telemetry, recovery, Python differential gates, and bridge tradeoffs. It rejects
x86 AVX2/Q8_K throughput as Apple f32-decode evidence. Implementation belongs
to Feature 017; no Rust runtime code was added by Feature 016.

## Remaining limitations

- One M1 Ultra and one exact checkpoint/quantization/sequence were measured.
- The Python/MLX path is a research/reference implementation.
- Dense trunk timing is not decomposed; the warm residual is material.
- OS page cache was uncontrolled.
- The final stack is terminal state advance, not required to expose token eight.
- No long-context, serving, cancellation-under-full-load, multi-machine,
  external RAID, Rust-native, or direct Metal claim is established.

## CI

GitHub Actions run
[`31325691273`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31325691273)
passed at `c37807687191f2f69c2b9ad174c9fa763ce57479`:

- Apple Silicon workspace baseline: passed in 1m41s;
- Apple MLX small-fixture validation: passed in 2m14s.

The fixture job excludes external model access and covers the research suite,
evidence package, worker protocol, generated router integration, native device
smoke, tensor fixtures, and synthetic routed MoE. The exact reconciliation
commit receives the same workflow before final handoff.

## Next feature

Begin `017-rust-native-inference-runtime` with the exact slab-read/decode
boundary, native ownership, and representative M2 Max trunk fixtures. Keep
`018-direct-quantized-metal-runtime` separate and profile-neutral. The first
Metal kernel cannot be selected until trunk fixtures attribute MLA/attention
projections, dense pre/post-attention transforms, embeddings if material, final
norm/output projection, and any Q6_K tensors on those paths.

## Evidence and reproduction

- Golden record:
  `docs/research/glm52/raw/f016-inference-golden8-iq3-0001.json`
- Derived profile:
  `docs/research/glm52/raw/f016-golden8-derived-profile-0001.json`
- Generated table:
  `docs/research/glm52/tables/f016-golden8-derived-profile.md`
- Post-run calculations:
  `docs/research/glm52/raw/f016-golden8-post-run-calculations-0001.json`
- Complete GGUF trunk inventory:
  `docs/research/glm52/raw/f016-gguf-trunk-inventory-0001.json`
- Post-run calculation report:
  `docs/research/glm52/POST_GOLDEN8_CALCULATIONS.md`
- Record validator:
  `python3 -m unittest scripts.research.tests.test_glm52_golden8_iq3_record -v`
- Derived-profile validator:
  `python3 scripts/research/analyze_glm52_golden8.py --check`
- Post-run calculation validator:
  `python3 scripts/research/analyze_glm52_post_run.py --check`
- Complete CI-safe research suite:
  `python3 -m unittest discover -s scripts/research/tests -v`
