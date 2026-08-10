# PulsarMLX Feature 017 Claude verification request

This is a verification-only request. Do not reopen the accepted architecture
and do not request a second broad design review.

## Reviewed boundary

- Prior reviewed SHA: `0e59d9786b96ce0aaad513bae71702a57ef23b6f`.
- Remediation branch: `feat/017-rust-native-inference-runtime`.
- Final SHA and final CI run are recorded in the sprint report and this packet
  is updated with the corresponding remediation commit.

## Fixes to verify

- B1: owned-stream construction has one creation and one destruction path;
  1,000-cycle counter evidence is balanced.
- B2: refcounted ownership state survives late MLX callbacks; source-first
  derived teardown passes without a sync inserted between the two destructions.
- B3: managed callback accounting and derived-array lifecycle accounting are
  separate and reconcile for source-first, derived-first, and multiple-derived
  cycles.
- B4: process-wide singleton context enforcement rejects a second context and
  recovers after full teardown; CPU restoration frees allocated handles.
- Shape conversion rejects zero and `INT_MAX + 1` counts before allocation.
- Fixture provenance is bound to source SHA `60145f8` and explicitly scoped to
  synthetic checkpoint-free validation. The real-checkpoint limitation is
  recorded rather than overclaimed.
- M1 P1 admission now requires environment identity, stream mode, singleton
  assertion, ownership reconciliation, and a 16 GiB absolute free-memory
  floor.

## Evidence

- Native adapter regression matrix: 8 tests passed locally, including 30/100
  lifecycle cycles and 1,000 owned-context cycles.
- Existing parity/lifecycle/Metal/soak evidence remains unchanged.
- Remote CI must be green for the final remediation SHA before this request is
  marked GO.

## Decision requested

Return exactly one of:

- `GO`: B1-B4 and provenance/admission fixes are closed; one bounded M1 Ultra
  F017 P1 is admitted.
- `NO-GO`: list only remaining concrete blockers before that single P1.

Do not execute P1 from ColPanicM2. Do not authorize P2 or golden-eight from
this verification request.
