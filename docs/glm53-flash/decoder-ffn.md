# Dense decoder FFN composition

This bounded synthetic adaptation executes only the retained dense `ClampedSwiGLU`, `ClampedMLP`, the pure-ops HyperConnection closure, and the retained `_ffn_block` body. Its explicit branch is `training=True`, which selects `_hc_ops`; the excluded fused kernel name is a refusing sentinel. No Metal fused-kernel result is claimed.

The fixture uses one batch, two sequence positions, two residual streams, hidden width two, nonidentity mixing parameters, and two Sinkhorn iterations. The scalar oracle independently implements float operations, RMS normalization, Sinkhorn row/column order, dense clamp/SwiGLU, and the transposed residual expansion. The tolerance is `1e-4`, a pre-observation float32 comparison allowance for this small pure-ops path; it is not a device-wide numerical claim.

This is not a full decoder: attention selection, routed experts, cache sequencing, model outputs, quantization, storage, and serving remain out of scope.

The declared recipe mutations use the same frozen fixture: bypass post-attention RMS normalization, bypass the FFN HyperConnection output, and replace the original residual passed to `hc_expand` with zeros. Each must differ from the source-body canonical output; startup failure does not count as detection. They are external, named transformations and do not hand-edit the verified extracted node bodies.
