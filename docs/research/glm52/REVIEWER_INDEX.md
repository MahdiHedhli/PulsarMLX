# GLM-5.2 Reviewer Index

**Feature**: `016-glm52-full-execution`
**Protocol**: [EXPERIMENT_PROTOCOL.md](EXPERIMENT_PROTOCOL.md)

## How to review

1. Confirm protocol freeze predates real-weight measurements.
2. Confirm checkpoint identity file matches local shards (sizes + SHA-256).
3. Walk claims ledger F016-*; every verified claim links to raw evidence.
4. Confirm privacy: no usernames, hostnames, home paths, tokens.
5. Confirm CI-safe tests pass without `PULSARMLX_GLM_GGUF`.
6. Confirm Tier-3 fails closed when checkpoint missing.

## Sections

### Methodology (checkpoint-free)

- [EXPERIMENT_PROTOCOL.md](EXPERIMENT_PROTOCOL.md)
- [REPRODUCIBILITY.md](REPRODUCIBILITY.md)
- [LIMITATIONS.md](LIMITATIONS.md)
- Spec: `specs/016-glm52-full-execution/`

### Architecture

- [GLM52_CONTRACT.md](../../architecture/GLM52_CONTRACT.md)
- [Rust exact-decode boundary](../../architecture/RUST_EXACT_DECODE_BOUNDARY.md)
- Upstream pin: Pulsar `17dac547898e0e65bb073f13444708daf68edc3d`

### Admission

- [glm52-disk-admission.json](../../validation/glm52-disk-admission.json)
- Checkpoint identity: `docs/validation/glm52-checkpoint.json` (after download)

### Raw evidence

- `docs/research/glm52/raw/` — machine-readable parity and perf records
- [IQ2_XXS NumPy qualification](raw/f016-iq2-xxs-numpy-qualification-0001.json)
  — four complete matrices, raw timing samples, exact-bit comparisons, and
  allocation/resource observations
- [IQ3_XXS NumPy qualification](raw/f016-iq3-xxs-numpy-qualification-0001.json)
  — four complete down matrices across four shards, raw timing samples,
  exact-bit comparisons, and allocation/resource observations
- [Real IQ3_XXS down-matrix boundary](raw/f016-iq3-matrix-boundary-0001.json)
  — one-read vector load, synchronized MLX GPU build/matvec, exact scalar-mode
  comparison, resource observations, and raw timing samples
- [Real matrix boundary](raw/f016-matrix-boundary-0001.json) — one-read vector
  load, synchronized MLX GPU build/matvec, scalar comparison, and raw samples
- [Complete routed expert](raw/f016-routed-expert-0001.json) — gate/up/down,
  independent CPU oracle, mixed-quant timing, and deterministic MLX comparison
- [Complete routed expert with vector IQ3_XXS](raw/f016-routed-expert-iq3-0001.json)
  — gate/up/down one-read matrix execution, independent CPU oracle, split
  IQ2_XXS/IQ3_XXS timings, and deterministic MLX comparison
- [Layer-3 top-8 plus shared MoE](raw/f016-moe-layer3-0001.json) — exact route,
  independent CPU oracle, shared-cache cold/warm observations, and raw samples
- [Layer-3 top-8 plus shared MoE with vector IQ3_XXS](raw/f016-moe-layer3-iq3-0001.json)
  — exact route, independent CPU oracle, three one-read projections per routed
  expert, shared-cache cold/warm observations, and raw samples
- [Complete layer 3](raw/f016-layer3-0001.json) — frozen attention midpoint and
  route, architecture-reference comparison, exact decoder-mode bits, split
  attention/MoE timing, and raw samples
- [Complete layer 3 with vector IQ3_XXS](raw/f016-layer3-iq3-0001.json) — frozen
  attention midpoint and route, architecture-reference comparison, exact mode
  bits, and split attention/MoE timing after both dominant decoders
- [Vectorized P1](raw/f016-inference-p1-vectorized-0001.json) — clean full-stack
  golden-prefix run, complete routes, split cache metrics, per-quant timing,
  resources, and MLX GPU identity
- [P1 with vector IQ3_XXS](raw/f016-inference-p1-iq3-0001.json) — clean
  full-stack golden-prefix run after both dominant decoder qualifications,
  complete routes, warm shared-cache reuse, resources, and per-quant timing
- [P2 with vector IQ3_XXS](raw/f016-inference-p2-iq3-0001.json) — exact
  two-token golden prefix, three complete route stacks, 228 shared-cache hits
  per warm stack, resource checkpoints, and zero-fallback MLX identity
- [Frozen golden eight with vector IQ3_XXS](raw/f016-inference-golden8-iq3-0001.json)
  — exact full sequence, nine complete 79-layer stacks, 684 complete MoE route
  records, 1,824 shared-cache hits, resource checkpoints, and zero-fallback
  MLX GPU identity
- [Golden-eight derived profile](raw/f016-golden8-derived-profile-0001.json)
  and [generated table](tables/f016-golden8-derived-profile.md) — total/cold/warm
  observations, passive-watcher monotonicity witness, seven expert-cache-only
  per-quant deltas, uninstrumented residual, and prefetch/Feature-018 decisions
- [Post-golden-eight calculations](raw/f016-golden8-post-run-calculations-0001.json)
  with the [complete GGUF trunk inventory](raw/f016-gguf-trunk-inventory-0001.json)
  and [concise report](POST_GOLDEN8_CALCULATIONS.md) — token-eight selection
  boundary, per-layer uninstrumented residual, cleanup non-attribution, complete
  non-expert GGUF inventory, logical residency budgets, request amplification,
  and the two bounded trunk experiments
- [Post-Feature-016 whole-matrix trunk-read experiment](raw/post-f016-trunk-bulk-read-0001.json)
  and [generated comparison table](tables/post-f016-trunk-bulk-read-0001.md)
  — exact-bit real Q5_K, Q8_0, and Q6_K matrix comparisons plus a complete
  single-position layer-8 MLA boundary; request granularity is the only changed
  variable, and the result does not establish a token or full-layer speedup
- [Post-Feature-016 NumPy Q5_K qualification](raw/post-f016-q5-k-numpy-qualification-0001.json)
  and [generated qualification table](tables/post-f016-q5-k-numpy-qualification-0001.md)
  — four complete real attention-output matrices across four layers/shards,
  exact f32-bit scalar-oracle comparisons, deterministic repeats, signed-zero
  checks, raw decode samples, and bounded allocation/resource observations
- [Post-Feature-016 Q5_K dense integration](raw/post-f016-trunk-q5-integration-0001.json)
  and [generated integration table](tables/post-f016-trunk-q5-integration-0001.md)
  — one complete real Q5_K MLX matrix boundary and complete layer-3 MLA,
  exact f32-bit output, explicit non-Q5 scalar behavior, split timings, and raw
  counterbalanced samples
- [Post-Feature-016 NumPy Q8_0 qualification](raw/post-f016-q8-0-numpy-qualification-0001.json)
  and [generated qualification table](tables/post-f016-q8-0-numpy-qualification-0001.md)
  — four complete real 2-D matrices across four layers/shards, exact f32-bit
  scalar-oracle comparisons, deterministic repeats, signed-zero checks, and raw
  decode samples; per-head 3-D Q8_0 remains explicitly excluded
- [Post-Feature-016 2-D Q8_0 dense integration](raw/post-f016-trunk-q8-2d-integration-0001.json)
  and [generated integration table](tables/post-f016-trunk-q8-2d-integration-0001.md)
  — exact real matrix and complete layer-3 MLA output, with Q5_K held
  vectorized, only captured 2-D Q8_0 changed, and the unmodified per-head 3-D
  path retained in the residual
- [Post-Feature-016 Q8_0 head-slab storage experiment](raw/post-f016-q8-head-bulk-scalar-0001.json)
  and [generated table](tables/post-f016-q8-head-bulk-scalar-0001.md) — exact
  single-head and complete layer-3 MLA comparisons with unchanged scalar decode;
  49,152 row requests collapse to 128 head-slab reads without a material wall gain
- [Post-Feature-016 Q8_0 head-slab NumPy integration](raw/post-f016-q8-head-numpy-integration-0001.json)
  and [generated table](tables/post-f016-q8-head-numpy-integration-0001.md)
  — exact single-head and complete layer-3 MLA output with one read in both
  modes, split 128-head operation timing, and scalar-to-NumPy decoder isolation
- [Post-Feature-016 NumPy Q6_K qualification](raw/post-f016-q6-k-numpy-qualification-0001.json)
  and [generated table](tables/post-f016-q6-k-numpy-qualification-0001.md) — all
  five exercised trunk tensors, complete real matrices, exact f32-bit oracle
  comparisons, deterministic repeats, signed-zero checks, and raw timing samples
- [Post-Feature-016 Q6_K dense integration](raw/post-f016-trunk-q6-integration-0001.json)
  and [generated table](tables/post-f016-trunk-q6-integration-0001.md) — exact
  complete real layer-8 attention-output matrix and MLA output, with Q5_K and
  all Q8_0 paths held vectorized; validator-derived operation counts audit the
  raw record's retained legacy summary-label omission
- [P1 mixed-quant ranking](raw/f016-p1-quant-hotspot-ranking-0001.json) and
  [generated table](tables/f016-p1-quant-hotspots.md) — deterministic derivation
  from the committed P1 per-quant metrics; ranks measured component time rather
  than catalog tensor count
- [Revised P1 mixed-quant ranking](raw/f016-p1-iq3-quant-hotspot-ranking-0001.json)
  and [generated table](tables/f016-p1-iq3-quant-hotspots.md) — deterministic
  post-IQ3 ranking; identifies Q6_K as the next measured format and quantifies
  why shared residency remains valuable before P2

### Results (populated after runs)

- [RESULTS.md](RESULTS.md)
- [Feature 016 completion report](FEATURE_016_COMPLETION_REPORT.md)
- `tables/` / `figures/` generated from raw only
- Deterministic profile check:
  `python3 scripts/research/analyze_glm52_golden8.py --check`
- Deterministic post-run calculation check:
  `python3 scripts/research/analyze_glm52_post_run.py --check`

### Claims

- [CLAIMS_LEDGER.md](CLAIMS_LEDGER.md)

## Required reviewer checks

| Check | Status |
| --- | --- |
| Protocol tolerances frozen | yes |
| No full-model claim without C09–C11 | enforced in protocol |
| External RAID / M2 Max deferred | yes |
| Silent CPU fallback forbidden in perf mode | yes (implementation + tests) |
