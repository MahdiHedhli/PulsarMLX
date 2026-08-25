# F017 V9 root-continuity graph — Opus ARBITER cycle 03

Use a fresh `claude-opus-5` session at high effort in a detached read-only worktree. Review exact committed bytes at evidence head `0e7c6970e133435f5dc78bb4af74bf05f2cd5194`. Repository evidence outranks this request. Do not modify repository files, access original checkpoint shards, mint or execute Event 04, start its package, or execute P1 attempt 2. Executable adversarial tests are authorized only against synthetic roots under `/private/tmp`; set `PYTHONDONTWRITEBYTECODE=1` and disable pytest cache writes.

Cycle 02 accepted 23 claims and rejected exactly `C-JSON-005` and `C-IMPL-002`. Its exact response and claim-by-claim evidence are bound by authority manifest v8. The final repair is at implementation head `0c6a26cfaeebd087061d336fd0c766548d1adf5b`, tree `2074cfda355b07f04105e6b42b188447c00027a5`. Exact-head FULL_NATIVE run `32864924869` passed, including workspace and pinned native MLX; required native skips were zero. Evidence-only run `32866819097` passed at this packet's parent and launched zero native jobs.

The repair makes the direct-parser prohibition representation-independent in two layers:

1. imported capability export names are rejected regardless of the first-party module that exports them;
2. every direct or transported `.load`/`.loads` attribute use and dynamic `getattr(..., "load"|"loads")` is rejected name-agnostically outside the canonical parser and the exact offline quantization allowance.

The permanent regression family includes all three cycle-02 re-export mutations, an end-to-end mirror-tree exploit, non-direct member transport (`decoder = parser.json.loads`), and dynamic retrieval (`getattr(parser.json, "loads")`). The active 32-module closure still contains exactly the canonical parser call and the documented offline quantization allowance. The new measurement binds 43 implementation files and the repaired policy bytes.

You are the claim-by-claim ARBITER. Return an explicit `ACCEPT`, `REJECT`, or `UNRESOLVED` verdict for every one of the 25 readiness-critical claims in claim ledger v7. Reuse a cycle-02 ACCEPT only after verifying its measured dependencies were not invalidated. `UNRESOLVED` is not acceptance. Return exactly one global verdict: `ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_AUTHORIZATION` or `REJECT`. No conditional or interim acceptance.

Packet:

- authority manifest: `docs/architecture/reviews/evidence/f017-v9-root-continuity-authority-manifest-v8.json`
- graph state: `docs/architecture/reviews/evidence/f017-v9-root-continuity-graph-state-v7.json`
- claim ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-claim-ledger-v7.json`
- challenge ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-challenge-ledger-v6.json`
- support ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-support-ledger-v5.json`
- arbiter ledger through cycle 02: `docs/architecture/reviews/evidence/f017-v9-root-continuity-arbiter-ledger-v2.json`
- cycle-02 exact response: `docs/architecture/reviews/evidence/f017-v9-root-continuity-opus-arbiter-cycle-02-exact-response.json`
- implementation measurement: `docs/architecture/reviews/evidence/f017-v10-root-continuity-implementation-measurement-v12.json`
- root/decode qualification: `docs/architecture/reviews/evidence/f017-v10-root-continuity-bounded-decode-qualification-v11.json`
- retained runtime qualification: `docs/architecture/reviews/evidence/f017-event04-runtime-hardening-qualification-v10-v11.json`
- production rehearsal: `docs/architecture/reviews/evidence/f017-event04-production-shaped-no-access-rehearsal-v10-v12.json`
- exact-head FULL_NATIVE CI: `docs/architecture/reviews/evidence/f017-v10-root-continuity-full-native-ci-v6.json`
- root contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-accounting-root-continuity-v1.json`
- decode contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-bounded-artifact-decode-v1.json`
- runtime authority: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event04-runtime-authority-manifest-v10.json`
- implementation diff: `git diff 456b5d8d32bab01fb00fb98c25b1261be42e94e7..0c6a26cfaeebd087061d336fd0c766548d1adf5b`

Required direct attacks:

1. Re-run the exact cycle-02 first-party re-export mutations using both the bounded parser and canonical serializer as exporters.
2. Try different local aliases, module aliases, `from ... import json as alias`, and chained aliases.
3. Transport `json.loads`/`json.load` through assignments, containers, defaults, closures, returns, attributes, and call arguments.
4. Try dynamic access through `getattr`, `vars`, `__dict__`, `__getattribute__`, `operator.attrgetter`, `eval`, `exec`, `compile`, importlib, relative imports, and `sys.modules`/`os.sys.modules` paths.
5. Plant each bypass in a synthetic mirror of the active import closure and verify the policy returns nonzero before importing the planted runtime module.
6. If any mutation is accepted, demonstrate whether raw `RecursionError`, duplicate-key collapse, nonfinite acceptance, or noncanonical acceptance becomes reachable.
7. Independently census all `.load`/`.loads` references and calls in the active closure without importing the primary policy helper.
8. Verify the repaired policy itself is inside the 43 measured bindings and that every measurement entry equals exact `0c6a26cf:path` Git bytes.
9. Verify generator `--check`, authority validation, 204 decode attacks, 252 root attacks, 235 modeled root/decode executions, 201 retained runtime executions, and the 121-test active-authority suite.
10. Verify FULL_NATIVE run `32864924869`, head/tree identity, required jobs, historical/active separation, and native skip census zero.
11. Re-run representative root replacement, journal corruption, fallback failure, deep artifact, and nonserializable terminalization attacks sufficient to prove the direct-parser repair did not invalidate cycle-02 root/decode acceptances.
12. Verify all 47 modeled failure outcomes remain represented with zero generic fallback and zero uncontrolled modeled failures.
13. Verify production rehearsal resolves 1,410 graph tensors, rejects 399 non-access tensors, consumes all five graph shards in plan, and performs zero original shard access or numerical operations.
14. Verify the packet's manifest hashes and evidence-only run `32866819097`; native jobs on that evidence-only run must be zero.
15. Verify Event 04 has no live authorization, package start, retry, or execution; original checkpoint access is zero; P1 attempt 2 is absent; historical ledger is 175.

Use finding classifications `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`. Any `BLOCKING` or `NON_BLOCKING_REQUIRED` finding requires `REJECT` for its claim and globally.

Return one JSON object and no Markdown fences:

```json
{
  "reviewed_head": "0e7c6970e133435f5dc78bb4af74bf05f2cd5194",
  "reviewer_model": "claude-opus-5",
  "claim_verdicts": [
    {"claim_id":"C-REF-001","verdict":"ACCEPT|REJECT|UNRESOLVED","evidence":["..."],"invalidation_disposition":["..."]}
  ],
  "findings": [
    {"finding_id":"O-C03-001","claim_id":"C-...","classification":"BLOCKING|NON_BLOCKING_REQUIRED|DEFENSE_IN_DEPTH","attack":"...","observed":"...","required_repair":"..."}
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

The claim verdict list must contain every claim exactly once. Do not infer PASS from builder status, Gemini closure, or prior acceptance; reconstruct the evidence and execute the attacks.
