# Qwen3.8 Flash Next paging research (preparation only)

**Branch:** `research/qwen38-strata-pager-m2-20261003`

**Base:** `2d388856593b96a136fa5a6036c0e973919cedff` (`main`, accepted by the Studio Pulsar task after CI run `37153564019`; fetched on this M2 host and verified equal to `origin/main` on 2026-10-03). Recheck the remote and accepted main before integration.
**Strata source pin:** [`99f3dbd0b21d1401b3769e0c0d963913607f380b`](https://github.com/Niko1221/Strata/tree/99f3dbd0b21d1401b3769e0c0d963913607f380b). This is source research, not executed or copied code.

## Evidence and transfer boundary

- Strata's [`FileExpertSource::prefetch`](https://github.com/Niko1221/Strata/blob/99f3dbd0b21d1401b3769e0c0d963913607f380b/src/core/expert_source.cpp) stages selected expert blobs and skips copies already resident in its RAM complement. Its [generation program](https://github.com/Niko1221/Strata/blob/99f3dbd0b21d1401b3769e0c0d963913607f380b/src/program/generate.cpp) exposes profile-ranked residency and adaptive cache controls. These are scheduling leads for a separate MLX implementation, not a portable backend or an Apple throughput result.
- The proposed first transfer is **I/O-only routing lookahead**. Predicted routes may request pages; only the real router selects experts and weights for computation. Hints must not change arithmetic, checkpoint bytes, tensor interpretation, or output placement.
- Keep demand reads ahead of hints, cap outstanding requests and staging bytes, invalidate stale hints, and retain each buffer until its I/O and any GPU use finish. A later MLX implementation must prove these properties at actual asynchronous completion boundaries; the synthetic validator only defines the trace contract.
- Pulsar's [GLM-5.3 Flash negative result at `fb1e69f2`](https://github.com/MahdiHedhli/PulsarMLX/blob/fb1e69f2/docs/glm53-flash/persistent-serving-results.md) found four-token union misses per token of 80.7 versus 79.3 at a full-acceptance upper bound. Streamed prefill was slower and broke output identity. Do not assume speculation or prefill streaming will fix SSD misses on Qwen.
- Strata's CUDA/HIP and x86 kernels, mixed IQ/codebook formats, and SSD results are not interchangeable with MLX affine weights or M2 Max results. Keep its MIT notices if any code is later ported. Check the checkpoint's separate terms before acquisition.

## Host and capacity at reconnaissance

M2 Max MacBook Pro: 12 CPU cores, 38 GPU cores, 64 GiB unified memory, macOS 26.6.2. Internal Data volume free: 213,261,480 KiB (203.38 GiB) on 2026-10-03; this is not reserved. No Qwen3.8 weights were found in the checked internal Models directory, Hugging Face cache, or project paths. The two PulsarMLX model entries are symlinks to an unmounted external volume.

The published [checkpoint card](https://huggingface.co/pipenetwork/Qwen3.8-Flash-Next-MLX-mixed-4_8bit) reports 106.2 decimal GB on disk; the delegated 32 decimal GB n-gram budget remains an estimate until the shard catalog is inspected. Offloading only that estimate leaves 74.2 GB = 69.1 GiB resident, about 5.1 GiB beyond physical memory before all other allocations. The later [checkpoint admission audit](checkpoint-admission.md) records the newer disk snapshot and acquisition plan.

## Admission before a real-model run

1. Verify a clean, accepted `main` SHA with the Studio cleanup owner. This branch is isolated; no worktree pruning or GLM qualification change is part of the spike.
2. Use the [checkpoint admission audit](checkpoint-admission.md) for the now-verified pinned copy, file hashes, tensor names/shapes, quantization, tokenizer, license and stored norm-fold convention. A GGUF mixed-IQ result is not an MLX affine parity reference after requantization.
3. Establish an independent reference for routing IDs and weights, layer outputs, logits, and token IDs, with frozen tolerances. Record a no-prefetch baseline before timing any pager variant.
4. Hold prompt, context, stop policy, seed/greedy setting, checkpoint, quantization, and output length fixed across baseline and candidate. Separate cold startup, logically empty cache, and OS-warm page cache. Capture physical SSD traffic independently from logical store counters.
5. Compare routing-lookahead I/O alone first, then adaptive residency as a separate experiment. Record useful bytes present before demand, wasted bytes, cache pollution, per-request latency, TTFT, decode p50/p95/p99 and maximum stall, swap, and memory footprint. The 20+ sustained tokens/s goal is a target without a forecast. A 10% end-to-end benefit with no correctness regression or sustained swap/p95 harm is a **proposed** keep threshold, not an adopted gate.

The one pinned checkpoint copy was acquired and statically admitted on 2026-10-04 UTC. No checkpoint code was executed, benchmark run, or real-model numerical compatibility claimed. See the [receipt and admission evidence](checkpoint-admission.md#acquired-files-and-static-admission).
