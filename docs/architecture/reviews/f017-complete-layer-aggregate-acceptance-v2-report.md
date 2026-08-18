# F017 Complete-Layer Aggregate Acceptance v2 Freeze

The complete layer-3 acceptance surface is now frozen as
`f32(f64(DPREFIX-EXACT-1) + (routed_aggregate + f64(shared_output)))`.
The implementation-order evidence agrees across the Rust runner and independent
Python R10 oracle: the same FFN RMSNorm input feeds routed and shared experts,
the shared expert is gate/up/SwiGLU/down without an extra scale, routed and
shared outputs are combined in binary64, the residual is added once, and the
result is cast once to binary32.

The accepted thresholds are the immutable R10 final-output family: max absolute
`0.0625`, RMSE `0.03125`, and cosine minimum `0.999`. The routed-only v1
intermediate theorem and its cosine FAIL remain unchanged. V2 reuses v1's sound
routed interval without tightening and encloses the final f32 transport. Its
cosine rule is the pre-observation Euclidean tangent-ball lemma
`sqrt(1-(epsilon/A_lower)^2)`.

The scoped ambiguity is routing-weight uncertainty. A future independently
reproduced exact-class shared output is a fixed point (`delta_S=0`) for that
proof; any bounded shared output must instead supply component intervals.

Committed catalog evidence yields exactly three future shard-2 payloads:
Q5_K gate and up plus Q6_K down, totaling 27,623,424 packed bytes. Their future
recovery remains separately reviewed and would move the ledger from 163 to 166.
This freeze performed zero checkpoint reads, zero shard opens, and no real
shared-output or complete-layer evaluation.
