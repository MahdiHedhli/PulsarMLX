# Quantized resident weights and the mixed layout (Flash AN, Graph 20) — structural + equivalence

A real mixed-4/8 build quantizes everything with a `to_quantized` hook (8-bit
resident linears, embedding, multilinears and indexer projections; 4-bit
routed experts) and leaves the fp32 router gate, norms, convolutions and
hyper-connections alone. This graph exercises that on the hidden-64 admitted
stack under the supervised successor harness (`successor.py quantized-load`),
with no numeric oracle (the router reference's domain is ≤ 16): MLX's own
`nn.quantize`/`QuantizedLinear`/`QuantizedEmbedding` (the identity-bound
environment, not upstream code) driven by a class predicate built from a
config-style quantization block through the retained `_quantization_for_path`
— the per-path rule mlx-vlm uses — with the graph-15 admitted
`QuantizedSwitchLinear` and `QuantizedMultiLinear` bound as the `to_quantized`
targets that graphs 9 and 10 had refused.

Observed on CPU and Metal: exactly the 26 declared resident modules carry
scales at 8 bits and the 3 expert projections at 4 bits (bits recovered from
the packed shapes), the router gate stays fp32; the exported checkpoint
(116 tensors) reloads into a fresh model quantized from the config block
alone with `strict=True` and reproduces the logits **bit-identically**; the
same checkpoint through `repack` → `patch_model` (expert quant resolved as
`(64, 4, 'affine')`) → eager FFN on the patched layer → strict resident load
(8-bit resident tensors with their scales) gives logits equal to the
quantized model (0.0 CPU, 7.7e-7 Metal). The DeepSeek-V3.2 `Model.sanitize`
quantized branch — refused by graph 14's tripwire, admitted here with
`from_fp8` still refused — splits an 8-bit `kv_b_proj` into quantized
`embed_q` `[H, kvr, dq]` and `unembed_out` `[H, dv, kvr]` whose dequantized
values match the split of the dequantized `kv_b` within one quantization step
(1.9e-3 vs 1.95e-3), as re-quantization allows.

Three structural controls: swapping the predicate's bits is rejected by the
strict load (scales shapes), dropping a resident module's scales is rejected
(missing parameters), the untransposed `kv_b` split yields the wrong shape.
Geometry note: at this width three inputs are 32 wide (`f_b_proj`,
`g_b_proj`, the linear `o_proj`, `embed_q` along `dq`) and take group 32 —
the real model's are 128/256; found at first contact and recorded in the
fixture's `revision`.

Not established: numerical correctness beyond graphs 15/18/19's kernels and
this equivalence, fp8, the container prefix, tokenizer, real checkpoints,
throughput.
