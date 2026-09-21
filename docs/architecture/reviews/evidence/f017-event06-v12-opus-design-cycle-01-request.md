# F017 Event 06 V12 checkpoint-identity authority design ARBITER cycle 1

Use `claude-opus-5`, effort high, in this fresh detached read-only worktree. Review exact committed bytes only. Do not modify files and do not access checkpoint shard payloads.

Independently reconstruct the Event 05 failure from:

- `docs/architecture/reviews/evidence/f017-event05-v11-terminal-execution-failure-v2.json`
- `docs/architecture/reviews/evidence/f017-event05-v11-terminal-package-v2/package-evidence/failure-terminal-capsule.json`
- `scripts/research/f017_checkpoint_identity_producer_v10.py`
- `scripts/research/execute_f017_corrected_oracle_event_v11.py`

Review the V12 design and control plane:

- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-authority-design-v12.json`
- `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-lifecycle-design-v12.json`
- `docs/architecture/reviews/evidence/f017-event06-identity-producer-claim-ledger-v1.json`
- `docs/architecture/reviews/evidence/f017-event06-identity-producer-challenge-ledger-v4.json`
- `docs/architecture/reviews/evidence/f017-event06-identity-producer-support-ledger-v4.json`
- `docs/architecture/reviews/evidence/f017-event06-v12-gemini-design-cycle-03-normalized-result.json`

Required attacks: generic scope and operation-class separation; absence of event-number capability branches; candidate versus installed authority; exact types/key census/alias rejection; primary-secondary-identity triple validation before package claim; runtime revalidation after package start but before any shard open; exact package and consumer deltas for every modeled failure; generic fallback prohibition for modeled identity failures; V10/V11 historical immutability; synthetic instantiability and zero-original-access design; final fresh-GO boundary.

Issue one verdict for every exact claim ID: C-SCOPE-001, C-SCOPE-002, C-INTERFACE-001, C-VALIDATE-001, C-VALIDATE-002, C-VALIDATE-003, C-RUNTIME-001, C-RUNTIME-002, C-FAIL-001, C-FAIL-002, C-FAIL-003, C-HIST-001, C-SYN-001, C-NOACCESS-001, C-CI-001, C-GO-001. Allowed per-claim verdicts are ACCEPT, REJECT, UNRESOLVED. Design-stage claims may be ACCEPT only as implementable design obligations, not as proof that implementation already exists.

Return exactly one global verdict:

`ACCEPT_F017_CHECKPOINT_IDENTITY_AUTHORITY_V12_FOR_IMPLEMENTATION`

or

`REJECT`

No conditional acceptance. Cite exact committed paths and keys for every material conclusion. State blocking, non-blocking-required, and unresolved counts.
