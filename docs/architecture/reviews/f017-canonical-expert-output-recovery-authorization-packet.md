# F017 Canonical Expert-Output Recovery Authorization Packet

Status: `PRE_EXECUTION_CONDITION_LANDED_REQUIRES_RENEWED_INDEPENDENT_REVIEW`

Independent-review question:

> Does this package safely authorize exactly one future event to read the 24
> specified expert-weight payloads from shard 2 and produce eight canonical
> expert down-output vectors, while requiring exact agreement between two
> independent accepted decoders for every retained payload and without
> performing aggregate evaluation or any downstream execution?

## Fixed authority and scope

- Event: `F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1`
- Starting head: `81e187a1ce272386041e2d6445786ba14d07f91c`
- Canonical input: `DPREFIX-EXACT-1`, content SHA-256
  `9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11`
- Selected expert IDs: `[250, 10, 237, 73, 62, 177, 218, 28]`
- Access budget: 24 positional reads, 90,439,680 packed bytes, one shard open.
- Ledger plan: `139 -> 163`; partial failure is `139 + N` durable reads.
- Retry: forbidden. Second attempt: not authorized.
- Aggregate evaluation, candidate/model execution, representative M1-F0,
  dense-prefix replay, router/attention/shared-expert reads, and fallback reads
  are forbidden.

This preparation performed zero checkpoint reads and zero shard opens. It does
not authorize execution. A separate independent adversarial `GO` is required.

## Binding pre-execution amendment

The conditional review found that the original package cited the accepted
decoder lineage but did not make two independent decodes and their exact
agreement load-bearing for every real payload. The event therefore did not run.
This amendment requires, before the next checkpoint read and before expert
compute, both decoders to consume the same immutable retained packed bytes and
produce exactly equal canonical row-major little-endian f32 SHA-256 identities.

- IQ2_XXS decoder A: accepted Rust `decode_iq2_xxs_matrix` lineage.
- IQ2_XXS decoder B: independent Python `dequantize_matrix_iq2_xxs`
  specification transcription.
- IQ3_XXS decoder A: accepted corrected M1-E Rust
  `decode_iq3_xxs_matrix` lineage.
- IQ3_XXS decoder B: independent Python corrected
  `decode_iq3_xxs_spec` specification transcription.

Any mismatch is terminal: no decoder may be selected as a winner, no further
checkpoint read is permitted, and no expert-output authority is granted. The
gate uses the original 24 retained packed artifacts and adds zero checkpoint
reads.

All 24 keys, expert IDs, roles, offsets, sizes, quantization types, logical
shapes, and shard assignments were independently re-derived from catalog slice
formula `parent_data_offset_abs + expert_id * per_expert_packed_length` and the
accepted expert-166 crosscheck. The result is 24/24 PASS, shard 2 only, and
90,439,680 packed bytes without opening the checkpoint.

## Exact payload inventory

Every entry has one permitted read. Packed SHA-256 is intentionally a future
first-observation value because no authoritative prior payload hash exists for
these slices; the future event must bank and rehash each retained packed object.

| Ordinal | Expert | Role | Checkpoint key | Offset | Bytes | Quant | Logical shape `[out,in]` |
|---:|---:|---|---|---:|---:|---|---|
| 0 | 250 | gate | `blk.3.ffn_gate_exps.weight#250` | 4185544544 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 1 | 250 | up | `blk.3.ffn_up_exps.weight#250` | 5030983520 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 2 | 250 | down | `blk.3.ffn_down_exps.weight#250` | 3335313248 | 4816896 | IQ3_XXS | `[6144, 2048]` |
| 3 | 10 | gate | `blk.3.ffn_gate_exps.weight#10` | 3406976864 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 4 | 10 | up | `blk.3.ffn_up_exps.weight#10` | 4252415840 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 5 | 10 | down | `blk.3.ffn_down_exps.weight#10` | 2179258208 | 4816896 | IQ3_XXS | `[6144, 2048]` |
| 6 | 237 | gate | `blk.3.ffn_gate_exps.weight#237` | 4143372128 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 7 | 237 | up | `blk.3.ffn_up_exps.weight#237` | 4988811104 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 8 | 237 | down | `blk.3.ffn_down_exps.weight#237` | 3272693600 | 4816896 | IQ3_XXS | `[6144, 2048]` |
| 9 | 73 | gate | `blk.3.ffn_gate_exps.weight#73` | 3611350880 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 10 | 73 | up | `blk.3.ffn_up_exps.weight#73` | 4456789856 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 11 | 73 | down | `blk.3.ffn_down_exps.weight#73` | 2482722656 | 4816896 | IQ3_XXS | `[6144, 2048]` |
| 12 | 62 | gate | `blk.3.ffn_gate_exps.weight#62` | 3575666528 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 13 | 62 | up | `blk.3.ffn_up_exps.weight#62` | 4421105504 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 14 | 62 | down | `blk.3.ffn_down_exps.weight#62` | 2429736800 | 4816896 | IQ3_XXS | `[6144, 2048]` |
| 15 | 177 | gate | `blk.3.ffn_gate_exps.weight#177` | 3948730208 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 16 | 177 | up | `blk.3.ffn_up_exps.weight#177` | 4794169184 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 17 | 177 | down | `blk.3.ffn_down_exps.weight#177` | 2983679840 | 4816896 | IQ3_XXS | `[6144, 2048]` |
| 18 | 218 | gate | `blk.3.ffn_gate_exps.weight#218` | 4081735520 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 19 | 218 | up | `blk.3.ffn_up_exps.weight#218` | 4927174496 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 20 | 218 | down | `blk.3.ffn_down_exps.weight#218` | 3181172576 | 4816896 | IQ3_XXS | `[6144, 2048]` |
| 21 | 28 | gate | `blk.3.ffn_gate_exps.weight#28` | 3465369440 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 22 | 28 | up | `blk.3.ffn_up_exps.weight#28` | 4310808416 | 3244032 | IQ2_XXS | `[2048, 6144]` |
| 23 | 28 | down | `blk.3.ffn_down_exps.weight#28` | 2265962336 | 4816896 | IQ3_XXS | `[6144, 2048]` |

## Frozen computation

The retained canonical f32 layer-3 entry state is RMS-normalized with retained
`ffn_norm_weight` using strict increasing-index binary32 arithmetic and binary32
epsilon `9.999999747378752e-06`. Each expert then computes row-major f32 gate
and up projections, `SiLU(gate) * up` with binary32 rounding at each specified
operation, and a row-major f32 down projection. IQ2_XXS and corrected IQ3_XXS
decoding are bound to the accepted decoder contract. The f64 analytical-router
normalized state is diagnostic only and cannot override the generated f32
expert input.

## Retention and deterministic verification

The future event retains all 24 packed payloads at creation, before decode, in
an immutable read-only package. Two fresh-process fixed-order computations use
that retained package and the retained canonical input; all eight output hashes
must match exactly without another checkpoint read. The outputs are eight
independent canonical little-endian f32 `[6144]` artifacts of 24,576 bytes each
(196,608 bytes total), keyed by expert ID and hash-bound to their input and
three weight identities.

## Required review disposition

Only an independent verdict explicitly authorizing one event may release the
24-read recovery under this amended condition. The prior conditional verdict
does not release the amended package; no real access follows automatically.
