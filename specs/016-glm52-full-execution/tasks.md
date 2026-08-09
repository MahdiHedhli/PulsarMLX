# Tasks: 016-glm52-full-execution

## Phase 0 — Qwen baseline (done)

- [x] Tag `v0.2.0-qwen30b-e2e-research` @ 493234a

## Phase 1 — Disk admission (done)

- [x] Passed after space clearance (`docs/validation/glm52-disk-admission.json`)

## Phase 2 — Checkpoint acquisition (done)

- [x] NTFY start; download to internal `Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS`
- [x] All 6 shards complete + size check
- [x] Per-file SHA-256 + `docs/validation/glm52-checkpoint.json`
- [x] NTFY acquisition complete

## Checkpoint-independent (done / ongoing)

- [x] Experiment protocol + tolerances frozen
- [x] Results/repro/reviewer shells
- [x] Upstream glm-dsa map @ 17dac547; contract tightened
- [x] Expert cache skeleton + tests
- [x] Public-safe telemetry + privacy tests
- [x] Fail-closed execution guard + tests
- [x] IQ2_XXS dequant + synthetic tests
- [x] Synthetic sigmoid router + shared sink
- [x] Generation harness + frozen prompt texts
- [x] Multi-shard catalog/store tooling
- [x] CI suite `test_glm52_checkpoint_free.py`

## Phase 3 — Streaming runtime (partial; optimization continues)

- [x] Expert cache API (fake store)
- [x] Telemetry collector
- [x] Fail-closed mode
- [x] Wire cache to real multi-shard positional reads
- [ ] Prefetch policy integration

## Phase 4 — Architecture contract

- [x] KV freeze + upstream map
- [x] Complete tensor-name walk after C01 full catalog

## Phase 5 — Correctness ladder (real weights, done)

- [x] C01–C11 after checkpoint identity

## Phase 6–7

- [x] Full research execution evidence + `PULSARMLX_GLM52_REPORT.md` + tag `v0.3.0-glm52-e2e-research`
- [ ] Optimized inference performance and final optimization report

## Phase 8 — Weekend inference optimization

- [x] Preserve unchanged recovered P1 first-token evidence and golden prefix
- [x] Diagnose 0% decoded-cache hits with exact working-set accounting
- [x] Add a deterministic cache simulator with decoded/compressed/shared policy separation
- [x] Replace Python-row global LRU with compact fail-closed shared-expert residency and split metrics
- [x] Retain the first-stack-incomplete P2 attempt as superseded by the decoder-priority finding
- [x] Qualify a whole-block/whole-matrix NumPy IQ2_XXS decoder against exact scalar f32 bits
- [x] Integrate one-read, one-decode, one-MLX-build matrix execution behind explicit decoder modes
- [ ] Benchmark decode → real matrix → routed expert → layer-3 MoE → layer → P1 in order
- [ ] Inventory golden-trace mixed quant formats by measured token time
- [ ] Design a dedicated bit-exact Rust f32 dequantization boundary; do not reuse x86 Q8_K throughput claims
- [ ] Re-profile P1 and re-evaluate shared-cache value after vectorization
- [ ] Run P2 exactly two new tokens; require `[9703, 21615, 220]` and useful reuse
- [ ] Run the frozen eight-token golden only after P2 passes
- [ ] Evaluate prefetch and storage changes one measured variable at a time after decoder profiling
- [ ] Publish final optimization report, clean CI, and pushed repository state
