# Qwen3.8 runtime execution gate (not yet authorized)

Status: source review and command design only, 2026-10-04 UTC. No checkpoint Python was imported; no package was installed; no model forward, benchmark, or numerical parity run occurred. This plan applies to the one pinned checkpoint in [checkpoint admission](checkpoint-admission.md) and leaves the Studio GLM qualification worktree alone.

## Source and package pins

Use the checkpoint's verified 35,046-byte `qwen4_exp.py` (Git blob SHA-1 `433dbf15299d2793a7167ad5c97a374c194609d8`), corresponding to [PipeNetwork port `0352280b`](https://github.com/PipeNetwork/qwen38-flash-next-mlx/tree/0352280b927a731fd35276ac622ef2f28da5c936). Its imports and top-level AST were inspected without import. Eight centered norm families are already folded in the acquired converted weights; use their stored multipliers unchanged. Add one exactly once only for a separately admitted raw HF layout. Fix n-gram hash seed 1234, exact DeltaNet L2 q/k normalization, and causal sparse attention across the 2048-token indexer boundary before claiming numerical parity.

Proposed separate Python 3.13.13 environment, with **direct pins**, not a completed dependency lock:

| Package | Pin | Reason |
| --- | --- | --- |
| `mlx`, `mlx-metal` | `0.32.0` each | Meets port floor; Apple Silicon/macOS 26 wheels exist. |
| `mlx-lm` | `0.31.3` | Non-yanked release; needed `mlx_lm` port symbols present in this tag. |
| `numpy` | `2.4.5` | Present in existing Pulsar virtual environment; meets port floor. |
| `transformers` | `5.16.0` | Port's tiny-reference version; this release requires Hub 1.5+ and Safetensors 0.8+. |
| `huggingface-hub` | `1.5.0` | Satisfies Transformers 5.16 (`>=1.5,<2`). |
| `safetensors` | `0.8.0` | Satisfies Transformers 5.16 (`>=0.8`). |
| `tokenizers` | `0.23.1` | Satisfies Transformers 5.16 (`>=0.23.1,<0.24`). |

Before installation, resolve and hash-lock every transitive package (including `sentencepiece`, `protobuf`, `PyYAML`, `Jinja2`, and the remaining Transformers/Hub dependencies) for arm64/Python 3.13, verify wheel identity against the package indexes, and keep the environment outside the existing Pulsar `.venv`. Do not mix with system MLX 0.31.2, below the port's minimum. The published port's lower-bound `requirements.txt` is insufficient as a lock. No install command is approved by this document.

The [`mlx-lm` 0.31.3 loader](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/utils.py) first applies `mx.load` to **all** `model*.safetensors`, then imports and executes the `config.json` `model_file` through `spec.loader.exec_module`; with default `lazy=False`, it evaluates all parameters. `lazy=True` delays evaluation but does not implement a bounded pager. The [generate CLI](https://github.com/ml-explore/mlx-lm/blob/v0.31.3/mlx_lm/generate.py) passes `--trust-remote-code` to tokenizer configuration, not this model-file execution. Its stock full-checkpoint path is blocked on 64 GiB even for one output token. The model card's `load(..., trust_remote_code=True)` example is also incompatible with this tag's `load` signature. These are source-level observations, not runtime experiments.

## Exact safe smoke and resource gate

The only currently safe checkpoint smoke on this machine is static inspection, using the repository's standard-library-only checker. In the isolated Qwen worktree, run:

```sh
python3 -B scripts/research/admit_qwen38_static.py \
  --dest /Users/mhedhli/Documents/Codex/2026-10-03/task/models/Qwen3.8-Flash-Next-MLX-mixed-4_8bit-b2c422f3
```

Expected: 25 verified files in the acquisition receipt, 11 shards, 3,215 tensors, 148 centered norm tensors, no raw-HF markers, and `checkpoint_code_executed: false`. This checker does not import MLX or the bundled model. Reconfirm the manifest digests before an execution session; do not duplicate the 98.924 GiB repository. Stop if any checksum, size, header span, dtype, quantization triple, tokenizer stop ID, model-file hash, or norm convention differs.

For a later **runtime** smoke, first review and authorize an actual layer/expert pager and its instrumentation. There is no safe full-checkpoint inference command on this host today; adding `--max-tokens 1`, `lazy=True`, or `mx.set_memory_limit` to the stock loader does not meet the gate. The pager must allocate model weights on demand, exclude the unused vision tower, and prove that evicted weights release their MLX resources. Start with a synthetic tiny model only after package/code approval, then one greedy request of at most 64 prompt tokens and four output tokens; test the EOS boundary and 2050–2080-token sparse-prefill case separately. Freeze tokenizer output IDs, both stop IDs (248046, 248044), deterministic sampling, and route/logit probes before comparing arms.

Provisional physical-memory split: 40 GiB maximum resident model-weight/cache allocation; 8 GiB maximum measured runtime, KV, activation, and I/O staging allocation; 16 GiB left for macOS and other processes. **48 GiB is a total Qwen-process gate, not a weight-cache target.** The 64 GiB physical total is 68,719,476,736 bytes. The full 98.924 GiB repo and approximate 29.8 GiB n-gram portion imply routed experts and other tensors also need paging. Because [MLX `set_memory_limit`](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.set_memory_limit.html) is advisory and [`set_wired_limit`](https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.set_wired_limit.html) addresses only wired allocations, enforce the gate by sampling process resident footprint, MLX allocations, `vm_stat`/memory pressure, swap used and swap delta, and outstanding I/O buffers. Gate admission on available physical headroom before any weight load, and stop on process total >48 GiB, weight/cache >40 GiB, staging/runtime >8 GiB, any sustained swap growth or memory-pressure transition, failed bounded allocation, unexpected tensor materialization, or any mismatch in token IDs/logits/routing. Halt before latency sweeps if the first single-request packet fails. The sampling period and thresholds require calibration with an implementation; observations after allocation cannot make the stock full loader safe.

## Baseline and target

First qualify tiny-model calculations against an independently pinned Transformers 5.16 fixture. Then qualify the acquired converted checkpoint against a no-prefetch **paged** MLX compatibility arm on this M2, after proving residency. A stock, unmodified MLX baseline may be captured on a separate adequately sized host with the same checkpoint and package lock; it is not the M2 memory baseline. Record logits, routing IDs/weights and output IDs, then split TTFT and decode latency, cache warmth, useful/late/wasted bytes, and separately attributed physical SSD reads. The [trace contract](trace-contract.md) specifies request and completion accounting. Only after numerical parity and stable no-prefetch behavior compare I/O-only routing hints, with demand precedence and a bounded staging pool. The desired sustained 20+ tokens/s is an experimental target, with no prediction that this hardware will reach it.
