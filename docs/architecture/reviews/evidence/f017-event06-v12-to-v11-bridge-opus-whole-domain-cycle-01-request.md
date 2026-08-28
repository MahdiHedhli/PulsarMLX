# F017 Event 06 V12-to-V11 Bridge — Whole-Domain Opus Arbitration, Cycle 01

Use `claude-opus-5` at high effort in a fresh detached read-only worktree. Review committed bytes only. Do not edit files, resolve or inspect any original checkpoint root, open any checkpoint shard, run numerical inference, create live authority or state, consume an Event 06 identity, retry/resume Event 04/05/06, or execute P1 attempt 2.

## Authority under review

- measured implementation head: `2729aa260695ec77e0b138ed73891da9d1291aab`
- measured implementation tree: `d5bc4245ff2bf2d93a8640d8fb5e878d6ca1fbbf`
- implementation evidence head: `c868b2a4504e2fbf1e48697407856533ad7c3c0f`
- FULL_NATIVE run: `33137473493`, result `PASS`, required/unexpected skips `0`
- evidence-only run: `33138365702`, result `PASS`, native jobs `0`
- bridge digest: `83712e17780debafc7981b17b996ac944bda9883a35b98f682a0f0163474e88b`
- Gemini whole-domain verdict: `ACCEPT_FOR_OPUS_WHOLE_DOMAIN_ARBITRATION`

Reconstruct and attack the exact bridge, execution plan, V12 wrapper adaptation, complete coordinator path, generator, tests, qualification, failure campaign, capability scan, no-access rehearsal, workflow, measurement, authority manifest, and Gemini challenge evidence.

## Required direct attacks

1. generation substitution among V12 identity, V11 consumer/result, and V4 numerical authority;
2. fake or union candidate admission and any widening of historical V11 or V12 validators;
3. independently valid substitutions of authorization, package, event IDs, source head/tree, installation receipt, identity terminal, access census, shard/census/catalog/descriptor identities, lease ownership, measurements, numerical digests, result/comparison/release/lifecycle authority;
4. bridge sealing, direct construction, copying, pickling, unauthorized serialization, mutable aliasing, and reconstruction drift;
5. missing bridge-digest binding in any consumer view, durable transition, result bundle, comparison, release, accounting, reconstruction, or package terminal;
6. descriptor substitution, path/root access capability, callback/reflection/subprocess/ambient-policy capability, and unchecked caller mapping;
7. incomplete or signature-incompatible V12 package-gate-to-terminal coordinator path, including any qualification mock that bypasses a real consumer signature;
8. duplicate primary, secondary-before-exact-primary-terminal, comparison-before-both-bundles, release/accounting/terminal reordering, replay, resume, or generic failure fallback;
9. numerical V4 or V11 result-authority drift;
10. mismatch between exact implementation head/tree, manifest, CI, qualification, and review evidence;
11. any original checkpoint resolution/access, live authority/state, Event 06 execution/ID consumption, P1 authority/execution, or historical-ledger mutation.

You may run only bounded synthetic or static validation that cannot resolve checkpoint roots, access checkpoint bytes, execute numerical cores, install authority, create durable live state, or consume IDs.

## Claim decisions

Issue exactly one `ACCEPT`, `REJECT`, or `UNRESOLVED` decision, with committed evidence, for every readiness-critical claim:

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

Report blocking, required, and unresolved finding counts. No conditional acceptance.

If and only if all 11 claims are `ACCEPT`, blocking findings are zero, required findings are zero, unresolved findings are zero, and the fresh Event 06 production-shaped no-access GO boundary is defensible, end with exactly:

`ACCEPT_F017_EVENT06_V12_TO_V11_BRIDGE_AND_READINESS`

Otherwise end with exactly `REJECT` and identify the smallest rejected or unresolved claim.
