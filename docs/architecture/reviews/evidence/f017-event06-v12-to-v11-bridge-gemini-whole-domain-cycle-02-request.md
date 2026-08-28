# F017 Event 06 V12-to-V11 Bridge Whole-Domain Gemini Challenge — Cycle 02

## Review authority

- Role: CHALLENGE, not final arbitration.
- Required model: `gemini-3.1-pro-high`.
- Effort: high.
- Reviewed evidence head: `8f943e67ffccd8b59c85f4bb05e00ed0fc18e943`.
- Measured implementation head: `7fbc641339f65619f77cca78a86eabc4d19277b7`.
- Measured implementation tree: `4ea92265360b7130948e52b8497f2802a7526702`.
- FULL_NATIVE run: `33141124246`, PASS, two required native jobs passed, zero required or unexpected native skips.
- Post-repair EVIDENCE_ONLY run: `33142149732`, PASS, zero native jobs launched.

Review committed bytes only in a fresh read-only checkout. Do not modify files,
resolve or open an original checkpoint root, execute Event 06, create live
authority, start a package, consume identities, run numerical inference, or
execute P1 attempt 2.

## Preserved cycle-01 rejection

Cycle 01 rejected `C-BRIDGE-PROV-001`, `C-BRIDGE-CALLPATH-001`,
`C-BRIDGE-LIFE-001`, and `C-BRIDGE-QUAL-001`. Directly verify the repairs:

1. the real V12 identity-stage producer is consumed through a typed adapter;
2. the execution plan, event plan, installed V12 authority, receipt, identity
   terminal, descriptor leases, measurement, numerical V4, and result V11
   provenance form one closed chain;
3. the production coordinator owns sealed package, primary, and secondary
   durable starts and invokes each numerical leg exactly once;
4. secondary start binds the complete exact primary terminal;
5. comparison, release, accounting, V11 bundle closure, and package terminal
   are implemented, with descriptor release on success and every modeled
   post-identity failure path;
6. qualification calls the production coordinator and real function signatures
   with fail-closed spies rather than bypassing consumer signatures;
7. valid independently constructed provenance substitutions fail, not merely
   malformed hashes.

## Required attacks

Attack generation truth, bridge-field deletion/addition/type/alias mutations,
V12/V11 admission boundaries, installed-authority and receipt substitution,
execution-plan substitution, identity-terminal/access-census substitution,
descriptor identity and lease-owner substitution, caller-supplied durable-start
digests, duplicate primary or secondary execution, secondary-before-primary,
comparison-before-bundles, release omission, accounting drift, terminal closure,
callbacks/reflection/ambient authority, canonical reconstruction, generic
fallback, numerical/result drift, no-access rehearsal, CI routing, original
checkpoint access, Event 06 state, and hidden P1 authority.

## Claim verdicts

Issue `SUPPORTED`, `CHALLENGED`, or `UNRESOLVED` for every claim:

- `C-BRIDGE-GEN-001`
- `C-BRIDGE-PROV-001`
- `C-BRIDGE-DIGEST-001`
- `C-BRIDGE-LEGACY-001`
- `C-BRIDGE-CALLPATH-001`
- `C-BRIDGE-LIFE-001`
- `C-BRIDGE-CAP-001`
- `C-BRIDGE-DRIFT-001`
- `C-BRIDGE-QUAL-001`
- `C-BRIDGE-CI-001`
- `C-BRIDGE-SAFETY-001`

Return structured findings with severity, claim ID, exact committed evidence,
attack performed, disposition, and earliest invalidated node. End with exactly
one global challenge disposition:

- `ACCEPT_FOR_OPUS_WHOLE_DOMAIN_ARBITRATION`
- `MATERIAL_CHALLENGE_REQUIRES_REPAIR`
- `UNRESOLVED`
