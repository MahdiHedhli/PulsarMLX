# Feature Specification: GLM-5.2 Full Execution

**Feature Branch**: `016-glm52-full-execution`
**Created**: 2026-08-07
**Status**: Active (weekend inference optimization; C01–C11 baseline complete)
**Input**: Complete transition from verified Qwen3-30B-A3B research runtime to verified full-model GLM-5.2 execution and performance on M1 Ultra internal SSD.

## Background and baseline

Features F002–F005 and F007–F015 verify an architecture-level Qwen3-30B-A3B
Q8_0 path (CPU vs MLX; Q8_0 weight dequant × f32 activation). F006 llama
bit-parity is rejected (F008 root cause). Tag
`v0.2.0-qwen30b-e2e-research` freezes that baseline.

This feature admits **GLM-5.2** (`glm-dsa`: MLA + DSA sparse attention + MoE)
on the **same machine’s internal SSD only**, without reopening Qwen claims.

## Goals

1. Immutable GLM-5.2 checkpoint admission on internal SSD after disk gate.
2. Streaming MLX runtime that never fully materializes the model in unified memory.
3. Frozen architecture contract from checkpoint + upstream source.
4. Correctness ladder GLM-C01…C11 through full logits and ≥8 generated tokens.
5. MLX-only performance protocol (TTFT, prefill, decode) with public-safe telemetry.
6. Publication package under `docs/research/glm52/` and `PULSARMLX_GLM52_REPORT.md`.

## Non-goals

- M2 Max testing
- External NVMe RAID
- Copying GLM weights to external drives
- Llama/CUDA fused bit-parity as success criteria
- Weakening Qwen evidence or tolerances to “make GLM pass”
- Production multi-tenant serving claims

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Disk and checkpoint admission (Priority: P0)

An engineer proves free space and then admits an immutable
`GLM-5.2-UD-IQ2_XXS` identity (size + SHA-256 + GGUF structure) on the
internal SSD before any GLM execution claim.

**Why this priority**: Without disk and identity, no further boundary is valid.

**Independent Test**: `docs/validation/glm52-disk-admission.json` and
`docs/validation/glm52-checkpoint.json` validate against gates.

**Acceptance Scenarios**:

1. **Given** free space ≥500 GiB (or ≥700 GiB if dual-copy download), **When**
   admission runs, **Then** result is `passed` and download may start.
2. **Given** free space below gate after safe cleanup only, **When** admission
   runs, **Then** result is `failed`, no download starts, Qwen baseline retained.

### User Story 2 — Streaming runtime (Priority: P1)

An engineer runs GLM layers with expert streaming, bounded caches, and
configurable memory budgets without silent full-model load or CPU fallback.

**Acceptance Scenarios**:

1. **Given** admitted GLM checkpoint and 128 GiB unified memory, **When** a
   full-model forward is configured, **Then** process RSS stays within budget
   and swap does not dominate.
2. **Given** missing expert data not yet prefetched, **When** a layer needs
   that expert, **Then** the runtime performs a bounded positional read (or
   fails closed), never invents zeros silently.

### User Story 3 — Correctness ladder (Priority: P1)

An engineer validates GLM-C01…C11 in order against an independent architecture
oracle / trusted reference that does not call the MLX path under test.

**Acceptance Scenarios**:

1. **Given** each completed boundary C0k, **When** evidence is published,
   **Then** claims ledger maps commit, checkpoint hash, command, metrics, and
   tolerances.
2. **Given** material numerical divergence, **When** depth expansion is
   attempted, **Then** expansion stops, first divergent op is isolated, and
   tolerance is not loosened.

### User Story 4 — Full execution and generation (Priority: P1)

An engineer obtains complete logits, one matching greedy token, and at least
eight generated tokens from a frozen text prompt.

### User Story 5 — Performance (Priority: P2)

An engineer records process-cold and warm TTFT, prefill, and decode metrics
on the MLX-only path with synchronized timers.

## Functional requirements

- **FR-001**: Prefer quant `GLM-5.2-UD-IQ2_XXS` (DS4-compatible recipe); do not
  switch to Unsloth 11-shard Q4 for convenience.
- **FR-002**: Disk admission must pass before any download.
- **FR-003**: Checkpoint identity (repo, revision, filenames, sizes, hashes,
  license) is recorded before execution claims.
- **FR-004**: Runtime uses `PULSARMLX_GLM_GGUF` (or shard directory env) — never
  private absolute paths in committed evidence.
- **FR-005**: MLX path supports mmap / positional reads, expert streaming,
  eviction, prefetch, and public-safe memory/I/O telemetry.
- **FR-006**: Independent CPU oracle must not import MLX worker modules.
- **FR-007**: Architecture contract freezes MLA, DSA, routing, experts, norms,
  residuals, RoPE, and cache state from source + GGUF metadata.
- **FR-008**: Correctness ladder C01–C11 is ordered; full-model support is
  claimed only after C09–C11 pass.
- **FR-009**: Performance mode excludes CPU-oracle cost from timers.
- **FR-010**: Hosted CI remains checkpoint-free; real GLM tests are Tier-3 local
  and fail closed when the model is absent (no silent skip-pass).
- **FR-011**: Qwen F002–F015 evidence is never rewritten or deleted by this feature.

## Correctness ladder (checkpoints)

| ID | Boundary |
| --- | --- |
| GLM-C01 | Metadata + tensor catalog |
| GLM-C02 | Embedding, norms, dense primitives |
| GLM-C03 | Router (IDs, order, weights) |
| GLM-C04 | Single real expert |
| GLM-C05 | Full routed MoE block |
| GLM-C06 | MLA attention |
| GLM-C07 | DSA sparse attention |
| GLM-C08 | Complete layer 0 |
| GLM-C09 | Depth ladder → full model |
| GLM-C10 | Full logits |
| GLM-C11 | Deterministic generation (≥8 tokens) |

## Success criteria

- Disk and checkpoint admission published and green.
- Full layer stack executes without full-model CPU fallback.
- Complete logits produced; top-1 greedy token agrees with independent reference.
- ≥8 generated tokens with deterministic replay.
- Performance evidence records TTFT, prefill, decode, memory, SSD I/O.
- Claims ledger + reviewer index validate; worktree clean; main = origin/main.
- Tag `v0.3.0-glm52-e2e-research` only after the above.

## Assumptions

- Host is M1 Ultra Mac Studio, 128 GB unified memory, internal SSD only.
- Preferred remote is Hugging Face `unsloth/GLM-5.2-GGUF` quant `UD-IQ2_XXS`
  (currently 6 shards totaling ~222 GiB) unless a verified single-file DS4
  equivalent is already local.
- Architecture-level numerical contract may differ from fused CUDA paths;
  differences require root-cause documentation (Qwen F008 pattern).

## Current state

The original disk stop was resolved without weakening the gate. The six-shard
checkpoint was admitted, hashed, and exercised through C11; the research
baseline is frozen at `v0.3.0-glm52-e2e-research`. The active work is the
bounded inference optimization in Phase 8 of `tasks.md`. The next external
checkpoint gate is P2: exactly two new tokens with exact golden-prefix parity,
MLX-only execution, and useful shared-expert cache reuse.
