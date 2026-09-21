# F017 Event 06 Sequence 17 — sanitized exact-tree review packet cycle 2

Review the exact committed implementation at head `77b5c0831f2ee199fc5c5b3f36190116bdc48466`, tree `d9dc86bc7c0d917cade6034aecc0c80e9803bbe0`. This is a no-access repair review, not an Event 06 execution authorization.

## Cycle 1 finding and repair

The first Opus review of head `ff0f1d6f04a469a10c7390459a917c4abb546845` rejected one in-scope accounting ambiguity: comparison, release, accounting, and package-terminal consumers accepted bare 64-hex digests, so a primary/secondary swap, self-pair, or unrelated digest could reach terminal closure. Repair loop 4 replaces those digest-only boundaries with exact sealed producer objects that validate bridge, role, authorization, package, event, result, and object-type continuity. The real downstream consumers are now invoked by twelve substitution attacks.

## Required review scope

Blocking findings are limited to a mechanically demonstrated possibility of: (1) incorrect irreversible checkpoint reads or real numerical consumption; (2) ambiguous authorization/package/primary/secondary accounting; or (3) retry, resume, identity reuse, or a second attempt. All other findings are advisory. Report blocking and unresolved counts separately.

Independently attack:

1. every generated producer-to-consumer boundary in the 37-edge DAG;
2. comparison role swapping, primary/secondary self-pairing, and raw-document substitution;
3. comparison-to-release, release-to-accounting, accounting-to-legacy-terminal, and accounting-closure-to-successor-terminal provenance;
4. the exact collapsed installed identity digest through bridge, consumers, receipts, accounting, and terminal;
5. attempts to reconstruct identity, change frozen numerical/result authority, create a GO or live authority, consume an Event 06 identity, open the checkpoint root or shards, run numerical operations, or alter accounting;
6. the Sequence 16 GO and superseded Sequence 17 prompt tombstones.

## Mechanical evidence and commands

- reproduction: `docs/architecture/reviews/evidence/f017-event06-v12-sequence17-causal-type-mismatch-reproduction-v1.json`
- repaired implementation measurement: `docs/architecture/reviews/evidence/f017-event06-v12-sequence17-implementation-measurement-v2.json`
- repaired qualification: `docs/architecture/reviews/evidence/f017-event06-v12-sequence17-dag-composition-qualification-v2.json`
- generated DAG: `specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-authority-dag-v1.json`
- DAG validator: `scripts/research/validate_f017_event06_authority_dag_v1.py`
- full control path: `scripts/research/f017_event06_dag_derived_control_path_v1.py`
- qualification driver: `scripts/research/qualify_f017_event06_dag_composition_v1.py`
- exact-head FULL_NATIVE: run `33262291399`

From a detached review worktree, the complete test suite can be run with the implementation worktree interpreter:

```text
PYTHONPATH=<review-worktree>/scripts/research /private/tmp/f017-seq14-source.G1OoWi/.venv/bin/python -m pytest -q <review-worktree>/scripts/research/tests/test_f017_*.py
```

Local results: 37/37 DAG edges and signature boundaries; 20/20 deterministic full-path repetitions with aggregate digest `2707682e18e531da407fb309a6b9e3114579c664169879d73738a2cda734f23f`; 148/148 structural edge mutations; 12/12 real downstream binding substitutions; 1,508/1,508 combined Sequence 17 mutation cases; 15 focused tests; 545 applicable F017 tests plus 147 subtests; frozen-authority drift 0; unexpected passes 0; all access, execution, live-authority, identity-consumption, and accounting counters 0; historical master ledger 175.

Return a concise structured verdict with reviewed head/tree, tests or inspections performed, blocking safety findings, unresolved findings, advisory findings, and one global verdict (`ACCEPT` or `REJECT`).
