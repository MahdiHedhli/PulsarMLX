# F017 Event 06 Sequence 17 — sanitized exact-tree review packet

Review the exact committed tree containing this packet. The measured execution implementation is commit `c6423485d84f7b0590747d49d9d17f59c2b2de04`, tree `4938b0490603caae24a7b3aa6fe02e7af0c1ff15`. This is a no-access repair review, not an Event 06 execution authorization.

## Review scope

The prior one-shot GO is tombstoned and nonreusable. The repaired path composes `CollapsedLivePromptIdentityV2` directly into the V12-to-V11 numerical bridge while preserving the exact installed identity digest. It introduces a generated 36-edge authority DAG, a validator that checks exact source/public-symbol coverage and topology, and a full synthetic no-access control path from real Sequence 14 qualification through identity, bridge, consumer views, synthetic receipts, comparison, release, accounting, and package terminal.

Blocking findings are limited to a mechanically demonstrated possibility of: (1) incorrect irreversible checkpoint reads or real numerical consumption; (2) ambiguous authorization/package/primary/secondary accounting; or (3) retry, resume, identity reuse, or a second attempt. Other findings are advisory. Report blocking and unresolved counts separately.

## Required independent attacks

1. Reproduce the prior `CollapsedLivePromptIdentityV2` versus `PromptBoundEventIdentityPlanV2` mismatch from the committed reproduction evidence.
2. Validate all 36 generated edges against actual public symbols and the full-path trace; identify source edges missing from the DAG, DAG edges missing from tests, disconnected components, or extraneous test edges.
3. Mutate installed event-identity digests through bridge input, bridge, consumer views, receipts, accounting, and terminal closure; verify fail-closure.
4. Inspect whether the repair reconstructs identity, changes frozen numerical/result authority, or makes any original-checkpoint access possible.
5. Execute or inspect the full synthetic no-access path and confirm accounting `0/0/0/0`, zero Event 06 identities instantiated/consumed, zero live installation/authorization, zero checkpoint root resolution/opens/hash/payload/mmap/tensor reads, and zero numerical execution.
6. Verify the Sequence 16 GO and the superseded Sequence 17 prompt remain tombstoned and nonreusable.

## Mechanical evidence

- causal reproduction: `docs/architecture/reviews/evidence/f017-event06-v12-sequence17-causal-type-mismatch-reproduction-v1.json`
- implementation measurement: `docs/architecture/reviews/evidence/f017-event06-v12-sequence17-implementation-measurement-v1.json`
- qualification: `docs/architecture/reviews/evidence/f017-event06-v12-sequence17-dag-composition-qualification-v1.json`
- generated DAG: `specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-authority-dag-v1.json`
- DAG validator: `scripts/research/validate_f017_event06_authority_dag_v1.py`
- full control path: `scripts/research/f017_event06_dag_derived_control_path_v1.py`
- qualification driver: `scripts/research/qualify_f017_event06_dag_composition_v1.py`
- Sequence 16 terminal authority: `docs/architecture/reviews/evidence/f017-event06-v12-sequence16-terminal-authority-manifest-v3.json`

Local results: 36/36 edges covered; 20/20 full-path repetitions with aggregate digest `9a871b5fbe52fad7cbd35f7e5c0a15a585ea5f120ae60894959b05be10b2cedf`; 1,492/1,492 combined mutations and modeled failures rejected; 21 focused tests passed; 545 applicable F017 tests plus 147 subtests passed; frozen-authority drift 0; unexpected passes 0; all access, execution, live-authority, identity-consumption, and accounting counters 0; historical master ledger 175.

Return a concise structured verdict with: reviewed head/tree, tests or inspections performed, blocking safety findings, unresolved findings, advisory findings, and one global verdict (`ACCEPT` or `REJECT`).
