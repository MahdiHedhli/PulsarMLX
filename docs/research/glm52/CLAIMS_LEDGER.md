# Claims ledger — Feature 016 GLM-5.2

| Claim ID | Claim | Evidence | source_commit | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| F016-C00 | Qwen e2e research baseline frozen | tag `v0.2.0-qwen30b-e2e-research` | 493234a | verified | Full Qwen stack; no tok/s claim |
| F016-C01a | Disk admission passed after space clearance | `docs/validation/glm52-disk-admission.json` | 1919ffe | verified | ≥500 GiB free; projected ≥250 after |
| F016-C01b | Experiment protocol + tolerances frozen before real-weight parity | `EXPERIMENT_PROTOCOL.md`, `raw/f016-tolerances-frozen-0001.json` | fb695e3 / 855fe33 | verified | Methodology only |
| F016-C01c | glm-dsa KV dims + upstream map frozen | `docs/architecture/GLM52_CONTRACT.md` | fb695e3+ | verified | C01 catalog complete; MLA names filled |
| F016-C01d | Checkpoint-free CI suite (cache, telemetry, router, IQ2, harness) | `scripts/research/tests/test_glm52_checkpoint_free.py` | f977a54+ | verified | 25 passed |
| F016-C01e | Frozen C11 prompt texts + token IDs (local tokenizer extract) | `raw/f016-frozen-prompts-0001.json` | 855fe33 | verified | IDs from GGUF GPT2/glm4 tables; extract not committed |
| F016-C01 | Complete multi-shard catalog (1809 tensors, 0 bad offsets) | `raw/f016-c01-catalog-0001.json` | c32fedb | verified | Full checkpoint identity |
| F016-C02 | Dense embd/RMSNorm/matvec finite + repeatable | `raw/f016-c02-dense-0001.json` | c32fedb | verified | |
| F016-C03 | Real router top-8 deterministic (layer 3) | `raw/f016-c03-router-0001.json` | e8f6cca | verified | Probe activation |
| F016-C04 | Single real expert + shexp SwiGLU bit-exact | `raw/f016-c04-expert-0001.json` | e9cffe2 | verified | |
| F016-C05 | Top-8+shared MoE aggregate repeatable | `raw/f016-c05-moe-0001.json` | e9cffe2 | verified | Mode-0 scale refined after |
| F016-C06 | Layer-0 MLA single-token finite + repeatable | `raw/f016-c06-mla-0001.json` | 83014ce | verified | Compact-KV path |
| F016-C07 | DSA policy + indexer loads + short-ctx range-fill | `raw/f016-c07-dsa-0001.json` | 83014ce | verified | Long-ctx top-k not claimed |
| F016-C08 | Complete layer-0 residual block | `raw/f016-c08-layer0-0001.json` | 83014ce | verified | |
| F016-C09 | Single-token 79-layer depth ladder finite | `raw/f016-c09-depth-0001.json` | — | verified | ~5511s; residual L2 grows; architecture path only |
| F016-C10 | Full vocab logits after 79-layer residual | `raw/f016-c10-logits-0001.json` | — | verified | finite; argmax 4766; bit-exact repeat; not quality claim |
| F016-C11 | Tokenizer-driven greedy generation ≥8 tokens | — | — | in progress | Background full-stack path |
| F016-PERF | MLX-only performance on M1 Ultra SSD | — | — | unsupported | After C11 |

## Rejected / blocked (historical)

| Claim | Status | Notes |
| --- | --- | --- |
| Disk admission 2026-08-07 first attempt | rejected | ~346 GiB free; shortfall ~154 GiB |

## Explicit non-claims

- GLM-5.2 full-model support
- Production tokens/sec
- CUDA equivalence
- M2 Max / RAID results
