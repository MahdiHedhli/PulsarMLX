# PulsarMLX Feature 017 fixture provenance audit

## Historical claim state before independent regeneration

Classification at `b7585de`: **PARTIALLY INDEPENDENT**. The seven-boundary
checkpoint-free scaffold passed against scalar Rust reference functions, but
no independent Python/NumPy oracle generated those expected values. It must
not be cited as independent-oracle parity. The existing fixtures are retained
as historical structural/reference artifacts while the independent v2 set is
generated and validated.

## Conclusion

The public Feature 017 ladder is a checkpoint-free synthetic semantic ladder.
It is not a real GLM-5.2 value distribution and must not be presented as
real-checkpoint determinism.

The frozen generator source is commit
`60145f8f18531e169e9fbfb676d1754efbfc4873` in
`crates/engine/src/f017_parity.rs`. The synthetic constructors generate packed
inputs, activations, routing vectors, expert matrices, attention values, layer
values, and output-head values. The frozen expected values are produced by the
scalar `reference_*` paths in the same source file and are compared against
the candidate decoder/orchestration paths. The candidate Q8_0 decoder is
`quant::decode_q8_0_matrix`; candidate semantic execution is in the
`run_*_fixture` functions.

This is an independent implementation path at the algorithm boundary: the
reference decoder, scalar matvec, scalar SiLU, reference attention, reference
normalization, reference logits, and reference top-k routines are separate
from the candidate/vectorized routines. It is not an independent language or
process. The manifests therefore state the exact implementation paths and
scope instead of claiming a Python-oracle run that did not occur.

## Boundary mapping

- Projection: `ProjectionFixture::synthetic_q8_0`, `run_projection_fixture`,
  `reference_decode`, and `project`.
- Router: `RouterFixture::synthetic`, `run_router_fixture`, frozen routing
  weights/IDs/output, and independent routing assertions.
- Complete expert: `ExpertFixture::synthetic`, `run_expert_fixture`,
  `reference_decode_matrix`, `reference_matvec`, and `reference_silu`.
- Top-8/shared: `Top8SharedFixture::synthetic`, `run_top8_shared_fixture`,
  `reference_softmax`, and `reference_aggregate`.
- MLA/dense: `MlaDenseFixture::synthetic`, `run_mla_dense_fixture`,
  `reference_rotate_pair`, `reference_dot2`, `reference_softmax_two`, and
  `reference_matvec2`.
- Complete layer: `CompleteLayerFixture::synthetic` and
  `run_complete_layer_fixture`, with component boundaries from the prior
  reference paths.
- Final norm/logits/top-k: `FinalOutputFixture::synthetic`,
  `run_final_output_fixture`, `reference_rms_norm`,
  `reference_output_logits`, and `reference_top_k_indices`.

The portable manifests bind generator path, generator source SHA, reference
path, candidate path, and synthetic-only scope. No model weight bytes are
redistributed.

## Limitation carried to P1

The synthetic ladder does not cover every real GLM-5.2 pattern, including f16
scale extremes, denormals, grid/sign edge patterns, and real-checkpoint
distribution tails. The first M1 Ultra P1 is the first real-checkpoint
integration test for those paths. P1 must retain fail-closed validation and
must not promote synthetic parity to a real-checkpoint claim.
