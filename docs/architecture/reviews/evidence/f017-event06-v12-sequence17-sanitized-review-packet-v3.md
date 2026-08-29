# F017 Event 06 Sequence 17 — sanitized exact-tree review packet cycle 3

Review the exact committed implementation at head `0dcd07185d794b464ffef5e57a4c2f8e5828fe74`, tree `1ba69ff2f8d4b0bc110930413aa35e7f5f4dcc26`. This is a no-access repair review, not an Event 06 execution authorization.

## Cycle 2 findings and repair

The second Opus review of head `b02992a9405cb48e4c9757676a6316523e5b3a6c` found four blocking provenance boundaries: a public raw-view minting helper, writable sealed v1 objects, incomplete legacy-terminal validation, and a bundle binder accepting arbitrary result-PASS mappings. It also left three provenance questions unresolved around raw transition-chain/V11-closure hashes, primary-terminal bundle binding, and multiple pure terminals. Repair loop 5 removes the public raw-view entry point; makes sealed v1 objects immutable; validates exact bundle-index schema, identity, role, package, event, and digest; requires exact sealed bundle, transition-chain, V11-closure, and accounting objects; invokes the complete legacy package-terminal validator; and expands the generated DAG to 40 typed edges. Eighteen real downstream substitution attacks now exercise those boundaries.

## Required review scope

Blocking findings are limited to a mechanically demonstrated possibility of: (1) incorrect irreversible checkpoint reads or real numerical consumption; (2) ambiguous authorization/package/primary/secondary accounting; or (3) retry, resume, identity reuse, or a second attempt. All other findings are advisory. Report blocking and unresolved counts separately.

Independently attack:

1. every generated producer-to-consumer boundary in the 40-edge DAG;
2. attempts to forge a sealed consumer view, mutate any sealed object, or pass raw mappings/digests at typed boundaries;
3. primary-terminal bundle provenance and role/event/package continuity;
4. transition-chain, V11-closure, accounting, legacy-terminal, and successor-terminal provenance;
5. the exact collapsed installed identity digest through bridge, consumers, receipts, bundles, accounting, and terminal;
6. attempts to reconstruct identity, change frozen numerical/result authority, create a GO or live authority, consume an Event 06 identity, open the checkpoint root or shards, run numerical operations, or alter accounting;
7. the Sequence 16 GO and superseded Sequence 17 prompt tombstones.

## Mechanical evidence and commands

- reproduction: `docs/architecture/reviews/evidence/f017-event06-v12-sequence17-causal-type-mismatch-reproduction-v1.json`
- repaired implementation measurement: `docs/architecture/reviews/evidence/f017-event06-v12-sequence17-implementation-measurement-v3.json`
- repaired qualification: `docs/architecture/reviews/evidence/f017-event06-v12-sequence17-dag-composition-qualification-v3.json`
- cycle-2 AGY result: `docs/architecture/reviews/evidence/f017-event06-v12-sequence17-agy-cycle-02-normalized-result-v1.json`
- cycle-2 Opus result: `docs/architecture/reviews/evidence/f017-event06-v12-sequence17-opus-cycle-02-normalized-result-v1.json`
- generated DAG: `specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-authority-dag-v1.json`
- DAG validator: `scripts/research/validate_f017_event06_authority_dag_v1.py`
- full control path: `scripts/research/f017_event06_dag_derived_control_path_v1.py`
- qualification driver: `scripts/research/qualify_f017_event06_dag_composition_v1.py`
- exact-head FULL_NATIVE: run `33264313283`

From a detached review worktree, the complete test suite can be run with the implementation worktree interpreter:

```text
PYTHONPATH=<review-worktree>/scripts/research /private/tmp/f017-seq14-source.G1OoWi/.venv/bin/python -m pytest -q <review-worktree>/scripts/research/tests/test_f017_*.py
```

Local results: 40/40 DAG edges and signature boundaries; 20/20 deterministic full-path repetitions with aggregate digest `206bfd9f3e11ed2879eb892c12ee608fdcf15de3fbdf0ead0942d370d1dc3775`; 160/160 structural edge mutations; 18/18 real downstream binding substitutions; 1,526/1,526 combined Sequence 17 mutation cases; 22 focused tests; 545 applicable F017 tests plus 147 subtests; frozen-authority drift 0; unexpected passes 0; all access, execution, live-authority, identity-consumption, and accounting counters 0; historical master ledger 175.

Return a concise structured verdict with reviewed head/tree, tests or inspections performed, blocking safety findings, unresolved findings, advisory findings, and one global verdict (`ACCEPT` or `REJECT`).
