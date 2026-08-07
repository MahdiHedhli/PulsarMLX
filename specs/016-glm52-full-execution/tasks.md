# Tasks: 016-glm52-full-execution

## Phase 0 — Qwen baseline (done)

- [x] Confirm worktree clean; main = origin/main
- [x] Fast-forward Documents checkout to F015 tip `493234a`
- [x] Run CI-safe research tests (258 passed; 1 pre-existing package fixture fail noted)
- [x] Verify Qwen claims evidence present under `docs/research/raw/`
- [x] Annotated tag `v0.2.0-qwen30b-e2e-research` created

## Phase 1 — Disk admission (blocked)

- [x] Measure free space (APFS internal)
- [x] Inventory expected model locations
- [x] Determine remote checkpoint size (UD-IQ2_XXS = 222.082 GiB)
- [x] Safe cleanup (partial + build targets)
- [x] Write `docs/validation/glm52-disk-admission.json` → **failed**
- [ ] Re-run admission when ≥500 GiB free

## Phase 2 — Checkpoint acquisition (blocked)

- [ ] NTFY before access
- [ ] Atomic download of all shards / single file
- [ ] SHA-256 + GGUF structure validation
- [ ] `docs/validation/glm52-checkpoint.json`
- [ ] Document `PULSARMLX_GLM_GGUF`

## Phase 3 — Streaming runtime

- [ ] GGUF multi-shard / single-file positional reader
- [ ] Expert address map + compressed expert cache
- [ ] Prefetch + eviction + telemetry
- [ ] Memory budget controls
- [ ] Fail closed on full-model materialization / silent CPU fallback

## Phase 4 — Architecture contract

- [ ] Parse GGUF KV + tensor catalog
- [ ] Map MLA / DSA / MoE from upstream source revision
- [ ] Freeze `docs/architecture/GLM52_CONTRACT.md`

## Phase 5 — Correctness ladder

- [ ] GLM-C01 metadata
- [ ] GLM-C02 dense primitives
- [ ] GLM-C03 router
- [ ] GLM-C04 single expert
- [ ] GLM-C05 full MoE
- [ ] GLM-C06 MLA
- [ ] GLM-C07 DSA
- [ ] GLM-C08 layer 0
- [ ] GLM-C09 depth ladder → full
- [ ] GLM-C10 full logits
- [ ] GLM-C11 generation ≥8 tokens

## Phase 6–7 — Execution, performance, publication

- [ ] Full-model logits NTFY
- [ ] First token NTFY
- [ ] Benchmark protocol freeze + runs
- [ ] `docs/research/glm52/*` package
- [ ] `PULSARMLX_GLM52_REPORT.md`
- [ ] CI fixtures (no weights)
- [ ] Tag `v0.3.0-glm52-e2e-research` only after complete

## Stop condition

**Active**: disk admission cannot be satisfied through safe cleanup.
Do not download GLM until free ≥ 500 GiB (direct) or ≥ 700 GiB (dual-copy).
