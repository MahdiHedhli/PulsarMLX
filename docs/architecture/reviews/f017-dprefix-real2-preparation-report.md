# PulsarMLX F017 DPREFIX-REAL-2 Preparation Report

## Outcome

`GO FOR DPREFIX-REAL-2 PREPARATION ADVERSARIAL REVIEW`

The predecessor attempt remains permanently terminal. The successor is a
fresh, authorized and unconsumed attempt held pending independent review.
This preparation performed zero checkpoint access and left the real-payload
ledger at 99.

## Native shape defect

- Root-cause class: `CANDIDATE_IMPORT`.
- First failing stage: `layer_0.attention.k_head_0`.
- Tensor: `blk.0.attn_k_b.weight`.
- GGUF shape: `[192,512,64]`.
- Predecessor semantic import: matrix `[512,192]`, vector `[512]`.
- Correct import: matrix `[192,512]`, vector `[512]`.
- First divergence: candidate `attn_k_b` per-head import/orientation.
- The prior rehearsal used reduced head geometry (`qk_nope=8`, `kv_lora=16`)
  and therefore never exercised the real `[192,512,64]` special orientation.

The predecessor exact-real-shape path fails with the structured contraction
diagnostic. The successor applies one explicit transpose and passes the same
native operation with exact scalar-oracle parity. The full three-layer shape
graph passed 10 deterministic exact-real-shape synthetic repeats.

## Persistence and failure closure

REAL-2 freezes the order:

`oracle finalize → persist Class-A values → fsync/freeze manifest → candidate spawn`

It also durably retains every packed payload immediately after its read and
hash journal entry. A forced native candidate failure proved that the packed
package and oracle layer-2/layer-3 products survive, rehash correctly, and
remain read-only. The failure banker records structured stage/tensor/shape,
dispatch, backend, lifecycle, oracle, and packed-package evidence.

The downstream policy is frozen before observation:

`ORACLE_STATE_USABLE_FOR_ANALYTICAL_ROUTE_PLANNING_ONLY`

This does not authorize M1-F0 execution. Candidate/oracle/metric reruns from a
future retained packed package require a new explicit authorization and may
never launch automatically.

## Gate summary

- Packed hard gates: 40.
- Decoded hard gates: 2 (`token_embd.weight`, `blk.0.ffn_down.weight`).
- Packed-only gates: 38.
- REAL-2 access plan: 40 payloads / 1,431,263,232 bytes.
- Ledger plan: `99 → 139`.
- Memory floor: 27 GiB remains safe because packed retention is streamed to
  durable storage rather than retained as an additional in-memory copy.
- Automatic retry: false.
- Automatic M1-F0 continuation: false.
- Checkpoint access during preparation: 0.
