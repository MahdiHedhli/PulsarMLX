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

## AN repair (2026-09-16): interpreter-stable provenance and asserted kill matrix

The K provenance digests were built on `ast.dump`, whose output changed across
Python releases, so the candidate failed `DENSE_FFN_CALLER_CONTRACT` under the
CI-pinned 3.12 line while passing on the 3.14 that produced it, and recorded no
interpreter binding. Digests now use a canonical structural AST form
(`source._canonical`, scheme `canonical-ast/1`) that was shown to produce
identical digests under 3.12.11 and 3.14.6. `provenance.json` records the
scheme, and `load()` cross-checks the language/hyper-connection anchors and the
stored caller bodies (via their canonical AST) instead of pinning them only
transitively. `regenerate_provenance.py --check` verifies that the committed
provenance and the loader pin equal a fresh regeneration; a test runs it.

Mutant outcomes are no longer accepted by "any fixture killed it". The frozen
`expected_kill_matrix` in `fixtures.json` declares, per mutant and fixture,
`KILL` or `INACTIVE`, with a declared kill-margin factor of 10 over the output
allowance: a `KILL` cell needs `max_absolute_error >= 10 * 1e-4`, an `INACTIVE`
cell needs it `<= 1e-4`, and anything between is `WEAK` and fails. Mutants are
single-site with a declared occurrence index and asserted needle count; the
former two-site `hc-axis` mutant is split into `hc-axis-initial` and
`hc-axis-loop` (the loop site is expected `INACTIVE` for one Sinkhorn round).
Tolerance comes from the fixture contract; a wrong-shaped mutant output is a
`shape` kill rather than a comparison error. Events carry computed values
(AST equality, caught refusal messages, counted evaluations), not literals.

A fifth fixture, `sinkhorn-3-h3-clamp-active` (hc_mult 3, shape [1,2,3,2],
deterministic generator recorded in the fixture), exists because the weak
transpose margin reported by earlier reviews on the Sinkhorn-3 fixtures is
structural: a converged 2x2 doubly-stochastic `comb` is symmetric, so
transposing it is nearly the identity and only the convergence residual
(8.3e-4) is observable. The same fixed-point argument makes the initial-axis flip
(`hc-axis-initial`) weak on those fixtures (9.1e-4). Those four cells are
declared `WEAK_STRUCTURAL` (error strictly between the allowance and the
margin) and both mutants must kill at full margin on the H=3 fixture, whose
oracle `comb` asymmetry is 0.07. Thirty-five cells: twenty-five expected
kills, six expected inactive, four declared weak-structural. The kill-margin factor was not lowered. This
remains fixture-scale method qualification of the adapted caller, not real
model or runtime correctness.

## Compile-gate equivalence (AN, Graph 7)

`Glm5NextDecoderLayer.__call__` routes B=1, L=1 decode steps through
`mx.compile(self._ffn_block)`. `test_glm53_flash_decoder_ffn_compile.py` consumes
the admitted closed graph without altering it and compares the compiled
function with the eager one on every dense-FFN fixture, on CPU and on Metal,
for the full fixture input and its L=1 decode-step slice. The predeclared rule
is the fixture output allowance (1e-4); bitwise equality is recorded but not
required. Observed: bitwise-equal everywhere except the hc_mult-3 fixture on
CPU (1.8e-7 / 2.4e-7, float32 reassociation under compile); Metal bit-equal
on all fixtures. A compiled residual-omitting mutant exceeds the allowance on
every device/fixture cell. On hosted CI a missing Metal device fails the test;
locally it is recorded as NOT_EXECUTED, never as a pass.
