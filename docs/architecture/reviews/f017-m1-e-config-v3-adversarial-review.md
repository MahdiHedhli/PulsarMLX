# F017 M1-E Config-v3 Preparer Adversarial Review

**Verdict: GO FOR M1-E ATTEMPT 3**

## Adversarial findings

The reviewed parser fails closed against schema downgrade, future or unknown
minor/major versions, duplicate schema keys, v2/v3 field mixing, stale
preparer identity, config/hash mismatch, wrong attempt number, stale evidence,
and decoder/activation/scaffold/Tier-B substitution. All rejection paths under
review complete before checkpoint access.

Identity-only metadata cannot affect expected numbers: the numerical semantic
projection contains only expert/tensor identities, checkpoint/map bindings,
activation, decoder, scaffold, Tier-B, and execution arithmetic requirements.
The independence audit found no Rust FFI, MLX, candidate subprocess, candidate
decoded matrix, candidate stage output, or candidate metric dependency.

The valid v3 path was exercised from an unrelated cwd with a relocated private
package and an approved later authorization head. The updated preparer
finalized the synthetic oracle before candidate start; the native runner then
produced 10 equal per-stage repeat records and 30 dispatches. A changed
intermediate and stale/mutated oracle each failed closed.

Attempts 1 and 2 remain immutable and rejected under SHA-256
`346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119`
and `8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00`.
Attempt 3 remains unconsumed.

