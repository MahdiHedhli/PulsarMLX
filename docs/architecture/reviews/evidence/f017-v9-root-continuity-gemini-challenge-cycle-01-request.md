# F017 V9 root-continuity graph — Gemini CHALLENGE cycle 01

Use a fresh `gemini-3.1-pro-high` session at high effort. Work read-only from exact committed bytes at evidence head `be5466479cda2a02bc5f23bcabd0c03a09862f7f`. Repository evidence outranks this request. Do not modify files, access original checkpoint shards, mint or execute Event 04, or execute P1 attempt 2.

Your role is CHALLENGE, not arbiter. Produce challenge rows only. Attack every one of the 25 readiness-critical claims in `docs/architecture/reviews/evidence/f017-v9-root-continuity-claim-ledger-v1.json`. A claim without a defect may receive no challenge, but explicitly report the census of attacked claim IDs.

Packet:

- authority manifest: `docs/architecture/reviews/evidence/f017-v9-root-continuity-authority-manifest-v2.json`
- graph state: `docs/architecture/reviews/evidence/f017-v9-root-continuity-graph-state-v1.json`
- claims: `docs/architecture/reviews/evidence/f017-v9-root-continuity-claim-ledger-v1.json`
- implementation diff: `git diff 5869bb436acc7fca4c1a4c1e2d5a774eb8d91f45..ce46483776154bc92ac3b59ea339cb7fceb2f84a`
- implementation measurement: `docs/architecture/reviews/evidence/f017-v10-root-continuity-implementation-measurement-v6.json`
- qualification: `docs/architecture/reviews/evidence/f017-v10-root-continuity-bounded-decode-qualification-v5.json`
- retained runtime qualification: `docs/architecture/reviews/evidence/f017-event04-runtime-hardening-qualification-v10-v5.json`
- rehearsal: `docs/architecture/reviews/evidence/f017-event04-production-shaped-no-access-rehearsal-v10-v5.json`
- CI: `docs/architecture/reviews/evidence/f017-v10-root-continuity-full-native-ci-v1.json`
- root contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-accounting-root-continuity-v1.json`
- decode contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-bounded-artifact-decode-v1.json`

Directly attack accounting-root identity, path rename/replacement/symlink/recreation, retained descriptor assumptions, fallback-as-sink semantics, journal corruption and partial records, false-zero derivation, monotonic lower bounds, and terminal obligations after every durable-start level. Attack bounded-parser limits, the string/escape-aware depth scanner, exact-boundary behavior, RecursionError normalization, import/alias/dynamic-resolution bypasses of the direct-parser policy, and malformed-root plus malformed-artifact cross-products. Check authority rebinding, exact-head CI, numerical-byte isolation, and original-checkpoint-access counters.

Return one JSON object and no Markdown fences:

```json
{
  "reviewed_head": "be5466479cda2a02bc5f23bcabd0c03a09862f7f",
  "reviewer_model": "gemini-3.1-pro-high",
  "attacked_claim_ids": ["C-..."],
  "challenges": [
    {
      "challenge_id": "G-C01-001",
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
