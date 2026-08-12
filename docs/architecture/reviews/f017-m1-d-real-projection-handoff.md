# F017 M1-D Real-Projection Handoff

## Status

**PREPARED / NOT AUTHORIZED / NOT EXECUTED**

This packet freezes the next one-boundary proposal. It does not authorize
checkpoint payload access, projection execution, MLX compute, M1-D, or P1.

## Prior-gate bindings

- runtime source SHA:
  `b29202171a279cd3bb2ac2cf4dc6b3be7486019e`;
- accepted M1-A evidence SHA-256:
  `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`;
- accepted M1-B evidence SHA-256:
  `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770`;
- accepted M1-C evidence SHA-256:
  `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e`;
- checkpoint-set SHA-256:
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`;
- catalog SHA-256:
  `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0`;
- production tensor-map contract SHA-256:
  `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`.

## Proposed single projection

The proposed first production-adapter projection is a material Q8_0 MLA
boundary already represented by the checkpoint-free R5 contract:

| Field | Frozen metadata-only value |
| --- | --- |
| Tensor | `blk.0.attn_kv_a_mqa.weight` |
| Role | layer-0 MLA KV latent projection |
| Shard | `GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf` |
| Absolute offset | 1,077,266,272 |
| Packed length | 3,760,128 bytes |
| GGUF type | `Q8_0` |
| GGUF dimensions | `[6144, 576]` |
| Production boundary | packed read -> reviewed Q8_0 decode -> contiguous f32 -> production MLX matvec -> synchronized f32 output |

The packed length is derived from the frozen Q8_0 block contract and the next
catalog offset; M1-D admission must independently revalidate it before access.
No payload was read while preparing this packet.

## Required activation and numerical contract

Before a future authorization, freeze one independent local-only activation of
length 6,144 with source/provenance and IEEE-754 hash. The deterministic exact
scaffold must remain the bit-level semantic oracle. The production MLX result
must use the already-reviewed R5/Tier-B separation and fail closed on numerical
or dispatch divergence; thresholds may not be invented after candidate output.

## Future one-attempt constraints

A separate M1-D authorization must permit exactly one matrix boundary and
require:

- exact shard/tensor/range and checkpoint identities;
- bounded short-read-safe packed access;
- Q8_0 oracle parity before production execution;
- one production `MlxContext`, explicit synchronization, teardown, and full
  lifecycle reconciliation;
- exact activation/output provenance;
- zero fallback, reference, or qualification-scaffold dispatch in production;
- local-only payload policy and public-safe evidence;
- one attempt and mandatory stop.

M1-E through M1-G, T017-141, P1, P2, golden-eight, Feature 018 integration,
and output-head residency remain blocked.
