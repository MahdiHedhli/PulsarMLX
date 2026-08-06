# Feature 002 Research Limitations

**Status**: Real Apple MLX layer-0 router evidence is published with verified
package-level claims. The capability boundary still stops at the router.
Deeper model operations remain unsupported.

Normative boundaries and stop conditions remain in the [Feature 002
specification](../../specs/002-qwen-router-parity/spec.md) and [experiment
protocol](EXPERIMENT_PROTOCOL.md).

## Evidence-derived limitations

- Scope is exactly `layer_0_router_only` over `blk.0.ffn_gate_inp.weight` for the
  frozen two-row `ffn_norm-0` input. No expert MLP, aggregation, attention,
  full layer, logits head, or generation path was executed.
- Claims F002-C01 through F002-C03 are package-level verified for the bounded
  layer-0 router only; raw records retain provisional claim_boundary status by
  protocol while package promotion uses matching clean-checkout evidence.
- Timing labels retain OS-cache-uncontrolled first-process semantics; they are
  not controlled cold-filesystem measurements and are not tokens/sec.
- Hosted CI does not receive the external checkpoint. Fixture-only CI cannot
  re-prove the real Apple result.
- Two earlier producer candidates failed independent sanitization/post-processing
  and must not be reused as verified evidence.
- A temporary resource-admission stop occurred when load averages exceeded the
  frozen `0.75 × logical CPU count` ceiling; the eventual admitted run used a
  quiet window under that ceiling.
- Privacy publication required an exact allowlist for schema-required public
  `host_monotonic_clock`, `host_wall_duration_ns`, and `host_to_device` fields
  so the privacy filter no longer false-positive rejected protocol keys while
  still rejecting bare host/hostname identifiers.

## Predeclared methodology constraints

- Hosted CI is limited to committed fixtures, schemas, scripts, and publication
  boundaries unless an operator supplies the external checkpoint out of band.
- Feature 002 does not provide Linux/CUDA runtime validation of fork changes.
- Protocol v1 does not purge operating-system caches.
- Protocol v1 has no legal production exclusion rule for omitted real samples.

## Unavailable observations

Power-mode fields may remain unavailable when the unprivileged `pmset` probe
does not expose them. Expert outputs, routed aggregation outputs, complete-layer
activations, model logits, and generated tokens remain unavailable by design.

## Unsupported interpretations

Even the passing router records cannot establish expert MLP execution,
selected-expert aggregation, attention or prior-layer parity in PulsarMLX, a
complete transformer layer or model, language-model-head logits, tokens,
generation, serving, full or giant model inference, projected tokens per
second, custom Metal optimization, or Linux/CUDA runtime parity.
