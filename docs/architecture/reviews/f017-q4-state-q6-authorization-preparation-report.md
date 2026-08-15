# PulsarMLX F017 Q4_K State Closure + Q6_K Authorization Preparation Report

Starting SHA: `45f27650a019d8d10aa48032fe7a78b81e767ab4`.

The committed Q4 evidence is accepted and immutable. Its successor attempt ledger records the same already-banked reality and adds a fail-closed cross-artifact reconciliation. The payload ledger remains 58; checkpoint access in this phase is zero.

## Q4 closure

- Terminal evidence SHA: `035ad4351406c24c65667a5322f1ffae71589f046a5ba3f591b8a4e3f6140994`.
- Attempt: authorized, consumed, executed, checkpoint accessed.
- Terminal class: `EXACT_REAL_BYTE_QUALIFIED`.
- Transition: `57 -> 58`, exactly one payload.
- Result: `Q4_K STATE TRIAD RECONCILED`.
- Historical non-execution and authorization-amendment events remain distinct.

## Q6 authorization package

- Attempt: `Q6K-REAL-1`, authorized and unconsumed.
- Target: `blk.0.ffn_down.weight`, shard 2, offset 1203482464, shape `[12288, 6144]`, Q6_K.
- Packed budget: 61931520 bytes, one shard open, one positional read, one payload.
- Expected future transition: `58 -> 59` after a real payload read.
- Corrected decoder source: `1d285e58d5b5c55368191cccb881a56dc78560d7e2541e8d94b5217cd382548d`.
- Defect closure target: `F017-Q6K-LANE-ORDER-001`.
- Decoder rule: canonical little-endian f32 `A == B == C`, no tolerance or majority vote.
- Sufficiency: `ONE Q6_K PAYLOAD SUFFICIENT`.
- Canonical preflight target: `READY_TO_EXECUTE_Q6_K_REAL_BYTE_QUALIFICATION`.

No automatic retry, second Q6 payload, dense-prefix continuation, M1-F, M1-G, or P1 is authorized.

## Dense-prefix preservation

Prompt/token package, exact 40-tensor inventory, 27 GiB residency admission, Tier-B numerical contract, hidden-state retention, routing v3, and representative M1-F0 handoff are byte-identical to their accepted versions. Only prerequisite planning references are superseded by Q6 handoff v3.

Internal verdict: `GO FOR Q6_K AUTHORIZATION ADVERSARIAL REVIEW`.

Exact next action: independent adversarial review. Q6_K remains unexecuted.
