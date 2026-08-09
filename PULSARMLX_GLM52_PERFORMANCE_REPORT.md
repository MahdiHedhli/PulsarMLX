# PulsarMLX GLM-5.2 performance report (in progress)

**Status**: living document for the weekend optimization sprint  
**Golden tag**: `v0.3.0-glm52-e2e-research`  
**Golden sequence**: `[9703, 21615, 220, 16, 13, 16, 16, 15, 15]`  
**Correctness rule**: optimized path must match golden before throughput claims

## Baseline research path (committed)

| Metric | Value | Evidence |
| --- | --- | --- |
| C11 wall (8 new tokens) | **48730.7 s** (~13.5 h) | `docs/research/glm52/raw/f016-c11-generation-0001.json` |
| Typical decode stack | ~**5335 s** | C11 log means |
| Logits (full vocab) | ~**79 s** | C11 log / C10 |

### Hotspot probe (layer 3, token 9703)

| Block | seconds |
| --- | ---: |
| moe_top8_plus_shared | ~50.8 |
| mla_layer3_pos0 | ~18.9 |
| shared_expert | ~10.0 |
| single_routed_expert | ~5.0 |
| router | ~0.06 |
| embed | ~0.01 |

Raw: `docs/research/glm52/raw/f016-hotspot-profile-0001.json`  
Narrative: `docs/research/glm52/HOTSPOT_REPORT.md`

**Primary cost**: expert dequant + SwiGLU matvec (×8 routed + 1 shared) per MoE layer × 76 MoE layers × tokens.

## MLX-only / cached path

| Milestone | Status |
| --- | --- |
| P1 first new token + expert cache | **golden prefix matched** — token `21615`; 15146.448 s |
| P2 two-token golden + useful reuse | pending cache diagnosis |
| Full 8-token golden match | blocked on P2 correctness + reuse |
| Expert prefetch | not started |
| Published tok/s | **not claimed** |

### Recovered P1 result

The original post-run JSON was recovered byte-for-byte after the reboot at
`docs/research/glm52/raw/f016-inference-p1-token1.json` (667 bytes, SHA-256
`b62c3062adc21498e1af19111202ac4a976aaa48106e7de7852f78280b8b2bfb`).
It records the exact sequence `[9703, 21615]`, matching the frozen first-token
golden prefix, with 15146.448245750013 seconds total wall time:

| Phase | Seconds |
| --- | ---: |
| Prompt-token stack | 6850.770356416004 |
| First-token logits | 92.97717149998061 |
| Generated-token stack | 8202.700665666023 |

The decoded expert cache recorded 0 hits, 4104 misses, 3934 evictions, and
8556380160 resident bytes. This proves the optimized path crossed its first
token-ID correctness gate, but it is not a performance success: the second
full stack pass also had no cache hit. The recovered legacy record does not
embed a schema identifier, checkpoint set hash, or execution commit. Its
checkpoint and source provenance therefore remain contextual rather than
self-contained, and no throughput or full-golden claim is promoted from P1.

## Configuration (defaults)

- Expert decoded cache budget: 8 GiB (P1 run)
- Storage: existing multi-shard positional pread (no mmap change yet)
- Mode: inference (cached experts) vs research (uncached)
- P1 cache representation: decoded Python f32 rows, one cache entry per
  `tensor_name#expert_id`

## Limitations

- Python research runtime, not a production server
- Residual scale on long research ladders is large; quality not claimed
- ssd-llm used for design only (no runtime dependency)
- P1 did not retain routing IDs, storage/dequant timing, bytes read, RSS, or a
  source/checkpoint identity inside the result; the cache redesign must add
  these fields before P2

## Commands

```sh
export PULSARMLX_GLM_GGUF=$HOME/Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS
.venv/bin/python scripts/research/glm52_profile_hotspots.py
.venv/bin/python scripts/research/glm52_inference.py --mode inference --n-new 1 --cache-gib 8
```
