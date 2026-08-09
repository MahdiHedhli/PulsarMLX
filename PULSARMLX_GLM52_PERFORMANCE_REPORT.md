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
| P2 two-token golden + useful reuse | paused in stack 1; decoder ladder now precedes retry |
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

### Cache-thrash diagnosis

The committed catalog and a committed 76-layer C09 routing trace drive the
checkpoint-free simulator at
`scripts/research/glm52_cache_simulator.py`. Its deterministic output is
`docs/research/glm52/raw/f016-cache-simulation-0001.json`. The trace is replayed
identically to isolate policy mechanics; P1 did not retain its own routed
expert IDs, so routed-expert overlap is not claimed.

| Quantity | Exact value |
| --- | ---: |
| Cache key | `tensor_name#expert_id` |
| Entries per full MoE stack | 2052 |
| Decoded bytes per tensor slab | 50331648 (48 MiB) |
| Decoded bytes per complete expert | 150994944 (144 MiB) |
| Decoded stack working set | 103280541696 (96.1875 GiB) |
| Compressed stack working set | 9070411776 (~8.4475 GiB) |
| Shared-expert decoded set | 11475615744 (10.6875 GiB) |
| Shared-expert compressed set | 2105769984 (~1.9612 GiB) |
| 8 GiB decoded capacity | 170 slabs (56 complete experts + 2 slabs) |

The legacy cache stores gate, up, and down as independent decoded Python-f32
row-list entries. It is created once per `generate` call and is not reset
between tokens. P1 performed exactly two 2052-access stacks; 4104 misses minus
3934 evictions equals the 170 resident entries, so the counters reconcile and
the second stack was not merely cold-start accounting. For an identical
sequential replay, each key's LRU stack distance is 2051 entries. Every tested
decoded-LRU budget from 8 through 48 GiB is smaller than the 96.1875 GiB set
and therefore produces zero warm decoded hits. This is classical cyclic LRU
thrash, not a router bottleneck or per-token cache reset.

The simulator separates storage and decode reuse:

| Policy | Budget | Warm storage hits | Warm decoded hits | Redequants |
| --- | ---: | ---: | ---: | ---: |
| decoded global LRU | 8–48 GiB | 0 | 0 | 2052 |
| compressed global LRU | 8 GiB | 0 | 0 | 2052 |
| compressed global LRU | 16–48 GiB | 2052 | 0 | 2052 |
| decoded shared-only | 8 GiB | 170 | 170 | 1882 |
| decoded shared-only | 16–48 GiB | 228 | 228 | 1824 |

The implemented P2 design is a protected decoded shared-expert tier:
shared experts execute at every MoE layer, so their reuse is guaranteed without
predicting routed experts. A logical 16 GiB budget contains all 228 shared
slabs and avoids their redequantization on the next token. The P2 runtime now
decodes into compact f32 storage, builds and synchronizes an MLX matrix, retains
only shared matrices, and releases each non-resident routed matrix after
synchronized use. It fails closed on MLX errors and records current/peak RSS
plus separate storage, decode, matrix-build, matvec, reuse, and transient-release
counters. These are model-free implementation facts; useful real-checkpoint
reuse remains unverified until P2. A compressed tier remains a later measured
storage experiment because its hits do not avoid dequantization.

## Configuration (defaults)

- Expert decoded cache budget: 8 GiB (legacy P1); 16 GiB (P2 protocol)
- Storage: existing multi-shard positional pread (no mmap change yet)
- Mode: inference (cached experts) vs research (uncached)
- P1 cache representation: decoded Python f32 rows, one cache entry per
  `tensor_name#expert_id`
- P2 policy: compact evaluated MLX/f32 shared-expert protection; 16 GiB logical
  cap, routed-matrix transient release, live memory admission, and RSS evidence

### Superseded P2 attempt

The first P2 attempt at source commit `a34964e` was gracefully interrupted at
46m15s while still inside its first full stack. No stack checkpoint, generated
token, parity result, or reuse result existed. Current RSS was 18112118784 bytes
and system memory remained 97% free. The retained record is
`docs/research/glm52/raw/f016-inference-p2-superseded-0001.json`.

The stop was caused by experiment reprioritization, not a correctness or memory
failure. The interrupt traceback landed in scalar IQ2_XXS dequantization while
loading a routed up-projection. Source review shows nested Python scalar loops,
row-by-row reads, and Python-float materialization before MLX construction. A
whole-matrix vectorized decoder correctness/performance ladder therefore runs
before another P2 attempt. The cache implementation and diagnosis remain
preserved; their real two-token benefit is still unverified.

### Revised experiment order

1. exact-f32-bit NumPy IQ2_XXS qualification on synthetic blocks, real rows,
   and complete real expert matrices;
2. one positional matrix read, one contiguous vector decode, one evaluated MLX
   matrix, and the existing MLX matvec behind an explicit decoder mode;
3. decode, real matrix, routed expert, layer-3 MoE, layer, then P1 benchmarks;
4. mixed-quant hotspot ranking by measured golden-trace time;
5. dedicated bit-exact Rust f32 boundary design;
6. cache re-evaluation, then P2 retry.

The bounded ladder has now passed through the complete layer rung. P1 remains
the next required boundary; no new P2 is eligible until that clean full-stack
result and its revised mixed-quant hotspot inventory are committed.

### Qualified IQ2_XXS decode boundary

Source commit `968cfac` passed the clean-worktree Tier-3 qualification on the
M1 Ultra with NumPy 2.4.5. Four complete `2048 × 6144` gate matrices selected
from layers 3, 20, 40, and 60 spanned checkpoint shards 2–5. Every matrix and
the three sampled rows per matrix matched the unchanged scalar decoder at the
exact f32 `uint32` bit pattern, with zero mismatches and deterministic repeat
hashes. The synthetic suite separately retained signed-zero coverage.

For the layer-3 matrix (12,582,912 weights), after three warmups per mode and
ten retained measurements per mode:

| Decoder | Median seconds | Mean seconds | Sample stddev | Median weights/s |
| --- | ---: | ---: | ---: | ---: |
| scalar reference | 1.424142 | 1.425866 | 0.007503 | 8,835,434 |
| NumPy vectorized | 0.050588 | 0.051395 | 0.002059 | 248,733,448 |

The median decoder-only speedup was **28.15×**. Instrumented vector decode
reported a 363,726,280-byte traced peak and a 16,826,368-byte RSS increase from
its post-benchmark baseline while producing a 50,331,648-byte contiguous f32
matrix. Process peak RSS was 2,335,965,184 bytes; this includes prior scalar
reference allocations and must not be interpreted as the vector decoder's
standalone working set.

Raw samples, matrix hashes, allocation observations, and exact environment are
in `docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json`. The
result verifies only decode correctness and throughput. It does not establish
a routed-expert, MoE, layer, P1, P2, or token-generation speedup.

### Real matrix load/build/matvec boundary

At source `d8af70b`, the explicit vector mode executed the frozen layer-3
expert-15 gate matrix through one complete 3,244,032-byte positional read,
whole-matrix decode, contiguous f32 handoff, synchronized MLX GPU matrix build,
and MLX matvec. The scalar reference used 2,048 row reads. Ten counterbalanced
measured samples per mode followed three warmups per mode.

| Component (median) | scalar reference | NumPy vectorized |
| --- | ---: | ---: |
| storage read | 0.001586 s | 0.000546 s |
| dequantization | 1.132615 s | 0.080100 s |
| contiguous buffer | 0.245952 s | 0.000090 s |
| MLX matrix build/eval | 0.006688 s | 0.005179 s |
| MLX matvec | 0.006087 s | 0.004780 s |
| total before cleanup | 1.393479 s | 0.090525 s |
| total with cleanup | 1.396795 s | 0.093871 s |

The synchronized output contained 2,048 f32 values with zero bit-pattern
mismatches between modes and deterministic hashes across every measured run.
The median total-before-cleanup improvement was **15.39×**. The separately
retained process-first vector observation was 0.097841 s, but OS page cache was
not purged, so it is not described as controlled cold latency. Raw evidence:
`docs/research/glm52/raw/f016-matrix-boundary-0001.json`.

This is a complete real matrix boundary, not a complete routed expert: gate,
up, activation, down, and weighting are measured together only at the next
ladder rung.

### Complete real routed expert

At source `bbbbaae`, the frozen layer-3 expert 15 executed gate and up in
IQ2_XXS, SwiGLU, the IQ3_XXS down projection, and its architecture-normalized
route weight. The independent scalar CPU oracle ran twice with identical f32
hashes. The vectorized MLX result passed the frozen `5e-3 + 5e-3·|reference|`
tolerance with zero mismatches, 4.37e-11 maximum absolute error, and cosine
similarity above 0.9999999999999. Scalar-reference and vectorized MLX outputs
were bit-identical and deterministic across all ten measured samples.

| Component (median) | scalar reference | NumPy vectorized |
| --- | ---: | ---: |
| storage read | 0.007312 s | 0.004877 s |
| dequantization | 3.557103 s | 1.406925 s |
| contiguous buffer | 0.741363 s | 0.246274 s |
| MLX matrix build/eval | 0.021867 s | 0.018218 s |
| MLX matvec | 0.024966 s | 0.017280 s |
| total | 4.365715 s | 1.706290 s |

Median complete-expert improvement was **2.56×**. Per-quant timing shows the
remaining vector-path cost is now dominated by the scalar IQ3_XXS down
projection: in a representative measured sample it used about 1.28 s dequant
plus 0.245 s buffer construction, while both IQ2_XXS matrices together used
about 0.126 s dequant and negligible buffer time. This measured single-expert
inventory motivates later mixed-quant ranking but does not authorize changing
the ladder order or claiming top-8 MoE/token performance. Raw evidence:
`docs/research/glm52/raw/f016-routed-expert-0001.json`.

### Layer-3 top-8 plus shared MoE

At source `c2337db`, the complete layer-3 MoE boundary passed with the exact
golden top-8 IDs and architecture-normalized weights, eight routed experts,
shared expert 0, aggregation, and residual addition. Two 49-second independent
CPU-oracle passes had identical output hashes. The vector MLX result had zero
tolerance mismatches, 3.73e-9 maximum absolute error, cosine similarity above
0.999999999999999, and exact deterministic bits against scalar-reference MLX.

After three warmups populated the three protected shared matrices, ten measured
samples per mode each recorded three shared-cache hits, 24 routed misses, and
27 synchronized MLX matvecs:

| Component (warm median) | scalar reference | NumPy vectorized |
| --- | ---: | ---: |
| storage read | 0.065709 s | 0.041934 s |
| dequantization | 29.580994 s | 11.561970 s |
| contiguous buffer | 6.126871 s | 2.040321 s |
| MLX matrix build/eval | 0.163397 s | 0.135225 s |
| MLX matvec | 0.222778 s | 0.133762 s |
| router/aggregation/cleanup remainder | 0.158726 s | 0.150191 s |
| total | 36.309373 s | 14.062472 s |

Median warm-MoE improvement was **2.58×**. The separately retained
process-first vector sample was 23.172902 seconds with zero cache hits and all
three shared matrices loaded; the 9.11-second difference from the warm median
is an observed same-process shared-residency effect, not controlled cold-file
latency. Raw evidence: `docs/research/glm52/raw/f016-moe-layer3-0001.json`.

This boundary excludes attention and therefore is not a complete transformer
layer or token-generation result.

### Complete transformer layer 3

At source `a78bc46`, the complete position-0 layer-3 boundary executed MLA/DSA
attention, the frozen post-attention top-8 plus shared MoE, and both residual
updates. Two architecture-reference executions repeated exactly at the frozen
attention-midpoint hash and route
`[15,177,233,41,166,26,10,152]`. The reference comparison had zero tolerance
mismatches and 3.73e-9 maximum absolute error. Both MLX decoder modes produced
exactly equal deterministic f32 bits across ten measured samples.

The architecture reference is intentionally not called an independent CPU
oracle for complete attention because its dense helper may use the shared MLX
reference path; independent scalar correctness remains established for the
preceding complete-MoE rung.

| Component (warm median) | scalar reference | NumPy vectorized |
| --- | ---: | ---: |
| attention | 18.012330 s | 18.002312 s |
| MoE | 35.210090 s | 13.648985 s |
| storage read | 0.058493 s | 0.037860 s |
| dequantization | 28.635887 s | 11.198760 s |
| contiguous buffer | 5.957976 s | 1.990166 s |
| MLX matrix build/eval | 0.162626 s | 0.134045 s |
| MLX matvec | 0.213846 s | 0.135787 s |
| total | 53.230274 s | 31.687686 s |

Median warm complete-layer improvement was **1.68×**. Attention was unchanged,
as expected; the improvement is confined to the expert decoder boundary. The
process-first vector observation was 40.498847 seconds with zero shared-cache
hits; measured observations reused all three shared matrices. Peak process RSS
was 7,076,659,200 bytes and memory pressure remained normal. Raw evidence:
`docs/research/glm52/raw/f016-layer3-0001.json`.

This is one complete layer, not a full 79-layer stack, first-token latency, or
token-generation throughput result.

## Limitations

- Python research runtime, not a production server
- Residual scale on long research ladders is large; quality not claimed
- ssd-llm used for design only (no runtime dependency)
- P1 did not retain routing IDs, storage/dequant timing, bytes read, RSS, or a
  source/checkpoint identity inside the result; P2 uses a new self-contained
  evidence schema and is not merged with the legacy P1 record

## Commands

```sh
export PULSARMLX_GLM_GGUF=/path/to/final/GLM-5.2-UD-IQ2_XXS
uv run --frozen python scripts/research/qualify_iq2_xxs_numpy.py \
  --output docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json
# P2 remains blocked until the intervening benchmark ladder through P1 passes.
uv run --frozen python scripts/research/glm52_inference.py --mode inference \
  --n-new 2 --cache-gib 16 --cache-policy decoded_shared_only \
  --out docs/research/glm52/raw/f016-inference-p2-token2.json
```
