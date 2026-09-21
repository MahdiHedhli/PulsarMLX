# F017 V9 root-continuity graph — Gemini CHALLENGE cycle 02 corrected packet

Use a fresh `gemini-3.1-pro-high` session at high effort. Work read-only from exact committed bytes at evidence head `9dd33af17131fc8bccaa7e36195c349a5d1c76ac`. Repository evidence outranks this request. Do not modify files, access original checkpoint shards, mint or execute Event 04, or execute P1 attempt 2.

Your role is CHALLENGE, not arbiter. Re-attack every one of the 25 readiness-critical claims in `docs/architecture/reviews/evidence/f017-v9-root-continuity-claim-ledger-v2.json`, with special focus on all seven cycle-01 support dispositions. A claim without a defect may receive no challenge, but explicitly report the census of attacked claim IDs. Do not inherit the builder's CLOSED status without reconstructing the implementation and tests.

The original cycle-02 request is preserved as historical evidence. This successor corrects its graph-ledger paths after the evidence-only append-only guard required successor ledgers.\n\nPacket:

- authority manifest: `docs/architecture/reviews/evidence/f017-v9-root-continuity-authority-manifest-v4.json`
- graph state: `docs/architecture/reviews/evidence/f017-v9-root-continuity-graph-state-v2.json`
- claims: `docs/architecture/reviews/evidence/f017-v9-root-continuity-claim-ledger-v2.json`
- cycle-01 challenges: `docs/architecture/reviews/evidence/f017-v9-root-continuity-challenge-ledger-v2.json`
- cycle-01 support: `docs/architecture/reviews/evidence/f017-v9-root-continuity-support-ledger-v1.json`
- implementation diff: `git diff be5466479cda2a02bc5f23bcabd0c03a09862f7f..3f138d50014db76f7591281c96a7f3d8da6c2253`
- implementation measurement: `docs/architecture/reviews/evidence/f017-v10-root-continuity-implementation-measurement-v7.json`
- qualification: `docs/architecture/reviews/evidence/f017-v10-root-continuity-bounded-decode-qualification-v6.json`
- retained runtime qualification: `docs/architecture/reviews/evidence/f017-event04-runtime-hardening-qualification-v10-v6.json`
- rehearsal: `docs/architecture/reviews/evidence/f017-event04-production-shaped-no-access-rehearsal-v10-v6.json`
- exact-head CI: `docs/architecture/reviews/evidence/f017-v10-root-continuity-full-native-ci-v2.json`
- root contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-accounting-root-continuity-v1.json`
- decode contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-bounded-artifact-decode-v1.json`

Directly rerun or reconstruct these cycle-01 attacks: manifest symlink TOCTOU; intermediate-parent substitution within the accounting-root claim scope; retained journal in-place truncation plus deleted starts; repeated monotonic lower-bound observations; float tokens at 257, 10,000, and 1,000,000 characters; `sys.modules` and `builtins.__import__` parser-policy bypasses; and external-inode hardlinks in synthetic roots. Then search for materially new representation-independent bypasses in accounting-root identity, fallback-as-sink semantics, journal corruption, bounded numeric tokens, structural scanning, direct-parser policy, terminal obligations, exact measurement, CI, and zero-access isolation.

Return one JSON object and no Markdown fences:

```json
{
  "reviewed_head": "9dd33af17131fc8bccaa7e36195c349a5d1c76ac",
  "reviewer_model": "gemini-3.1-pro-high",
  "attacked_claim_ids": ["C-..."],
  "prior_challenge_dispositions": [{"challenge_id":"G-C01-...","status":"CLOSED|REOPENED","reason":"..."}],
  "challenges": [
    {
      "challenge_id": "G-C02-001",
      "claim_id": "C-...",
      "attack": "...",
      "mutation_or_trace": "...",
      "expected_behavior": "...",
      "observed_behavior": "...",
      "severity": "BLOCKING|NON_BLOCKING_REQUIRED|DEFENSE_IN_DEPTH",
      "affected_artifacts": ["..."],
      "status": "OPEN"
    }
  ],
  "original_checkpoint_access_observed": 0
}
```

Do not provide a global acceptance verdict. If tooling prevents a direct attack, add an OPEN challenge describing the missing proof rather than assuming PASS.
