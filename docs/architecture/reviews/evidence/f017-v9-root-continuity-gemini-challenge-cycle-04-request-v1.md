# F017 V9 root-continuity graph — Gemini CHALLENGE cycle 04

Use a fresh `gemini-3.1-pro-high` session at high effort. Work read-only from exact committed bytes at evidence head `a40d59c801a8c79a696a4ed73e9fc923f91521c2`. Repository evidence outranks this request. Do not modify files, access original checkpoint shards, mint or execute Event 04, start its package, or execute P1 attempt 2.

Your role is CHALLENGE, not arbiter. Attack all 25 readiness-critical claims in `docs/architecture/reviews/evidence/f017-v9-root-continuity-claim-ledger-v8.json`, concentrating executable attacks on repaired claims `C-JSON-005` and `C-IMPL-002`. Opus cycle 03 accepted the other 23 claims and rejected these two after finding transported JSONDecoder/submodule forms, operator attrgetter/methodcaller retrieval, and package-shaped first-party dependencies omitted from the audited closure.

The repair is implementation head `0b9888ca71009f6d99e2de833d8654e9cab6d9b9`, tree `64ad6322fb111c175eb891ffda486cee121db337`. It rejects any first-party attribute whose member is a capability export name such as `json`, prohibits operator as a dynamic-resolution module, follows first-party package `__init__.py` plus dotted submodules, and fails closed when an existing first-party shape cannot resolve to inspected source. It adds 15 permanent regressions. Exact-head FULL_NATIVE run `32868949412` passed with required native skips zero. Evidence-only run `32870714111` passed at this exact evidence head and launched zero native jobs.

Packet:

- authority manifest: `docs/architecture/reviews/evidence/f017-v9-root-continuity-authority-manifest-v9.json`
- graph state: `docs/architecture/reviews/evidence/f017-v9-root-continuity-graph-state-v8.json`
- claims: `docs/architecture/reviews/evidence/f017-v9-root-continuity-claim-ledger-v8.json`
- Opus cycle-03 challenges: `docs/architecture/reviews/evidence/f017-v9-root-continuity-challenge-ledger-v7.json`
- cycle-03 support: `docs/architecture/reviews/evidence/f017-v9-root-continuity-support-ledger-v6.json`
- Opus arbiter ledger: `docs/architecture/reviews/evidence/f017-v9-root-continuity-arbiter-ledger-v3.json`
- cycle-03 exact response: `docs/architecture/reviews/evidence/f017-v9-root-continuity-opus-arbiter-cycle-03-exact-response.json`
- implementation diff: `git diff 0c6a26cfaeebd087061d336fd0c766548d1adf5b..0b9888ca71009f6d99e2de833d8654e9cab6d9b9`
- implementation measurement: `docs/architecture/reviews/evidence/f017-v10-root-continuity-implementation-measurement-v13.json`
- root/decode qualification: `docs/architecture/reviews/evidence/f017-v10-root-continuity-bounded-decode-qualification-v12.json`
- runtime qualification: `docs/architecture/reviews/evidence/f017-event04-runtime-hardening-qualification-v10-v12.json`
- rehearsal: `docs/architecture/reviews/evidence/f017-event04-production-shaped-no-access-rehearsal-v10-v13.json`
- exact-head CI: `docs/architecture/reviews/evidence/f017-v10-root-continuity-full-native-ci-v7.json`
- root contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-accounting-root-continuity-v1.json`
- decode contract: `specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-bounded-artifact-decode-v1.json`

Direct attacks:

1. Re-run every O-C03-001 transported JSONDecoder, decoder-submodule, raw_decode, scan_once, object_pairs_hook, scanner, hoisted-class, partial, and canonical-serializer-exporter mutation in a synthetic mirror before importing the planted module.
2. Re-run O-C03-002 with operator.attrgetter, operator.methodcaller, operator.itemgetter, imported member aliases, dotted strings, dynamically constructed strings, defaults, closures, containers, and call transport.
3. Re-run O-C03-004 using package `__init__.py`, dotted submodules, namespace-package shapes, `from package import submodule`, nested packages, and an existing first-party directory that cannot resolve to inspected source.
4. Search for remaining ways to obtain `json`, `sys`, `builtins`, `importlib`, or `os` from first-party module attributes, descriptors, annotations, globals, defaults, closures, classes, comprehensions, pattern matching, and import machinery.
5. Try alternative structural decoders that would falsify the exact JSON-authority claims; distinguish the frozen JSON clause from defense-in-depth surfaces.
6. Independently enumerate the active import closure and all JSON decoder members without importing the primary checker.
7. Verify current legitimate runtime behavior remains accepted: canonical parser, canonical serializer dumps, documented offline quantization loads, sys.executable, and sys.stderr.
8. Verify all 43 measurement bindings against exact Git bytes, generator --check, 136 combined tests, 252 root cases, 204 decode cases, 235 modeled root/decode executions, 201 retained runtime executions, 47 outcomes, and FULL_NATIVE run 32868949412.
9. Run representative root substitution, journal corruption, deep artifact, terminalization, and rehearsal checks sufficient to detect transitive invalidation of the 23 previously accepted claims.
10. Verify all 1,410 graph tensors, 399 non-access denials, all five graph shards in plan, all 11 formats, zero path reopen, zero live leases, and zero original checkpoint access.
11. Verify no Event-04 authorization, package start, retry, or execution; no P1 attempt 2; historical ledger 175.

Return one JSON object and no Markdown fences:

```json
{
  "reviewed_head":"a40d59c801a8c79a696a4ed73e9fc923f91521c2",
  "reviewer_model":"gemini-3.1-pro-high",
  "attacked_claim_ids":["C-..."],
  "prior_challenge_dispositions":[{"challenge_id":"O-C03-001","status":"CLOSED|REOPENED","reason":"..."}],
  "challenges":[{"challenge_id":"G-C04-001","claim_id":"C-...","attack":"...","mutation_or_trace":"...","expected_behavior":"...","observed_behavior":"...","severity":"BLOCKING|NON_BLOCKING_REQUIRED|DEFENSE_IN_DEPTH","affected_artifacts":["..."],"status":"OPEN"}],
  "original_checkpoint_access_observed":0
}
```

Do not provide a global acceptance verdict. If tooling prevents a direct attack, add an OPEN challenge describing the missing proof rather than assuming PASS.
