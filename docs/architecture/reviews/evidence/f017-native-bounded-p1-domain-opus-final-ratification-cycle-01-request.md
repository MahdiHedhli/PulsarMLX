# F017 Native Bounded-P1 Domain — Opus 5 Final Ratification, Cycle 1

## Decision authority and reviewer independence

Act as the final independent adversarial reviewer for this gate. The operator has explicitly replaced the former Claude Fable 5 final-review requirement with **Claude Opus 5**. This is a fresh final ratification, not a continuation or promotion of the prior Opus interim review.

Review committed bytes only. Use a clean detached worktree at exact implementation target `ab236b924f7dd7a95d226c5bb528315a4a68d72c` on `feat/017-rust-native-inference-runtime`. The current evidence authority is `affdd2a9d60f92a8e71bc8c6f28d14752111a13f`. Recompute hashes. Inspect CI directly with repository `MahdiHedhli/PulsarMLX`, run `32574711605`; do not inherit prose claims.

The append-only reviewer-policy transition is:

- `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-final-review-policy-transition-v1.json`
- SHA-256 `c2608b669c3bebf986d2735a156431ee4f3babb1fa648006f257dffec73c187c`
- committed at `affdd2a9d60f92a8e71bc8c6f28d14752111a13f`

It changes reviewer identity only. Numerical, implementation, accounting, retention, execution-safety, and acceptance standards are unchanged. The prior interim ACCEPT is evidence, not final authority. Reach your own conclusion.

Do **not** execute real M1 Ultra P1, open original-checkpoint payload, perform full-model real-checkpoint inference, create a live P1 authorization, or modify reviewed repository bytes. Temporary mutation/build state must remain outside the detached reviewed worktree.

## Frozen authority graph

Recompute every binding from Git objects rather than trusting this list.

| Authority | Path / identity | SHA-256 or value |
|---|---|---|
| frozen implementation | Git commit | `ab236b924f7dd7a95d226c5bb528315a4a68d72c` |
| implementation code base | Git commit | `038cdbfdf707dc80d2a548650885922cfa5aeb9e` |
| current evidence authority | Git commit | `affdd2a9d60f92a8e71bc8c6f28d14752111a13f` |
| exact-head CI | GitHub Actions run | `32574711605`, expected success at `ab236b924…` |
| committed CI evidence | `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-ci-32574711605.json` | `5591b0a135ebccbe1305afabf0d8123d4eb054937e64d6a20c074bcf08fde10e` |
| final-review package | `docs/architecture/reviews/evidence/f017-native-bounded-p1-domain-final-review-package-v1.json` | `c40ccfbde041f9158f27e93451e782077c69753f79cca4b36daf2699b32ac80f` |
| D0 v2 numeric contract | `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v2.json` | `cc62cdc7550e3a25f55de783e9eb7c68f6cf03d0eafb944a86dc8a2a60007fb9` |
| D1 counter contract | `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-counter-semantics-v1.json` | `f3aab3b065628f96bfe1fab1a045a9af3d2261e2b5d7ef69c1528fb0a7d88246` |
| D2 accounting/residency | `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-accounting-residency-v1.json` | `d2312004f05cafbfd1f1779ccfbbb9e1a0c8c5b4e916aa0601abb04dbefe9c84` |
| comparison-read grant | `specs/017-rust-native-inference-runtime/contracts/f017-native-d3-5-comparison-read-grant-v1.json` | `340e91aa3f00c91b0275c052307dba1ab0ebef091b3e07f99e4121a4bc1c788f` |
| retention reuse grant | `specs/017-rust-native-inference-runtime/contracts/f017-native-representative-retention-reuse-grant-v1.json` | `b22a11c829000fd9d333a62a662dd1b274a9a710aa4ccd6afb8f7df789dc9b28` |
| comparison grant acceptance | `docs/architecture/reviews/evidence/f017-native-d3-5-comparison-read-grant-acceptance-v1.json` | `3c584eef10d9373cd5bcd21eab791fa6e08bc469d4c6db78542e879323b7bf22` |
| ungranted diagnostic disclosure | `docs/architecture/reviews/evidence/f017-native-d3-5-ungranted-diagnostic-read-disclosure-v1.json` | `a1daa331ce641b7e34459de1f7a5584632c8cb5bce82862a66e93b330e9aa03b` |
| D3.5 result | `docs/architecture/reviews/evidence/f017-native-d3-5-numerical-grading-result-v1.json` | `472a3085111ed023c3fafafc97600edaba4e6b8dbc0f58d35020561b650fa7e4` |
| D3.5 acceptance | `docs/architecture/reviews/evidence/f017-native-d3-5-numerical-qualification-acceptance-v1.json` | `9d4d29870e8aa67d9ca9ed2702bddd4b9248930204e4f03f05c5f05f2727b163` |
| admission contract v2 | `specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-admission-contract-v2.json` | `cf07ccfdd1a85413268b530368c93ba07695c235dcc69afa096133d17e68b2fb` |
| banked bounded executor | `specs/017-rust-native-inference-runtime/bin/f017-native-bounded-p1` | `6f0ad9370caf2582934a917029476f505e1a3792b46cbdfe046c7cda85cf31dc` |
| checkpoint manifest | `docs/validation/glm52-checkpoint.json` | `34b65d586c86d24ee10f3a2ed55491fb3a5a6b9ddbaf893bf9e0ab962c96cf8f` |
| tensor catalog | `docs/research/glm52/raw/f016-c01-catalog-0001.json` | `135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19` |
| synthetic full-model v2 | `docs/architecture/reviews/evidence/f017-native-full-model-synthetic-qualification-v2.json` | `2a73ef07a3062e313726179a628b7030dca88dc51cea89145544fc3629beb91b` |
| historical master ledger | historical branch path `docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v2.json` | `aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e`, terminal `175` |

The accepted retained qualification claim is `MIXED_D0_V2_CLASS/PASS`. Its scope is the representative layer-3 S0→S2 surface, not the entire 79-layer forward. The remaining forward is admitted only through pinned F016 structure, generalized per-stage semantics, synthetic full-graph qualification, and the one bounded real P1 gate.

## Review history to inspect, not inherit

Reconstruct all three Opus cycles and the cross-vendor Gemini/AGY history. Important identities:

| Cycle | Request SHA | Exact response SHA | Normalized SHA | Result |
|---|---|---|---|---|
| Opus C1 | `a65a8c4d89b1dce1805bba6892f0d615a15f79b92e99ca1e135ed16b05d80b6b` | `283d11a413206be9a82baa8d2690778f23b9efa20785c9f103305f5d54e44682` | `b6b08c9d6bb5dd6e06858b19253dfe98ebe77def172aa4fe370eaf8cb45ec497` | REJECT |
| Opus C2 | `a597f14e65221d1ee78874f0d21e5c939b33cdb3c35b7f0d2d3f79b72195b5db` | `b89eb63d7ae372ae4f226ec0a60db3640b8740d01b130de33b058e4cfbaa4251` | `4ade469de333f5c773a5707a557f019b0de8238fd6b3101a29d12284ded31d25` | REJECT |
| Opus C3 | actual invoked `0d3a7b35aec30e29b299d6ab5cdf1247a44f3242f85c336486692759a1c230be` | `433df44cbe2c8ebc05963f18cc534da7ac967e6ae0fd0667f182276c63b4f2a5` | `7e31e423b254add48759a60f83fbdf80880e3520087ab145cea48014a32b072c` | INTERIM ACCEPT |
| Gemini C3 via AGY | `adf4ad3b8d885920fef1286f6361d2e8cd88d3214b83239168dd4c4ba70f829c` | `a6ab062b3d1c69007fd156c5a859372f77be4063612689660074add4bfb2026f` | `a2d7f60ea9760405cab384e6f82bf38de0019c36d3c93f0cf5fa2aad3bb32e35` | NO MATERIAL DISAGREEMENT |

### Mandatory C3 request-SHA discrepancy reconciliation

The C3 reviewer prose reported `7417d345c12422784fabd8b6c8133a9d05b58846ab7275a99472b413df255aba`, while the exact committed request actually invoked and banked hashes to `0d3a7b35aec30e29b299d6ab5cdf1247a44f3242f85c336486692759a1c230be`. Independently resolve the Git history and exact response. Do not inherit either label. Decide whether the discrepancy affects evidentiary sufficiency.

## Required independent attacks

Rerun the highest-value attacks. Do not merely cite C3.

1. Recompute all load-bearing hashes and prove `ab236b924…` is the implementation reviewed.
2. Inspect CI `32574711605` directly, including head, jobs, logs, pinned native MLX, skip behavior, D3.5, B1/B2, producer, accounting, and synthetic qualification.
3. Reconcile the C3 request-SHA discrepancy above.
4. Recheck D3.5 comparison-read authority: exact 89-read receipts, allowed sizes/SHAs, canonical mapping and serialization; prove the disclosed 14 ungranted diagnostic reads did not become comparison authority.
5. Recheck all 34 D0 classifications and frozen tolerance bindings. Recompute the OCB derivations for ordinals 20, 21, 25, 27, and 28, including gamma and operand selection. Look for post-hoc leakage from the 680 captures.
6. Recheck routing expert membership, order, and ties before numeric grading. Confirm intentional distinctions cannot be promoted to production equivalence.
7. Recheck the full 79-layer native producer for representative-route hardcoding, missing layers/experts/formats, wrong loops, and Python or cross-runtime evidence stitching.
8. Recheck all 11 quantization formats and their decoder bindings, block geometry, scales, non-finite handling, and lack of fallback.
9. Recheck the six-shard / 1,809-tensor plan, exact root/census, offset/size bounds, duplicate handling, symlink/write protection, config/catalog agreement, and no payload opening in plan-only qualification.
10. Recheck KV initialization and RoPE at position zero; attention, residual, final norm/logits/top-k; exactly one output token; mandatory stop; no retry/resume/continuation.
11. Recheck all 22 D1 accounting producers. Attempt all-zero and stale snapshots, missing/forged producers, pre/post swaps, and semantic invariants. Logical and independent native free accounting must remain distinct.
12. Recheck that the production executor emits the exact receipt. Attempt a hand-authored receipt, unknown/missing fields, wrong types/identities/timestamps/counters, terminal mismatch, wrong prompt/result tokens, and mandatory-stop false.
13. Recheck RN1: exclusive owned claim; only this invocation may terminalize what it durably started; terminal counts derive from and cross-check receipts. Attack replay, fresh authorization after contract-wide claim, races, attempt-ID traversal/absolute paths, state-root symlinks/aliases, stale authorization, replacement terminal, retry and continuation.
14. Recheck exact M1 Ultra brand/arm64, MLX 0.31.2, MLX-C 0.6.0, dylib/executable identities, environment/thread pins, runtime drift, 16 GiB fresh-memory observation, and sample age ≤5 seconds.
15. Reconstruct historical master ledger SHA and receipt continuity to terminal 175. Confirm native event accounting is separate; page faults/residency are not historical payload reads.
16. Recheck the 10-fresh-process synthetic full-model qualification. Confirm one shared orchestration path, a tensor-math-only inert boundary, meaningful route variation, independent expected token, exact freshness, and no original checkpoint reachability.
17. Rerun B1 missing-native-free while logical accounting remains; it must fail. Rerun the exact B2 source-first/no-eval/no-sync lifetime regression under pinned native MLX. Recheck independent oracle policy and executable residual-edge assertions.
18. Verify safety state throughout: real P1 executions 0, original-checkpoint reads 0, live P1 authorizations 0.

## Seven C3 defense-in-depth findings: fresh reassessment required

Do not preserve these severities by precedent. Promote any item that weakens the live P1 boundary.

1. `F017-OPUS-C3-F1`: banked synthetic executable predates containment repair; CI builds source but executes banked old bytes. C3 independently ran the exact-head source build 10/10. Decide whether the stale banked qualification must be rebound before **domain acceptance**, before live authorization, or is non-blocking evidence debt.
2. `F017-OPUS-C3-F2`: historical C2-F6 rationale says execution code was unchanged, which became false. Decide whether exact-head rederivation repairs substance and whether historical wording needs a supplemental correction.
3. `F017-OPUS-C3-F3`: plausible ~14 GiB working peak against a 16 GiB floor could burn the one attempt on OOM. Decide whether this is only availability or an unsafe admission ambiguity.
4. `F017-OPUS-C3-F4`: catalog `type_id` geometry and `type` decoder channels lack a direct mechanical cross-check; exact bound catalog is currently consistent. Attack silent under-fill/fallback and determine bind point.
5. `F017-OPUS-C3-F5`: operator authorizer creates state root before attempt-ID/contract cross-check, potentially wedging authorization. Determine whether availability-only or exploitable.
6. `F017-OPUS-C3-F6`: real producer path lacks a converse inert producer-identity guard. Determine whether existing exact executor/backend binding is sufficient for this gate.
7. `F017-OPUS-C3-F7`: accounting validation permits a semantically inert all-zero pair. Determine whether live native FFI makes it unreachable or whether liveness deltas are required before acceptance.

For each give prior disposition, your new assessment, and promotion/demotion if any.

## Severity and verdict

Use only `BLOCKING`, `NON_BLOCKING_REQUIRED`, and `DEFENSE_IN_DEPTH`. Both `BLOCKING` and `NON_BLOCKING_REQUIRED` prevent acceptance. Every finding needs a stable ID, path/symbol, evidence, failure mode, exact repair, CI impact, and whether prior D0/D3.5 evidence is invalidated.

Return exactly one final verdict token:

`ACCEPT_FOR_SINGLE_BOUNDED_M1_ULTRA_P1`

or

`REJECT`

No interim, conditional, or continue verdict. Acceptance authorizes only readiness for a future human GO/no-GO decision; it does not issue authorization or execute P1.

End with exact safety facts:

- `REAL_M1_ULTRA_P1_EXECUTED_DURING_REVIEW: NO`
- `ORIGINAL_CHECKPOINT_READS_DURING_REVIEW: 0`
- `LIVE_P1_AUTHORIZATION_CREATED_DURING_REVIEW: NO`
