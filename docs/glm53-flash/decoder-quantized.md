# Quantized expert and attention projections (Flash AN, Graph 15, slice 1)

The retained `QuantizedSwitchLinear` (mlx-vlm `switch_layers.py`, sha256
`914b40c9…`) and `QuantizedMultiLinear` (mlx-vlm `mla.py`, `da01333e…`) —
refused stubs in every earlier graph — are admitted by canonical-AST identity
with a global census and an `mx` op census, and qualified under the
supervised successor harness (`successor.py quantized`) against a stdlib
affine-dequantization reference over **frozen quantized arrays**: the
fixture's packed uint32 words, scales and biases were produced by a stdlib
quantizer in the generator (little-endian codes, per-group scale and bias
along the input axis, value = code·scale + bias), never by `mx.quantize`, so
the expected values are fixed before any candidate runs. `mx.dequantize` of
the frozen arrays agrees with the stdlib dequantization within 1.5e-8 on both
backends: the fixture's format is MLX's.

MLX supports group sizes 32, 64 and 128 only, so the router reference's
≤16-dimensional domain cannot host this path; the qualification is of the
kernels the checkpoint uses, standalone: a `SwitchGLU` with `ClampedSwiGLU`
over three `QuantizedSwitchLinear` modules (4 experts, hidden 64,
intermediate 128, three tokens with two given experts each) at 4-bit/g64 and
8-bit/g32, observed at the gate and up projections and the expert outputs
(`gather_qmm`, 1.7e-7 to 3.0e-7); and a `QuantizedMultiLinear` (2 heads,
64→48) in both transpose modes (`quantized_matmul`, 1.8e-7 to 5.0e-7). The
quantization error of the frozen codes against the original fp32 weights is
reported (1.7e-2 at 4 bits, 9.8e-4 at 8 bits), not asserted: it is lossy by
design. The `quant_predicate` name→bits mapping (8-bit for `mlp.gate`,
`e_score_correction_bias` and `.indexer`, default otherwise) is frozen on
real key names.

The matrix was filled prospectively from reference variants per target
(five mutants of the switch node evaluated on both switch cases, one of the
multilinear node); all eleven cells match on both backends. Two rows are
discriminating: forcing `bits=8` and forcing `group_size=32` kill the 4-bit/
g64 case and are inactive on the 8-bit/g32 case, exactly as predicted.
`biases-dropped` was predicted as a value kill; the candidate rejects it
(`gather_qmm` without biases in affine mode), which is also a kill. The
fixture's first version used intermediate 48, which is not a multiple of the
group size; `mx.quantize` rejected it at first contact, before any numeric
observation, and the fixture was regenerated with 128 (recorded in the
fixture's `revision`).

Not covered: `nn.quantize` of the admitted stack (its hidden size cannot be
grouped), loading a quantized checkpoint (`scales`/`biases` keys, the
quantized `kv_b_proj` split), quantized KV caches, `mode != 'affine'`, the
sorted-indices path (`indices.size >= 64`), and any real checkpoint.
