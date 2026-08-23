# F017 lifecycle-interface design review — cycle 3 (final interface budget)

Review committed bytes only in detached read-only worktree:

`/private/tmp/f017-lifecycle-interface-review-c3.2KRsmx`

Reviewed head:

`5be2917007de6800337965e22621a2ded6c82b37`

This is the third and final budgeted interface-design checkpoint. Do not modify the worktree. Recompute, regenerate, execute the validator, and independently attack the design.

Cycle 2 returned REJECT with B-1 through B-6, N-1 through N-8, and D-1 through D-3. Verify these repairs:

- Candidate and installed authorization now have exactly identical 96-identity sets, paths, types, top-level census, and byte-identity semantics. Candidate SHA and validation-report SHAs live outside installed bytes.
- Nested package/primary/secondary/lifecycle-plan leaves are now validated against exact nested censuses.
- The task, geometry, catalog path, P1 prohibition, full memory authority, qualification authority, authorization state/live/scope, all package and consumer lifecycle fields, all grant paths, all attempts/retries/resume values, and all receipt/terminal schemas are typed identities.
- Primary and secondary roles, producers, decoders, capabilities, event IDs, and accounting classes are pinned/distinct.
- The independent validator now freezes 129 identity names/types, 21 column counts, 2,296 always-required cells, critical grammar facts, pins, and consumer independence. It rejects 10 semantic drift mutations, including consistent multi-document drift.
- Unstarted-consumer closure is modeled as four package-terminal outcomes. Consumer terminal hashes are outcome-conditional in package receipts, never fabricated for unstarted consumers.
- Every generic artifact has a fixed schema ID, an exact artifact-ID channel, exact binding paths/types, and an exact payload-key census. Artifact readback SHA binds the entire schema+identity+payload document.
- All grant fields are typed identities, including boolean hardening.
- Package/primary/secondary ledgers carry typed event class, sequence, predecessor, result, durable-start semantics, and chain rules.
- Historical ledger is pinned by branch, exact path, SHA, terminal 175, and delta 0.
- V3 supersession now binds exact retired paths and historical SHAs plus required behaviors.
- Root relationships now specify required strict ancestry, direction, disjointness, path normalization, strict resolution, and non-symlink ancestry.
- Primary-then-secondary ordering and memory freshness are explicit.
- Approval `authority_head` is separate from the append-only evidence descendant.

Attack particularly:

1. Any remaining self-reference or unconstructible identity.
2. Candidate/install byte identity and installation-receipt feasibility.
3. Nested census/path representability for all 129 identities.
4. Whether conditional package outcomes truthfully close before-primary, before-secondary, post-secondary, and success paths without false consumer starts.
5. Whether artifact ID, schema, bindings, and payload channels are exact and non-conflicting.
6. Whether role/numerical independence and accounting classes are mechanically pinned.
7. Whether frozen independent validation catches generator-consistent drift and path collisions.
8. Whether ledger chain semantics prevent reservation/counting confusion.
9. Whether historical ledger and v3 supersession are exact enough for implementation.
10. Whether implementation can proceed without original checkpoint access or numerical changes.

Severities:

- `BLOCKING`
- `NON_BLOCKING_REQUIRED`
- `DEFENSE_IN_DEPTH`

Both BLOCKING and NON_BLOCKING_REQUIRED prevent acceptance. Return exactly one terminal verdict:

- `ACCEPT_INTERFACE_DESIGN_FOR_V4_IMPLEMENTATION`
- `REJECT`

No conditional acceptance. This is not the final whole-domain review.
