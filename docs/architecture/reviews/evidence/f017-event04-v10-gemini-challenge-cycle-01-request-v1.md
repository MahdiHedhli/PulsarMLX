# F017 Event-04 V10 Gemini CHALLENGE — Cycle 01

Use a fresh `gemini-3.1-pro-high` session at high effort. Review exact committed bytes at the commit containing this request. Work read-only. Do not access checkpoint shards, rerun Event 04, run either oracle, modify execution evidence, or execute/mint P1 attempt 2.

The one-shot V10 package terminalized with `ORACLE_EXECUTION_FAILURE`. The primary process completed 79 layers and wrote a 3,104,598-byte output, but the measured runtime then rejected that output through `ArtifactDecodeError: artifact bytes exceed bound` because `DEFAULT_LIMITS.max_bytes` is 1,048,576. No primary receipt or terminal was banked, the secondary did not start, and no comparison ran. The package accounting is package 1 / primary 1 / secondary 0; six identity hashes completed; all five leases were released; retry is prohibited.

Attack the committed evidence and emit challenge rows only. In particular verify:

1. the fresh GO and one-shot non-replay constraints;
2. candidate/install byte identity and exact V10 authority;
3. six-shard identity, shard-1 identity-only handling, and five-descriptor continuity;
4. whether the raw primary output really shows 79 layers, shards 2–6, all 11 formats, complete logits, and zero path reopens;
5. whether the 1 MiB bounded-decoder limit is the exact terminal cause;
6. accounting package 1 / primary 1 / secondary 0 and historical ledger 175;
7. release attempted 5 / successful 5 / live 0;
8. the absence of a primary receipt/terminal, secondary start/output, and comparison;
9. whether the raw primary output is outside the package terminal's transitive SHA closure;
10. whether `ORACLE_EXECUTION_FAILURE` and `READY_TO_PREPARE_P1_ATTEMPT_2_AUTHORIZATION: NO` are the only defensible dispositions;
11. whether the evidence-only validator repair is scoped to CI evidence interpretation and changes no measured execution byte;
12. any credential or checkpoint payload leakage in committed evidence.

Review these load-bearing artifacts first:

- `docs/architecture/reviews/evidence/f017-event04-v10-terminal-execution-result-v1.json`
- `docs/architecture/reviews/evidence/f017-event04-v10-immutable-execution-evidence-index-v1.json`
- `docs/architecture/reviews/evidence/f017-event04-v10-execution-claim-ledger-v5.json`
- `docs/architecture/reviews/evidence/f017-event04-v10-execution-graph-state-v5.json`
- `docs/architecture/reviews/evidence/f017-event04-v10-terminal-package-v1/`
- `scripts/research/f017_bounded_artifact_decode_v1.py`
- `scripts/ci/validate_evidence_change.py`

Return strict JSON with:

```json
{
  "reviewed_head": "<exact HEAD>",
  "reviewer_model": "gemini-3.1-pro-high",
  "challenges": [
    {
      "challenge_id": "G-E04-C01-001",
      "claim_id": "<claim>",
      "attack": "<attack>",
      "mutation_or_trace": "<trace>",
      "expected_behavior": "<expected>",
      "observed_behavior": "<observed>",
      "severity": "BLOCKING|NON_BLOCKING_REQUIRED|DEFENSE_IN_DEPTH",
      "affected_artifacts": ["<path>"],
      "status": "OPEN"
    }
  ],
  "supported_facts": ["<fact>"],
  "conceded_execution_claims": ["<claim id>"],
  "recommended_global_disposition": "REJECT",
  "original_checkpoint_access_observed": {
    "identity_hash_reads": 6,
    "shard_opens": 6,
    "tensor_read_operations": 13141066
  },
  "p1_attempt_2_observed": false
}
```

Do not call a failed or incomplete event accepted merely because its failure evidence is internally consistent.
