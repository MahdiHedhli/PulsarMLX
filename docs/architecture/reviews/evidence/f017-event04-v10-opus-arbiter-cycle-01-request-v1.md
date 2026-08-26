# F017 Event-04 V10 Opus ARBITER — Cycle 01

Use a fresh `claude-opus-5` session at high effort in a detached read-only worktree. Review exact committed bytes at the commit containing this request. Git and committed evidence outrank this request. Do not modify files, open/hash/mmap/pread checkpoint shards, rerun Event 04, run either oracle, or mint/execute P1 attempt 2.

The one-shot package is terminal and non-replayable. It returned `ORACLE_EXECUTION_FAILURE`: the primary process completed all 79 layers and wrote a 3,104,598-byte result, after which the measured 1,048,576-byte bounded-artifact limit rejected that result with `ArtifactDecodeError`. No primary receipt/terminal was banked, secondary never started, and comparison did not run. Accounting is package 1 / primary 1 / secondary 0. All five graph leases were released. Historical ledger is 175.

Issue one verdict (`ACCEPT`, `REJECT`, or `UNRESOLVED`) for every one of the 28 readiness-critical claims in `f017-event04-v10-execution-claim-ledger-v5.json`, followed by a global verdict of exactly `ACCEPT_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EVIDENCE` or `REJECT`. No conditional acceptance.

Required attacks:

1. authority/measurement and candidate/install mismatch;
2. fresh GO, exact IDs, one-shot non-replay;
3. root-continuity and fallback accounting misuse;
4. malformed or deeply nested committed evidence;
5. all six shard identity receipts and shard-1 graph-use prohibition;
6. descriptor substitution, path reopen, and the phase-aware lease census;
7. raw primary output completeness: 79 layers, shards 2–6, 11 formats, 154880 logits;
8. absence of primary receipt/terminal and whether the raw output is outside package-terminal SHA closure;
9. absence of secondary start/output and comparison;
10. accounting package 1 / primary 1 / secondary 0;
11. exact release census and live leases zero;
12. altered logits, thresholds, or historical-token leakage;
13. immutable copy/index SHA identity;
14. Gemini challenge and builder support disposition;
15. EVIDENCE_ONLY run `32914873074`, requiring zero native jobs;
16. FULL_NATIVE run `32914924270` for the CI-validator repair;
17. validator repair scope versus measured execution bytes;
18. hidden P1 authority or P1 execution.

Primary review inputs:

- `docs/architecture/reviews/evidence/f017-event04-v10-terminal-execution-result-v1.json`
- `docs/architecture/reviews/evidence/f017-event04-v10-immutable-execution-evidence-index-v1.json`
- `docs/architecture/reviews/evidence/f017-event04-v10-execution-claim-ledger-v5.json`
- `docs/architecture/reviews/evidence/f017-event04-v10-execution-graph-state-v5.json`
- `docs/architecture/reviews/evidence/f017-event04-v10-terminal-package-v1/`
- `docs/architecture/reviews/evidence/f017-event04-v10-execution-challenge-ledger-v2.json`
- `docs/architecture/reviews/evidence/f017-event04-v10-execution-support-ledger-v2.json`
- `scripts/research/f017_bounded_artifact_decode_v1.py`
- `scripts/ci/validate_evidence_change.py`

Return strict JSON, under 2,500 words:

```json
{
  "reviewed_head": "<exact HEAD>",
  "reviewer_model": "claude-opus-5",
  "claim_verdicts": [
    {
      "claim_id": "E-REF-001",
      "verdict": "ACCEPT|REJECT|UNRESOLVED",
      "evidence": ["<direct evidence>"],
      "invalidation_disposition": ["<disposition>"]
    }
  ],
  "findings": [
    {
      "finding_id": "O-E04-C01-001",
      "claim_id": "<claim>",
      "classification": "BLOCKING|NON_BLOCKING_REQUIRED|DEFENSE_IN_DEPTH",
      "attack": "<attack>",
      "observed": "<observed>",
      "required_repair": "<repair or terminal future-event requirement>"
    }
  ],
  "accepted_claim_count": 0,
  "rejected_claim_count": 0,
  "unresolved_claim_count": 0,
  "corrected_oracle_classification": "ORACLE_EXECUTION_FAILURE",
  "event_04_retry_observed": false,
  "secondary_execution_observed": false,
  "p1_attempt_2_observed": false,
  "global_verdict": "ACCEPT_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EVIDENCE|REJECT"
}
```

Acceptance of truthful failure evidence does not imply successful oracle completion or P1 readiness. Conversely, reject any claim whose stated success condition was not met even if the failure was safely terminalized.
