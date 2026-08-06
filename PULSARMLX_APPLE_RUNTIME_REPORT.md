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
| F005 Complete MoE residual block (indep. MoE path) | Complete (F005-C01) |
| F007 Pre-FFN residual capture + RMSNorm link | Complete (F007-C01) |
| F006 Complete transformer layer vs llama `l_out` | **Rejected / blocked** (MoE kernel gap) |
| F008+ Multi-layer, logits, tokens, benchmarks | **Blocked on F006** |
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

### Feature 005 — Complete MoE residual block

- Form: `y = ffn_inp-0 + top-8 MoE(ffn_norm-0)`  
- Residual capture sha256 `673441ded7…832d` (two independent matches)  
- ffn_norm freeze identity retained from F002  
- RMSNorm cross-check max abs ~**8.5e-8**  
- MLX vs CPU max abs ~**6.2e-8**, 0 mismatches  
- Evidence: `docs/research/raw/005-moe-block/`

### Feature 007 — Pre-FFN residual capture

- Graph: `ffn_inp-0` = post-attention residual; `ffn_norm-0` = RMSNorm(`ffn_inp-0`)  
- Residual sha `673441ded7…832d` (2 independent captures)  
- CPU RMSNorm vs F002 freeze: max abs ≈ **8.5e-8** / **9.5e-8**, 0 mismatches  
- F002 fixture **not** regenerated  
- Evidence: `docs/research/raw/007-pre-ffn-residual/`

### Feature 006 — Layer-0 output (rejected)

- Captured `l_out-0` / `ffn_moe_out-0` from pinned llama.cpp  
- Independent F005 block vs `l_out-0`: max abs ≈ **3.43e-3**, 182 mismatches  
- Cosine F004 vs llama MoE ≈ **0.999990**  
- Llama `ffn_moe_topk` row0 IDs match F002: **[114, 45, 99, 46, 98, 74, 102, 65]**  
  (gap is expert MLP / accumulation, not routing selection)  
- Evidence retained: `docs/research/raw/006-layer-out/`  
- **No F006 verified claim.** Deepest verified remains F005.

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

- Feature 006 blocked: independent MoE vs llama fused MoE max abs ~3.4e-3.  
- No attention re-implementation on MLX, multi-layer, logits, sampling,
  generation, or serving.  
- No giant-model or multi-device claims.  
- Hosted CI is fixture-only; real checkpoint runs are local.

## Threats to validity

- Single-host (M1 Ultra class) results.  
- Q8_0 decode + f32 MLX matvec path may not match a fused Metal implementation.  
- OS page cache affects I/O gauges.  
- Feature 003/004 package verification is claim-file based, not yet a full
  Schema 1.2 experiment package like Feature 002.

## Future work (roadmap order)

1. **Unblock F006**: align independent Q8_0 MoE with llama fused `ffn_moe_out`  
2. Then F007 multi-layer → F008 logits → … → F012 scaling/GLM  

## Publication checklist

- [x] Raw evidence for F002–F005  
- [x] Claims ledgers F002–F005  
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

## Feature 005 reproduction

```sh
export PULSARMLX_MODEL_GGUF=/path/to/Qwen3-30B-A3B-Q8_0.gguf
# residual capture (optional if using published ffn_inp-0.f32le):
# ./scripts/research/capture_residual_oracle.sh --model ... --llama-source ... --work-dir ... --output-dir ...
PYTHONPATH=scripts/research uv run python -B scripts/research/moe_block_parity.py \
  --model "$PULSARMLX_MODEL_GGUF" \
  --f002-oracle docs/research/raw/002-router-parity/oracle/f002-router-oracle-freeze-0001.json \
  --residual-f32le docs/research/raw/005-moe-block/ffn_inp-0.f32le \
  --norm-f32le docs/research/raw/005-moe-block/ffn_norm-0.f32le \
  --oracle-out /tmp/f005-oracle.json \
  --evidence-out /tmp/f005-parity.json \
  --source-commit "$(git rev-parse HEAD)"
```

## Continuation instructions (post-F006 blocker)

Deepest verified boundary: **Feature 005** residual MoE block
(`y = ffn_inp + independent top-8 MoE(ffn_norm)`).

### Unblock Feature 006

1. Diff independent Q8_0 expert matvec / SwiGLU / weight application against
   llama.cpp fused `build_moe_ffn` for expert 114 alone using captured
   `ffn_moe_out` contribution isolation if available.
2. Check expert tensor layout (row-major vs packed), Q8_0 block decode, and
   whether llama accumulates expert outputs in f16/f32 differently.
3. Do **not** loosen 5e-4 tolerances or replace the independent oracle with
   llama outputs without a new admitted contract.
4. When max abs vs `ffn_moe_out-0` is within frozen tolerances, re-run residual
   add and `l_out-0` parity; only then open F007 multi-layer.

### Reproduction of rejection

```sh
# published captures under docs/research/raw/006-layer-out/
python3 -c "import json; print(json.load(open('docs/research/raw/006-layer-out/f006-layer-out-parity-0001.json'))['comparison_f004_agg_vs_llama_ffn_moe_out'])"
```

### GLM

Not admitted. No attempt until F006–F011 succeed on admitted Qwen checkpoints.
