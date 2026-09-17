# sanitize and strict weight loading (Flash AN, Graph 14, slice 1)

`LanguageModel.sanitize` (the renamed capsule's own method, unchanged
upstream) is qualified together with the DeepSeek-V3.2 `Model.sanitize` it
delegates to — taken whole from the retained mlx-vlm `deepseek_v32/language.py`
(sha256 `cd210c73…`, the router track's retained text) by canonical-AST
identity with a global census and executed under a tripwire `mx` that refuses
`from_fp8`, `quantize` and `dequantize`, so the fp8 and quantized branches
cannot run on this fixture — under the supervised successor harness
(`successor.py sanitize`).

The fixture is a synthetic checkpoint in the upstream HF naming as the pinned
pipenetwork `glm5_next.py` container `sanitize` hands it to the language
model (`model.layers.N.*`, `model.embed_tokens.weight`, `model.norm.weight`,
`lm_head.weight`; key names taken from the retained `GLM-5.3-Flash-BF16`
safetensors index), built from the graph-11 stack fixture's parameters: per-
part `{q,k,v}_conv1d.weight` in the HF `(C, 1, K)` layout, forget-gate
parameters at `self_attn.*` with `A_log`/`dt_bias` supplied in bfloat16
(bf16-exact values), `hc_attn_*`/`hc_ffn_*`, per-expert `experts.E.*`,
`kv_b_proj.weight` (to be split into `embed_q`/`unembed_out`), an MTP layer
at index `num_hidden_layers` and a `mtp.` key. The reference
(`decoder_stack_sanitize/oracle.py`) models the mapping on nested lists
(drops, renames, conv fusion in q,k,v order and the `(C,1,K)→(C,K,1)` axis
move, forget-gate move, expert stacking, the transposed `kv_b` split, the
fp32 cast) and yields the 58 expected parameters.

Observed on CPU and Metal: the sanitized key set equals the reference's (and
the model's, by the strict load), no dtype mismatch (the bf16 inputs come out
float32), every value equals the fp32 rounding of the reference value
exactly, the three dropped keys are absent, the strictly loaded fresh model's
parameters equal the directly built model's bit for bit, and its logits match
the frozen stack logits (8.2e-7 / 8.9e-7). The fp8 dequantisation path is
asserted refused. All eight prospective cells match: six capsule mutants
(MTP filter, hc rename collision, conv fusion order, conv axis move, fp32
cast, forget-gate move) and two DeepSeek-V3.2 mutants (untransposed `kv_b`
split, reversed expert stacking); five are rejected by the strict load or by
the dtype boundary, three kill by value (0.252, 1.244, 2.142) exactly where
the reference variants predicted (0.125 at parameter level for the conv
order; the candidate cell reports the larger logits effect).

Not covered: fp8 (`weight_scale_inv`) dequantisation, quantized checkpoints
(`scales`/`biases`, `to_quantized`), the vision tower, the container-level
prefix mapping itself (documented from the pinned source, not executed),
`cast_predicate`/`quant_predicate`, and any real checkpoint.
