# F017 numerical output interface — Opus numerical ARBITER cycle 01

Act as final numerical arbiter, read-only, in the self-contained clone supplied
by the caller. Review exact committed head
`046b1a81eb6d6e969a1773f609576d0123a8f507`, tree
`c8343640e2b8184024a2a4b0861aea5fd1065a3c`.

The measured numerical implementation is head
`858f2013829993a23508b673a4bbc1d6b8d6e243`, tree
`0919de5f7142b5320e275edd57daa8948185db08`; descendants are evidence-only.
FULL_NATIVE run `32971168057` passed, required native skips 0. Evidence-only run
`32972935273` passed with native jobs launched 0.

Independently:

1. reconstruct both historical V2 core authorities;
2. inspect both successor V3 cores and compare numerical expressions/order;
3. rerun legacy equivalence and output-interface tests;
4. independently verify every payload SHA and every payload element;
5. prove each role executes its graph exactly once and does not recompute final
   normalization or output projection;
6. verify source-read equality;
7. attempt output mutation and control serialization;
8. inspect the capability policy for callback, reflection, I/O, checkpoint,
   subprocess, lifecycle, authorization, and dynamic-import authority;
9. verify primary/secondary numerical independence;
10. inspect the complete V4 requalification and exact-head CI;
11. verify original checkpoint access is zero and do not access original shards.

Issue an explicit verdict for each readiness-critical numerical claim:
`C-OUT-001`, `C-OUT-002`, `C-FORM-001`, `C-FORM-002`, `C-LEGACY-001`,
`C-LEGACY-002`, `C-BITS-001`, `C-BITS-002`, `C-PURITY-001`,
`C-ONEEXEC-001`, `C-INDEP-001`, `C-QUAL-001`, `C-CI-001`.

Allowed claim verdicts: `ACCEPT`, `REJECT`, `UNRESOLVED`.

Return strict JSON with reviewed_head, reviewed_tree, blocking,
non_blocking_required, defense_in_depth, claim_verdicts (each with claim_id,
verdict, evidence, invalidation_disposition), original_checkpoint_access,
unresolved_material_disagreement, and global_verdict.

The only acceptable global success string is:
`ACCEPT_F017_NUMERICAL_OUTPUT_INTERFACE_AND_REQUALIFICATION`.
Otherwise return `REJECT`. No conditional acceptance.
