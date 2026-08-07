# Tasks: 016-glm52-full-execution

## Phase 0 — Qwen baseline (done)

- [x] Tag `v0.2.0-qwen30b-e2e-research` @ 493234a

## Phase 1 — Disk admission (done)

- [x] Passed after space clearance (`docs/validation/glm52-disk-admission.json`)

## Phase 2 — Checkpoint acquisition (in progress)

- [x] NTFY start; download to internal `Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS`
- [ ] All 6 shards complete + size check
- [ ] Per-file SHA-256 + `docs/validation/glm52-checkpoint.json`
- [ ] NTFY acquisition complete

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

## Phase 3 — Streaming runtime (partial)

- [x] Expert cache API (fake store)
- [x] Telemetry collector
- [x] Fail-closed mode
- [ ] Wire cache to real multi-shard positional reads
- [ ] Prefetch policy integration

## Phase 4 — Architecture contract

- [x] KV freeze + upstream map
- [ ] Complete tensor-name walk after C01 full catalog

## Phase 5 — Correctness ladder (real weights)

- [ ] C01–C11 after checkpoint identity

## Phase 6–7

- [ ] Performance + `PULSARMLX_GLM52_REPORT.md` + tag `v0.3.0-glm52-e2e-research`
