# F017 D3.5 retained-qualification authority adjudication — Claude Fable 5

## Independent verification results (required attacks 1–3)

**Hashes and Git state.** Current detached head is fe7b13d6 (the
adjudication-request commit); the three request-listed artifacts are
byte-identical at both fe7b13d6 and the declared target head f38dc275, and all
three recomputed SHA-256 digests match the request exactly. All five
`committed_authority` bindings in the execution evidence (D0 v2 `cc62cdc7…`,
grant `b22a11c8…`, package `a2fc41cd…`, consumer `ea4280f4…`, enforcer
`bbab9aab…`) verify at the execution head 4e1f9268 and are unchanged at
f38dc275. The D0 v1 base contract hashes to its bound value `e30b8647…`.

**Validator.**
`scripts/research/validate_f017_native_retained_qualification_execution_v1.py`
(confirmed read-only: JSON loads and SHA-256 hashing only) prints
`F017_NATIVE_RETAINED_QUALIFICATION_EXECUTION_EVIDENCE: PASS` against the
machine-local root.

**Receipt censuses and terminal count.** All 20 runs have `actual_count ==
len(reads) == expected_count == 40`, ordinals 0–39 complete, 40 distinct
roles, `checkpoint_read == false` and `original_checkpoint_shard_open ==
false` on every row, and `expected_sha256 == before == consumed == after` on
all 800 rows. The terminal count 800 is receipt-derived: the validator
independently censuses 20 × 40 receipt rows and requires equality with
`terminal.json`'s asserted 800; I confirmed the census myself.

**Determinism, identities, ownership.** 20 run directories (`fresh-00..09`,
`same-00..09`), 34 stages each, per-stage SHA and byte-length verified against
manifests; manifests, receipt files, and `33-production_s2.f32le` are
byte-identical across all 20 runs. The three evidence-bound hashes the
validator does not itself check (`representative_manifest_sha256`,
`representative_read_receipt_sha256`, `production_s2_sha256`) all verify
against machine-local bytes, as do the three canonical roots (720 files,
22,326,600 bytes). Owner/durable-start are identical, nonce and PID chain owner
→ terminal match, one attempt, `retry_permitted`/`resume_permitted` false —
owner-only terminalization holds. The 34-stage vocabulary matches the accepted
canonical vocabulary; runtime pins (MLX 0.31.2, mlx-c 0.6.0, libmlx
`6622caeb…`, libmlxc `a060915d…`, thread limits all "1") match the committed
package, which the consumer's `validate_package` enforces. Spot-hashing retained
input tensors on disk (s0, routed.0.gate, shared.down, router) matches the grant
SHAs. Zero original-checkpoint reads/shard opens and zero payload-ledger delta
are receipted and validator-enforced. One limitation: the native executable's
banked SHA cannot be independently re-verified because the binary is not
committed; it is accepted as a banked identity only.

## Findings

**F5-ADJ-01 — BLOCKING (blocks any D3.5 numerical PASS; does not impeach the
execution evidence)**

Hashes of non-byte-equivalent produced/expected values **cannot** instantiate
the D0 numeric metrics (required attack 4). Evidence: comparing the banked
capture manifest against the D0 v2 `oracle_registry`, 7 of 10 bound comparison
ordinals differ — ordinal 12 (S1: produced `7e08b2d8…` vs expected
`8309377e…`), 13, 19, 26, 31, 32, and 33 (S2: `cef89456…` vs `03413142…`);
only ordinals 0, 17, 18 match. `native_intermediate_tier_b`,
`native_final_tier_b`, and `routing_weight` are elementwise metrics (max-abs,
RMSE, cosine, per-coordinate caps); a hash mismatch conveys only "not
byte-identical" and carries zero metric information. Failure mode: a hash-only
grader must either fail every non-identical ordinal (falsely failing
intended-close comparisons) or pass without evidence. Required repair: a
payload-reading comparison step. No re-execution of the qualification event is
required — produced bytes are deterministic and SHA-banked.

**F5-ADJ-02 — BLOCKING (blocks any D3.5 numerical PASS)**

Existing accepted reuse authorities and D0 SHA bindings are **not** sufficient
native-consumer read authority for expected artifacts; consumer-scoped doctrine
requires a new explicit comparison-read grant (required attack 5). Evidence:
the grant's `allowed_reads` enumerates exactly the 40 input tensors plus one
output root; expected comparison payloads (retained S1, router-normalized,
shared F32, F64 proof references, derived S2) appear nowhere in any
`allowed_reads`. The repo's own receipt discipline treats a SHA binding as an
integrity assertion and a grant row as read authority — they are distinct, and
D0 v1 itself says execution is
`NOT_AUTHORIZED_UNTIL_CONSUMER_SCOPED_GRANT_ACCEPTED`. Failure mode: a grading
consumer reading expected payloads today would perform unreceipted, ungranted
reads. Required repair: an append-only comparison-read grant enumerating each
expected artifact path + SHA, a designated grading consumer, and per-read
receipts, accepted before any numerical acceptance.

**F5-ADJ-03 — BLOCKING (for numerical acceptance of ordinals 20, 21, 25, 27,
28)**

Independent synthetic component fixtures **cannot alone** grade the
representative retained values for `NUMERICALLY_BOUNDED_REQUIRED` rows without
retained expected intermediates (required attack 6). The
`operand_conditioned_matvec` pass rule compares every coordinate against
`expected` under a cap computed from `f64(weight)·f64(input)` of the **actual**
operands. The synthetic seven-boundary oracle supplies synthetic operands and
expectations; it qualifies the implementation at fixture points but provides
neither the expected values nor the caps for the representative operands. These
are distinct evidentiary claims, exactly as the builder's AR-02 disposition
states. Required repair: an authorized f64 reference producer evaluated on the
actual retained operands (itself needing read authority per F5-ADJ-02), or an
append-only D0 revision that retains expected intermediates for those rows.

**F5-ADJ-04 — NON_BLOCKING_REQUIRED**

The AGY/Gemini `CONTINUE` response is overruled (required attack 7). It is
internally contradictory — a `NON_BLOCKING_REQUIRED` severity is by definition
acceptance-relevant and cannot coexist with "No action required" — and its
central claim ("repository doctrine explicitly permits a D3.5 PASS solely from
hashes") is factually refuted by the committed bytes (F5-ADJ-01: 7/10 bound
ordinals differ). It also conflates execution-time reads (the runner correctly
needs none) with grading-time read authority (the actual question). Its
`CONTINUE` verdict carries no adjudicative weight; this adjudication is the
controlling disposition. Required repair: bank this adjudication as the
resolution of `builder_disagreement`.

**F5-ADJ-05 — NON_BLOCKING_REQUIRED**

`direct_production_copy: true` is hard-coded on all 34 stage rows by
`DirectoryCapture` in
`crates/f017-native/src/bin/retained_qualification.rs` (both `capture` and
`capture_u16`). This is semantically false for natively computed stages whose
bytes demonstrably differ from the production references (7 bound ordinals),
and the flag appears nowhere else in the committed tree to license a different
meaning. Failure mode: a future grading or provenance consumer could read
banked manifests as claiming production byte provenance. Required repair:
append-only vocabulary correction (e.g., `native_recomputation`) before any
consumer relies on manifest semantics; the SHAs themselves remain valid, so
the execution evidence stands.

**F5-ADJ-06 — DEFENSE_IN_DEPTH**

All per-run capture files, including receipts, are byte-identical across the 20
runs and carry no run-distinguishing identity (no run nonce or timestamp); the
same/fresh-process distinction rests solely on the wrapper-authored
`repeat-result.json`. This is an inherent consequence of the byte-determinism
claim, not a defect, but future events should bind a per-run nonce into receipts
so a copied directory is distinguishable from a re-execution at the receipt
layer.

**F5-ADJ-07 — DEFENSE_IN_DEPTH**

The expected reference bytes originate from an MLX 0.32.1 environment
(historical `package.json` at the readiness root, libmlx `c30b1529…`), while
native qualification pinned 0.31.2. Cross-environment numeric comparison is
the intended design, but the future comparison-read grant / grading contract
should record this environment skew explicitly.

## Remaining adjudicated confirmations

- **Epistemic lock (attack 8): preserved.** D0 v2 exact-value-locks
  `misderived_tolerance_repair` to
  `APPEND_ONLY_NEW_D0_REVISION_FROM_FRESH_CORPUS_EXCLUDING_TRIGGERING_D3_5_OUTPUT_AND_NEW_FABLE_REVIEW`;
  the evidence declares `d3_5_result_may_falsify_d0: true` and
  `may_set_or_tune_tolerance: false`. This adjudication sets and tunes nothing;
  any tolerance revision requires a fresh non-trigger corpus and a new D0
  review.
- **Scope (attack 9): confirmed.** Evidence, grant, package (layer-3 `blk.3`
  tensors, position 0), and D0 `scope_limitations` all bind D3.5 to
  representative layer-3 S0→S2 only; `full_forward_qualified_by_d3_5: false`.
- **P1 instantiability (attack 10): confirmed and classified.** The committed
  architecture at the execution head still declares
  `real_full_checkpoint_bounded_p1_math: NOT_YET_INSTANTIABLE_BLOCKS_FINAL_DOMAIN_ACCEPTANCE`,
  and phase invariants show zero real P1 executions and zero live P1
  authorization artifacts. Classification: the phase may **not** proceed to a
  binding exact P1 contract before that producer exists and before the
  F5-ADJ-02/03 repairs land; append-only non-binding drafting is permitted, but
  no P1 authorization artifact may be created or consumed.
- **Another retained numerical execution: not required.** The banked captures
  are deterministic and SHA-bound; numerical grading can proceed as a separate
  read-only comparison event once the comparison-read grant and
  oracle-instantiation repairs are accepted.

## Adjudication verdict

**`ACCEPT_D3_5_EXECUTION_EVIDENCE_ONLY`**

The executed event stayed strictly within its granted authority (only the 40
enumerated reads occurred, all receipted; expected payloads were never read),
every committed and machine-local binding verifies, and the evidence honestly
declines to claim numerical acceptance. This acceptance covers execution,
accounting, and determinism only. It is not a D3.5 numerical PASS and not native
domain acceptance; any numerical PASS is blocked until F5-ADJ-01/02/03 are
repaired, and real P1 remains unexecuted and unauthorized.
