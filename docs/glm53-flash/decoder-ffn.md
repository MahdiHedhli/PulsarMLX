# Prospective dense FFN qualification (Flash K)

This bounded fixture adapts the complete retained
Glm5NextDecoderLayer._ffn_block by renaming only the function to
source_ffn_block. Arguments, annotations, comment, HC collapse, RMSNorm,
clamped MLP and residual expansion are retained. Upstream is
Blaizzy/mlx-vlm@8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90.
The language and hyper-connection bodies have fixed SHA256 trust anchors.
The entire caller AST, selected node ASTs, closed global dependencies and
candidate graph identities are validated before the first selected definition
or compile decorator executes. The graph's provenance digest is fixed in the
loader; its normalized source body removes only that digest literal to avoid
a circular self-hash. An external source-free harness binds all actual source
bytes before import. There is no production tamper-bypass flag.

The finite matrix was banked privately before source edits: iteration counts
one and three, each with clamp-active retained weights and clamp-inactive
gate/up weights multiplied by 0.1. All arrays use float32. Input shape is
[1,2,2,2]; three MLP intermediate channels. Unused I residual fixture data is
removed because the actual caller's residual is its x input.

The independent scalar oracle uses Python math and binary64 arithmetic. It
imports no candidate arithmetic helpers. Explicit absolute allowances of 1e-4
at every boundary preserve I's existing float32 allowance. Small dot products,
bounded fixture magnitudes and at most three Sinkhorn rounds justify this
fixture-scale allowance; it is not a guarantee for arbitrary input. No
post-observation tuning is permitted. Unexpected shape/type, empty/ragged
arrays and either-direction nonfinite inputs are rejected before comparison.

Paired candidate/oracle boundaries are xc, post, comb, norm, gate, up,
activation, mlp, residual and output. External wrappers call unchanged
functions once, copy values for evidence, and return original objects. Their
body is hashed before observations. A separate uninstrumented actual caller
evaluation must match the observed output exactly. The actual _hc_ops branch
is recorded with training state and iteration count; excluded fused HC
refuses. Dtype and shape are independently checked for every boundary.

Qualification tests exercise the actual loader with graph-owned altered
scratch-file bytes, with an execution spy requiring zero adaptations on
refusal. Test-owned runnable mutants change the actual caller, selected HC or
clamp nodes; the production loader separately refuses their identical altered
bodies. Numerical execution occurs only in an explicit test-only direct
harness. Each mutant's complete body, diff, compilation identity, successful
evaluation, expected/output values and semantic decision are retained.
Shape-truncation and late-validation loader mutants have independent semantic
decisions. Syntax/import failures cannot count as numerical kills.

Normal and optimized Python runs are separate captured processes without
bytecode writes, under the unchanged admitted confinement/capture method.
A source-free doctor precedes project imports. Final runs must use a fresh
clean checkout of the new repaired commit and the same frozen fixture/oracle.
Detailed results and exact counts are evidence outputs, not fixture-authored
answers. Source acceptance remains a separate parent review decision.

I's missing historical pre-repair fixture remains UNKNOWN and is never
reconstructed. This fixture performs no model access, checkpoint/tokenizer
access, full forward, real inference, GO/P1 or ledger operation.
