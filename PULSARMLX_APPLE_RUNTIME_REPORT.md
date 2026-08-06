# PulsarMLX Apple Runtime Report

**Generated**: 2026-08-06  
**Repository**: https://github.com/MahdiHedhli/PulsarMLX  
**HEAD at report**: see `git rev-parse HEAD` on main (this file commits with the tip)

## Executive summary

PulsarMLX has progressed from Feature 001/002 device and **layer-0 router**
parity into **real expert execution** and **top-8 routed aggregation** on the
immutable Qwen3-30B-A3B Q8_0 checkpoint under Apple MLX 0.32.0.

| Milestone | Status |
| --- | --- |
| F001 Apple MLX + bounded Q8_0 slice | Complete (prior) |
| F002 Layer-0 router parity | Complete (verified claims F002-C01–C03) |
| F003 Single routed expert full MLP | Complete (F003-C01, expert 114) |
| F004 Top-8 aggregation | Complete (F004-C01) |
| F005+ Complete MoE residual, layers, logits, tokens | **Not started / blocked on residual stream capture** |
| GLM-5.2 | **Not admitted** |

## Feature completion

### Feature 002 — Router

- Exact top-8 IDs/order vs independent CPU oracle  
- Full 128-output metrics within frozen tolerances  
- Primary + clean-checkout reproduction  
- Evidence: `docs/research/raw/002-router-parity/`

### Feature 003 — Single expert

- Expert **114** (F002 top-8 rank-0)  
- Gate / up / SiLU-SwiGLU / down / routing-weight scale  
- Max abs error ~**7.4e-8**, 0 mismatches  
- Reproduced with matching MLX weighted hash  
- Evidence: `docs/research/raw/003-expert-mlp/`

### Feature 004 — Top-8 aggregation

- Experts **[114, 45, 99, 46, 98, 74, 102, 65]**  
- Weighted sum of full MLPs  
- Max abs error ~**6.2e-8**, 0 mismatches  
- I/O gauges: 40,108,032 bytes/pass; cold ~3.76 ms, warm ~3.28 ms wall  
- Evidence: `docs/research/raw/004-top8-moe/`

## Correctness

All MLX results compared to independent CPU oracles (no MLX imports in oracle
path for expert scripts). Tolerances: absolute 5e-4 + relative 5e-4. Zero
allowed mismatches on published passes.

## Performance / memory / I/O

- No tokens/sec or full-model load benchmark claimed.  
- F004 I/O gauges only cover expert tensor range re-reads (OS-cache
  uncontrolled).  
- Memory: process stayed within normal pressure; no thermal warnings recorded
  during admitted runs.

## GLM status

**Not started.** GLM is not supported. No GLM checkpoint identity, load,
router, experts, logits, or greedy token evidence exists.

## Limitations

- No residual-add into MoE block (need residual stream capture before
  `ffn_norm`).  
- No attention, multi-layer, logits, sampling, generation, serving.  
- No giant-model or multi-device claims.  
- Hosted CI is fixture-only; real checkpoint runs are local.

## Threats to validity

- Single-host (M1 Ultra class) results.  
- Q8_0 decode + f32 MLX matvec path may not match a fused Metal implementation.  
- OS page cache affects I/O gauges.  
- Feature 003/004 package verification is claim-file based, not yet a full
  Schema 1.2 experiment package like Feature 002.

## Future work (roadmap order)

1. **F005** Residual-aware MoE block (requires residual capture)  
2. **F006** Complete transformer layer  
3. **F007** Multi-layer replay  
4. **F008–F010** Logits → greedy token → prompt replay  
5. **F011–F012** Benchmark harness + scaling (GLM only after all succeed)

## Publication checklist

- [x] Raw evidence for F002–F004  
- [x] Claims ledgers F002–F004  
- [x] Reviewer index updates  
- [x] Focused git commits pushed to main  
- [ ] Full clean-checkout automation for F003/F004 (F003 partial; F004 single run)  
- [ ] Unified package verifier for multi-feature claims  
- [ ] Final CI attestation commit after each feature tip  

## Exact reproduction (Feature 004)

```sh
export PULSARMLX_MODEL_GGUF=/path/to/Qwen3-30B-A3B-Q8_0.gguf
# identity: size 32483931648 sha256 4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c
PYTHONPATH=scripts/research uv run python -B scripts/research/top8_aggregate.py \
  --model "$PULSARMLX_MODEL_GGUF" \
  --f002-oracle docs/research/raw/002-router-parity/oracle/f002-router-oracle-freeze-0001.json \
  --oracle-out /tmp/f004-oracle.json \
  --evidence-out /tmp/f004-parity.json \
  --source-commit "$(git rev-parse HEAD)"
```

## Feature 003 reproduction

```sh
python3 -B scripts/research/expert_oracle.py \
  --model "$PULSARMLX_MODEL_GGUF" \
  --f002-oracle docs/research/raw/002-router-parity/oracle/f002-router-oracle-freeze-0001.json \
  --expert 114 \
  --output /tmp/f003-oracle.json
PYTHONPATH=scripts/research uv run python -B scripts/research/expert_parity_mlx.py \
  --model "$PULSARMLX_MODEL_GGUF" \
  --oracle /tmp/f003-oracle.json \
  --evidence /tmp/f003-parity.json \
  --source-commit "$(git rev-parse HEAD)"
```
