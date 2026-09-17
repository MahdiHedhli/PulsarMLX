# MoE block composition (Flash AN, Graph 9, slice 1)

`Glm5NextMoE` (renamed only; canonical-AST equality with the upstream class is
enforced) is qualified as one composed forward pass under the supervised
successor harness (`successor.py moe`), against an independent stdlib oracle
(`scripts/research/glm53_flash/decoder_moe/oracle.py`) composed from the
accepted router selection reference (`rc_oracle.reference`), a binary64
per-expert `down(clamped_swiglu(up x, gate x))` stage, a score-weighted
combine and the shared `ClampedMLP` via the same clamped stage. The gate is
the router track's `Builder` (unchanged upstream `Glm5NextMoEGate` over the
retained selector, bound to the environment manifest); the routed experts are
`SwitchGLU` over the switch-layer nodes (`_gather_sort`, `_scatter_unsort`,
`SwitchLinear`, `SwiGLU`, `SwitchGLU`) taken whole from the retained
`mlx_vlm/models/switch_layers.py` text (pinned `8d79dbcf`, sha256
`914b40c9…`) with a global census; `ClampedSwiGLU`/`ClampedMLP` come from the
dense-FFN admitted namespace. The default `swiglu` activation and
`QuantizedSwitchLinear` (`to_quantized`, `gather_qmm`) are refused stubs and
their refusal is asserted; `gather_mm` stays an MLX core op.

Observed boundaries on the frozen fixture (`moe-e4-k2-t2`: 4 experts, hidden
4, top-2, intermediate 3, one shared expert, scaling 2.5, limit 1.0, two
tokens, selection margins 0.076/0.026): the selected expert set and the
per-id scores, each selected expert's switch output row, the shared output
and the block output, all within the 1e-4 allowance on CPU and Metal
(measured errors 6e-9 to 8e-8). The reference records 6 clamp-active
elements (4 inside routed experts, 2 in the shared expert), so the clamp is
exercised, not merely present.

Five capsule mutants are decided cell by cell against a matrix frozen before
any observation, with a factor-10 margin; all five kill on both backends.
Four kill by value (unweighted combine 0.15, shared expert omitted 0.29,
expert/score pairing reversed 0.088, routed activation unclamped 1.66). The
wrong-combine-axis mutant is killed by MLX's shape rejection, which the
frozen matrix names as the expected outcome ("a shape mismatch is a kill by
rule"); the first controls version only caught `RuntimeError` and let that
`ValueError` escape as a test error, and its unclamped mutant substituted the
switch-layer `SwiGLU`, whose default activation is a refused stub, so that
cell would have been "killed" by a refusal rather than observed. Both were
corrected before any supervised PASS: exceptions raised by a mutated block
are recorded with their type and count as a kill, and the unclamped mutant
now relaxes the clamp limit so the admitted activation path is observed. The
matrix itself is unchanged.

Slice 2 (quantized-path exclusion): the loader now takes a census of every
`mx.<name>` attribute referenced by each function of the admitted switch-layer
nodes and refuses admission if `gather_qmm`, `quantized_matmul`, `quantize` or
`dequantize` appears anywhere except `SwitchLinear.to_quantized` (whose target
class is the refused stub); `SwitchLinear.__call__` must reference exactly
`expand_dims` and `gather_mm`. A test-only control rebuilds the block over a
tripwire `mx` that raises on those ops and reproduces the admitted output
bit-for-bit, and a `gather_mm -> gather_qmm` mutant of `SwitchLinear.__call__`
is refused by the digest, by the census, and trips at forward time. This
establishes that the executed expert path is the unquantized `gather_mm`
path only; `gather_qmm`/`QuantizedSwitchLinear` (the mixed-4/8 checkpoint's
expert path) remain unqualified.

Run history: the first supervised attempt (`moe-cpu-1`, 18:25 on
2026-09-16) exited before the harness ran, inside the child's own doctor
probe (the MLX cpu/metal compiled-addition check), about fifty seconds before
the host kernel panicked on a network-stack allocation failure with ~170 MB
free; the child had peaked at 53 MB. After reboot the same doctor path passed
in every child. The failed attempt is retained, not promoted.

Not covered: grouped routing (`n_group > 1`), quantized experts, sparse
attention and the indexer, the model stack, real weights, quantized or
native-BF16 parity, and any real-model claim. The supervised operation runs
under the admitted `env-g1` identity (mlx 0.32.2); the offline CI module
(`scripts/research/tests/test_glm53_flash_decoder_moe.py`) checks the oracle
recompute, the retained texts' admission and the frozen matrix/recipe
agreement without importing MLX.
