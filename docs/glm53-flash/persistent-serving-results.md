# GLM-5.3-Flash unpruned persistent paged serving — results (2026-09-20)

Compact results of the persistent-serving research round (private graph G52–G61, 2026-09-19/20). Machine-readable values: [`persistent-serving-summary.json`](persistent-serving-summary.json); claim/source manifest: [`persistent-serving-manifest.json`](persistent-serving-manifest.json). Nothing here is a production claim; see *Scope and limitations*.

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

`GET /readyz` → `{"ready": true}`; `POST /v1/chat/completions` (OpenAI-style; add `"pulsar_trace": true` for token ids, per-token times and store deltas). Fresh-process reference for one request: `paged_reference.py --offload <repack-dir> ... --messages request.json --log out.json` with the same flags. Offline tests: `scripts/research/tests/test_glm53_flash_stop_policy.py`, `test_glm53_flash_serve_offload.py` (fake model; the live HTTP tests need fastapi/uvicorn/httpx).

## Corrections

- 2026-09-20 (independent gpt-6-astra review, finding P2-FLASH-01): the G57 reference first-token times and reference decode rates in `persistent-serving-summary.json` had been copied from the G56 pilot references (15.35/15.35/15.36 s; 2.63/2.63/2.62 and 3.15/3.15/3.15 tok/s) instead of the G57 block references (16.05/15.61/15.64 s; 2.62/2.64/2.64 and 3.09/3.19/3.19 tok/s); corrected, strata now named explicitly. The paired latency ratios and verdicts were computed from the correct values and are unchanged.
