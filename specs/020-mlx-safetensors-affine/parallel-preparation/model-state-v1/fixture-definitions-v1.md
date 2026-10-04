# Synthetic fixture definitions v1
MIT, authored formulas only, no checkpoint-derived values. fixtures.py is the
executable definition. Seven tokens with modular dyadic patterns, two independent
salts across KDA layers 0/4 and sparse layers 3/7. Initial recurrence [2,3] and
raw convolution suffix [2,7] are nonzero, signed and asymmetric. Kernel taps
vary by channel and time. Gate lower bound -5, A_log=.125, dt_bias=(.0625,-.125).
Sparse index keys/gates/query are width 2; independent attention query/key and
values are width 3; pool 2, topk 2, always tail. Only position, index key, gate,
attention key and value persist; queries/head weights remain per-step operands. Query-specific pools are visible only after both members. Absolute origins
13,41,101 discriminate relative/absolute confusion. One-head projected fixture
is a mathematical state boundary, not actual module geometry or MLA cache.

Independent oracle stores recurrence value-major and reconstructs convolution
from complete history. Sparse oracle enumerates completed pools directly; the
candidate uses the retained selector with invisible slots and incremental history.
Candidate output/state and oracle output/state compare atol=1e-12, rtol=1e-10;
IDs, positions, epochs, histories and chunk-final candidate states compare exactly.

Nonidentity mHC has four streams, width 3 and 24 coefficient rows; nonsymmetric
comb distinguishes input/output stream transpose. Tiny dense/routed/shared MLP
uses hidden 3/intermediate 4/four experts. Original sigmoid scores differ from
corrected ranking; all-.5 exact ties choose smallest ID only as a toy convention.
Embedding/head matrices [5,3] differ; final norm weights are not ones. These are
separate boundary probes, not an end-to-end decoder or source execution claim.

Tests enumerate all 64 partitions; check reset, interleaving, cancellation,
duplicate/stale commits, context limit, epochs and layer identities. Prospective
mutants lose convolution history, shift sparse positions, transpose mHC/state,
drop tail, reverse history/taps or swap state kinds. Injected late computation
failure verifies no partially published state. No padded, masked, evicted,
quantized or real-checkpoint state is exercised.

The candidate selector uses bypass_short=False, unlike the retained source
T<=index_topk dense fallback. For this pool=2/topk=2 fixture, each short prefix
selects every visible token (tail at T=1; full pool at T=2), so numerical attention
agrees while selector control flow differs. No source-dispatch equivalence is claimed.
Wrong-role controls substitute index key for attention key both directly (shape
refusal) and padded to width 3 (numerical mismatch with unchanged index choices).
