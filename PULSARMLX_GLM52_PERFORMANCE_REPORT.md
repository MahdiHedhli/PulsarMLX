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
| P1 first new token + expert cache | **running** (`glm52_inference.py --n-new 1`) |
| Full 8-token golden match | pending P1 |
| Expert prefetch | not started |
| Published tok/s | **not claimed** |

## Configuration (defaults)

- Expert decoded cache budget: 8 GiB (P1 run)
- Storage: existing multi-shard positional pread (no mmap change yet)
- Mode: inference (cached experts) vs research (uncached)

## Limitations

- Python research runtime, not a production server
- Residual scale on long research ladders is large; quality not claimed
- ssd-llm used for design only (no runtime dependency)

## Commands

```sh
export PULSARMLX_GLM_GGUF=$HOME/Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS
.venv/bin/python scripts/research/glm52_profile_hotspots.py
.venv/bin/python scripts/research/glm52_inference.py --mode inference --n-new 1 --cache-gib 8
```
