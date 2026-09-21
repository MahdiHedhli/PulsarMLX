# F017 V9 root-continuity graph — Opus ARBITER cycle 01

Use a fresh `claude-opus-5` session at high effort in a detached read-only worktree. Review exact committed bytes at evidence head `1c5356ad58376fc4f8a11cb69f251d3c2da680ca`. Repository evidence outranks this request. Do not modify files, access original checkpoint shards, mint or execute Event 04, or execute P1 attempt 2.

You are the claim-by-claim ARBITER. Return an explicit `ACCEPT`, `REJECT`, or `UNRESOLVED` verdict for every one of the 25 readiness-critical claims in the claim ledger. `UNRESOLVED` is not acceptance. Also return exactly one global verdict: `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_AUTHORIZATION` or `REJECT`. No conditional or interim acceptance.

Packet:

- final authority manifest: `docs/architecture/reviews/evidence/f017-v9-root-continuity-authority-manifest-v6.json`
- graph state: `docs/architecture/reviews/evidence/f017-v9-root-continuity-graph-state-v5.json`
- claim ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-claim-ledger-v5.json`
- challenge ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-challenge-ledger-v4.json`
- support ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-support-ledger-v3.json`
- implementation measurement: `docs/architecture/reviews/evidence/f017-v10-root-continuity-implementation-measurement-v9.json`
- root/decode qualification: `docs/architecture/reviews/evidence/f017-v10-root-continuity-bounded-decode-qualification-v8.json`
- retained runtime qualification: `docs/architecture/reviews/evidence/f017-event04-runtime-hardening-qualification-v10-v8.json`
- production rehearsal: `docs/architecture/reviews/evidence/f017-event04-production-shaped-no-access-rehearsal-v10-v9.json`
- exact-head CI: `docs/architecture/reviews/evidence/f017-v10-root-continuity-full-native-ci-v4.json`
- root contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-accounting-root-continuity-v1.json`
- decode contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-bounded-artifact-decode-v1.json`
- runtime authority: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-authority-manifest-v10.json`
- implementation diff since prior cycle support: `git diff 3f8fa960f4a0df7ab0cd64e6c1aab9de4e8c5aba..4f47078e69b7847e486c9ecc14f95f5c793e3d98`

Independently perform these direct attacks:

1. Replace the primary root with an empty directory after package start.
2. Replace the primary root with a symlink.
3. Rename the original root and recreate its pathname.
4. Make the primary root unreadable.
5. Corrupt and truncate the retained accounting journal.
6. Make the fallback unusable.
7. Verify no false zero under every durable-start lower bound.
8. Verify terminal obligation after package, primary, and secondary durable starts.
9. Inject deeply nested JSON at every durable-start class.
10. Inject malformed journal, receipt, and terminal artifacts.
11. Search the active import closure for direct or indirectly resolved `json.load`/`json.loads`, including `os.sys.modules`, import aliases, object-graph traversal, and dynamic attributes.
12. Verify no raw `RecursionError` crosses terminalization.
13. Inspect exact runtime-derived accounting outcomes.
14. Inspect all 47 modeled failure outcomes and their 235 executions.
15. Inspect FULL_NATIVE run `32856475208`, both required jobs, and skip census zero.
16. Verify original checkpoint access is zero.
17. Verify no Event-04 authorization or execution exists.
18. Verify no P1 attempt-2 authority or execution exists.

Also attack the cycle-03 repairs directly: component-by-component directory acquisition, final path/descriptor identity comparison, retained synthetic-root descriptor reuse, offline accounting without `lstat`/pathname reopen, the pre-package exact-outcome zero rule, `os.sys`, `getattr(os,'sys')`, `vars`, `__builtins__`, and Python object-graph capability traversal.

Use findings classifications `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`. Any BLOCKING or NON_BLOCKING_REQUIRED finding requires `REJECT` for its claim and globally.

Return one JSON object and no Markdown fences:

```json
{
  "reviewed_head": "1c5356ad58376fc4f8a11cb69f251d3c2da680ca",
  "reviewer_model": "claude-opus-5",
  "claim_verdicts": [
    {"claim_id":"C-REF-001","verdict":"ACCEPT|REJECT|UNRESOLVED","evidence":["..."],"invalidation_disposition":["..."]}
  ],
  "findings": [
    {"finding_id":"O-C01-001","claim_id":"C-...","classification":"BLOCKING|NON_BLOCKING_REQUIRED|DEFENSE_IN_DEPTH","attack":"...","observed":"...","required_repair":"..."}
  ],
  "accepted_claim_count": 0,
  "rejected_claim_count": 0,
  "unresolved_claim_count": 0,
  "original_checkpoint_access_observed": 0,
  "event_04_authorization_observed": false,
  "p1_attempt_2_observed": false,
  "global_verdict": "ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_AUTHORIZATION|REJECT"
}
```

The claim verdict list must contain every claim exactly once. Do not infer PASS from builder status or Gemini closure; reconstruct the evidence and attack it.
