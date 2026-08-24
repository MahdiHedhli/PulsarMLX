# F017 Event-04 Authority Reconciliation Opus Review Cycle 01

Use a fresh `claude-opus-5` session at high effort in a detached read-only worktree. Review exact committed repository bytes at evidence head `a71d23f2f4371324bf513688813e6a5854351fcc`. The accepted implementation measurement head is `418a4121ceeb396b56a83158ce2424c138ec7ffa`, tree `eb3374332e5b943a5d37379a3b16e0886af823a3`, and the reconciled authority bundle head is `d5d4c412180d7a32e25bafff6f25ef598438e885`. Repository bytes outrank this request.

Do not modify repository files, access original checkpoint shard payloads, mint or execute Event 04, run a real oracle, or execute P1 attempt 2. Use temporary scratch outside the worktree for mutations.

Independently perform all of the following:

1. reconstruct the original parser/coordinator mismatch;
2. compute parser SHA-256 from exact measured Git bytes;
3. compute coordinator SHA-256 from exact measured Git bytes;
4. inspect implementation measurement V4 and all 64 entries;
5. inspect the stale scientific-access V6 authority and the append-only successor;
6. inspect the original lifecycle declaration and correction declaration;
7. verify every path/SHA equality across Git, measurement, scientific access, correction, authority manifest, inert fixture, and rehearsal;
8. mutate parser and coordinator bindings independently;
9. mutate the measurement head and tree;
10. mutate outer and inner artifacts consistently while leaving Git bytes unchanged;
11. prove exact Git bytes still control after coordinated mutation;
12. inspect the corrected inert fixture and refusal of live authority;
13. inspect completeness of the corrected authority manifest;
14. rerun the production-shaped no-access rehearsal;
15. inspect FULL_NATIVE run `32726480096` at `d5d4c412180d7a32e25bafff6f25ef598438e885`, EVIDENCE_ONLY run `32727677562` at `c442e54e5004cf231e6571142dd60a8b3a141d78`, and the banked CI census;
16. verify required native skips are zero and evidence-only native jobs are zero;
17. verify no Event-04 authorization or execution exists;
18. verify original checkpoint shard opens/reads remain zero and P1 attempt 2 is absent.

Rerun `scripts/research/validate_f017_event04_authority_reconciliation_v1.py` against the corrected V2 bundle with all 18 mutations. Confirm that a valid outer scientific-access SHA cannot excuse stale internal parser/coordinator bindings. Rerun the corrected rehearsal only in its metadata-only mode.

Gemini cycle 01 reviewed head `c442e54e5004cf231e6571142dd60a8b3a141d78` and returned `ACCEPT`, with zero blocking and non-blocking-required findings and no material disagreement. Its exact response and normalized result are committed at the reviewed evidence head.

Classify findings as `BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`. Both `BLOCKING` and `NON_BLOCKING_REQUIRED` prevent acceptance. Return exactly one final verdict:

- `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_AUTHORIZATION_PREPARATION`
- `REJECT`

No conditional acceptance.
