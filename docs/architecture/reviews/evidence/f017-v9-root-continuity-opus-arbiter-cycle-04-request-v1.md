# F017 V9 root-continuity graph — Opus ARBITER cycle 04

Use a fresh `claude-opus-5` session at high effort in a detached read-only worktree. Review exact committed bytes at evidence head `08f5c26705968bc5878f3290ad832a7ee86b1a26`. Repository evidence outranks this request. Do not modify repository files, access original checkpoint shards, mint or execute Event 04, start its package, or execute P1 attempt 2. Executable adversarial tests are authorized only against synthetic roots under `/private/tmp`; set `PYTHONDONTWRITEBYTECODE=1` and disable pytest cache writes.

Cycle 03 accepted 23 claims and rejected exactly `C-JSON-005` and `C-IMPL-002`. Gemini challenge cycle 04 attacked all 25 readiness-critical claims and reproduced three blocking bypasses against those two claims: transported `getattr`, capability extraction through `logging.sys` using the transported builtin, and decorator-form `@eval`. Its exact response wrapper records a transport interruption after a complete JSON challenge response was emitted; challenge ledger v8 preserves the three executed attacks without treating the wrapper transport as acceptance.

The final repair is at implementation head `a3394e442b154718b0e41dd0a653a17dc428015d`, tree `58e7bcdfa58c5f7c46406220ea2f7a3c635c6cf9`. It rejects every dangerous dynamic builtin name when transported outside its direct-call position. This covers assignments, annotations, named expressions, containers, defaults, closures, returns, decorators, class attributes, and aliases without relying on the alias spelling. The exact Gemini traces and adjacent forms are permanent regressions. The active 32-module import closure retains only the canonical JSON parser site and documented offline quantization allowance.

Exact-head FULL_NATIVE run `32872983381` passed at head `08d14c1252244b10fb2bce338819e698a3173924`, tree `2c29dfc8b26ca501ac5e7ba46dc3a440687cac5c`: classifier, workspace baseline, pinned native MLX, and aggregate all passed; required native skips were zero. Evidence-only run `32874678290` passed at this packet head and launched zero native MLX jobs.

You are the claim-by-claim ARBITER. Return an explicit `ACCEPT`, `REJECT`, or `UNRESOLVED` verdict for every one of the 25 readiness-critical claims in claim ledger v9. Reuse a prior ACCEPT only after verifying its measured dependencies were not invalidated. `UNRESOLVED` is not acceptance. Return exactly one global verdict: `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_AUTHORIZATION` or `REJECT`. No conditional or interim acceptance.

Packet:

- authority manifest: `docs/architecture/reviews/evidence/f017-v9-root-continuity-authority-manifest-v10.json`
- graph state: `docs/architecture/reviews/evidence/f017-v9-root-continuity-graph-state-v9.json`
- claim ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-claim-ledger-v9.json`
- challenge ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-challenge-ledger-v8.json`
- support ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-support-ledger-v7.json`
- arbiter ledger through cycle 03: `docs/architecture/reviews/evidence/f017-v9-root-continuity-arbiter-ledger-v3.json`
- Gemini cycle-04 exact response: `docs/architecture/reviews/evidence/f017-v9-root-continuity-gemini-challenge-cycle-04-exact-response.json`
- Opus cycle-03 exact response: `docs/architecture/reviews/evidence/f017-v9-root-continuity-opus-arbiter-cycle-03-exact-response.json`
- implementation measurement: `docs/architecture/reviews/evidence/f017-v10-root-continuity-implementation-measurement-v14.json`
- root/decode qualification: `docs/architecture/reviews/evidence/f017-v10-root-continuity-bounded-decode-qualification-v13.json`
- retained runtime qualification: `docs/architecture/reviews/evidence/f017-event04-runtime-hardening-qualification-v10-v13.json`
- production rehearsal: `docs/architecture/reviews/evidence/f017-event04-production-shaped-no-access-rehearsal-v10-v14.json`
- exact-head FULL_NATIVE CI: `docs/architecture/reviews/evidence/f017-v10-root-continuity-full-native-ci-v8.json`
- root contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-accounting-root-continuity-v1.json`
- decode contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-bounded-artifact-decode-v1.json`
- runtime authority: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-authority-manifest-v10.json`
- implementation diff: `git diff 0b9888ca71009f6d99e2de833d8654e9cab6d9b9..a3394e442b154718b0e41dd0a653a17dc428015d`

Required direct attacks:

1. Re-run the exact Gemini `my_getattr = getattr; my_getattr(obj, 'lo'+'ads')` mutation in a synthetic mirror before importing the planted module.
2. Re-run the exact `logging.sys` extraction mutation and demonstrate whether `json.loads` can be reached.
3. Re-run the exact `@eval` decorator mutation.
4. Transport each dangerous builtin through assignments, annotated assignments, walrus expressions, tuple/list/starred unpacking, lists, tuples, sets, dictionaries, defaults, keyword defaults, closures, lambdas, returns, yields, comprehensions, class attributes, decorators, and call arguments.
5. Try aliases obtained from `builtins`, `__builtins__`, first-party exports, defaults, descriptors, globals, import machinery, and unmonitored standard-library modules.
6. Re-run every cycle-03 transported JSONDecoder, decoder-submodule, raw_decode, scan_once, object_pairs_hook, scanner, partial, operator, and package-shaped import mutation.
7. Plant each bypass in a synthetic mirror of the active import closure and require policy rejection before importing the planted module.
8. If any mutation is accepted, demonstrate whether raw `RecursionError`, duplicate-key collapse, nonfinite acceptance, or noncanonical acceptance becomes reachable.
9. Independently census all JSON decoder members and dangerous builtin transports in the active closure without importing the primary checker.
10. Verify legitimate current behavior remains accepted: canonical parser, canonical serializer `dumps`, documented offline quantization `loads`, `sys.executable`, and `sys.stderr`.
11. Verify the repaired policy is one of 43 measured bindings and every measurement entry equals exact `a3394e44:path` Git bytes and current bytes.
12. Verify generator `--check`, 99 focused tests, 144 combined tests, 204 decode attacks, 252 root attacks, 235 modeled root/decode executions, and 201 retained runtime executions.
13. Verify FULL_NATIVE run `32872983381`, head/tree identity, required jobs, historical/active separation, and native skip census zero.
14. Re-run representative root replacement, journal corruption, fallback failure, deep artifact, and nonserializable terminalization attacks sufficient to prove the policy repair did not invalidate the 23 prior acceptances.
15. Verify all 47 modeled outcomes remain represented with zero generic fallback and zero uncontrolled modeled failures.
16. Verify production rehearsal resolves 1,410 graph tensors, rejects 399 non-access tensors, covers shards 2–6 and all 11 formats, and performs zero original shard access or numerical operations.
17. Verify manifest hashes and EVIDENCE_ONLY run `32874678290`; native MLX jobs on that run must equal zero.
18. Verify Event 04 has no live authorization, package start, retry, or execution; original checkpoint access is zero; P1 attempt 2 is absent; historical ledger is 175.

Use finding classifications `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`. Any `BLOCKING` or `NON_BLOCKING_REQUIRED` finding requires `REJECT` for its claim and globally.

Return one JSON object and no Markdown fences:

```json
{
  "reviewed_head": "08f5c26705968bc5878f3290ad832a7ee86b1a26",
  "reviewer_model": "claude-opus-5",
  "claim_verdicts": [
    {"claim_id":"C-REF-001","verdict":"ACCEPT|REJECT|UNRESOLVED","evidence":["..."],"invalidation_disposition":["..."]}
  ],
  "findings": [
    {"finding_id":"O-C04-001","claim_id":"C-...","classification":"BLOCKING|NON_BLOCKING_REQUIRED|DEFENSE_IN_DEPTH","attack":"...","observed":"...","required_repair":"..."}
  ],
  "accepted_claim_count": 0,
  "rejected_claim_count": 0,
  "unresolved_claim_count": 0,
  "original_checkpoint_access_observed": 0,
  "event_04_authorization_observed": false,
  "event_04_package_start_observed": false,
  "p1_attempt_2_observed": false,
  "global_verdict": "ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_AUTHORIZATION|REJECT"
}
```

The claim verdict list must contain every claim exactly once. Do not infer PASS from builder status, Gemini support, or prior acceptance; reconstruct the evidence and execute the attacks.
