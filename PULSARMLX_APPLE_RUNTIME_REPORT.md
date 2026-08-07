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
| F006 Layer-0 vs llama bit-parity | **Rejected** (preserved); architecture oracle = F005 |
| F008 F006 root cause (Q8_0×Q8_0 vs f32 dequant) | **Complete (F008-C01)** |
| F009 Layer-0 attention → ffn_inp | **Complete (F009-C01/C02)** |
| F010 Complete layer-0 (attn+MoE) | **Complete (F010-C01)** |
| F011 Multi-layer stack (1…48 full model) | **Complete (F011-C01/C02)** |
| F012 Full logits | **Complete (F012-C01)** |
| F013 First greedy token | **Complete (F013-C01)** token **320** |
| F014 Bounded short-prompt generation | **Complete (F014-C01)** seq `[0,1,320,16]` |
| F015 Reproducible wall-clock benchmarks | **Complete (F015-C01)** (not tok/s) |
| Larger checkpoints / GLM-5.2 | **Not admitted** (Qwen green first) |

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

### Feature 006 — Layer-0 / llama bit-parity

- Llama bit-parity **rejected** (evidence preserved).  
- Architecture-level layer-0 MoE residual **verified** as F005.  
- Root cause: Feature 008.

### Feature 008 — F006 root cause

- Pairwise: A≈B ~**6e-8**; B≠C ~**3.4e-3** (cosine ~0.99999).  
- First diverge: expert **gate/up** Q8_0 matvec (not routing, not residual).  
- llama: F32 act → **Q8_0 requant** → Q8_0×Q8_0 dots  
  (`type_traits_cpu[Q8_0].vec_dot_type = Q8_0`).  
- Independent oracle / PulsarMLX: **f32 dequant weights × f32 act**.  
- Q8_0×Q8_0 reproduction matches llama expert 114 within ~**2e-7**.  
- Contract **B**: keep architecture oracle; do not claim llama bit-parity.  
- Evidence: `docs/research/raw/008-f006-root-cause/`

### Feature 009 — Layer-0 attention

- Qwen3MoE: GQA 32/4, head_dim 128, NeoX RoPE θ=1e6, per-head q/k RMSNorm.  
- Graph: `attn_norm → QKV → q/k norm → rope_ext NEOX → attn → Wo → + residual = ffn_inp`.  
- MLX vs architecture CPU: max_abs ≈ **1.1e-7**, cos ≈ 1.0.  
- vs frozen llama `ffn_inp-0`: max_abs ≈ **2.4e-3** (secondary Q8 act drift; F008 contract B).  
- Evidence: `docs/research/raw/009-layer0-attention/`

### Feature 010 — Complete layer-0

- Full layer: architecture attention + MoE residual.  
- MLX vs CPU max_abs ≈ **1.1e-7**; top-8 experts match F004/F005.  
- Evidence: `docs/research/raw/010-011-layer-stack/f010-complete-layer0-0001.json`

### Feature 011 — Multi-layer / full model

- Depth ladder **1 → 2 → 4 → 8 → 16 → 48** all passed under architecture oracle.  
- Per-layer drift metrics (max_abs, mean, RMSE, cos, norm_ratio, first max index).  
- Peak MLX–CPU max_abs ≈ **4.3e-4** (L3); final L47 ≈ **1.8e-4**; no unbounded growth.  
- Evidence: `docs/research/raw/010-011-layer-stack/`

### Feature 012–013 — Logits + greedy token

- 48-layer residual + `output_norm` + Q8_0 `output.weight` logits.  
- Logits max_abs ≈ **7.6e-6**; top-1/top-5 agree.  
- Greedy token **320** (CPU = MLX).  
- Evidence: `docs/research/raw/012-013-logits-greedy/`

### Feature 014 — Short-prompt generation

- Greedy extend 2 tokens from `[0,1]` → **`[320, 16]`**; full seq `[0,1,320,16]`.  
- Per-step CPU head agree; final dual residual check passed; first-token repeatable.  
- Evidence: `docs/research/raw/014-short-prompt-gen/`

### Feature 015 — Reproducible benchmarks

- Wall-clock dual stack depth-48 ≈ **962 s**; research path only.  
- **Does not claim tokens/sec.**  
- Evidence: `docs/research/raw/015-benchmark/`

## Correctness

All MLX results compared to independent CPU oracles (architecture path:
Q8_0 weight dequant × f32 activation). Tolerances: absolute 5e-4 + relative
5e-4. Llama Q8_0×Q8_0 bit-parity is **not** the contract (F008).

## Performance / memory / I/O

- No tokens/sec or production throughput claimed.  
- Research-path wall times published under F015.  
- Memory: process stayed within normal pressure on dual 48-layer runs.

## GLM status

**Not admitted.** Smaller-model (Qwen3-30B-A3B-Q8_0) correctness is green
through generation. GLM-5.2 remains out of scope until an explicit scaling
feature admits a GLM checkpoint identity.

## Limitations

- Research dual CPU+MLX path is not an optimized KV-cache serving runtime.  
- No sampling; greedy argmax only.  
- No larger checkpoints admitted yet.  
- Hosted CI is fixture-only; real checkpoint runs are local.  
- Llama fused Q8×Q8 path intentionally not matched (F006/F008).

## Threats to validity

- Single-host (Apple Silicon) results.  
- Q8_0 decode + f32 MLX matvec may not match a fused Metal kernel.  
- Multi-layer MLX–CPU error plateaus ~4e-4 (within tol) — accumulation, not
  structural routing break in admitted runs.  
- Generation dual-check is expensive without KV cache.

## Future work (roadmap order)

1. Progressively larger admitted Qwen checkpoints (same architecture oracle).  
2. KV-cache / optimized generation path (still architecture-correct).  
3. GLM-5.2 **only after** smaller-model green remains.  

## Publication checklist

- [x] Raw evidence for F002–F005, F007–F015  
- [x] Claims ledgers F002–F005, F007–F015  
- [x] Architecture full-model stack + logits + greedy + short gen  
- [x] Focused git commits pushed to main  
- [ ] Full clean-checkout automation for F003/F004 (F003 partial; F004 single run)  
- [ ] Unified package verifier for multi-feature claims  
- [ ] Optimized serving / tok/s (not claimed)  

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

## Continuation instructions

Deepest verified boundary: **full 48-layer architecture stack + logits +
greedy token + bounded 2-token generation** on Qwen3-30B-A3B-Q8_0.

### Next roadmap

1. Larger admitted checkpoints (same contract).  
2. KV-cache generation + real short text prompts (tokenizer).  
3. GLM-5.2 only after smaller-model remains green.  

### Reproduction of rejection (F006 llama bit-parity)

```sh
# published captures under docs/research/raw/006-layer-out/
python3 -c "import json; print(json.load(open('docs/research/raw/006-layer-out/f006-layer-out-parity-0001.json'))['comparison_f004_agg_vs_llama_ffn_moe_out'])"
```

### GLM

Not admitted. Qwen full-model architecture path is green; GLM requires a
separate admitted checkpoint program.
