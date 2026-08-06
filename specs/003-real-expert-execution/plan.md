# Implementation Plan: Real Expert Execution

**Branch**: `003-real-expert-execution` | **Date**: 2026-08-06 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-real-expert-execution/spec.md`

## Summary

Implement a fail-closed Apple MLX path that executes **one** full routed expert
MLP from the immutable Qwen3-30B-A3B Q8_0 checkpoint for expert index **114**
(Feature 002 single-row top-8 rank-0), using the genuine `ffn_norm-0` input row
and Feature 002 normalized routing weight, compared to an independent CPU
oracle. Publish append-only research evidence. No aggregation, layer, logits,
or generation.

## Technical Context

**Language/Version**: Rust workspace + Python 3.12 worker/oracle tooling  
**Primary Dependencies**: MLX 0.32.0, existing `mlx-backend`, Feature 001 Q8_0
decode, Feature 002 research package  
**Storage**: External GGUF; evidence under `docs/research/raw/003-expert-mlp/`  
**Testing**: Unit/contract tests (CI), real-checkpoint local only  
**Target Platform**: macOS arm64 Apple Silicon  
**Project Type**: Systems runtime + research evidence  
**Performance Goals**: Correctness only; retain optional timing gauges without
tokens/sec claims  
**Constraints**: Independent CPU oracle; no silent tolerance loosening;
NTFY before model access; public-safe evidence  
**Scale/Scope**: One expert, one input row, one weighted output vector

## Constitution Check

- [x] Additive Apple path only; Linux/CUDA selection unchanged  
- [x] Fail-closed identity and resource admission  
- [x] Evidence before claims  
- [x] Feature 001/002 claims not rewritten  

## Project Structure

### Documentation (this feature)

```text
specs/003-real-expert-execution/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md
```

### Source Code (repository root)

```text
crates/mlx-backend/          # expert MLP admission + validate-expert command
python/pulsar_mlx_worker/    # MLX expert runner (if worker path used)
scripts/research/            # expert oracle, sanitizer hooks, package paths
fixtures/research/expert-v1/ # model-free fixtures
docs/research/raw/003-expert-mlp/
docs/research/               # claims, reviewer index, results updates
```

**Structure Decision**: Extend existing mlx-backend + research package rather
than a new crate.

## Complexity Tracking

No constitution violations requiring justification.

## Implementation Phases

1. **Contracts & fixtures**: expert evidence schema fields, model-free golden.  
2. **Oracle**: CPU full-expert freeze for expert 114.  
3. **Admission**: inspect expert gate/up/down ranges for index 114.  
4. **MLX path**: evaluate full MLP + weight scale on GPU.  
5. **Parity command**: external candidate + comparison.  
6. **Publication**: sanitize, raw, tables, claims, repro, CI.

## Dependencies

- Feature 002 frozen oracle/input/top-8/weights (committed).  
- Feature 001 Q8_0 decode and model identity.  
- External checkpoint path `$PULSARMLX_MODEL_GGUF`.
