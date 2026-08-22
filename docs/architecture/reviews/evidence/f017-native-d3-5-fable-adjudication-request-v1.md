# F017 D3.5 retained-qualification authority adjudication

Reviewer: `claude-fable-5`

Track: independent numerical/authority adjudication. Review committed bytes
only at the exact pushed target below. Do not edit repository files, read the
original checkpoint, rerun D3.5, or execute P1.

## Target

- Branch: `feat/017-rust-native-inference-runtime`
- Head: `f38dc275b86799712725765cec489089a4a4db50`
- D3.5 execution evidence:
  `docs/architecture/reviews/evidence/f017-native-retained-qualification-execution-evidence-v1.json`
  (`13b1a3a653cf0325f59b0b3b035b7804439a19c000ef8ddf19dad9ecb8316ac8`)
- Evidence validator:
  `scripts/research/validate_f017_native_retained_qualification_execution_v1.py`
  (`620e8c03725682830951d68ef05a4d641d0470b3881cb46dfba145f1d66eff96`)
- AGY/Gemini review:
  `docs/architecture/reviews/evidence/f017-native-d3-5-cross-vendor-agy-gemini-review-v1.json`
  (`d61fc1142c5f58030be15fdcb0c5b8bf4f57a35e0192662dafd08c45f4a68dbd`)

## Facts to verify independently

The machine-local event root is
`/Users/mhedhli/.local/share/pulsarmlx/f017/native-representative-retained-qualification-1`.
It claims one durable owner/attempt, COMPLETE terminal, 10 same-process and 10
fresh-process runs, 34 stages per run, 40 authorized retained tensor reads per
run, 800 receipts total, identical stage bytes across all runs, zero original
checkpoint reads/shard opens, and zero historical payload-ledger delta.

The execution evidence intentionally does not declare D0 numerical acceptance.

## Required attacks

1. Recompute all committed request hashes and run the execution-evidence
   validator against the machine-local bytes.
2. Verify `actual_count == len(reads) == 40` for all 20 receipt censuses and
   terminal count 800 is receipt-derived.
3. Verify exact 20x34 byte identity, fixed vocabulary/serialization, runtime
   identities, owner-only terminalization, and zero original-checkpoint access.
4. Decide whether hashes of non-byte-equivalent produced/expected values can
   instantiate D0 numeric metrics without reading both payloads.
5. Decide whether existing accepted reuse authorities and D0 SHA bindings are
   sufficient native-consumer read authority for expected artifacts, or whether
   consumer-scoped doctrine requires a new explicit comparison-read grant.
6. Decide whether independent synthetic component fixtures can alone grade the
   representative retained values for all D0 `NUMERICALLY_BOUNDED_REQUIRED`
   rows whose representative expected intermediates were not retained.
7. Attack the AGY/Gemini `CONTINUE` response, including the contradiction
   between `NON_BLOCKING_REQUIRED` and `No action required`.
8. Preserve the epistemic lock: D3.5 may falsify D0 but may not set/tune a
   tolerance. Any tolerance revision requires a fresh non-trigger corpus and a
   new D0 review.
9. Confirm D3.5 scope is representative layer-3 S0-to-S2 only, not the full
   forward needed by P1.
10. Confirm the committed architecture still says real full-checkpoint bounded
    P1 math is not instantiable, and classify whether the phase may proceed to
    an exact P1 contract before that producer exists.

## Response requirements

Return stable finding IDs with `BLOCKING`, `NON_BLOCKING_REQUIRED`, or
`DEFENSE_IN_DEPTH`; exact paths/evidence; failure mode; required repair; and
whether another retained numerical execution is required.

Return exactly one adjudication verdict:

- `ACCEPT_D3_5_EXECUTION_EVIDENCE_ONLY`
- `PARK_FOR_D3_5_AUTHORITY_REPAIR`
- `REJECT_NATIVE_DOMAIN`

An execution-evidence acceptance is not a D3.5 numerical PASS and is not native
domain acceptance. Real P1 remains unexecuted and unauthorized.
