# F017 V9 root-continuity graph — Opus ARBITER cycle 02 corrected packet

Use a fresh `claude-opus-5` session at high effort in a detached read-only worktree. Review exact committed bytes at evidence head `09a1122e93f38de9b8cdc6bcebe6a60ab5b71f6f`. Repository evidence outranks this request. Do not modify repository files, access original checkpoint shards, mint or execute Event 04, or execute P1 attempt 2. Executable adversarial tests are authorized only against synthetic roots under `/private/tmp`; set `PYTHONDONTWRITEBYTECODE=1` and disable pytest cache writes.

The cycle-02 v1 request is preserved as historical evidence. No review completed from it because its incorrectly expanded evidence hash did not resolve; this successor changes that hash to the exact Git commit and makes no substantive review-scope change.

Cycle 01 produced no arbiter verdict because its tool mode prevented executable attacks. Its exact response is historical evidence, not an acceptance or rejection. Five candidate issues from that response are explicitly recorded in challenge ledger v5. Four were repaired at implementation head `456b5d8d32bab01fb00fb98c25b1261be42e94e7`; the fifth is reconciled by the two distinct, documented qualification repetition policies. Exact-head FULL_NATIVE run `32859713646` passed after those repairs.

You are the claim-by-claim ARBITER. Return an explicit `ACCEPT`, `REJECT`, or `UNRESOLVED` verdict for every one of the 25 readiness-critical claims in claim ledger v6. `UNRESOLVED` is not acceptance. Also return exactly one global verdict: `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_AUTHORIZATION` or `REJECT`. No conditional or interim acceptance.

Packet:

- final authority manifest: `docs/architecture/reviews/evidence/f017-v9-root-continuity-authority-manifest-v7.json`
- graph state: `docs/architecture/reviews/evidence/f017-v9-root-continuity-graph-state-v6.json`
- claim ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-claim-ledger-v6.json`
- challenge ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-challenge-ledger-v5.json`
- support ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-support-ledger-v4.json`
- cycle-01 exact response: `docs/architecture/reviews/evidence/f017-v9-root-continuity-opus-arbiter-cycle-01-exact-response.json`
- implementation measurement: `docs/architecture/reviews/evidence/f017-v10-root-continuity-implementation-measurement-v10.json`
- root/decode qualification: `docs/architecture/reviews/evidence/f017-v10-root-continuity-bounded-decode-qualification-v9.json`
- retained runtime qualification: `docs/architecture/reviews/evidence/f017-event04-runtime-hardening-qualification-v10-v9.json`
- production rehearsal: `docs/architecture/reviews/evidence/f017-event04-production-shaped-no-access-rehearsal-v10-v10.json`
- exact-head CI: `docs/architecture/reviews/evidence/f017-v10-root-continuity-full-native-ci-v5.json`
- root contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-accounting-root-continuity-v1.json`
- decode contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-bounded-artifact-decode-v1.json`
- runtime authority: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-authority-manifest-v10.json`
- implementation diff: `git diff 4f47078e69b7847e486c9ecc14f95f5c793e3d98..456b5d8d32bab01fb00fb98c25b1261be42e94e7`

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
11. Search the active import closure for direct or indirectly resolved `json.load`/`json.loads`, including `os.sys.modules`, import aliases, object-graph traversal, dynamic attributes, `eval`, `exec`, `compile`, and relative imports.
12. Verify no raw `RecursionError`, `TypeError`, or other uncontrolled decode/serialization exception crosses terminalization.
13. Inject a non-serializable terminal payload and verify both bound roots fail through the maximal-constructible result without partial authority.
14. Inject constructor failures after one and two directory-descriptor acquisitions and verify no retained-descriptor leak.
15. Independently enumerate the active import closure and compare it with all 43 measured implementation bindings.
16. Inspect exact runtime-derived accounting outcomes.
17. Inspect all 47 modeled failure outcomes. Reconcile rather than conflate: the root/decode suite executes all 47 exactly five times (`235`); the retained runtime suite executes ordinary outcomes three times and high-risk outcomes five times (`201`).
18. Inspect FULL_NATIVE run `32859713646`, required jobs, historical/active separation, and required native skip census zero.
19. Verify production-shaped rehearsal resolves all 1,410 graph tensors, rejects all 399 non-access tensors, and performs zero shard opens/reads/numerical operations.
20. Verify original checkpoint access is zero.
21. Verify no Event-04 authorization, package start, or execution exists.
22. Verify no P1 attempt-2 authority or execution exists.

Use finding classifications `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`. Any `BLOCKING` or `NON_BLOCKING_REQUIRED` finding requires `REJECT` for its claim and globally.

Return one JSON object and no Markdown fences:

```json
{
  "reviewed_head": "09a1122e93f38de9b8cdc6bcebe6a60ab5b71f6f",
  "reviewer_model": "claude-opus-5",
  "claim_verdicts": [
    {"claim_id":"C-REF-001","verdict":"ACCEPT|REJECT|UNRESOLVED","evidence":["..."],"invalidation_disposition":["..."]}
  ],
  "findings": [
    {"finding_id":"O-C02-001","claim_id":"C-...","classification":"BLOCKING|NON_BLOCKING_REQUIRED|DEFENSE_IN_DEPTH","attack":"...","observed":"...","required_repair":"..."}
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

The claim verdict list must contain every claim exactly once. Do not infer PASS from builder status or Gemini closure; reconstruct the evidence and execute the attacks.
