# F017 Checkpoint Identity Lifecycle V7 — Opus Design Review, Cycle 05

Reviewed exact committed bytes at `833d96109f79f51a7627da61d8e854a95e2b15d7` in a detached read-only worktree. No original checkpoint shard was opened, hashed, mmapped, or pread; no Event-04 authority was minted; no real oracle or P1 attempt 2 executed; and no reviewed file was modified.

## Verdict

`REJECT`

The reviewer verified closure of all eleven cycle-04 required findings, all 16 committed mutation probes, all 14 manifest bindings, 39 states, 52 transitions, 29 maximal traces, 15 reachable outcomes, historical ledger terminal 175, active live generation `NONE`, and original checkpoint access zero.

## BLOCKING

1. `checkpoint_identity_receipt` requires `descriptor_lease_manifest_sha256`, but the bound lease manifest is created only after the receipt is sealed. The receipt is unsatisfiable on every trace.
2. `primary_descriptor_continuity_report` inherits a mandatory `primary_continuity_report_sha256` whose sole binding is the same artifact. The schema therefore requires a SHA-256 of itself, and the validator skips inherited `schema_ref` keys.
3. `secondary_descriptor_continuity_report` permits zero descriptor identities on `COMPLETE_SUCCESS`, voiding the required post-primary continuity check across all five retained graph descriptors.

## NON_BLOCKING_REQUIRED

1. SHA-256 back-reference closure remains one level deep and does not resolve global bindings transitively; success outcomes do not require the identity durable start or package claim reached through those bindings.
2. Primary and secondary pre-start failures have delta zero but do not forbid their corresponding durable-start artifacts.
3. The lifecycle model's unconditional safety invariants and 16 adjacent safety declarations are not independently validator-gated.
4. `EVIDENCE_BANKING_FAILURE` omits both continuity reports even though that outcome is defined as after complete execution.
5. Path timing covers only 15 of 30 banked artifact kinds, omitting load-bearing durable-start and ledger artifacts.

## DEFENSE_IN_DEPTH

The reviewer also reported transition-name path-timing ambiguity, absent lease-artifact prohibitions on identity failures, a vacuous post-claim terminal path that bypasses release states, a bare byte-census literal, unconstrained `path_reopen_count`, one ungated duplicate path-reopen declaration, unchecked descriptor-identity field restatements, and a validator-local ignored-path allowlist.

Implementation entry remains closed. The fifth and final permitted design-review cycle is exhausted.
