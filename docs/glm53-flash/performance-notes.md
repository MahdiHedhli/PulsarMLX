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
| Hybrid read path: `mincore` → memmap copy if resident, else `preadv` in an 8-thread pool | memmap only; pread only; threaded memmap | measured per 14.2 MB expert: memmap hot 36–40 GB/s but cold 0.7 GB/s (2.3 with 16 threads); preadv cold 6.3 GB/s ×8 threads, hot 7 GB/s; mincore costs ~1 µs |
| No cross-layer prefetch yet | predict layer L+1's experts from the previous token | routing is unknown before the layer; predictor untested; recorded as open |
| Compare paged variants by logits/hits, not text hash | require identical greedy text | sorted vs per-expert kernels differ at bf16 ulp level; text flips at near-ties |
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

1. Rung 3: prefill served from the store without the wave serialization
   (batch all waves' reads first; or stream whole files when the miss count
   of a layer exceeds a threshold, i.e. the bulk path with store admission).
2. Warm-state load through the pool at full SSD rate (29 s for 69 GB → ~12 s).
3. Cross-layer prefetch is blocked on routing unknown before the layer;
   the previous token's routes as a predictor is untested.
4. Multi-prompt / longer-generation variance for every table above.
5. REAP37 (118 GB) resident on a quiet Studio: quality vs REAP50, fit check.
6. MacBook 64 GB usable tier: needs a pruned build under ~50 GB or 2–3-bit
   experts; paging alone stays ≤ 2 tok/s.
