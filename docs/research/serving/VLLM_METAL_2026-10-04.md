# vLLM Metal: serving research for PulsarMLX

Checked 2026-10-04. This is a source review and an experiment proposal, not a
roadmap decision, deployment approval or measured PulsarMLX comparison. No
vLLM installation, benchmark or serving change accompanied this note.

## Source pins

- Upstream stable release: [vLLM Metal v0.30.0](https://github.com/vllm-project/vllm-metal/releases/tag/v0.30.0),
  published September 23, 2026, commit
  `15f0b215c89825928ac796ab8face335f714163f`. The release tracks vLLM 0.30.0
  and pins MLX 0.32.1.
- Upstream performance context: [September 22 announcement](https://vllm.ai/blog/2026-09-22-vllm-metal-v0-28-0).
  Its measurements describe earlier releases and workloads; they are not
  v0.30.0 measurements on our hardware.
- PulsarMLX design and implementation inspected at
  `8932939e9db0ceaa05337db8c65f5c1c03fa94fa`, with the inherited main baseline
  `2d388856593b96a136fa5a6036c0e973919cedff`.

## What vLLM Metal supplies

The announcement describes vLLM's V1 scheduler, chunked prefill, paged KV and
OpenAI-compatible frontend around mlx-lm model execution. Packed token batches
and custom paged attention permit mixed prefill/decode work.

The v0.30.0 release states that vLLM owns allocation and physical layout of
scheduler-managed KV/state caches; Metal consumes zero-copy MLX views. It also
reports a zero-copy MLX/PyTorch DLPack bridge. These are cache/tensor ownership
claims, not proof of zero-copy SSD-backed weights.
[Release](https://github.com/vllm-project/vllm-metal/releases/tag/v0.30.0)

Source inspection confirms the worker passes scheduler output to the model
runner and initializes its KV cache from vLLM's cache configuration:
[`worker.py`, lines 183–254](https://github.com/vllm-project/vllm-metal/blob/15f0b215c89825928ac796ab8face335f714163f/vllm_metal/v1/worker.py#L183).
The separate cache policy budgets scheduler-visible attention/state storage:
[`cache_policy.py`](https://github.com/vllm-project/vllm-metal/blob/15f0b215c89825928ac796ab8face335f714163f/vllm_metal/v1/cache_policy.py).
The runner is the execution integration surface:
[`model_runner.py`](https://github.com/vllm-project/vllm-metal/blob/15f0b215c89825928ac796ab8face335f714163f/vllm_metal/v1/model_runner.py).

## Oversized weights remain a separate problem

In the ordinary single-stage lifecycle, `lazy_weights` is false; laziness is
enabled for pipeline stages that prune non-owned layers. The text loader
passes that value to `mlx_lm_load`. This is a default eager model-loading
contract, not PulsarMLX's bounded expert-range contract.
[`model_lifecycle.py`, lines 101–120 and 350–365](https://github.com/vllm-project/vllm-metal/blob/15f0b215c89825928ac796ab8face335f714163f/vllm_metal/v1/model_lifecycle.py#L101)

No bounded expert or per-layer-embedding (PLE) SSD cache/admission interface was
identified in the inspected lifecycle, worker, runner and cache-policy paths.
This is a scoped inspection result, not a claim about every upstream extension.
Paged KV addresses request state capacity; it does not, by itself, admit an
approximately 182 GB checkpoint on a 128 GB host. Model-specific PLE paging,
where applicable, must be established explicitly; it is not inferred as a
GLM-5.3 Flash feature from this review.

## Our serving architecture: plan versus implementation

The [strategy at the inspected commit, lines 137–151](https://github.com/MahdiHedhli/PulsarMLX/blob/8932939e9db0ceaa05337db8c65f5c1c03fa94fa/docs/roadmap/PULSARMLX_STRATEGY.md#L137)
plans Rust ownership of catalogs, reads, admission, residency, prefetch,
routing, model state, generation, cancellation and serving. Dense execution
uses a narrow MLX bridge; qualified compressed expert kernels may use Metal.
[Stage F, lines 219–223](https://github.com/MahdiHedhli/PulsarMLX/blob/8932939e9db0ceaa05337db8c65f5c1c03fa94fa/docs/roadmap/PULSARMLX_STRATEGY.md#L219)
places OpenAI-compatible serving after a stable local runtime.

The inherited [`pulsar-serve`](https://github.com/MahdiHedhli/PulsarMLX/blob/8932939e9db0ceaa05337db8c65f5c1c03fa94fa/crates/serve/src/main.rs#L13)
is Linux/CUDA-only. Its sequential accept loop is at line 209. Although its
opening comment says prefill starts from zero, the actual code at lines
186–208 and 1357–1389 retains prefix history and can restore/rewind recurrent
state. This is not an implemented native Apple serving layer.

The [Flash persistent research server results](https://github.com/MahdiHedhli/PulsarMLX/blob/8932939e9db0ceaa05337db8c65f5c1c03fa94fa/docs/glm53-flash/persistent-serving-results.md#L26)
describe source `971db9c16f982f367d1759b5ccda03a506cf6672`: Python/MLX,
one generation at a time, bounded queue four. Resident weights, expert slots,
maps and read resources persist; prompt KV, sparse-attention, recurrent,
convolution and generation state are fresh per request. Prefix reuse was off.

Generic [backend contracts](https://github.com/MahdiHedhli/PulsarMLX/blob/8932939e9db0ceaa05337db8c65f5c1c03fa94fa/crates/backend/src/runtime.rs#L199)
exist, but no vLLM adapter contract or roadmap commitment was found in the
inspected design/specification paths. The server's vLLM/SGLang comment at
line 1420 concerns a client reasoning-control field, not backend integration.

## What performance claims do and do not transfer

The announcement's main serving comparisons emphasize concurrent agent
requests on M5 Pro, including multi-turn/prefix reuse. Its NAX prefill path is
M5-specific; earlier Macs use another path. Its roughly 20% MTP output-rate
gain at concurrency one is one Gemma 4 experiment, not GLM or Qwen evidence.
[Announcement](https://vllm.ai/blog/2026-09-22-vllm-metal-v0-28-0)

The [pinned model matrix](https://github.com/vllm-project/vllm-metal/blob/15f0b215c89825928ac796ab8face335f714163f/docs/supported_models.md#L72)
lists Qwen3 and Qwen3-Next families. A family listing does not qualify our exact
checkpoint, tokenizer, mixed quantization or Flash Next semantics. GLM-5.3
Flash is not listed. The release warns that hybrid GDN prefix-cache on/off
parity still diverges on some divergent-suffix prompts.
[Known boundaries](https://github.com/vllm-project/vllm-metal/releases/tag/v0.30.0)

## Integration choices for future evaluation

| Choice | Work and interpretation |
| --- | --- |
| Separate resident baseline | Lowest integration effort for an already supported checkpoint that fits memory. Measures serving behavior without substituting for oversized-weight research. |
| Pulsar expert/PLE storage inside the runner | Substantial model and storage integration. Preserve checked ranges, quantization, cache identity, admission, slot lifetime and GPU fences; coordinate with scheduler-owned request state. |
| Custom vLLM worker adapter over Pulsar execution | High effort: explicitly translate scheduling, positions, state/block tables, cancellation, results and ownership. An OpenAI-compatible API alone is insufficient. |
| Retain native Pulsar engine and port qualified ideas | Fits the current plan. Borrow scheduling or attention ideas only behind independent correctness and measured-benefit gates. |

These are research options, not selections. Rust's
[dispatch ownership contract](https://github.com/MahdiHedhli/PulsarMLX/blob/8932939e9db0ceaa05337db8c65f5c1c03fa94fa/docs/architecture/contracts/f017-f018-native-kernel-boundary-v1.md#L24)
resolves identity, admission and residency before dispatch, and prevents slot
reuse until GPU completion. A vLLM integration must avoid duplicate weight
owners and competing unified-memory budgets. Per-request retained state needs
complete KV, sparse-attention, recurrent and convolution isolation; prefix
matching, eviction, cancellation and restoration require separate tests.

Request batching can increase the union of cold experts and SSD traffic.
Our [retained Flash negatives, lines 170–175](https://github.com/MahdiHedhli/PulsarMLX/blob/8932939e9db0ceaa05337db8c65f5c1c03fa94fa/docs/glm53-flash/persistent-serving-results.md#L170)
support measuring this explicitly. They do not establish a universal batching
penalty or negate resident-model vLLM results.

## Proposed first comparison

Use the exact same resident checkpoint revision, tokenizer/chat template,
quantization, prompts, stopping rules, greedy sampling and hardware budget.
Disable speculation and prefix reuse initially. Start at concurrency one,
then two and four. Record TTFT, per-request decode rate, aggregate throughput,
p95 latency, completion/refusal/cancellation counts, peak memory, compressor
and swap. Define numerical/token/state parity before timing.

A separate oversized SSD experiment must additionally freeze source/range
identity and measure requested versus physical bytes, cache hit/miss rates,
read amplification, staging memory and GPU lifetime. It must preserve full
hybrid state semantics. Re-admit budgets on M1 Ultra and M2 Max independently;
do not transfer M5 or resident-model claims to them.

The [optimization register, OPT-01 through OPT-08](https://github.com/MahdiHedhli/PulsarMLX/blob/8932939e9db0ceaa05337db8c65f5c1c03fa94fa/docs/roadmap/OPTIMIZATION_ROADMAP.md#L68)
already requires profiling, trace-driven residency, bounded staging and
retained-state correctness before serving/performance acceptance. This note
adds references without changing that sequence or authorizing a new run.
