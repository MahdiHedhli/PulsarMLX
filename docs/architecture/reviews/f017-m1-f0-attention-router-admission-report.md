# PulsarMLX F017 M1-F0 Attention/Router Admission Report

## Result

`READY FOR M1-F0 ADVERSARIAL REVIEW`

No real checkpoint payload was accessed. M1-F0 was not executed or authorized.
M1-F remains not authorized.

## Source and evidence reconciliation

- starting SHA: `de25a5327cffbd30c8e4898df8f019ec9f084c94`
- runtime/tooling identity: `3192b31e4fe3008f0182548a45f7117948d83afd`
- accepted M1-E evidence: `0f85ee81205836a492a9dd44d71e56dc6ce46b22a5064f51c5f37dd561f292a9`
- M1-F ordering blocker: `f7f6d7bc387481f99386a19f13a5f561d3ee4bff18f5e197ffcfe9a42a18b4b6`
- checkpoint/catalog/map: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` / `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0` / `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`

The catalog cannot freeze routing: it identifies tensor metadata, not the
values of `top8(sigmoid(router × rms_norm(attention_residual(input))) + bias)`.
The historical route is input-dependent and is expressly prohibited. The
architecture now uses separate M1-F0 discovery and M1-F qualification stages.

## Frozen layer-3 input

- generator Git SHA: `0a175b68c969fafddd02e907d4487ae1343f9be0`
- generator file SHA-256: `8dd7e9b8a4e4a6bfdb5a71535dabd28b4495209df326a88650b6831efc26d32d`
- fixture artifact SHA-256: `33be5f7ed93a29621b39034246a8bf088111fa4138b0966179aad94a138e63c4`
- package SHA-256: `eb5693c99f73c2a95d71aec947b8a18a6c07c71dbbb460490af82b617dba9283`
- hidden: `decc4ef42e1cf5d6cbee2fe6d46f3cd29b6dd39b9bb997d1083e7a7228ed86cf`
- position: `af5570f5a1810b7af78caf4bc70a660f0df51e42baf91d4de5b2328de0e83dfc`
- empty MLA cache: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- DSA range-fill state: `2bb5d053425b308fbef711827f82a50aa05a6cc2ae11952f3f90447ff0d27764`
- mask: `4bf5122f344554c53bde2ebb8cd2b7e3d1600ad631c385a5d7cce23c7785459a`
- Python / NumPy / PRNG / seed: `3.13.13` / `2.4.5` / `PCG64` / `17017006`

All components use canonical binary encodings. Position 0 makes DSA
`range_fill([0])`; no indexer weight is part of M1-F0.

## Exact tensor allowlist and budget

| role | tensor | type | packed bytes |
|---|---|---:|---:|
| attention norm | `blk.3.attn_norm.weight` | F32 | 24,576 |
| query LoRA A | `blk.3.attn_q_a.weight` | Q5_K | 8,650,752 |
| query LoRA norm | `blk.3.attn_q_a_norm.weight` | F32 | 8,192 |
| query heads | `blk.3.attn_q_b.weight` | Q8_0 | 35,651,584 |
| KV latent + RoPE | `blk.3.attn_kv_a_mqa.weight` | Q8_0 | 3,760,128 |
| KV latent norm | `blk.3.attn_kv_a_norm.weight` | F32 | 2,048 |
| key-nope heads | `blk.3.attn_k_b.weight` | Q8_0 | 6,684,672 |
| value heads | `blk.3.attn_v_b.weight` | Q8_0 | 8,912,896 |
| attention output | `blk.3.attn_output.weight` | Q5_K | 69,206,016 |
| router input norm | `blk.3.ffn_norm.weight` | F32 | 24,576 |
| router projection | `blk.3.ffn_gate_inp.weight` | F32 | 6,291,456 |
| router bias | `blk.3.exp_probs_b.bias` | F32 | 1,024 |

All are in shard 2. Exact budget: 12 payloads, one shard open, 12 positional
reads, 139,217,920 compressed bytes, 666,430,464 decoded bytes, zero expert
payloads.

## Oracle, decoder, selection, and numerical contracts

- independent preparer SHA-256: `ec9a679b78ccd5adb5353cb689cefe642307a07fdb9a266d65d99dab86c6e48d`
- decoder contract SHA-256: `2ef792969f48398dd18b876eae2b4a45d063bcc76169b83d8c5561cc6f9da66e`
- exact scaffold SHA-256: `6f6278715159c24e21c60ded97b993fd575393de9b4b16b3fc4dbfb16d1416cb`
- selection contract SHA-256: `4207845cd22f89a42c42a5ab8ef240cf1af5db3434c2cabac0ecfe9d1beddd0a`
- numerical contract SHA-256: `e380416041b750535f6339da25710ab8633f6fe1561c4494919b010d392dbb01`

The oracle is Python/NumPy only and contains independent F32/Q8_0/Q5_K
decoders. Frozen cross-language block identities are `05ff0999…76c79` for
Q8_0 and `6168658f…478e7` for Q5_K. No Rust, MLX, FFI, candidate output,
expert computation, or Feature 018 dependency exists.

Attention/router numerical stages use frozen operand-conditioned forward-error
composition. Top-8 IDs are exact, with score-descending/lower-ID tie-breaking;
the rank-8 lower bound must exceed rank-9 upper bound. Routing bytes use eight
little-endian f64 values. No post-observation retuning is permitted.

## Immutable config and preflight

- execution-config SHA-256: `b1adab3dc981b3baca82279d96deb9cc8dbf79176d3ee248ee354d6e9ab4366d`
- preflight result: `READY_TO_EXECUTE_M1_F0`
- checkpoint reads / decodes / oracle / MLX / attempt consumption: `0 / 0 / false / 0 / false`

Preflight validates config identity, catalog metadata, input components,
contracts, budgets, attempt state, and absence of authorization. Future real
execution additionally requires a separate external-review-derived,
hash-bound authorization before the preparer can open its typed private
package.

## Checkpoint-free qualification

- synthetic evidence SHA-256: `5b63c0a6be3e5a1f60f78c4b0a492051ad3217c0cc6d7e1e0c083c5ffad16c7b`
- 10/10 complete attention/router discoveries were byte-identical;
- exact synthetic top-8: `[188,57,158,117,87,16,218,46]` (not a real route);
- zero expert access/dispatch, fallback, backend error, complete-layer output,
  or logits;
- six real-shaped stress families passed without contract changes;
- time-bounded soak: 43 cycles / 430 discoveries, no mismatch, peak RSS
  38,640 KiB; soak SHA-256 `b92b5511397510b7288f15d7c76cdcc2b1616054b5ef1cd5b7ec0903871b54bf`.

## Failure injection and attempt semantics

The suite rejects historical-route substitution, stale/different input,
expert or adjacent-layer tensor, missing/wildcard tensor, wrong router bias,
decoder mutation, budget excess, top-k inversion, routing-weight drift, config
mutation, attempt reuse, absent authorization, traversal, and symlink escape.

Preflight/admission failures do not consume an attempt. A future M1-F0 attempt
is consumed only after external authorization, config and host admission, and
transition into bounded real oracle execution. It may never share an
authorization with M1-F.

## Review and phase disposition

- internal review: `GO FOR M1-F0 ADVERSARIAL REVIEW`
- adversarial packet:
  `docs/architecture/reviews/f017-m1-f0-adversarial-review-packet.md`
- final-head Apple-native CI: pending the documentation/evidence head
- real M1-F0 execution performed: `false`
- M1-F0 authorization issued: `false`
- M1-F authorization issued: `false`

Exact next action: perform an independent adversarial review of the frozen
M1-F0 package. Do not access the real checkpoint or authorize M1-F.
