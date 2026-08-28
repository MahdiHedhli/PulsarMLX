# F017 Event 06 V12-to-V11 bridge design

## Decision

Introduce a separate, sealed numerical execution-authority bridge. The bridge preserves four simultaneous facts: checkpoint identity authority is V12, numerical consumers are V11, numerical formulas remain V4, and result authority remains V11. It does not rewrite either historical schema and does not emit candidate-shaped V11 bytes.

## Data model and provenance

The bridge is derived only after package start from three sealed inputs: a validated V12 installed authority plus its receipt, a validated V12 identity-stage binding, and a separately validated Event 06 execution plan. The identity-stage binding contains the identity terminal, manifest, access-census and descriptor-set digests plus the five lease identities. The execution plan contains fresh event identities and exact measured source, numerical, tensor-catalog, result, comparison, release, accounting and lifecycle bindings.

The bridge validator independently rechecks equality edges shared by those inputs. It then canonicalizes one closed 39-field document and returns a sealed object. The canonical SHA-256 is the bridge identity. Direct construction, copying, pickling, arbitrary mappings, callbacks, ambient configuration, and unchecked paths are rejected.

Role-specific immutable views contain only the fields needed by that consumer and always include the bridge digest and V12 provenance. A view is not a candidate and cannot pass a historical candidate validator. Numerical adapters use unchanged V11 numerical cores and descriptor-backed target sources through explicit bridge-aware entry points.

## Producer-consumer matrix

| Producer | Consumer | Bound authority | Gate |
|---|---|---|---|
| V12 installation validator | bridge validator | authorization, package, installed bytes, receipt | installed posture only |
| V12 identity producer | bridge validator | terminal, manifest, access census, five descriptor identities and leases | complete identity terminal |
| Event 06 execution-plan validator | bridge validator | fresh event IDs, source head/tree, measurements, V4/V11 authorities | one-shot plan |
| bridge validator | primary adapter | primary event, numerical V4 SHA, tensor catalog, five descriptors | primary not started |
| bridge validator | secondary adapter | secondary event, numerical V4 SHA, tensor catalog, five descriptors, primary terminal | exact primary terminal |
| primary/secondary adapters | V11 result-bundle builder | immutable output bytes plus bridge binding | one core call per role |
| both result terminals | independent comparator | both bundle indices plus bridge binding | both exact terminals |
| comparator | release/accounting | comparison terminal plus bridge binding | comparison complete |
| release/accounting | package terminal | recursive closure plus bridge binding | zero live leases |

## Complete coordinator path

The repair-generation coordinator owns the complete sequence from readiness and V12 candidate/install validation through package-start gate, identity terminal, bridge derivation, one primary call, one secondary call, comparison, release, accounting, and package terminal. A validation-only traversal binds the same function signatures and phase gates but uses sealed spies which fail if any root, file, numerical core, live-state, installation, or ID-consumption function is reached.

## Safety proofs

- The bridge is downstream of V12 installation, package-start gate, and identity terminal, so it cannot create a second live authority or bypass package start.
- Event number is validated data in the execution plan; no event-number branch grants a capability.
- Historical V11 candidate validation remains untouched and continues to reject V12 and bridge documents.
- Historical V12 candidate and installed schemas remain closed at 28 and 30 fields.
- Every consumer and durable transition binds the same bridge digest; reconstruction revalidates all provenance before returning an identical sealed object.
- Every modeled failure has a phase-specific terminal outcome and preserves the exact durable prefix without retry or generic fallback.

## Qualification plan

Qualification uses synthetic values and temporary roots only. It performs at least 20 fresh-process deterministic reconstructions, real-signature end-to-end traversal, exhaustive field deletion/addition/type/alias mutations, all named provenance substitutions, ordering and one-shot mutations, copy/pickle/direct-constructor/callback attacks, reconstruction after every transition, exact lifecycle-outcome tests, zero-capability census, zero V4/V11 drift, and historical-evidence hashes. It then runs targeted and applicable regression tests, formatting, linting, generators in check mode, synthetic qualification, failure qualification, production-shaped no-access rehearsal, exact-head FULL_NATIVE CI, whole-domain review, and final EVIDENCE_ONLY CI.
