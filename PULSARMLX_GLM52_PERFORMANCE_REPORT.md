# PulsarMLX GLM-5.2 performance report (closeout in progress)

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
| vectorized P1 rerun | **golden prefix matched** — token `21615`; 6294.015 s; 228 decoded hits |
| vectorized P1 after IQ3_XXS | **golden prefix matched** — 4582.511 s; 228 decoded hits |
| P2 two-token golden + useful reuse | **passed** — exact prefix; 6552.475 s; 456 decoded hits |
| Full 8-token golden match | **passed** — exact sequence; 18522.659 s; 1824 decoded hits |
| Expert prefetch | pending evidence-backed decision; storage is not assumed dominant |
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
counters. P2 and golden-eight subsequently verified 228 shared hits in every
warm stack, with zero eviction or CPU fallback. A compressed tier remains a
later measured storage experiment because its hits do not avoid
dequantization.

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
preserved; the later P2 and golden-eight records verify their real-checkpoint
reuse separately.

### Revised experiment order

1. exact-f32-bit NumPy IQ2_XXS qualification on synthetic blocks, real rows,
   and complete real expert matrices;
2. one positional matrix read, one contiguous vector decode, one evaluated MLX
   matrix, and the existing MLX matvec behind an explicit decoder mode;
3. decode, real matrix, routed expert, layer-3 MoE, layer, then P1 benchmarks;
4. mixed-quant hotspot ranking by measured golden-trace time;
5. dedicated bit-exact Rust f32 boundary design;
6. cache re-evaluation, then P2 retry.

The bounded ladder passed through P1, P2, and the frozen golden-eight gate.
Closeout analysis now separates expert-cache per-quant timing from the
uninstrumented trunk before any new decoder, prefetch, or Metal target is
selected.

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

### Vectorized P1 full-stack pilot

At clean source `2de160f`, explicit `numpy_vectorized` mode executed both
79-layer stacks and reproduced `[9703,21615]` exactly on MLX GPU with zero CPU
fallbacks. Total wall time was 6294.014912 seconds versus 15146.448246 seconds
for the recovered legacy cross-commit observation (2.41× lower wall time, not a
controlled benchmark population). Cold prompt and shared-warm generated-token
stacks took 3446.820720 and 2769.003203 seconds. The warm stack recorded 228
decoded shared-cache hits, zero evictions, 2,105,769,984 storage bytes avoided,
and 11,475,615,744 decoded bytes avoided. Peak RSS was 82,768,297,984 bytes;
every resource sample remained normal.

This is one P1 pilot and does not itself establish P2 correctness,
golden-eight generation, steady-state throughput, or a controlled cold/warm
population. Later records establish the first two gates separately. Raw evidence:
`docs/research/glm52/raw/f016-inference-p1-vectorized-0001.json`.

### Frozen golden-eight and derived closeout profile

At clean source `1a2ca76`, the exact frozen sequence
`[9703,21615,220,16,13,16,16,15,15]` passed across one cold prompt stack and
eight warm generated-token stacks. The complete evidence wall was 18522.659
seconds; the recorded time-to-first-token component sum was 2646.650 seconds.
Warm stack time had median 1921.882 seconds, mean 1916.364 seconds, sample
standard deviation 12.887 seconds, and range 1892.662–1928.536 seconds. The
last 1928.536-second stack advances terminal model state after token eight was
already selected, so it is reported separately from user-visible completion.

The run retained 1,824 shared-cache hits, avoided 16,846,159,872 compressed
bytes and 91,804,925,952 decoded bytes, and recorded no evictions, admission
rejections, or CPU fallbacks. All retained resource samples were normal.

A passive watcher preserved eight distinct complete snapshots and observed no
cumulative-counter reset. Seven one-stack intervals (generated tokens 2–8)
were valid for subtraction. Earlier overwritten snapshots were not recreated,
so cold per-quant attribution is unavailable. The warm per-quant ranking is
**EXPERT-CACHE PATH ONLY**: IQ2_XXS led at 69.672 mean component-seconds and
IQ3_XXS followed at 50.304; Q6_K contributed only 0.378 because protected
shared matrices were resident.

Warm expert-cache storage averaged 3.872 seconds, only 0.20% of mean stack
wall, so prefetch/storage implementation is deferred. By contrast, the warm
uninstrumented residual had a 1675.492-second median and 87.18% median fraction.
It is not a direct trunk or cleanup measurement. This prevents selecting the first direct-quantized Metal kernel from
expert-only quantization counters. Representative M2 Max fixtures must first
attribute MLA/attention projections, dense transforms, embeddings if material,
final norm/output projection, and any Q6_K tensors on those paths.

Historical walls below are cross-commit observations with different scopes,
not a controlled same-binary population and not a tokens-per-second estimate:

| Boundary | Recorded wall seconds | Scope |
| --- | ---: | --- |
| Research C11 | ~48730.7 | eight-token research generation baseline |
| Legacy P1 | 15146.448 | recovered one-token prefix observation |
| Vectorized P1 | 4582.511 | IQ2_XXS + IQ3_XXS, one-token prefix |
| P2 | 6552.475 | two-token prefix, three stacks |
| Golden eight | 18522.659 | exact eight-token continuation, nine stacks |

Raw evidence: `docs/research/glm52/raw/f016-inference-golden8-iq3-0001.json`
and `docs/research/glm52/raw/f016-golden8-derived-profile-0001.json`. Generated
table: `docs/research/glm52/tables/f016-golden8-derived-profile.md`.

### Post-Feature-016 bounded trunk optimization

The isolated M1 Ultra study first changed only read granularity. Whole-matrix
reads collapsed representative positional-read counts by 6,144x–16,384x while
keeping scalar decoder arithmetic unchanged, but median boundary walls changed
between -0.445% and +0.608%. Storage calls were not the material warm cost.

Inventory-driven exact-bit NumPy decoder qualification then measured Q5_K at
31.25x and Q8_0 at 75.76x decode-only. Q6_K matched scalar f32 bits for every
exercised trunk tensor and measured 42.98x on the bounded layer-8 Q-A decode.
Integrated complete MLA boundaries remained exact: layer-3 Q5_K/Q8_0 work fell
to 0.769746 s after head-slab vectorization, and layer-8 MLA fell from
55.137022 s to 1.762948 s after Q6_K integration. One complete layer-8 median
fell from 97.071291 s to 44.266072 s while retaining exact output and routes.

At clean source `9b6ab666`, the admitted exact P1 reproduced `[9703,21615]` on
MLX GPU with zero CPU fallbacks, zero evictions, and normal resource state:

| P1 boundary | Seconds |
| --- | ---: |
| Total evidence wall | 1425.756125 |
| Cold prompt stack | 1021.931135 |
| Full-vocabulary logits | 87.007223 |
| First-token selection component boundary | 1108.938358 |
| Wall-minus-terminal selection upper bound | 1108.997454 |
| Retained terminal state-advance stack | 316.758671 |

The terminal stack occurs after token `21615` has already been selected and is
not user-visible first-token selection latency. The warm stack recorded 228
shared-cache hits, 2,105,769,984 compressed bytes avoided, 11,475,615,744
decoded bytes avoided, and 69,699,502,080 bytes maximum retained peak RSS.

Warm expert-cache attribution totaled 248.615785 seconds: 9.655801 storage,
203.329484 decode, 18.102678 buffer, 9.215110 MLX build/evaluation, and 8.312711
matvec. Another 68.142886 seconds remains explicitly uninstrumented, and logits
are separate. Storage prefetch remains deferred. The combined per-quant table
ranks Q6_K first, but it combines cold and warm; it cannot select a warm-path
Metal kernel because shared Q6_K matrices were resident and the P1 schema lacks
per-stack quant deltas. Feature 018 therefore remains profile-neutral.

The P1 is one clean-process correctness run, not a timing population. Its lower
wall than legacy and earlier vectorized P1 observations is a cross-commit
observation, not a controlled same-binary comparison or a tokens-per-second
claim. Raw and derived evidence:
`docs/research/glm52/raw/post-f016-inference-p1-trunk-q6-0001.json` and
`docs/research/glm52/raw/post-f016-p1-trunk-profile-0001.json`.

## Limitations

- Python research runtime, not a production server
- Residual scale on long research ladders is large; quality not claimed
- ssd-llm used for design only (no runtime dependency)
- Legacy P1 did not retain routing IDs, storage/dequant timing, bytes read,
  RSS, or source/checkpoint identity. P2 and golden-eight use self-contained
  records and are not merged with that legacy observation.
- Nested per-quant metrics cover only the expert-cache path. Dense trunk and
  logits work require separate attribution before selecting a Metal target.

## Commands

```sh
export PULSARMLX_GLM_GGUF=/path/to/final/GLM-5.2-UD-IQ2_XXS
uv run --frozen python scripts/research/qualify_iq2_xxs_numpy.py \
  --output docs/research/glm52/raw/f016-iq2-xxs-numpy-qualification-0001.json
uv run --frozen python scripts/research/glm52_inference.py --mode inference \
  --n-new 2 --cache-gib 16 --cache-policy decoded_shared_only \
  --decoder-mode numpy_vectorized \
  --out docs/research/glm52/raw/f016-inference-p2-iq3-0001.json
uv run --frozen python scripts/research/glm52_inference.py --mode inference \
  --n-new 8 --cache-gib 16 --cache-policy decoded_shared_only \
  --decoder-mode numpy_vectorized \
  --out docs/research/glm52/raw/f016-inference-golden8-iq3-0001.json
python3 scripts/research/analyze_glm52_golden8.py --check
```
