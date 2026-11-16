# DPF-001 — M2 iPad prefill proof of concept

**Run dates:** 2026-10-10–11\
**Decision:** The M2 iPad contributes useful prefill compute over the direct USB connection. **Go for a bounded validation experiment; no-go for PulsarMLX runtime integration yet.** This PoC is complete and the test services have been stopped.

## Fixed setup

- Mac: M2 Max MacBook Pro, 38 GPU cores, 64 GB RAM. iPad: 12.9-inch Pro (6th generation, M2), iPadOS 26.2.1, 16 GB RAM inferred from the 1 TB configuration.
- Direct cable: macOS reports the iPad on a built-in USB 3.1 bus at **10 Gb/s**. The live `en28` link-local wired interface answered 20/20 ICMP probes. This is USB networking, not a 40 Gb/s Thunderbolt peer link. CoreDevice file-service measurements are in the [initial feasibility note](DPF-001-ipad-prefill-feasibility.md); they are not Backburner socket throughput.
- Backburner source: `c03893748386a65c6a7312be39659c9d35026de3`; its pinned llama.cpp fork: `1839b78175d4f89f74023a2ced04f4e558abc4d4`. No PulsarMLX runtime files were changed.
- Backburner's split prefill activates only for `LLM_ARCH_QWEN35` in this fork. The locally available Gemma GGUF cannot exercise it. A [Qwen3.5 4B Q4_K_M GGUF](https://huggingface.co/twoody/Qwen3.5-4B-GGUF) was downloaded to the external scratch volume for this expanded PoC (2,783,446,880 bytes), with SHA-256 verified against the publisher's value: `b7508d8b4a652bc020a439aafdd4ce1527d49774865ce3334a43b16dbeaa90ca`. Its metadata reports `qwen35`, width 2,560, 32 trunk layers plus one unused MTP layer, and full attention interval 4.
- The existing `split-gguf.py` generated a headless tail for layers **[24, 32)** (8 trunk layers, 0.56 GB of tensors). The tail metadata, tensor count, and lack of token/output head tensors were checked. No model or build files were placed in the repository.
- Backburner's local `tests/security/run.sh` passed: cable policy 71/71, tunnel tests 22/22, sensitive-file checks 45/45, and listener lint. Live exposure results and a busy-session limitation are below.

## Mac-only baseline — measured

Pinned fork `llama-server`, same quantized model, `-ngl 999 -fa on -c 8192 -np 1 -ctk q8_0 -ctv q8_0 -b 4096 -ub 256 -t 2 -tb 2 --cache-ram 0 --ctx-checkpoints 0`, bound to `127.0.0.1`. Raw `/completion` requests used a fixed synthetic prompt, `n_predict=32`, temperature 0, seed 42, `cache_prompt=false`; each reported `cache_n=0`. One warm request per prompt length was excluded. Results are from three single-request repetitions per length; model-load and server startup time are excluded.

| Prompt tokens | Prefill times (ms) | Median (ms) | Median rate | Output stability |
| ---: | --- | ---: | ---: | --- |
| 2,014 | 4020.0, 4186.2, 4020.0 | **4020.0** | 501 tokens/s | 3/3 exact text match |
| 4,014 | 8368.3, 8340.1, 8433.7 | **8368.3** | 480 tokens/s | 3/3 exact text match |

The full per-request JSONL data and the tiny benchmark client are in `DPF-001-poc-20261010/` on the external scratch volume. These timings are for this 4B model and pinned fork; they are not PulsarMLX measurements.

**Model-specific transfer bound (estimate):** A 256-token f32 boundary residual at width 2,560 is **2.5 MiB**. At the observed 10 Gb/s USB physical rate, its byte-only one-way floor is **2.1 ms**. Remote KV/recurrent-state traffic adds to this. The application and worker measurements below supersede the earlier unknowns.

## Direct comparison — measured on October 11

A device-targeted build registered the iPad and generated a development profile that includes it. The signature verified, including `com.apple.developer.kernel.increased-memory-limit`; `devicectl` installed and launched the existing Backburner app. No iPad application was authored for this test. The earlier unsigned archive was rejected by the stock iPad and produced no inference result.

The split server used the baseline flags plus `LLAMA_SPLIT_TAIL`, `LLAMA_SPLIT_L=24`, `LLAMA_SPLIT_MIN=512`, `LLAMA_SPLIT_ONE_BATCH=1`, and `LLAMA_SPLIT_VERBOSE=1`. Today’s servers were restricted to loopback, used a temporary API key, and restricted CORS. The Mac still retains the full model and executes decode locally. Model loading, tail transfer, and server startup are excluded from prefill times.

| Prompt tokens | Mac alone, rerun median | Mac + iPad median | Prefill time reduction | Throughput increase | Total request wall time, Mac → split |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2,014 | 4,020.6 ms | 3,160.4 ms | **21.4%** | **27.2%** | 4.656 → 3.817 s |
| 4,014 | 7,914.0 ms | 6,349.4 ms | **19.8%** | **24.6%** | 8.609 → 7.053 s |

Three measured requests per cell; one warm request per length excluded. Split samples were **2811.1 / 3231.6 / 3160.4 ms** and **6349.4 / 6304.3 / 6367.7 ms**. The Mac rerun samples were **4020.6 / 3887.9 / 4022.0 ms** and **7801.3 / 7914.0 / 8157.8 ms**. The Mac’s 4k median changed by 5.4% from the previous day, so the table uses today’s lower baseline.

The logs confirmed layers **[24,32)** on the iPad, **7 remote chunks** for 2,014 tokens and **15** for 4,014; the final partial chunk stayed local. The iPad counter reached **162 chunks** across the main run, fresh-prompt check, and repeat. This was actual remote computation, not silent fallback. All main-run and repeat 32-token output prefixes were exactly the same text, and every request reported `cache_n=0`. These include the model's thinking prefix; they do not establish completed-answer, numerical-state, or long-generation correctness.

A second split run, after the Mac rerun, used two measured repetitions per length: **2464.1 / 3020.1 ms** for 2k and **6120.3 / 6191.1 ms** for 4k. A fresh, numbered-record prompt of **2,068 tokens** took **2912.9 ms Mac-only vs 2620.5 ms split**, a **10.0%** reduction, with identical text. This fresh comparison is one pair, with different server histories.

**Material limitation:** the excluded first 2k request on today’s Mac server took **2452.6 ms**, faster than the initial split warm request (**2904.5 ms**). The cause of first-request and subsequent timing differences was not isolated. The evidence establishes a gain in these repeated tests and the fresh paired sample; it does not establish a universal 20% gain or improved cold-request latency. No statistical confidence interval, varied production workload, long existing context, or sustained thermal soak was tested.

## Transport, memory, and exposure — measured

- **Application transfer:** the initial HTTP fetch failed while the iPad’s local-network permission was pending. After the user granted it, the same transfer succeeded: **573 MB in 1.1 s, 525 MB/s** (approximately 4.2 Gb/s). This is one large Mac→iPad file transfer over the app’s cable service, including its file write; it is not a bidirectional activation-protocol benchmark.
- **Control round trip:** 30 TCP-connect + `mem` request + complete JSON response samples gave **1.650 / 1.938 / 5.359 ms min/median/max**. This includes connection setup and app work, and cannot be compared directly with Backburner’s published 16-byte persistent-socket RTT.
- **Representative boundary payload:** a **2.5 MiB** synthetic f32-sized payload (`256 × 2560 × 4`) transferred through the existing HTTP fetch service in **51.100 / 28.558 / 29.036 ms**, median **29.036 ms**. HTTP setup and file handling dominate this small transfer. At the measured large-file rate, byte serialization alone would take about **5.0 ms**; that is a derived estimate, not a measured split-socket transfer time.
- **Remote stage:** after the first 806 ms worker chunk, logged iPad compute was approximately **270–299 ms per 256-token, 8-layer chunk**. Initial pipeline waits reached 832 ms; subsequent main-run waits were 0–3 ms. Tail-state merges took **65–159 ms per prompt** across both split runs. These are worker/server-reported timings, not independent wire captures.
- **Memory and heat:** the lowest reported remaining app allocation budget was **16,157 MiB**, peak process footprint **227 MiB**, and peak total system wired memory **1,915 MiB**. Metal allocations also affect system wired memory, so the small footprint is not the tail’s total memory use. Every sampled iPad thermal state was **0 (nominal)**. The short repeat found no thermal warning; it does not prove a fanless iPad’s long-duration rate.
- **Network exposure:** with no active tail client, the live checker passed **13 checks**, with the unpaired authenticated-tunnel test skipped. All four raw services rejected Wi-Fi traffic, denial counters increased, no tested Bonjour service was advertised, and the unpaired tunnel was closed. During an active tail session, the tail Wi-Fi probe remained **silent** rather than closing promptly; two checker assertions failed. After disconnecting the Mac client, all checks passed again. Source shows a serial accept loop with the cable filter before protocol reads. No unauthorized response bytes were observed, but prompt rejection/backlog behavior while busy remains a hardening and validation item before integration. See `exposure-final.txt` and `exposure-idle.txt`.

## Pipeline interpretation — estimates, not further measurements

The published GPU/core and bandwidth proxies in the [feasibility note](DPF-001-ipad-prefill-feasibility.md) suggested about one-quarter to three-tenths of the Mac’s capacity. The actual 8-layer worker time is more useful for this model, and shows why a 25% tail can overlap the Mac’s 75% head. The aggregate data does not establish a general M2/M2 Max compute ratio.

For plausible splits, assume a **500 ms full-Mac chunk**, similar layer cost, an illustrative effective iPad per-layer rate **r=0.45**, **5 ms boundary transfer**, and **100 ms state merge per request**. The rate is a rough fit to the measured chunk times, not a hardware specification. For tail fraction `f`, use `M=500(1-f)` and `I=500f/r+5` ms. A simplified schedule with `N−1` remote chunks and a local final chunk takes `max((N−1)M+500, M+(N−1)I)+100` ms.

| iPad tail | Estimated Mac stage | Estimated iPad stage + boundary | Estimated 8-chunk / 16-chunk completion | Estimated speedup vs Mac |
| ---: | ---: | ---: | ---: | ---: |
| 4/32 layers | 438 ms | 144 ms | 3.66 / 7.16 s | 1.09× / 1.12× |
| **8/32 (tested)** | 375 ms | 283 ms | 3.23 / 6.23 s | 1.24× / 1.29× |
| 12/32 layers | 313 ms | 422 ms | 3.36 / 6.74 s | 1.19× / 1.19× |

Only the 8-layer split was benchmarked. This arithmetic explains the observed order of magnitude; unequal hybrid layers, graph history, clocks, prefix mirroring, and traffic overlap can invalidate the other rows. There is enough evidence to stop this PoC without searching for an optimal split.

## Decision and remaining proof

1. **Usable wired transport? Yes:** direct 10 Gb/s USB networking, working app sockets, and 525 MB/s for the large file. Thunderbolt capability does not imply a 40 Gb/s application link on this connection.
2. **Enough compute to offset transfer? Yes for this tested Qwen3.5-4B split:** remote chunks ran and complete prefill, including state merge, was faster in the measured comparisons.
3. **Realistic improvement?** The main repeated samples showed about **20–21% shorter prefill**, or **25–27% higher prefill throughput**; the fresh paired sample showed **10% shorter prefill**. Initial-request behavior can regress. These are bounds on observed cases, not predictions for PulsarMLX, other models, or sustained operation.
4. **Smallest next experiment:** retain this app and model, alternate Mac-only/split runs over several distinct 2k/4k prompts and an appended prompt at realistic existing context, verify token or logits parity, and run continuously for 10–15 minutes while recording temperatures and both stages. Also check prompt Wi-Fi denial while the worker is occupied. No new framework is needed to answer these questions.
5. **Proceed or stop?** **Stop this completed PoC. Go only for that bounded validation if pursued; no-go for PulsarMLX runtime integration yet.** The transport/compute premise is now demonstrated, while workload generality, sustained behavior, and busy-session network handling remain unproved.

Evidence remains local under `DPF-001-poc-20261010/` on the external scratch volume: `results.jsonl`, `fresh-results.jsonl`, both split logs, Mac rerun log, transfer/RTT files, and benchmark clients. The test Mac server and iPad app process were stopped; the provisioned app and tail remain installed. No PulsarMLX runtime changes, commits, or merges were made by this PoC. The repository has unrelated pre-existing changes which were left untouched.
