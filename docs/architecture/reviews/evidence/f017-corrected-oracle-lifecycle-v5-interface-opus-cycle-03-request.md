# F017 lifecycle-v5 interface review — cycle 3

Review the exact committed bytes at `0bfbe244461cb4b36725269246394f36dc7d9d4f` in a detached, read-only worktree. Use Claude Opus 5 at high effort. Do not modify the worktree and do not access any original checkpoint shard.

This is the third and final interface-design checkpoint. Reconstruct cycle 1 and cycle 2 from committed request, exact-response, normalized-result, and repair-disposition artifacts. Independently rerun the lifecycle generator, semantic validator, unit tests, and adversarial mutations. Do not trust generated claims merely because generator and validator agree.

Attack, at minimum:

1. Whether fixed independent semantic projection hashes prevent coordinated model-plus-regeneration drift of authorization fields, transition preconditions, prohibited side effects, accounting, paths, serialization, measurement, supersession, and P1/expected-token boundaries.
2. Whether candidate and installed authorization documents have one exact realizable layout, contain no generic `bindings` channel, carry identical authorization fields, exclude candidate self-SHA and post-candidate report SHAs, and can be byte-identical.
3. Whether installation receipt evidence, rather than authorization bytes, binds candidate SHA, installed SHA, and both candidate-validation reports.
4. Whether every transition failure has a distinct durable-prefix variant with exact path state, actual ledger deltas, complete required artifacts, and the complete forbidden-artifact complement.
5. Whether unstarted consumers can acquire fabricated receipt, terminal, ledger, or SHA evidence; whether started consumers can omit required evidence; and whether package/comparison artifacts are forbidden before their phases.
6. Whether payload-to-binding duplicate values have an exact equality rule and exact key census.
7. Whether all artifact schema IDs, identity paths, top-level keys, payload keys, self-SHA rules, grammar records, authority sources, and writers are pinned bidirectionally.
8. Whether root roles, all 36 root relations, absent-leaf validation, per-artifact path descriptors, artifact post-create validation, candidate removal, and candidate/installed descriptor relationships are satisfiable and independently anchored.
9. Whether readback serialization defines exact covered bytes and full durability/reopen/parse/schema/SHA sequence.
10. Whether implementation measurement semantics and required path census are exact enough for the implementation phase to instantiate a commit-head/path/SHA manifest without self-reference.
11. Whether current-tree v1, v2, and v3 production mint/execute surfaces are truthfully retired while historical commits remain reconstructable.
12. Whether the 46 permanent mutations meaningfully cover these guarantees rather than succeeding through no-op tautologies.

Classify findings as `BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`. Both blocking and non-blocking-required findings prevent acceptance. State whether any finding requires numerical-source change or original-checkpoint access.

Required terminal verdict, exactly one:

- `ACCEPT_LIFECYCLE_V5_INTERFACE_FOR_IMPLEMENTATION`
- `REJECT`

Confirm safety: Event 04 authorization absent, Event 04 unexecuted, original checkpoint access zero, real oracle executions zero, P1 attempt 2 absent, historical master ledger 175, and the four numerical authority SHAs unchanged.
