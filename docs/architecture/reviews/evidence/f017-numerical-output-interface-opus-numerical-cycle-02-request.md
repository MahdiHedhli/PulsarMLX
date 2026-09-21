# F017 numerical output interface — Opus numerical ARBITER cycle 02

Fresh read-only session. Review exact committed head
`ed1e8a49c0c8e3ec6a8328e7f82c9313c051dd78`, tree
`131af78d451fab30d3983759826c7a189c74dbd5` in the self-contained clone.

Cycle 01 accepted all twelve numerical engineering claims plus C-QUAL-001, but
rejected because C-CI-001 had been closed prematurely and the R8 receipt had a
corrupt requalification SHA. Verify both repairs independently:

1. claim-ledger-v6 leaves C-CI-001 PROPOSED, introduced at R17 and dependent
   on C-V11-002 and C-QUAL-001;
2. node-r8-receipt-v2 supersedes v1, closes no claim, and uses typed
   path/SHA bindings with the exact requalification SHA;
3. scripts/ci/validate_evidence_change.py rejects unpaired receipt SHAs and
   resolves every typed receipt binding;
4. the new regression tests cover both acceptance and rejection;
5. exact-head FULL_NATIVE run 32976273072 at repair head
   050e986b70e0b5253acfba68863b5c1dcabc5d24 passes with required native skips
   0;
6. EVIDENCE_ONLY run 32978071844 at this reviewed head passes evidence
   validation with native jobs launched 0.

Reconfirm that no repair changed either V3 numerical core or the V4 numerical
contract/requalification, and preserve cycle-01 ACCEPT verdicts where their
dependencies remain exact.

Issue ACCEPT/REJECT/UNRESOLVED for the numerical-stage claims:
`C-OUT-001`, `C-OUT-002`, `C-FORM-001`, `C-FORM-002`, `C-LEGACY-001`,
`C-LEGACY-002`, `C-BITS-001`, `C-BITS-002`, `C-PURITY-001`,
`C-ONEEXEC-001`, `C-INDEP-001`, `C-QUAL-001`.

Report `C-CI-001_stage_disposition` exactly as either
`PROPERLY_DEFERRED_TO_R17` or `INVALID`. Do not accept the V11-wide CI claim at
this stage; R17 must decide it after C-V11-002 exists.

Never access original checkpoint shards. Return strict JSON with reviewed_head,
reviewed_tree, blocking, non_blocking_required, defense_in_depth,
claim_verdicts, C-CI-001_stage_disposition, original_checkpoint_access,
unresolved_material_disagreement, and global_verdict.

Required numerical-stage success:
`ACCEPT_F017_NUMERICAL_OUTPUT_INTERFACE_AND_REQUALIFICATION`.
Otherwise return `REJECT`. No conditional acceptance.
