# GLM-5.3-Flash unpruned persistent paged serving — results (2026-09-20)

> **Repository note (2026-09-20).** The code these results describe is now on the default branch: the paged/serving path under [`scripts/research/glm53_flash/`](../../scripts/research/glm53_flash/), the streaming-prefill experiment (default-off, a retained negative result) in [`scripts/research/glm53_flash/dogfood/`](../../scripts/research/glm53_flash/dogfood/) with its tests `scripts/research/tests/test_glm53_flash_stream_prefill.py` and `..._stream_prefill_policy.py`, and the expert-cache ceiling as the explicit `--max-expert-cache-bytes` flag in `scripts/research/glm53_flash/dogfood/paged_reference.py` (default 60000000000). The measurements, claims and limitations below are unchanged and remain pinned to source commit `971db9c1`.

Compact results of the persistent-serving research round (private graph G52–G61, 2026-09-19/20). Machine-readable values: [`persistent-serving-summary.json`](persistent-serving-summary.json); claim/source manifest: [`persistent-serving-manifest.json`](persistent-serving-manifest.json). Nothing here is a production claim; see *Scope and limitations*. The accepted expert budget was raised from 60e9 to 70e9 bytes after these runs: the tables below are the 60e9 record, and [*Expert budget 70e9 (2026-09-20)*](#expert-budget-70e9-2026-09-20) carries the newer measurements and the current recommended launch line.

## What was tested

| | |
|---|---|
| Model | **unpruned** `pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit` (288 routed experts / top-8 / 42 MoE layers; experts affine 4-bit g64 with bf16 scales, ~14.2 MB each; residents 8-bit). No pruning, no MTP in any comparison. |
| Host | Mac Studio M1 Ultra, 128 GB unified memory, internal SSD, macOS 26.0; mlx 0.32.2, mlx-vlm 0.7.0 @ `8d79dbcf`, pipenetwork `glm5_next` @ `a61a7c7d`, Python 3.11.15 |
| Source | candidate [`971db9c1`](https://github.com/MahdiHedhli/PulsarMLX/commit/971db9c16f982f367d1759b5ccda03a506cf6672) (CI run 35486415420 success) on `serve/glm53-flash-unpruned-persistent-20260919b`; predecessor `9721d935` |
| Runtime | Python/MLX research server [`serve_offload.py`](https://github.com/MahdiHedhli/PulsarMLX/blob/971db9c16f982f367d1759b5ccda03a506cf6672/scripts/research/glm53_flash/dogfood/serve_offload.py): the paged loader (`run_offload.load_offloaded`, `PulsarSlotStore`) behind the existing `serve_resident` HTTP app and inference worker |
| Accepted configuration | expert budget **60,000,000,000 B** (100 slots per MoE layer), coalesce gap 0, per-expert slot writes, wired buffers, page-aligned reads, 8 read workers, 64 MiB chunks, bulk_min 4, prefill step 256, greedy, reasoning effort low, warm-state readmission off, prefix reuse off |
| Reference arm | the same paged path in a **fresh process per request** with an empty store ([`paged_reference.py`](https://github.com/MahdiHedhli/PulsarMLX/blob/971db9c16f982f367d1759b5ccda03a506cf6672/scripts/research/glm53_flash/dogfood/paged_reference.py)) |

## Corrected termination (applies to both arms)

The paged loader built the tokenizer/processor without the checkpoint's eos ids, so the stream stopping set held only `<|endoftext|>` (154820); mlx-vlm's `stream_generate` never resets it from the model config (only `generate()` does). Every historical stream therefore ran past the model's end-of-turn marker `<|user|>` (154827) to `max_tokens`. The correction ([`stop_policy.py`](https://github.com/MahdiHedhli/PulsarMLX/blob/971db9c16f982f367d1759b5ccda03a506cf6672/scripts/research/glm53_flash/dogfood/stop_policy.py), policy `glm5-eos-v1`) installs the checkpoint's declared terminal set `[154820, 154827, 154829]` after verifying each id is a control token. Three historical prompts re-run on the real model terminate naturally in 7 / 5 / 11 tokens with pre-terminal greedy prefixes identical to history. **Removed tail generation is never reported as a throughput improvement**; all latency comparisons below use the same corrected policy in both arms. Caveat: the literal text `<|user|>` also encodes to 154827.

## Persistence semantics

Retained across requests: resident weights, expert slot tensors and their logical map, replacement-policy counters, read resources. Fresh for every request: the prompt cache (KV, sparse-attention, recurrent and convolution state), positions, generation state, detokenizer, cancellation/deadline state. Prefix reuse is off. Greedy token ids were identical to the fresh-process reference in every paired request of every block (G57: 3 blocks; G60: 6 blocks; G58: 120/120 tasks; mixed-warm subset 20/20).

## Request latency: cold vs warm store (128 generated tokens)

Ratio = persistent request latency (submit → completion, after load) ÷ fresh-process reference (`generate()` after load), paired per block; gain rule frozen before the runs: ratio ≤ 0.95 in every one of ≥ 3 blocks.

| Stratum | Ratios (blocks) | Verdict |
|---|---|---|
| cold first request (empty logical store) vs reference, S (25-token prompt) | 0.997 / 1.008 / 1.009 | parity, no regression (critical stratum) |
| exact repeat of S | 0.855 / 0.862 / 0.884 | **gain 12–14 %** |
| A-B-A return to S | 0.890 / 0.906 / 0.907 | **gain 9–11 %** |
| repeat of M (149-token prompt) | 0.948 / 0.968 / 0.952 | no gain under the rule (3–5 %) |
| confirmation on disjoint prompts (6 blocks): exact repeat S2 / A-B-A / M2-after-S2 | 0.848–0.876 / 0.871–0.897 / 0.890–0.925 | gains reproduced |
| sustained 512-token request (blocks 4–6) | 0.950 / 0.952 / 0.966 | no gain under the rule |

Mechanism: the gain is **prefill**. First token on S: 15.5–15.7 s on an empty store vs 7.4–8.8 s warm (fresh-process reference 15.6–16.1 s). **Decode stayed at 2.6–3.3 tokens/s in both arms** in every stratum (S ≈ 2.6, M ≈ 3.2, 512-token ≈ 2.95): the 60 GB budget holds ~35 % of the ~170 GB expert corpus, so decode is miss-bound and persistence does not change it. Session cost is reported separately: server load 2.1–2.3 s plus 5–10 s to readiness; reference load ≈ 2.2 s per process (page-cache warm) plus process start. Uncertainty: three-block spreads as shown; no interval beyond the spread is claimed. The 149-token M prompt is not long-context coverage.

## Quality retention (fresh sealed suite, 120 units)

Synthetic suite frozen before any run: 120 units, 5 domains × 24, 108 problem groups, prompts 27–121 tokens, `max_tokens` 256, greedy. Reference = fresh process per task; candidate = one cold-started persistent process over the sealed order.

- Identity: **120/120** task pairs token-identical through the terminal boundary; **120/120** natural terminations in both arms.
- Task score: **119/119 relative retention** (0 losses, 0 gains, 1 shared failure, 0 unusable, 0 timeouts); per domain 24/24, 24/24, 23/23, 24/24, 24/24.
- Groups: 107 reference-success groups, **107 retained**, 0 lost.
- Exact one-sided 95 % lower bound on retention: **0.9724** (= 0.05^(1/107)) under the declared independent-group binomial assumption.

Read this as **scope-limited relative retention of the persistent candidate against the fresh-process paged reference on a synthetic suite**. It is not a general "97.24 % accuracy", not a certification of the base model, and not a comparison against an original higher-precision checkpoint; grouping does not prove representativeness. The mixed-warm subset (20 tasks after priming the store with an unrelated prompt) was 20/20 identical to the sealed-order outputs.

## Soak (two separately reported segments; never stitched)

| | Segment 1 | Segment 2 |
|---|---|---|
| Schedule | frozen: 6 h or 240 requests, first wins | amended before the run: 6 h duration cap, request cap 400 |
| Duration / end | **4.31 h**, request cap | **6.03 h on one process**, duration cap |
| Admitted / completed / cancelled by design / failed | 240 / 222 / 18 / 0 | 335 / 309 / 26 / 0 |
| Sentinel (`What is 17 times 6?` → `102`) | 36/36 identical | 51/51 identical |
| Engine / watchdog failures | none | none |
| Compressor / swap | 1.02–1.06 GiB / 118.7 MiB flat | 1.00–1.02 GiB / 118.7 MiB flat |
| RSS (expert slots are Metal buffers outside RSS) | 10.8–15.8 GiB | 10.8–16.4 GiB |
| Latency drift | none (first- vs second-half medians equal per stratum) | none |

**Usability, separately from lifecycle health.** The client required a usable answer only for the strata S, B, S_append, S_edit, SENTINEL and SLOWCLIENT_S, and all of those were usable (segment 1: 56/56, 37/37, 19/19, 19/19, 36/36, 18/18; segment 2: 77/77, 51/51, 26/26, 26/26, 51/51, 26/26). The medium stratum **M (149-token prompt, 128-token cap, effort low) had 0/37 usable answers in segment 1 and 0/52 in segment 2**: every M request hit the cap inside its `<think>` block, as recorded before the soak in the pilot. So the soak establishes process/lifecycle health (no failed requests, sentinel parity, no trigger, flat memory), not answer usability for M at that cap. The 120-task quality run above is a different workload (256-token cap) with its own 120/120 natural terminations and is not evidence about the M soak stratum.

**Records vs tokens.** Ledgers count stream result records: 129 for a 128-token request under `length` (the last record repeats the final token) and 513 for 512; under `stop` the last record is the terminal token. Decode steps are 128 / 512. The quality scorer normalizes this before comparing ids.

## Lifecycle qualification (pilot)

A-B-A identical; streaming and non-streaming identical; history append/edit; client disconnect releases the worker in 0.5 s; queue bound (4 accepted with identical outputs, 2 rejected `503 overloaded` at 6 concurrent); slow consumer completes server-side; admission `400` above 2048 prompt tokens or 512 output tokens; health endpoints ≤ 2 ms during generation; a poisoned store makes the engine not-ready without automatic reload (fake-model test; no real poisoning occurred). Kept failure: the first server process aborted on its first request because MLX 0.32.2 binds a lazily `mx.load()`-ed array to the loading thread's stream; residents are now materialized at load.

## Scope and limitations

One host; defined request limits (prompt ≤ 2048 tokens, `max_tokens` ≤ 512, queue 4, one generation at a time); synthetic checks and a synthetic task suite; OS page cache observed, not controlled; no independently measured physical SSD bytes (store counters are logical/requested bytes); no M2 Max qualification; the request deadline cancels at the next token and does not interrupt a stall before the first token (a limitation, not a hard timeout); **no deployment authorization** — the candidate never replaced the default service. Legacy pruned-service restoration figures are operational appendix values and are excluded from every table here. Independent adversarial review of the whole graph: ACCEPT with two non-blocking findings (the deadline limitation above; a client plan bug that invalidated one confirmation stratum, which was rerun).

## Reproduction (source-pinned)

At commit `971db9c1`, with the retained repack directory (expert-contiguous layout, produced by the retained mlx-vlm `repack`) and the environment pins above:

```sh
python -u scripts/research/glm53_flash/dogfood/serve_offload.py \
  --offload <repack-dir> --expert-cache-bytes 60000000000 --max-expert-cache-bytes 60000000000 \
  --coalesce-gap 0 --write-mode per-expert --wire --read-workers 8 --read-chunk-mib 64 --prefill-step-size 256 \
  --stop-policy glm5-eos-v1 --max-prompt-tokens 2048 --max-output-tokens 512 --default-max-tokens 256 \
  --max-queue 4 --request-deadline-s 900 --host 127.0.0.1 --port 18080
```

The recommended budget is now **70e9** (see *Expert budget 70e9*): the same line with

```sh
  --expert-cache-bytes 70000000000 --max-expert-cache-bytes 70000000000
```

and the memory watchdog's ceiling raised from 80 GiB to 90 GiB; every other flag is unchanged. Two caveats belong with that line: the 70e9 soak exposure is 80 requests / 1.33 h against 335 requests / 6.03 h at 60e9, so the longer segment has not landed yet, and 80e9 (134 slots per layer) is **not** admitted on a 128 GB host.

`GET /readyz` → `{"ready": true}`; `POST /v1/chat/completions` (OpenAI-style; add `"pulsar_trace": true` for token ids, per-token times and store deltas). Fresh-process reference for one request: `paged_reference.py --offload <repack-dir> ... --messages request.json --log out.json` with the same flags (at `971db9c1` that script pins its admitted ceiling at 60e9 internally and refuses a 70e9 budget with `EXPERT_CACHE_OVER_BUDGET`; the 70e9 reference runs therefore went through `run_offload.py`, and the ceiling is being made an explicit `--max-expert-cache-bytes` flag in a separate commit). Offline tests: `scripts/research/tests/test_glm53_flash_stop_policy.py`, `test_glm53_flash_serve_offload.py` (fake model; the live HTTP tests need fastapi/uvicorn/httpx).

## Corrections

- 2026-09-20 (independent gpt-6-astra review, finding P2-FLASH-01): the G57 reference first-token times and reference decode rates in `persistent-serving-summary.json` had been copied from the G56 pilot references (15.35/15.35/15.36 s; 2.63/2.63/2.62 and 3.15/3.15/3.15 tok/s) instead of the G57 block references (16.05/15.61/15.64 s; 2.62/2.64/2.64 and 3.09/3.19/3.19 tok/s); corrected, strata now named explicitly. The paired latency ratios and verdicts were computed from the correct values and are unchanged.

## Expert budget 70e9 (2026-09-20)

A follow-on measurement round on the same host and the same source commit `971db9c1` (no code change) profiled decode at the accepted 60e9 budget, simulated the capacity curve, then ran a paired 60e9 → 70e9 ladder on the CLI and an admission round on the persistent server. Outcome: **70,000,000,000 B (117 slots per MoE layer) replaces 60,000,000,000 B (100 slots) as the recommended expert budget for this configuration on this host.** It is a flag change, reversible, and nothing was deployed.

### Where decode time goes at 60e9

Stage profile, S prompt, 40 decode tokens: 2.60 tok/s uninstrumented (385 ms/token); 2.48 tok/s (404 ms) with stage boundaries forced to evaluate — the instrumented run is diagnostic, not a throughput figure.

| Stage | ms/token | Share |
|---|---:|---:|
| cold expert reads | 266.7 | 66 % |
| host sync of the routing indices (42 ×) | 57.0 | 14 % |
| materialize (numpy → mx, in-place scatter, eval) | 34.6 | 9 % |
| `gather_qmm` compute | 35.0 | 9 % |
| slot policy (touch) | 3.8 | 1 % |

Decode is bound by ~2 serialized small cold reads per layer (3.0 ms per miss; 89.3 misses/token in the instrumented profile) plus the 42 host syncs. Read microbenchmarks with no model loaded put one cold 14.2 MB expert at 2.78 ms with 64 MiB chunks and 2.40 ms with 1 MiB (5.1 → 5.9 GB/s single-stream), two experts at 4.9 → 4.5 ms and four at 9.5 → 8.7 ms: these reads are latency-bound, not bandwidth-bound, so chunk tuning is worth ≤ 10 %. The lever is **fewer misses**, i.e. more slots.

### Simulated capacity curve

Exact LFU-decay replay of 7 retained gap-0 decode traces (the same policy the store runs). Per layer-step the decode miss count is P(0) = 0.22, mean 1.83, max 8; per token mean 77 (p50 75, p90 111), and the steady state equals the cold start (first/second half 72–91 vs 72–86).

| Slots / layer | Budget | Decode misses / token | Hit rate |
|---:|---:|---:|---:|
| 100 | 59.5 GB | 75.9 | 0.774 |
| 117 | 69.6 GB | 63.7 | 0.810 |
| 125 | 74.3 GB | 58.6 | 0.826 |
| 140 | 83.2 GB | 50.1 | 0.851 |
| 160 | 95.1 GB | 40.6 | 0.879 |

60e9 maps to 100 slots, 70e9 to 117 and 80e9 to 134.

### Measured 60e9 → 70e9 on the CLI (3 blocks × 6 prompts, paired, arm order alternated)

18 of 18 pairs complete. Same process shape in both arms; the only difference is the budget flag.

| Metric | Result |
|---|---|
| Identity | **18/18 token-identical** (same `tokens` sha in both arms of every pair) |
| Sustained decode (last half) | **+9.1 % … +17.4 %** per pair, mean **+13.4 %**; block means 1.129 / 1.140 / 1.133; every pair ≥ 1.091 |
| Decode tok/s, same six prompts | 60e9 **2.75–3.64**, 70e9 **3.06–4.20**; 512-token sustained prompt 2.75–2.80 → 3.10–3.12 |
| Decode misses / token | **−14.4 % … −18.6 %**, mean **−16.4 %** (simulated prior −16 % — the trace simulator is validated as a predictor) |
| Total request latency | **× 0.887 … × 0.954**; first token unchanged (× 0.991–1.041) |
| Peak MLX memory | 73.3–75.5 GB → 83.4–85.6 GB, i.e. **+10,107,224,064 B** — the slot-arena delta and nothing else (per-pair deltas span 10,107,061,398–10,107,226,392 B) |
| Memory gate | 38/38 runs ended `TARGET_EXITED`, **no watchdog trigger**, compressor growth 0 MiB, swap growth 0 MiB, 0 fill failures, no poisoned store |
| Worst host free memory | **4.61 GiB** at 70e9 (15.20 GiB at 60e9) — thin, and the reason the server needed its own admission |

80e9 (134 slots, a further +10.107 GB) would drive projected free memory below zero on this host and is **not admitted**.

### Persistent server at 70e9

The server was admitted separately because its own envelope (server RSS and the page cache from reference runs) is not the CLI's.

- **Lifecycle**: all ten pilot sequences pass exactly as at 60e9 (A-B-A isolation, stream/non-stream parity, history append and edit, cancel releasing the worker in 0.52 s, queue bound 4 accepted / 2 × `503 overloaded`, slow consumer, `400` admission refusals, health probes ≤ 2.1 ms during generation, test-seam reset forgetting 4914 = 117 × 42 experts and keeping identity).
- **Identity**: the pilot A-B-A token hash is `01db42d6f4b2`, the same hash the 60e9 pilot produced; the sentinel ids are the same tuple at both budgets; 12/12 soak sentinels identical.
- **Reference parity**: a fresh process with an empty store at 70e9 produced token ids identical to the server's for the sentinel, S and M prompts (identical even before the record-count normalization).
- **Soak**: 80 requests over 4792.8 s (1.33 h) on one process — 62 completed, 6 cancelled by design, **0 failed**, 0 non-200 records; no watchdog trigger; compressor 1.197 → 1.185 GiB (it fell), swap flat at 175.56 MiB; RSS 10.8–16.9 GiB with threads and fds flat; **minimum host free memory 5.65 GiB**; store residency reaches the full 4914 experts (69,561,483,264 B) and stays there, hit rate 74.6 % at the end.
- **Latency context** (not a gate): 10–13 % lower request latency on every stratum, e.g. S 55.48 → 48.81 s, M 68.66 → 60.85 s, sentinel 8.11 → 7.13 s; store hit rate 69.4 % → 73.8 % on the pilot.

Caveats carried with the admission: (1) the 70e9 soak exposure is 80 requests / 1.33 h against the 60e9 base of 335 requests / 6.03 h — a 6 h segment at 70e9 is the natural follow-up and has not run, so no production-shaped claim is made at 70e9; (2) macOS un-wires the MLX buffers while the server is idle (wired ~83.5 → ~3.1 GiB in idle samples, rising again on the next request) — the pages stay resident and the compressor stays flat; this is accounting, not release, and it is present at 60e9 too; (3) `paged_reference.py` at `971db9c1` hard-codes the 60e9 ceiling in its `verify_artifact` call and refuses a 70e9 budget, so the 70e9 fresh-process reference ran through `run_offload.py` (same loader, same store, same stop policy, byte-identical prompts); making that ceiling an explicit `--max-expert-cache-bytes` flag is a separate public commit.

### Streaming prefill: measured, negative, not a candidate

The hypothesis for a larger budget was to stop the prefill pass from writing into the slot store (`--prefill-mode stream`: read each wave's experts as transients, run the same three `gather_qmm` calls, drop them) and spend the reclaimed memory on slots. Under the frozen gates the result is **no gain**: the memory hypothesis passed (peak transient 3,385,655,296 B against a 4.0e9 B gate, store counters undisturbed), but **identity failed** — 3 of 6 prompts diverge, and the probe shows why: a layer differs exactly when its trailing stream wave holds fewer than 64 experts, because MLX's plain and sorted `gather_qmm` kernels are not bit-equal (max abs ≤ 0.125 in bf16, with argmax flips) and the baseline's `slots.size >= 64` rule selects the sorted kernel where the short wave selects the plain one. Prefill was also **slower**, not 1.5 × faster (block max 0.763 ×; first token 15.6 → 23.8 s on the short code prompt), because the stream path reads the same unique-expert byte set the slot path reads (52.8 vs 54.2 GB) and overlaps nothing; end-to-end it ran 1.07–1.32 × slower, with early decode 0.55–0.82 × over the first 8 tokens because a streamed prefill admits nothing to the decode store. Finally the premise itself was stale: with per-expert slot writes the **baseline's** own prefill transient at 60e9 is ≤ 2.6 GB, worth ≤ 4 slots per layer, so even a perfect stream prefill could not have bought a meaningful budget increase. The work is retained on its branch, default-off, and is **not a candidate**; a correct stream path would have to reproduce the baseline's geometry and kernel selection exactly.

### Two levers that do not reduce I/O

- **Speculative / union batching.** Verifying k consecutive tokens in one forward pass, scored at the full-acceptance upper bound, needs the union of their experts: at k = 2 that union is **13.8–14.1 of 16** per layer, and misses/token move only 80.7 → 79.3 at k = 4. Top-8-of-288 routing gives almost no overlap between adjacent tokens, so there is nothing to amortize.
- **Request batching.** Two concurrent requests amortize 0.77–0.79 — i.e. they produce *more* total misses than running one at a time.

Both are recorded as measured negatives, not as untested ideas.
