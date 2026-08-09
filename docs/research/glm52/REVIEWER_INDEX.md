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
- [Layer-3 top-8 plus shared MoE](raw/f016-moe-layer3-0001.json) — exact route,
  independent CPU oracle, shared-cache cold/warm observations, and raw samples
- [Complete layer 3](raw/f016-layer3-0001.json) — frozen attention midpoint and
  route, architecture-reference comparison, exact decoder-mode bits, split
  attention/MoE timing, and raw samples
- [Vectorized P1](raw/f016-inference-p1-vectorized-0001.json) — clean full-stack
  golden-prefix run, complete routes, split cache metrics, per-quant timing,
  resources, and MLX GPU identity
- [P1 mixed-quant ranking](raw/f016-p1-quant-hotspot-ranking-0001.json) and
  [generated table](tables/f016-p1-quant-hotspots.md) — deterministic derivation
  from the committed P1 per-quant metrics; ranks measured component time rather
  than catalog tensor count

### Results (populated after runs)

- [RESULTS.md](RESULTS.md)
- `tables/` / `figures/` generated from raw only

### Claims

- [CLAIMS_LEDGER.md](CLAIMS_LEDGER.md)

## Required reviewer checks

| Check | Status |
| --- | --- |
| Protocol tolerances frozen | yes |
| No full-model claim without C09–C11 | enforced in protocol |
| External RAID / M2 Max deferred | yes |
| Silent CPU fallback forbidden in perf mode | yes (implementation + tests) |
