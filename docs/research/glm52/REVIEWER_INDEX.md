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
  per-quant deltas, trunk residual, and prefetch/Feature-018 decisions
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

### Claims

- [CLAIMS_LEDGER.md](CLAIMS_LEDGER.md)

## Required reviewer checks

| Check | Status |
| --- | --- |
| Protocol tolerances frozen | yes |
| No full-model claim without C09–C11 | enforced in protocol |
| External RAID / M2 Max deferred | yes |
| Silent CPU fallback forbidden in perf mode | yes (implementation + tests) |
