# Linear attention beyond the 5-token kernel domain (Flash AN, Graph 17)

The accepted linear-attention reference has a finite domain of at most 5
tokens per call, and the admitted module's Metal kernel admission refused
longer calls (`MODULE_KERNEL_DOMAIN`). This graph qualifies single-call
prefills of 8, 16, 33 and 64 tokens through the admitted
`Glm5NextLinearAttention` (the linear track's namespace with its counters and
kernel admission) under the supervised successor harness
(`successor.py linear-long`) **without touching the accepted reference's text
or domain**: the reference for a long sequence is the chunked composition of
the accepted reference — chunks of at most 5 tokens with the reference's own
`cache0`/`cache1` carried between chunks, each carried value rounded to
float32 (a declared cast point: the reference requires fp32-dyadic external
inputs, and the candidate's cache is float32). Each chunk's error radii are
computed by the reference itself and stay under its 1e-4 tolerance
(maximum output radius 3.0e-5 over all chunks); the reference self-refuses if
they did not.

The kernel admission bound became a per-load parameter, `max_sequence`,
whose default is 5 for every operation accepted before this graph; only the
`linear-long` operation loads with 64. Inputs are one-negative-lane sign
patterns of uniform dyadic magnitude in [1/2, 63/64] with the decoder-layer
generator's accepted parameter family.

Observed on CPU (ops path) and Metal (fused kernel): single-call outputs
within 6e-8 of the reference at every length, final caches within the
linear track's cache tolerances; the same inputs run chunked (≤5 tokens per
call, inside the existing domain) with the real `ArraysCache` match the
reference chunk by chunk; the single call and the chunked candidate agree to
≤3e-8 (bit-identical at 8, 33 and 64 on Metal). The domain-gate control
shows the default load still refuses the 8-token single call on Metal.

Not covered: batch > 1 and padding at long sequences, S > 64, the layer and
stack operations at long S (they still load with the default 5), and any
real-model claim.
