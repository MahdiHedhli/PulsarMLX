# PulsarMLX Feature 018 IQ3_XXS-Down Qualification

## Executive result

The IQ3_XXS routed-down extension is qualified through an exact P1. The strict
Metal scaffold consumes packed IQ3_XXS bytes directly, uses no complete f32
weight materialization or hidden CPU fallback, and passed the frozen Tier B
numerical contract from one matrix through the composed IQ2/IQ3 expert, MoE,
complete-layer, and P1 boundaries.

The bounded complete-layer profile now places dense/trunk dequantization above
either direct expert kernel. No third direct-quantized kernel was selected, and
neither P2 nor golden-eight was run.

## Repository boundary

- Sprint starting SHA: `167fdba75663461956302973f9c86bac8792c4ab`
- Frozen contract commit: `c6299abc`
- Synthetic evidence source: `9b4ca284`
- Real matrix evidence source: `20c2be41`
- Composed ladder sources: `feeb222e`, `39397d48`, and `111aa9d0`
- Exact P1 evidence source: `8b7a1bfc`
- Banked evidence head before closeout: `8f42ae24`
- Branch: `feat/018-direct-quantized-metal-runtime`

The final closeout SHA and exact CI run are reported by the pushed branch and
the session handoff; a committed document cannot truthfully name its own SHA.

## Frozen numerical contract and oracle

Contract version `f018-iq3-down-v1` was committed before candidate execution.
The bit-exact oracle is scalar IQ3_XXS decode followed by f32 multiplication
and sequential-column f32 accumulation. The optimized whole-matrix NumPy plus
synchronized MLX path is a Tier B performance reference, not the bit-exact
oracle.

The single-matrix envelope is absolute/relative `0.00025`, cosine at least
`0.9999995`, and norm ratio `[0.99975, 1.00025]`. The composed-boundary envelope
remains absolute/relative `0.005`, cosine at least `0.999`, and norm ratio
`[0.995, 1.005]`, with exact routes and greedy tokens. Thresholds were not
changed after observation.

## Kernel and ownership

The qualified kernel is the deterministic one-thread-per-output-row scaffold.
It reads the GGML IQ3_XXS 98-byte/256-weight block directly, resolves grid,
scale, and sign metadata, and accumulates columns in increasing order. It does
not first materialize a full f32 matrix. Qualification compilation explicitly
uses `fastMathEnabled = NO`, safe/precise floating-point functions, and Metal
language version 3.2.

Rust-owned page-aligned slabs are registered with no-copy Metal buffers.
Completion-handler retention, in-flight accounting, immutable generations, and
teardown protection keep allocation and registration alive until every
referencing command buffer completes. Validation-mode direct failures are
fatal; unsupported formats and roles are chosen as explicit reference
dispatches before candidate invocation.

The isolated IQ3 oracle and kernel follow the existing Python research-path
IQ3 byte interpretation. The repository's other runtime decoders need a formal
cross-runtime packed-format fixture before shipping integration; this report
does not declare an unqualified decoder implementation incorrect.

## Qualification ladder

| Boundary | Classification | Direct median (s) | Reference median (s) | Same-boundary ratio | Scope |
| --- | --- | ---: | ---: | ---: | --- |
| Synthetic 64x2048 | Tier B, deterministic | 0.000454979 | n/a | n/a | checkpoint-free scaffold |
| Real IQ3 down matrix | Tier B, deterministic | 0.000610605 | 0.123234876 | 201.824x | layer 3, expert 15 |
| Complete routed expert | Tier B, deterministic | 0.018807751 | 0.269965292 | 14.35x | direct IQ2 gate/up + IQ3 down |
| Top-8 plus shared MoE | Tier B, deterministic | 0.226394771 | 1.705199125 | 7.53x | shared expert remains reference |
| Complete layer 3 | Tier B, deterministic | 0.950992354 | 2.677491229 | 2.82x | attention remains reference |

The synthetic population retained 100 identical candidate hashes. The real
matrix retained 30 measured warm samples and had zero elementwise tolerance or
signed-zero mismatches; maximum absolute error was `6.9849e-10`, RMSE was
`1.031e-10`, cosine was `0.9999999999996638`, and norm ratio was
`0.9999999756666862`. It was not f32-bit identical and is therefore Tier B,
not `golden_identical`.

The composed expert used three stable packed slabs. Each warm sample recorded
three hits, three resident entries, zero evictions, zero fallback, and zero
complete-f32 Metal weight bytes. The top-8 boundary dispatched 16 direct IQ2
gate/up projections and eight direct IQ3 down projections; the protected shared
expert remained the explicit MLX reference path.

## Exact P1

At clean source `8b7a1bfc`, the optional combined mode reproduced exact P1
`[9703,21615]`.

| Boundary | Seconds |
| --- | ---: |
| Complete evidence wall | 990.044242625 |
| Cold prompt stack | 833.188530042 |
| Full-vocabulary logits | 77.987068333 |
| Terminal warm stack | 78.446275458 |
| Direct packed storage | 3.410163118 |
| Direct kernel intervals | 2.743788668 |
| Direct synchronized calls | 5.215071666 |

The run recorded 1,136 direct routed-expert executions, 80 intentional explicit
reference executions, 3,408 direct GEMVs, 228 protected shared-cache hits,
normal retained resource observations, and zero CPU fallback or direct error.
The bounded three-slot worker rotated routed expert slabs and recorded 3,405
evictions with zero routed slab hits; this is expected transient policy behavior
and not a protected shared-cache eviction.

For context only, the prior IQ2-only P1 recorded 1043.247634125 s total and a
127.009654625 s terminal warm stack. The differences of 53.203391500 s and
48.563379167 s are cross-commit observations, not a controlled timing
population or general throughput claim.

## Post-IQ3 profile and decision

The deterministic bounded layer-3 profile ranked:

1. dense/trunk dequantization: `0.651695598` s;
2. complete MoE boundary: `0.207311958` s;
3. router: `0.056043729` s;
4. dense/trunk matvec: `0.041801989` s;
5. dense/trunk build/eval: `0.038241864` s.

This is a one-layer profile, not a full-stack warm-token ranking. It is enough
to defer a third expert-format kernel; it is not enough to choose the next
production kernel. The next measured gate is integration of the qualified
format-neutral ownership/dispatch contract into the Rust-native runtime plus a
fresh profile of the dense/trunk boundary. Direct IQ3 parallelism is also
deferred because the strict sequential scaffold already materially beat the
optimized reference at the admitted boundary.

## Feature 017 handoff

Only format-neutral requirements cross the boundary:

- multiple packed-format capabilities expressed as data, not hard-coded layout;
- generation-protected stable slots and in-flight completion ownership;
- generic per-format/per-role timing and failure telemetry;
- a format-independent multi-projection request/response contract;
- multiple strict pipelines in one worker/context;
- fail-closed validation and explicit reference dispatch semantics.

IQ3 layout tables, shader source, tensor names, thresholds, and qualification
evidence remain Feature 018 responsibilities. No wholesale Feature 017 merge
occurred.

## Evidence and reproduction

- Synthetic: `raw/f018-iq3-xxs-synthetic-0001.json`
- Real matrix: `raw/f018-iq3-xxs-down-matrix-0001.json`
- Routed expert: `raw/f018-iq2-iq3-routed-expert-0001.json`
- Top-8/shared MoE: `raw/f018-iq2-iq3-moe-layer3-0001.json`
- Complete layer: `raw/f018-iq2-iq3-complete-layer3-0001.json`
- Bounded profile: `raw/f018-iq3-post-layer-hotspots-0001.json`
- Exact P1: `raw/f018-inference-p1-direct-iq2-iq3-0001.json`

CI-safe regeneration and validation:

```sh
cargo run -p stream --bin iq3-metal-evidence -- --out /tmp/f018-iq3.json
uv run --frozen python scripts/research/analyze_glm52_iq3_xxs_metal.py --check
uv run --frozen python scripts/research/analyze_glm52_routed_expert_iq3_metal.py --check
uv run --frozen python scripts/research/analyze_glm52_iq3_composed_metal.py --check
uv run --frozen python scripts/research/analyze_f018_iq3_hotspots.py --check
uv run --frozen python scripts/research/analyze_f018_iq3_p1.py --check
uv run --frozen python -m unittest scripts.research.tests.test_f018_evidence
```

Real checkpoint runners additionally require the already admitted checkpoint
through `PULSARMLX_GLM_GGUF`; no private path or checkpoint bytes are committed.

## Closeout validation

The local closeout passed:

- 10 IQ2 and 8 IQ3 native Metal tests;
- 2 compile-fail lifetime tests;
- 474 complete research tests and 89 Python worker tests;
- workspace `cargo check --workspace --all-targets` and
  `cargo test --workspace --no-fail-fast`;
- native MLX device smoke, 7 bounded tensor fixtures, synthetic routed-MoE,
  and the Rust-to-worker router integration;
- evidence/package, generated-artifact, privacy, staged-safety, Spec Kit, and
  `git diff --check` gates.

Publication commit `91572eb9` passed both Apple Silicon jobs in GitHub Actions
run `31416369616`: `Apple Silicon workspace baseline` and
`Apple MLX small-fixture validation`. The inherited macOS warnings remain
documented and were not promoted to new failures.

The final `Mahdi-Dev` notification was acknowledged by the repository helper at
`2026-08-10T17:57:47Z`.

## Unsupported capabilities

- no P2 or golden-eight evidence for the direct IQ2/IQ3 mode;
- no steady-state tokens/second, long-context, or production-readiness claim;
- no direct shared-expert, attention, logits, or all-format coverage;
- no parallel IQ3 kernel or direct fused top-8 kernel;
- no Rust-native generation loop or server integration;
- no claim that the bounded three-slot research worker is a production cache.

## Exact next gate

Keep the third kernel unselected. Review the format-neutral lifecycle and
dispatch changes for focused Feature 017 integration, then profile the
Rust-native dense/trunk boundary. Reopen kernel selection only from that
measured end-to-end opportunity.
