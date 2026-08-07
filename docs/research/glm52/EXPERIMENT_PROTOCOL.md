# GLM-5.2 Experiment Protocol

**Feature**: `016-glm52-full-execution`
**Status**: **FROZEN** (methodology only — no measured results)
**Host class**: Apple Silicon M1 Ultra, 128 GB unified memory, **internal SSD only**
**Oracle contract**: architecture-level independent CPU vs MLX (not fused CUDA / llama bit-parity)
**Baseline frozen**: tag `v0.2.0-qwen30b-e2e-research` (Qwen path; not rewritten)

## 1. Scope

### In scope

- Admit immutable `GLM-5.2-UD-IQ2_XXS` multi-shard GGUF on internal SSD
- Streaming MLX runtime with bounded expert residency
- Correctness ladder **GLM-C01 … GLM-C11**
- MLX-only performance timing after correctness gates
- Publication package under `docs/research/glm52/`

### Out of scope (this feature)

- M2 Max testing
- External NVMe RAID
- Second quantizations or alternate downloads for convenience
- Production multi-tenant serving claims
- Llama/CUDA fused bit-parity as a success criterion
- Weakening Qwen F002–F015 evidence

## 2. Checkpoint identity (required before real-weight claims)

| Field | Value |
| --- | --- |
| Repo | `unsloth/GLM-5.2-GGUF` |
| Quant | `UD-IQ2_XXS` |
| Form | 6 shards |
| Expected total bytes | `238458632928` |
| Env | `PULSARMLX_GLM_GGUF` → directory of complete shards |

Before C01 real-weight pass:

1. All six files present
2. Exact byte sizes match frozen table
3. Per-file SHA-256 recorded
4. Checkpoint-set identity frozen in `docs/validation/glm52-checkpoint.json`
5. Free space ≥ 250 GiB after admission

**Incomplete shards must not** support claims that require full catalog identity.

## 3. Cache-state definitions

| Label | Meaning |
| --- | --- |
| `process_cold` | New process; no prior GLM mmap/expert cache in this process. OS page cache **not** controlled unless explicitly scrubbed and documented. |
| `os_cache_warm` | Same machine after prior full or partial reads; OS may retain pages. |
| `expert_census_warm` | Expert address map built; no guarantee experts are resident. |
| `model_resident_partial` | Some experts/attn tensors admitted under budget. |
| `ssd_streaming` | Misses served from internal SSD positional reads. |

A run labeled **truly cold** must document OS-cache control (or explicitly state it was **not** controlled).

## 4. Cold / warm performance definitions

| Role | Definition |
| --- | --- |
| Process-cold pilot | First generation in a fresh process after open+index; may include census. |
| Warm-up generation | Discarded for reported stats; brings expert/OS caches to steady state. |
| Measured warm | Timed after warm-up; MLX synchronized at timer end. |

Minimum practical set when cost allows:

- 1 process-cold pilot
- 1 warm-up generation
- 3 measured warm generations

If fewer measured samples: label **preliminary** and record reason.

## 5. Numerical tolerances (FROZEN before real-weight parity)

These apply to architecture CPU vs MLX unless a boundary publishes a tighter bound.

| Boundary class | Absolute | Relative | Pass rule |
| --- | ---: | ---: | --- |
| Dense F32 / RMSNorm | `5e-4` | `5e-4` | `err ≤ abs + rel·|ref|` every element |
| Dequant + matvec (IQ2/QK) | `5e-3` | `5e-3` | same; document first-max index |
| Router scores (f32 path) | `5e-4` | `5e-4` | continuous scores |
| Router expert IDs / order | exact | — | exact match |
| Residual / layer output | `5e-3` | `5e-3` | plus geometry (cos ≥ 0.999) |
| Full logits | `5e-2` | `5e-3` | top-1 exact; top-5 set optional report |
| Greedy token | exact ID | — | CPU head vs MLX agree |

**Do not loosen these after seeing results.** If a boundary fails:

1. Preserve failing evidence
2. Isolate first divergent op
3. Fix implementation or document accepted implementation-specific contract (F008-style)
4. Optionally add a **new** named contract with explicit non-claims — never silently edit this table

## 6. Geometry metrics (every layer / residual boundary)

Record for each compared vector:

- max absolute error
- mean absolute error
- RMSE
- max relative error
- cosine similarity
- norm ratio (`‖actual‖ / ‖ref‖`)
- first maximum-error index
- deterministic repeatability (two-run SHA or exact match)

## 7. Correctness ladder acceptance

| ID | Boundary | Accept when |
| --- | --- | --- |
| **C01** | Metadata + tensor catalog | All shards; offsets in range; types known or listed unsupported; arch KV consistent |
| **C02** | Dense primitives | Embedding row + RMSNorm + ≥1 dense matvec within tol vs CPU oracle |
| **C03** | Router | Exact top-k IDs/order; weights within tol; deterministic |
| **C04** | Single expert | Full gate/up/act/down/scale within tol |
| **C05** | Full MoE block | Shared + routed aggregate + residual within tol |
| **C06** | MLA | Full MLA path on real tensors within tol |
| **C07** | DSA | Indexer, top-k rows, sparse visibility, prefill+decode state OK |
| **C08** | Layer 0 complete | Attn+MoE residual within tol |
| **C09** | Depth ladder | 1,2,4,8,16,…,**79** layers; bounded error growth; stop only on real divergence |
| **C10** | Full logits | Complete vocab logits; top-1 agree; metrics recorded |
| **C11** | Generation | ≥1 greedy token; ≥4 tokens; **≥8 tokens** tokenizer-driven; deterministic replay |

Full-model support is claimed **only** after C09+C10+C11 pass.

### Depth ladder

Default: `1 → 2 → 4 → 8 → 16 → 32 → 64 → 79`
Skip a rung only if the Spec Kit plan records a justification.

## 8. Memory-pressure stop conditions

Abort the run (fail closed) if any of:

- free process headroom drops below frozen **24 GiB** minimum (configurable, default 24)
- sustained **critical** memory pressure (macOS memory_pressure or equivalent) for >30 s
- swap growth dominates step time (swap delta large and correlated with stalls)
- expert cache would exceed admitted compressed budget without eviction path
- full-model materialization attempted beyond admitted budget

Record the stop reason; do not continue and report partial success as full-model.

## 9. Fail-closed execution mode

Performance / research mode **must fail** if:

- MLX device path unavailable
- operation silently uses CPU fallback
- unsupported quant type encountered without declared handler
- expert read outside declared tensor range
- headroom below threshold

## 10. Performance protocol (after C11)

- MLX-only; CPU oracle **not** in timer path
- Synchronize MLX before stopping timers
- Internal SSD only
- Report process-cold pilot, warm-up (discarded), measured warm samples
- Metrics: open/index time, TTFT, prefill t/s, decode t/s (4/8/16 tokens if time), bytes read, cache stats, RSS/peak, swap, thermal
- Aggregate: n, median, mean, std, min, max, p25, p75, CV
- Do not compare directly to CUDA as equivalent hardware

## 11. Privacy

Committed evidence must not contain:

- username, hostname, serial, UUID, IP
- absolute home paths (use env vars / public-safe roles)
- tokens, signed URLs

## 12. Prompt freeze (C11)

| ID | Category | Text (frozen) |
| --- | --- | --- |
| P-MIN | minimal | `Hello` |
| P-FACT | short factual | `What is the capital of France?` |
| P-CODE | short code | `Write a Python function that returns 42.` |
| P-REASON | short reasoning | `If all cats are animals and some animals are black, can we conclude some cats are black? Answer yes or no and one sentence.` |

Token IDs recorded after tokenizer identity freeze (not invented here).

## 13. Sample-count rules

| Experiment cost | Minimum measured samples | Label if fewer |
| --- | ---: | --- |
| Cheap unit / synthetic | 1 + deterministic replay | — |
| Single boundary parity | 1 primary + 1 replay | — |
| Full 79-layer dual parity | 1 primary + replay SHAs | expensive OK |
| Warm generation perf | 3 | preliminary if 1–2 |
| Process-cold perf | 1 pilot | always pilot |

## 14. Change control

Any protocol change after first real-weight measurement requires:

1. New protocol version field
2. Preserved original table
3. Explicit claims ledger note
