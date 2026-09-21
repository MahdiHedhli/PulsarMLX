# F017 Native Bounded-P1 Domain — Opus 5 Final Ratification, Cycle 2

## Independent decision authority

Act as the final independent adversarial reviewer for this gate under the operator-authorized Claude Opus 5 policy. This must be a fresh session. Do not inherit the cycle-1 result, the earlier cycle-3 interim result, or their severities. Review committed bytes only from a clean detached worktree at exact implementation target `e3fd6ca64f299e3b2293e0522c46fa66ebe09b13` on `feat/017-rust-native-inference-runtime`.

The evidence head containing the exact-head CI record and this request is the commit that adds this request; independently obtain it from the authoritative branch after fresh fetch. Inspect Git objects and CI directly. Recompute every hash. Do not execute real M1 Ultra P1, open original-checkpoint payload, perform full-model real-checkpoint inference, create a live P1 authorization, or modify reviewed repository bytes.

The reviewer-policy transition is:

- path: `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-final-review-policy-transition-v1.json`
- SHA-256: `c2608b669c3bebf986d2735a156431ee4f3babb1fa648006f257dffec73c187c`
- operator-authorized final reviewer: `claude-opus-5`
- standards changed: none

## Cycle-1 rejection and exact repair chain

Reconstruct rather than trust:

| Artifact | SHA-256 / commit |
|---|---|
| cycle-1 request | `8400bdb8a0e9f36aeebe08789f8c42465f6b187efb28623ce9265ab9ab254d2c` |
| cycle-1 exact response | `b627c169b3c9b241a642eda370c1834846545ab010ff798c51c24aa8c518e6d4` |
| cycle-1 normalized result | `3d91e8c8df26b95bfea3f6a59077daabc7f649086f1d86733f8e124eb63bdbde` |
| repair disposition | `92eb02d186832229f95c608cad70e37aff5d3dbe2a3b5d5fbee03ac03d267c4d` |
| repair commit 1 | `4faa404c4205d172251436781b6d54042e8409f6` |
| repair/evidence commit 2 and implementation target | `e3fd6ca64f299e3b2293e0522c46fa66ebe09b13` |
| exact-head CI | run `32578854836`, expected success at `e3fd6ca6…` |
| committed CI evidence | `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-ci-32578854836.json`, SHA `b5450e92f641413a93d8c9be41c4bf87089911dd9c0fddc4a9623ffbc4038fb2` |

Cycle 1 returned `REJECT`, zero BLOCKING and four `NON_BLOCKING_REQUIRED` findings:

1. `F017-OPUS-C4-01`: stale banked synthetic executable permitted attempt-root traversal.
2. `F017-OPUS-C4-02`: CI built exact source but executed a stale banked binary while stamping the current head.
3. `F017-OPUS-C4-03`: all-zero/stale 22-counter delta pairs were accepted.
4. `F017-OPUS-C4-04`: authorizer hard-pinned Fable and the obsolete `ACCEPT` verdict vocabulary.

Do not accept repair claims on prose. Rerun the attacks against exact repaired bytes:

- prove the exact source-built synthetic binary is the one executed and authority-bound;
- rerun attempt-ID traversal and absolute-path mutations against both banked source-exact binaries;
- independently run ten fresh processes or mechanically verify and spot-rerun the source-built qualification;
- mutate a genuine executor-produced receipt to all-zero accounting while repairing its receipt/terminal hashes; it must still fail semantic qualification;
- remove one required liveness delta at a time and verify failure;
- verify the authorizer requires `claude-opus-5` and exact verdict `ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1`;
- verify authority checks occur before state-root creation.

## Rebound authority graph

| Authority | Path / identity | SHA-256 or value |
|---|---|---|
| reviewed implementation | Git commit | `e3fd6ca64f299e3b2293e0522c46fa66ebe09b13` |
| execution-code source head | Git commit | `4faa404c4205d172251436781b6d54042e8409f6` |
| exact-head CI | GitHub Actions run | `32578854836` |
| D0 v2 | `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v2.json` | `cc62cdc7550e3a25f55de783e9eb7c68f6cf03d0eafb944a86dc8a2a60007fb9` |
| D1 | `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-counter-semantics-v1.json` | `f3aab3b065628f96bfe1fab1a045a9af3d2261e2b5d7ef69c1528fb0a7d88246` |
| D2 | `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-accounting-residency-v1.json` | `d2312004f05cafbfd1f1779ccfbbb9e1a0c8c5b4e916aa0601abb04dbefe9c84` |
| D3.5 result | `docs/architecture/reviews/evidence/f017-native-d3-5-numerical-grading-result-v1.json` | `472a3085111ed023c3fafafc97600edaba4e6b8dbc0f58d35020561b650fa7e4` |
| admission contract v2 | `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-admission-contract-v2.json` | `91248295cac2f078e47576e5f22b4f7d0457bf9b3b11645c8e46406b8b1a2e03` |
| banked bounded executor | `specs/017-rust-native-inference-runtime/bin/f017-native-bounded-p1` | `21f405cae64469ab1aed89e571464f6b2278681578d714718cb7183ba01fb062` |
| banked synthetic executor v3 | `specs/017-rust-native-inference-runtime/bin/f017-native-synthetic-p1-v3` | `3bf2db898e574f00e7b312ac1ab140c8d707183e402367958f863f8cef879be8` |
| inert source authority v3 | `specs/017-rust-native-inference-runtime/fixtures/f017-native-tiny-full-model-inert-authority-v3.json` | `e0ee71870738de9100217abc1a1570a4816e960ad5ad971af86edd3cf0108eb9` |
| source-built synthetic qualification v3 | `docs/architecture/reviews/evidence/f017-native-full-model-synthetic-qualification-v3.json` | `c1b012a40a8ffecdb3912d343b193e30d7c47b130fc255496eb00a114af32360` |
| historical master ledger | historical branch `docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json` | `aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e`, terminal `175` |

The accepted retained qualification remains `MIXED_D0_V2_CLASS/PASS`, scoped only to representative layer-3 S0→S2. No tolerance or D3.5 numerical semantics changed during repair.

## Whole-domain attacks that remain mandatory

Perform a fresh whole-domain review, including all operator-required attacks:

1. Recompute all load-bearing hashes and verify exact implementation/evidence/CI identities.
2. Inspect CI `32578854836` directly: exact head, both Apple jobs, pinned native MLX, no required skips, D3.5, B1/B2, source-built producer, accounting, and synthetic qualification.
3. Reconcile the historical C3 request-SHA discrepancy: prose `7417d345…` versus actual invoked committed request `0d3a7b35…`.
4. Recheck D3.5: exact 89-read grant/census, sizes/SHAs, canonical stage mapping/serialization, and exclusion of the 14 disclosed ungranted diagnostic reads from authority.
5. Recheck all 34 D0 classifications and frozen tolerance bindings. Recompute OCB ordinals 20, 21, 25, 27, 28, including gamma and operand selection; detect post-hoc leakage from 680 captures.
6. Recheck routing membership/order/ties before numerical grading and intentional-distinction handling.
7. Recheck the full 79-layer native producer for representative-route hardcoding, missing layers/experts/formats, Python fallback, or cross-runtime evidence stitching.
8. Recheck all 11 quantization formats, decoder bindings, geometry/scales/non-finite handling, catalog type/type_id cross-check, and absence of fallback.
9. Recheck six-shard/1,809-tensor plan completeness, root/census/offset/size/duplicates/symlink/write protection/config agreement, with no plan-only payload opens.
10. Recheck KV and position-zero RoPE semantics, attention/residual/final norm/logits/top-k, exactly one output token, mandatory stop, no retry/resume/continuation, and rejection of the inert producer ID on the real path.
11. Recheck all 22 live D1 producers and semantic invariants. Attack all-zero/stale snapshots, missing producers, pre/post swaps, and accounting underflow. Logical and independent native free accounting must remain distinct.
12. Recheck executor-produced receipt exact schema. Attack hand-authored receipt substitution, missing/unknown keys, types/identities/timestamps/counters, terminal mismatch, tokens, and mandatory-stop false.
13. Recheck RN1 ownership: exclusive durable claim; this invocation alone can terminalize its attempt; receipt-derived terminal counts. Attack replay, fresh authorization after contract-wide claim, races, traversal/absolute IDs, state-root symlinks/aliases, stale authorization, replacement terminal, retry, and continuation.
14. Recheck exact M1 Ultra/arm64, MLX 0.31.2, MLX-C 0.6.0, dylib/executable/environment/thread identities, 16 GiB fresh-memory gate and sample age at most five seconds.
15. Reconstruct historical ledger continuity to 175 and confirm native event accounting remains separate from payload/page-residency accounting.
16. Recheck ten genuinely fresh synthetic full-model processes using the same source-built orchestration path, tensor-math-only inert boundary, meaningful route variation, independent expected token, and no original checkpoint reachability.
17. Rerun B1 missing-native-free with logical accounting preserved; it must fail. Rerun exact B2 source-first/no-eval/no-sync under pinned native MLX. Recheck independent oracle and executable residual edges.
18. Verify throughout: real P1 0, original-checkpoint reads 0, live P1 authorizations 0.

## Defense-in-depth reassessment

Independently reassess every cycle-1 defense item. The repair disposition claims `C4-06`, `C4-07`, `C4-08`, `C4-10`, `C4-11`, and `C4-13` are closed. Attack those closures. Reassess remaining `C4-05`, `C4-09`, and `C4-12` without inheriting severity. Promote anything that weakens the live P1 boundary.

For every finding provide a stable ID, severity (`BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH`), exact path/symbol, evidence, failure mode, required repair, CI impact, and whether D0/D3.5 evidence is invalidated. Both BLOCKING and NON_BLOCKING_REQUIRED prevent acceptance.

Return exactly one final verdict token:

`ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1`

or

`REJECT`

No interim, conditional, or continue verdict. Acceptance means only that a separate human GO/no-GO decision may be presented. It does not issue a token or execute P1.

End with:

- `REAL_M1_ULTRA_P1_EXECUTED_DURING_REVIEW: NO`
- `ORIGINAL_CHECKPOINT_READS_DURING_REVIEW: 0`
- `LIVE_P1_AUTHORIZATION_CREATED_DURING_REVIEW: NO`
