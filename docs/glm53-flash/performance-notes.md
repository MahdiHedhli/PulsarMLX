# Performance notes: GLM-5.3-Flash on Apple silicon (handoff, 2026-09-17)

Measured facts, the mechanism behind each, and the method that found it. Written
so the next person (or the next model) can reuse the methods and skip the dead
ends. Every number here has a record under the private evidence tree
(`Planning/flash-dense-ffn-20260916an/dogfood/`, `graph22`–`graph24`); the
public docs `dogfood.md`, `pulsar-expert-store.md`, `decoder-offload.md` carry
the narrative. Machines: **Studio** = Mac Studio M1 Ultra, 128 GB, macOS 26.0,
internal SSD; **MacBook** = MacBook Pro M2 Max, 64 GB, internal NVMe (and an
external "APFS 2TB" drive that is ~1.6× slower for this workload). mlx 0.32.2,
mlx-vlm 0.7.0 @ `8d79dbcf`, pipenetwork glm5_next @ `a61a7c7d`.

## 1. The model's traffic per token (why the ceilings are what they are)

GLM-5.3-Flash: 45 layers (34 linear-attention, 11 DSA/MLA), 288 routed
experts, top-8, 3 dense layers, 1 shared expert. Mixed-4/8 build: 169.4 GiB
= ~159.5 GiB of routed experts (42 × 288 × 14.2 MB at 4-bit/g64 with bf16
scales) + ~10 GiB of 8-bit residents. Per token: 42 × 8 × 14.2 MB = **4.8 GB
of routed-expert weights + ~10 GB of residents ≈ 15 GB of weight traffic**.

- Fully resident bandwidth ceiling: ~19 ms/token on M1 Ultra (800 GB/s),
  ~37 ms on M2 Max (400 GB/s) → 25–50 tok/s before compute.
- Paged: every miss is a 14.2 MB read. At 78% hits (Studio, 70 GB store)
  that is ~74 misses ≈ 1 GB/token from the SSD → ≥0.2 s at 5 GB/s. **No
  residency policy reaches 20 tok/s for the unpruned build on 128 GB**: it
  would need ≥95% hits with reads fully overlapped, or ≥99.5% without.
- REAP50 (pipenetwork, 144 of 288 experts, 96.3 GB) fits 128 GB resident.

## 2. Resident serving (REAP50 on the Studio) — graph 23

| Metric | Value | Note |
|---|---|---|
| Load | 24–29 s | 96.3 GB materialized from internal SSD (`lazy=False`) |
| Decode | **21.2–22.7 tok/s** (9 runs) | 96 and 256 tokens; identical text across runs |
| Prefill, steady state | **59 / 98 / 187 tok/s** at 16 / 64 / 256 tokens | wired buffers |
| Prefill via `generate`, warm process | 67 / 68 / 86 tok/s (25 / 25 / 67 tokens) | `--warmup 8` |
| Peak memory | 100.2–100.5 GB | under the 115.4 GB recommended working set |
| First prompt of a fresh process | 0.5–2 tok/s | see wiring settle below |

**Finding — OS eviction of cold experts (the "prefill is slow" trap).**
Symptom: prompt processing at 0.7–6 tok/s while decode was 22. Per-stage
profile (eval after every layer stage) put ~3 s of every prefill pass in the
MoE FFN blocks, **~70 ms per layer flat in token count** (16/64/256 tokens:
2.83/3.09/3.38 s), while the same block on the same activations timed warm
costs 4–5 ms and one MoE layer in isolation costs 5 ms at T=16 and 25 ms at
T=256. Decode touches 8 of 144 experts per layer; under host memory pressure
(~20 GB of unrelated apps, swap at 21.9 of 22.5 GB) macOS evicted the experts
decode never touched and every prefill paged them back. **Fix:
`mx.set_wired_limit(max_recommended_working_set_size)`** (mlx-lm's practice).
Back-to-back A/B in the same host state: **unwired 2.2 / 17 / 58 → wired
59 / 98 / 187 tok/s** at 16 / 64 / 256 tokens, swap-outs 0. Making the wired
set resident is a one-time per-process cost (31–45 s here, the OS paging the
other apps out; zero on a quiet host); a warm-up generate absorbs it in a
server process. Steady-state prefill then scales with the active expert
fan-out (82 experts at T=16 → 131 of 144 at T=256, 5 → 25 ms per MoE layer).

Method that found it: `profile_prefill.py` (wrap `self_attn`/`_ffn_block`
with timers + `mx.eval`), `profile_moe.py` (one MoE layer at T=1..256, sorted
vs unsorted gather), `profile_ffn_block.py` (real activations captured by a
hook; each stage timed warm), then `vm_stat` deltas per pass. **Rule: a cost
that is flat in T and 10× the warm cost of the same op is paging, not code.**

Host hygiene on the Studio that made the numbers stable: quit Docker
Desktop's Linux VM (Virtualization.framework, autostart), Hermes, ChatGPT/
Codex, Claude, Bark, Creative Cloud + Adobe services, LM Studio, MEGAsync,
Parallels Toolbox → ~20 GB freed; NotificationCenter (4.2 GB) and coreaudiod
(2.5 GB) looked leaked and were left alone. RustDesk kept for remote access.

Serving: `serve_resident.py` (OpenAI-style `/v1/chat/completions`,
streaming, `reasoning_content` split at `</think>`, `reasoning_effort`
low|medium|high → the template's `Reasoning Effort` line, default Max).
Over the LAN from the MacBook: 22.3–22.7 tok/s decode, prompt 56 tok/s once
warm. `reasoning_effort: low` answered a 3-tip question in 149 tokens; `high`
spent all 400 thinking — a short `max_tokens` with the default effort returns
no `content` at all.

## 3. Paged serving (unpruned build) — graphs 18–22, 24

### 3.1 Baseline numbers (upstream `ExpertStore` LRU + `OffloadedSwitchGLU`)

| Host | Offload dir | Budget | Decode | Prompt | Hit rate | Peak |
|---|---|---|---|---|---|---|
| MacBook | external drive | 32 GB | 0.590 tok/s | 0.62 | 57.8% | 45.4 GB |
| MacBook | internal NVMe | 32 GB | **0.951** | 1.42 | 57.8% | 45.4 GB |
| Studio | internal SSD | 70 GB | 2.96–3.49 (n=6) | 1.2–2.7 | 77.8% | 83.4 GB |
| Studio | internal SSD | 50 GB | 1.50 | — | 68.1% | — |

Storage alone: external → internal NVMe on the MacBook is +61%.

### 3.2 Where a paged token's time goes (per-token fits)

Method: `probe_decode.py` — `stream_generate`, one row per token with
wallclock and the store's hits/misses/evictions, then least squares
`dt = a + b·misses` and quarter means. This separates the **all-hit
intercept `a`** (compute + bookkeeping) from the **per-miss cost `b`**.

Studio, 70 GB, upstream path: `a` ≈ 0.16–0.22 s/token, `b` ≈ 2.4–3.1 ms per
miss in cold runs but 7.4–9.7 ms in warm-started runs; cold runs degrade
quarter by quarter (0.27 → 0.39 s/token) as the store fills. Two facts:

1. **The intercept is the eager per-expert loop**: `OffloadedSwitchGLU` host-
   syncs the routing, then per selected expert issues three
   `quantized_matmul` launches plus a full-array `out.at[...].add` scatter
   (~40 launches, 8 (N,K,D) copies per layer per token) → 4–5 ms/layer against
   ~1 ms for the resident `SwitchGLU`. Caps the path near 5 tok/s at 100% hits.
2. **Per-miss cost depends on the page cache**, and the page cache is a
   second-level cache of the same experts competing with the store: with the
   store full from token 0 (warm start) on a host whose memory is filled by
   store + residents + apps, misses come from disk (7–10 ms); a cold store
   fills gradually and rides the page cache left by prefill's bulk loads
   (2–3 ms). So a cold 96-token run over-reports steady-state throughput.
   `vm_stat` at the end of every run: ~87 GB wired, ~12 GB file-backed, free
   ≈ 60 MB. Budget choice therefore trades store hits against page-cache
   hits; leave headroom.

### 3.3 `mx.clear_cache()` per eviction (graph 22)

Upstream clears MLX's allocator cache after every eviction batch. Once the
store is full every miss evicts, so every miss returns its freed 14.2 MB
buffers to the OS and the next miss re-allocates. Stubbing the call:
cold 3.03 → 3.35, warm 2.32 → 2.62 tok/s (+10–13%). `PulsarExpertStore`
clears only above a cache-memory threshold (default 2 GiB; it never fired on
this model — MLX's own cache limit governs); peak memory unchanged. A/B at
70 GB (interleaved ×2): warm thr0 2.35/1.28 → thr2 2.65/2.67; MacBook 32 GB:
LRU 0.951, Pulsar warm 1.040 → 1.139.

### 3.4 Slot store (graph 24, ladder rung 2)

`PulsarSlotStore` + `PulsarSwitchGLU`: per layer a stacked (C, …) slot tensor
per projection part, an `expert_to_slot` map, LFU-with-decay over the slots,
calls processed in waves of ≤C experts (pinned), misses written in place
(`W[slots] = stacked`, the KV-cache pattern), three `gather_qmm` launches
over the slots with SwitchGLU's sort/unsort. Verified bit-exact against
per-expert `quantized_matmul` and ~2e-7 against the frozen reference.

Measured on the Studio, one layer (`profile_slot_layer.py`):

| Path | Cost |
|---|---|
| All-hit call at T=1 (was 4–5 ms upstream) | **0.83 ms** |
| All-hit call at T=16 | 8.8 ms |
| `mx.load` of a layer file (header parse, 2,592 tensors) | **4–5 ms** — per miss layer, ~190 ms/token; removed by parsing once |
| Read of a 14.2 MB expert, page-cache resident, memmap copy | ~0.35 ms (36–40 GB/s) |
| Read cold from SSD, memmap (16 KB synchronous faults) | 0.66–0.77 GB/s; 2.3 GB/s with 16 threads |
| Read cold, `preadv` into a buffer | 1.5–2.7 GB/s single thread; **6.3 GB/s with 8 threads** |
| Read hot, `preadv` | 7 GB/s (memmap is 5× better when resident) |
| Stack + scatter of 8 experts into slots | 2.9 ms (0.35 ms per expert) |

Hence the read path: parse each layer's safetensors header once; per miss
check page residency with `mincore`; resident → memmap copy on the calling
thread, else `preadv` in an 8-thread pool; stack and scatter once per
(projection, part). A cold 8-expert fill went 102 → 14.6 ms.

Real model, Studio 70 GB (interleaved): **slot cold 3.85 / 3.83, slot warm
4.69 / 4.61 tok/s vs LRU 3.49** (+33% warm; hit rate 84.9% warm / 75.9%
cold; ~90% of misses were cold reads). Prompt regressed to 1.2–1.3 tok/s
(LRU 2.7): the first prefill reads ~118 GB of misses through waves at ~6 GB/s
serialized with the scatters, where upstream's bulk path streams whole files
— the subject of rung 3. Warm-state load 29 s (69 GB through the pool).
MacBook, internal NVMe, 32 GB: **slot cold 2.00 / warm 2.03 tok/s vs LRU
1.14 (+75%)**, prompt 0.8–0.9 vs 2.2.

**Prefill on the paged tier (rung 3, measured, partially resolved).** With
the page cache evicted before every run (reading the 96 GB REAP50 files
through), Studio 70 GB: LRU prompt 2.43 / 2.60 tok/s; slot warm 3.58 / 3.78
(8 read workers) but 1.19–2.94 in other runs of the same configuration;
slot cold 1.24 / 1.41. A 25-token prompt is the worst case for a paged
store: it touches ~200 of 288 experts per layer, so its cost is per unique
expert (≥83 misses per layer with 117 slots ≈ 49 GB minimum, ~118 GB from a
cold store), not per token — longer prompts amortize. Read-path numbers for
a 93-expert cold batch: thread pool 676 ms, `mx.load` lazy loads evaluated
together 233 ms (5.7 GB/s) — MLX's reader parallelizes big batches better,
at a 4–5 ms header parse per call. `fill` therefore uses `mx.load` (entries
popped, nothing retained) when a batch has ≥4 cold experts and the
mincore/memmap/preadv path otherwise; warm-state load dropped 29 → 18 s.
32 read workers thrash (prompt 0.63). The repack files are hash-ordered
(an expert's nine tensors are scattered), so expert-contiguous coalescing
— one 14 MB sequential read per expert, adjacent misses merged into large
streaming reads — needs a re-repack with a sorted layout: the next
structural step for cold prefill. Quiet host: after the background apps were
quit, the resident server's load was 15.3 s and its warm-up 1.0 s (the
31–45 s settle was entirely the OS paging other apps out).

**Numerics.** The slot path's greedy text diverges from the upstream loop's
after ~50 tokens ("The user explicitly" → "The user has explicitly"; the
rest equivalent; slot runs are self-consistent per host). First-token logits
after prefill on the same prompt: top-5 identical in the same order, mean
|Δ| 0.097 and max 0.66 at |logit| ≈ 24 — one bf16 ulp (24 × 2⁻⁸ ≈ 0.09).
Cause: prefill at ≥8 routed indices takes the sorted `gather_qmm` kernel
(the kernel the resident `SwitchGLU` also uses) while the upstream loop uses
per-expert `quantized_matmul`; accumulation order differs. The mapping
itself is pinned by the tiny-geometry harness at ~2e-7 with waves and
evictions exercised, and slot-mapped `gather_qmm` was checked bit-exact
against per-expert `quantized_matmul` on the same weights. Treat the two
paths as numerically equivalent, not bit-identical; compare A/B by logits
and hit statistics, not by text hash.

## 3.5 Resident decode anatomy and MTP speculation (graph 25)

Step cost by token count on the Studio (REAP50, wired): **28 ms fixed +
17.5 ms per token** (T=1 45.6, T=2 65, T=4 98, T=8 161 ms). Ablation by
layer count: **1.0 ms per layer, linear, identical for linear-attention and
DSA layers, ~0.8 ms outside the layers**. Weight traffic is ~250 MB per
layer per token (0.3 ms at 800 GB/s), so ~0.7 ms/layer is per-kernel
dispatch (~40–50 kernels per layer, ~12–15 µs each). What does *not* fix it:
`mx.compile` of a whole linear layer (46.5 → 45.4 ms; elementwise chains
are not the cost), `mx.async_eval` pipelining (→ 43.6 ms: CPU-side work is
~3 ms), and the FFN-block compile the runtime already does (3%). A second
batch row costs 21 ms like a second token, so it is GPU-side execution of
many small kernels. The only way past it is fewer kernels per layer.

**Conclusion (the one to carry forward): the 26–28 ms fixed cost of every
decode step is GPU-side execution of ~2,000 small kernels (45 layers ×
40–50), not bandwidth, not CPU overhead, not anything `mx.compile`,
`async_eval`, batching or speculation can remove. Real gains on the
resident tier need fused Metal kernels in a qualified fork of the runtime
(graph 26): fewer launches per layer is the only lever left, and every
other technique (MTP, prompt lookup, batching) is bounded by it.**

**MTP speculative decoding** (the checkpoint's own next-token layer,
converted from the original FP8 checkpoint's layer 45 — 4.27 GB at 4/8-bit;
drafter on the pinned runtime's classes; greedy verify at T=k+1; per-position
linear-attention states recomputed on partial acceptance from the retained
delta-rule inputs): first-draft acceptance 0.72–0.87 (post-norm hidden input
measured slightly better than the pre-norm stream mean: 0.767/0.691/0.916 vs
0.747/0.674/0.871); 256-token results vs plain 22.5: **k=1 23.8 / 22.3 /
24.4, k=2 24.4 / 21.7 / 25.4** (short factual / long reasoning / code).
Verify+rollback equivalence: the wrapper's T=2 logits equal the pinned
path's exactly; rollback error (1.4 max logit) is the same magnitude as the
pinned T=2-vs-T=1 shape difference (1.3), i.e. numerics, not state. Ceiling
at 100% acceptance with k=1 is ~27 tok/s because of the fixed step cost;
MTP is kept (never worse than −3%, +8–13% on code-like text) but is not the
lever. Peak memory +4.3 GB (104.7 GB). Review caveats: the post-norm choice
rests on a 2–4 point A/B over three prompts (what would settle it: draft
log-likelihood over a validation slice, or the training code's convention);
the server keeps `draft_k=1` because reasoning-heavy text loses 1–3% at
k=2; the run card's tiny-geometry MTP oracle/operation was not built — the
strict load, the exact T=2 logit match of the verify wrapper and the
measured acceptance stand in for it, and the deviation is recorded.

## 3.6 Graph 26 assessment: what kernel fusion can and cannot buy

Measured per whole layer at T=1: 0.95 ms (linear) / 0.91 ms (DSA), against
~0.27 ms of ideal weight streaming at 800 GB/s (experts 113 MB + shared
25 MB + attention ~70 MB). The remainder splits between sub-peak M=1
quantized gemv / `gather_qmm` efficiency (an MLX kernel-quality matter) and
~50 launches of small ops per layer. Two cautions from the measurement
itself: per-block "chained" micro-benchmarks are order- and overlap-
sensitive (the same op read 0.03 and 0.7 ms) and must not be used to rank
fusion targets; and a kernel-choice that looked 4× faster in isolation
(sorted `gather_qmm` at T=1: 0.14 vs 0.61 ms) was *slower* end-to-end
(48–60 vs 46 ms/token). Only end-to-end decode timings count. MLX 0.32.2 is
the current release (2026-08-25), so there are no newer kernels to adopt.
Realistic ceiling for fused custom Metal kernels (hyper-connection chain,
linear-attention pre/post ops, router select): ~1.2–1.3× (46 → 35–38
ms/token) for weeks of Metal work with per-kernel qualification. Deferred;
recorded here so the next attempt starts from these numbers.

## 3.7 REAP37 does not fit the 128 GB Studio (graph 27)

Three attempts, all on an emptied host (every login item and daemon quit;
~98 GB free at idle). Eager load (`lazy=False`, wired limit set): RSS
climbed to 86 GB with the shard files' page cache at ~28 GB, then the
kernel **compressed 74 GB of the model's own pages** within 40 s (RSS fell
to 21 GB, 4.6 GB swapped out) — wiring had never applied, because Metal's
residency set only holds buffers while a command buffer is in flight and a
pure load submits none (`vm_stat` wired stayed ~5 GB throughout). Lazy load
(weights pulled in by the first forward, so each command buffer wires what
it touches): wired rose with the layers to ~38 GB, then dropped between
buffers; at 57 GB resident the compressor started (11.6 GB), swap resumed,
and the process died with a Metal GPU timeout (`kIOGPUCommandBufferCallback
ErrorTimeout`) — a command buffer stalled on paged-out weights. The kernel
prefers compressing inactive anonymous pages (already-loaded layers) to
dropping the active file-cache pages of the shard being read, so 118.3 GB
of weights plus the cache needed to read them exceeds RAM transiently on
both strategies. A page-cache-bypassing loader (`F_NOCACHE` byte-range
reads, as the slot store does) would probably get it loaded, but the
serving margin would be ~2 GB on 128 GB — any KV growth on a longer prompt
pushes it back into compression. **Verdict: REAP37 is a paged-only build on
this hardware; REAP50 (96.3 GB, peak 100–105 GB) is the largest resident
build.** Operational lesson recorded twice over: never `kill -9` a process
holding >100 GB of wired/compressed memory on a saturated box — the first
attempt's teardown wedged the host for an hour (two processes stuck in exit
state holding 117 GB, graceful restart impossible, hard reboot required);
kill on the *compressor* signal while free memory still exists, not on
"free pages" (the file cache makes that read zero during any large load).

## 3.8 Quality across the pruning ladder (graph 27)

Teacher-forced mean NLL per token of one fixed 331-token held-out passage
(`quality_probe.py`; a comparative indicator, not a benchmark):

| Build | Experts kept | Mean NLL | Perplexity | Top-1 | Path |
|---|---|---|---|---|---|
| Unpruned mixed-4/8 | 288 | **1.793** | 6.0 | 57.1% | paged (slot store, internal SSD) |
| REAP37 | 181 | 2.153 | 8.6 | 48.0% | paged (slot store, Promise array) |
| REAP50 | 144 | 2.594 | 13.4 | 43.5% | resident |

Pruning costs are large and roughly proportional to the experts removed;
REAP37 recovers about half of REAP50's loss but is paged-only on the Studio
(§3.7). The unpruned model is the fidelity tier and runs at 4–5 tok/s
through the slot store; REAP50 is the latency tier at ~22 tok/s.

Two more lessons from getting these numbers on the Promise array: (a) the
slot store must clear MLX's allocator cache above a threshold (added; a
331-token prefill otherwise reached 117 GB wired); (b) on slow storage the
kernel compresses the store's own slot tensors rather than drop the mmapped
expert files' page cache — `F_NOCACHE` on the `preadv` descriptor (added)
is not enough while the memmaps stay open, so the probe ran at a 15 GB
budget (the NLL does not depend on the budget; the run took 269 s instead
of 37 s on the internal SSD). Review caveats: one 331-token passage is a
directional indicator only (the run card asked for ~600 tokens plus three
side-by-side sample outputs; neither was delivered — the deviation is
recorded, and a multi-domain slice with standard errors is the next step
before any quality claim is made in public).

## 3.9 Nine-domain quality slice with error bars (graph 28)

Teacher-forced NLL per token on nine passages (own text plus public-domain
excerpts and this repository's code; `fixtures/research/glm53-flash-quality-
slice-v1/passages.json`, sha `cc1d3e13…`), one forward per passage:

| Passage (tokens) | Unpruned | REAP37 | REAP50 |
|---|---|---|---|
| Austen 1813 (335) | 0.070 | 0.422 | 0.717 |
| US Constitution (267) | 0.137 | 0.185 | 0.209 |
| Python, this repo (231) | 1.064 | 2.019 | 2.458 |
| Math explanation (269) | 0.899 | 0.937 | 1.091 |
| Dialogue (256) | 1.405 | 1.709 | 1.761 |
| News report (206) | 1.515 | 1.628 | 1.700 |
| Storage technical (246) | 1.706 | 2.207 | 2.539 |
| Biology (203) | 1.300 | 1.486 | 1.717 |
| French (226) | 1.262 | 2.805 | 3.153 |
| **Token-weighted NLL (ppl)** | **0.977 (2.66)** | **1.411 (4.10)** | **1.628 (5.09)** |
| Mean of passage means ± SE | 1.040 ± 0.194 | 1.489 ± 0.282 | 1.705 ± 0.311 |
| Token-weighted top-1 | 74.7% | 66.5% | 63.6% |

Paired per-passage deltas: REAP37 − unpruned **+0.449 ± 0.167** nats/token
(t = 2.7), REAP50 − unpruned **+0.665 ± 0.205** (t = 3.2), REAP50 − REAP37
**+0.217 ± 0.049** (t = 4.4); each pruned build is worse on 9 of 9
passages. The loss is concentrated where the 65k-token calibration set was
presumably thin: French (+1.5 / +1.9), code (+0.96 / +1.39), technical
prose (+0.5 / +0.8); legal and mathematical prose lose almost nothing. The
near-memorized public-domain texts (Austen 0.07, Constitution 0.14 for the
unpruned model) show pruning even erodes memorized continuations.
Practical reading: REAP50 is a latency tier with a real, domain-dependent
fidelity cost; on the one Python and the one French passage evaluated the
degradation was heaviest, on English prose and reasoning smallest — a
categorical claim about code or multilingual capability needs several
passages per domain, which this slice does not have. The unpruned paged
tier is the fidelity tier. The paired deltas are right-skewed by those two
passages, so the t-statistics overstate parametric confidence; the
distribution-free result is the one to quote: each pruned build is worse on
9 of 9 passages, exact sign-test p = 0.5⁹ ≈ 0.002.

Method notes: the REAP37 pass from the Promise array ran at 66–90 MB/s
however the reads were issued (61 KB transfers; `mincore` there reports
non-resident pages as resident, so the memmap path faulted) — the slice
finished in 6 minutes once its repack was copied to the internal SSD
(3.2 GB/s). Paged runs used a 50 GB store; REAP50 resident and paged
agree bit for bit (graph 27), so the paths compare like with like.

## 3.10 Expert-contiguous repack (graph 29) and the memory policy behind every thrash

`repack_v2.py` writes each layer file with every expert's nine tensors in
one byte range, experts in numeric order (MLX's own writer follows an
unordered map, so the container is written by hand and read back to verify
contiguity); `PulsarSlotStore` reads a cold batch on that layout as merged
ranges (adjacent misses coalesced, each range read in 64 MB chunks through
the pool, `F_NOCACHE`). Qualified: the frozen fixture in both layouts and
both residency modes is bit-identical (four passes per case), 9/9 mutants
killed including two layout mutants; a thread race in the file opener was
found and fixed on the way. **Measured gain: none on a fast SSD.** MacBook
NVMe, 93 cold experts: hash-ordered 4.7–6.3 GB/s (eight threads of
per-tensor reads already saturate the drive), contiguous 6.3 GB/s after the
chunked-parallel fix (a single 1.3 GB `preadv` on one thread had measured
3.0). The Promise array is bound by 61 KB transfers however reads are
issued. End-to-end cold prefill on the contiguous layout is **unmeasured**
(see below), so this is "no gain shown on a fast SSD", not "no gain
possible". Keep `repack_v2` as an option — correct, harmless, likely useful
on storage with expensive small reads. Review notes applied: all chunks of
all merged runs are now dispatched to the pool at once (small disjoint runs
had serialized), and the two layout mutants kill by rejection
(`np.frombuffer` length mismatch, `NOT_CONTIGUOUS`) rather than by value —
the matrix's KILL cells hold, the predicted reason did not.

**The memory policy (root cause of every thrash this session).** With hot
reads unpinned (`madvise(MADV_DONTNEED)` after each copy) the per-layer
warm-load trace still shows 47–73 GB of file-backed pages staying resident
while the compressor grows to 65 GB with the store's own tensors. Part of
that file-backed baseline is the process's own active mappings (the
resident shards through `mx.load`, upstream `patch_model`'s lazy maps of
every expert file, touched pages of the hot path) which the kernel cannot
discard while mapped; the rest is clean cache from earlier I/O. Either
way, macOS 26 compressed the inactive anonymous tensors first. The
trigger in these benchmarks was my page-cache eviction procedure (reading a
96 GB build through `cat` to flush the expert files), which manufactures
exactly that cache; earlier, the Docker VM and other apps did the same job.
A real server never runs the `cat`, and every runtime read path is now
`F_NOCACHE` or unpinned, so serving is unaffected — but **cold-prefill
benchmarks need `purge` (root) between runs**; without it the numbers
alternate between page-cache luck and compressor thrash and are not worth
reporting. Rule for the notes: on macOS, keep the page cache small before
any >60 GB allocation, kill only on compressor/swap-out growth, and
measure cold reads only after `purge`.

## 4. Decision log (what was chosen, what was rejected, on what evidence)

| Decision | Alternatives considered | Evidence / reason |
|---|---|---|
| Resident REAP50 as the usable tier on the Studio (rung 1 before any paging work) | REAP37 (118 GB, too tight with apps resident); unpruned + paging | §1 arithmetic: paging cannot reach 20 tok/s on 128 GB; REAP50 measured 22 tok/s first try |
| Wire the Metal buffers by default in the resident entrypoint/server | leave unwired; wire only on request | A/B 2.2/17/58 → 59/98/187 tok/s prefill; documented as "assumes a dedicated host" per review |
| Warm-up generate in the server, and report steady state separately from the first prompt | report first-prompt numbers only | the settle is a per-process cost (31–45 s, OS paging apps out), not model cost |
| Bounded `clear_cache` (threshold) instead of removing the call | never clear; keep per-eviction | +10–13% measured; MLX's own cache limit bounds memory (peak unchanged); threshold 0 reproduces upstream for A/B |
| Per-layer slot capacity (C = budget / layers / bytes) instead of a global byte budget | global LFU across layers (graph 21) | stacked tensors need a fixed per-layer allocation; per-layer skew is a known cost, left for measurement |
| Waves (≤C experts, pinned) for calls touching more experts than slots | refuse; grow slots temporarily; fall back to the per-expert loop | exact and simple; tiny fixtures force a split (C=2, 3 tokens) so it is under test |
| In-place slot writes via `__setitem__` | `slice_update` (2.6 ms) ; rebuild tensors (full copy) | measured 0.34 ms per 4 MB slot in a 256 MB tensor; a full copy would be 25× |
| Parse each layer's safetensors header once, read by byte range | `mx.load` per fill (lazy dict) ; cache the `mx.load` dict | header parse 4–5 ms × 42 layers ≈ 190 ms/token; a cached dict retains every materialized expert (memory grows to the whole model) |
| Hybrid read path: `mincore` → memmap copy if resident; else `preadv` in an 8-thread pool for small batches; else (≥4 cold experts) `mx.load` lazy loads evaluated together | memmap only; pread only; threaded memmap; `mx.load` always | per 14.2 MB expert: memmap hot 36–40 GB/s but cold 0.7 GB/s (2.3 with 16 threads); preadv cold 6.3 GB/s ×8 threads, hot 7 GB/s; 93-expert cold batch: pool 676 ms vs `mx.load` 233 ms; `mx.load` header parse 4–5 ms rules it out per decode miss; 32 threads thrash |
| Compare paged prefill only from an evicted page cache, and by unique-expert reads, not tokens | compare prompt tok/s across consecutive runs | consecutive runs share the page cache; a 25-token prompt's cost is per unique expert |
| No cross-layer prefetch yet | predict layer L+1's experts from the previous token | routing is unknown before the layer; predictor untested; recorded as open |
| Compare paged variants by logits/hits, not text hash | require identical greedy text | sorted vs per-expert kernels differ at bf16 ulp level; text flips at near-ties |
| Build MTP speculation before kernel work | kernel fusion first | MTP reuses existing weights and a day of runtime work; measured +0–13%, and it stacks with any later per-token gain |
| Per-position linear states by recomputing the delta rule over the accepted prefix on rollback | stepwise T=1 verification (34 × k extra attention calls ≈ 20 ms); mlx-vlm-style per-position state output (kernel change) | one small kernel per layer only on rejection; verbatim copy of the pinned forward keeps the pinned file untouched and the T=2 logits identical |
| MTP hidden = post-final-norm | pre-norm stream mean (DeepSeek-V3 convention) | acceptance A/B on three prompts favours post-norm on all three (small margin); kept switchable |
| Kill switch keyed on compressor/swap-out growth, not free pages | free-pages threshold | free pages hit zero from file cache during any large load (false trigger); compression + swap-outs are the true distress signal; killing at true saturation wedged the host |
| REAP37 declared paged-only after three loading strategies | NOCACHE loader; more daemons killed | eager and lazy loads both compressed/thrashed on an empty host; the margin would be ~2 GB even if loaded |
| Quality claims only from the nine-domain paired slice, never the single passage | one-passage indicator | paired deltas with SE across domains; ranking stable 9/9 |
| Repack v2 writes the safetensors container itself | rely on `mx.save_safetensors` order | MLX's writer follows an unordered map (neither insertion nor sorted order, verified) |
| Kernel fusion (fewer launches per layer) as the next resident-tier track, not more speculation | more draft tokens; tree drafts | acceptance decays 0.8 → 0.65 → 0.53 by position and the fixed step cost caps every speculative variant near 27–31 tok/s |
| Equivalent mutant replaced, revision recorded (graph 24) | keep an INACTIVE cell | `stale-slot-map` could not kill because `slot_of` is authoritative; `map-not-refreshed` is what the gather depends on |
| Quit the Studio's background apps (Docker VM, Hermes, Codex, Claude, Bark, CC, LM Studio, MEGAsync, Parallels); keep RustDesk; leave NotificationCenter/coreaudiod | kill everything; leave everything | operator's list; ~20 GB freed; the two daemons are system-owned and were only flagged |

## 5. Methods worth reusing on any model

- Freeze a run card, then a stdlib model + fixture with a prospective kill
  matrix, then measure; a mutant that observes INACTIVE is a fixture defect
  (graph 24: `stale-slot-map` was equivalent because `slot_of` is the
  authority; replaced by `map-not-refreshed`, revision recorded).
- Per-token fits (`dt = a + b·misses`) before touching a policy.
- Per-stage profile with `mx.eval` after each stage; compare against the
  same op timed warm in isolation; flat-in-T + 10× = paging.
- `vm_stat` deltas (swap-ins/outs, file-backed, wired) around every run;
  report the host's other resident applications.
- Interleave A/B variants and repeat (n ≥ 2); one 96-token run is not a
  steady state for a store that is still filling.
- Check allocator behaviour directly (`mx.get_cache_memory`, in-place
  `__setitem__` timing) before assuming.
- Read-path micro-benchmarks per storage state (cold/hot) before choosing
  memmap vs pread vs threads; the answer differs by 50×.

## 6. Open items (ordered)

0. Graph 26 (assessed, deferred — §3.6): fused Metal kernels in a
   qualified runtime fork; realistic 1.2–1.3×, weeks of work; rank targets
   only by end-to-end decode timings.

1. Cold-prefill A/B (hash vs contiguous, LRU vs slot) after `purge`: needs a
   passwordless-sudo rule for `/usr/sbin/purge` on the Studio and MacBook,
   an operator decision.
2. Warm-state load at full SSD rate (now 18 s for 69 GB; ~12 s possible).
3. Cross-layer prefetch is blocked on routing unknown before the layer;
   the previous token's routes as a predictor is untested.
4. Multi-prompt / longer-generation variance for every table above.
5. REAP37 (118 GB) resident on a quiet Studio: quality vs REAP50, fit check.
6. MacBook 64 GB usable tier: needs a pruned build under ~50 GB or 2–3-bit
   experts; paging alone stays ≤ 2 tok/s.
