# Loading path end to end: repack → ExpertStore → patch_model (Flash AN, Graph 19)

The retained mlx-vlm loading path a dogfood run takes is exercised over the
admitted two-layer stack at hidden 64 under the supervised successor harness
(`successor.py load-offload`): `plan`, `repack` and helpers, `patch_model`,
`_layer_id`, `_n_experts` from `moe_offload.py` (pinned `8d79dbcf`) and
`_quantization_for_path` from `one_bit.py` (sha256 `6771b900…`), each by
canonical-AST identity with a global census; `patch_model`'s two relative
function-body imports are omitted from the executed body and bound to the
admitted `OffloadedSwitchGLU` and `_quantization_for_path` (the omitted
spellings are in the contract); the sanitize fallback and the automatic
KV-reserve budget are refused stubs. **Structural + equivalence only** — no
numeric oracle composes at hidden 64 (the router reference's domain is ≤ 16).

The controls write a synthetic *converted* checkpoint into the child's work
directory: the admitted `LanguageModel`'s parameter names (the container
prefix already stripped, as graph 14 documents), seeded-init resident tensors,
the graph-15 frozen 4-bit/g64 routed experts stacked under
`model.layers.1.mlp.switch_mlp.*` as uint32 words, scales and biases, a
`model.safetensors.index.json` and a `config.json` with a `quantization`
block. `repack()` produces `experts/layer_0001.safetensors` with exactly the
36 expected per-expert keys and shapes, one resident shard holding the other
55 tensors, `offload_index.json` `{layers: [1], num_experts: 4}` and the
config passthrough. A fresh model is patched (`patch_model` swaps exactly the
MoE switch layer for an `OffloadedSwitchGLU` with the quant triple resolved
from config as `(64, 4, 'affine')`), and the resident shard loads with
`strict=True` — its key set equals the patched model's parameter names. A
3-token prefill and two decode steps with `make_cache` caches give logits
equal to the resident model whose experts are `QuantizedSwitchLinear` over the
same arrays (graph 15): bit-identical on CPU, 9.5e-7 on Metal. The store
serves the decode steps with misses/evictions under a two-expert budget.

**Finding.** `OffloadedSwitchGLU` evaluates the routing indices on the host
(`np.asarray(indices)`), which MLX forbids inside `mx.compile`; the decoder
layer compiles its FFN block at B=1, S=1 (`compile_ffn`). With the layer left
as constructed, the first offloaded decode step is rejected
(`[eval] Attempting to eval an array during function transformations`). The
required configuration — offloaded layers run the eager FFN path
(`layer.compile_ffn = False` on patched layers) — is applied by the controls
as a runtime setting, not an edit to any admitted node, and the crash is kept
as an asserted control. Neither the pinned pipenetwork code nor the pinned
mlx-vlm `patch_model` handles this; a real run must apply it.

Four structural controls: misclassifying shared experts as routed (the
repack yields 128 "experts" and `patch_model` rejects), inverting the expert
count check (nothing swapped, rejected), resolving 4-bit experts as 8-bit
(rejected by `quantized_matmul`), rotating the expert slices (equivalence
broken). A budget note: `patch_model` converts `expert_cache_gb*1e9` with
`int()`, so a budget of exactly two experts rounded one byte short; the
controls use 31,000 bytes (irrelevant at real gigabyte budgets).

Not established: `nn.quantize` of resident weights (they stay fp32 here; a
real mixed build quantizes them too), the container-level prefix mapping,
tokenizer/processor passthrough, the vision tower, multi-layer stores at real
sizes, throughput, any real checkpoint.
