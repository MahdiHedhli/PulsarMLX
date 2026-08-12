# F017 M1-C Real-Tensor Handoff

## Status

**PREPARED / NOT AUTHORIZED / NOT EXECUTED**

This document prepares one bounded local-only real tensor fixture. It does not
authorize checkpoint payload extraction, decode, projection, adapter compute,
M1-C execution, or P1.

## Prior gate bindings

- runtime source SHA:
  `b29202171a279cd3bb2ac2cf4dc6b3be7486019e`;
- accepted M1-A public evidence SHA-256:
  `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`;
- accepted M1-B public evidence:
  [`evidence/f017-m1-b-checkpoint-identity-v1.json`](evidence/f017-m1-b-checkpoint-identity-v1.json);
- accepted M1-B evidence SHA-256:
  `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770`;
- checkpoint-set SHA-256:
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`;
- checkpoint revision:
  `abc55e72527792c6e77069c99b4cb7de16fa9f23`.

## Proposed single boundary

The first M1-C boundary is the smallest simple real tensor that exercises an
exact positional read and an auditable F32 decode without projection or model
state:

| Field | Frozen value |
| --- | --- |
| Tensor | `output_norm.weight` |
| Shard | `GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf` |
| Shard SHA-256 | `d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36` |
| Absolute byte offset | 535,291,744 |
| Byte length | 24,576 |
| Quantization/storage | `F32`, little-endian |
| Dimensions | `[6144]` |
| Catalog provenance | `docs/research/glm52/raw/f016-c01-catalog-0001.json` |
| Catalog artifact SHA-256 | `135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19` |

The decoder contract is the exact F32 lane of
`quant::decode_source_row` at the frozen runtime source. Its source artifact
`crates/quant/src/lib.rs` has SHA-256
`b9d0c302ec9761432f55433d8b2b8208d4a366adc875370b7d7493d6cfc3b402`.
Before authorization, the M1-C packet must freeze an independent Python
little-endian F32 oracle generator and its source SHA; the Rust candidate may
not generate its own expected output.

## Future one-attempt contract

A separately authorized M1-C may perform exactly one bounded 24,576-byte
positional read for this tensor, create one permission-restricted local fixture,
decode it through the frozen F32 lane, compare it with the independent oracle,
and validate the local-only R13 manifest. It must record:

- exact source/checkpoint/shard/tensor/range identity;
- raw fixture byte length and SHA-256;
- exact decoded output SHA-256 and bitwise comparison;
- read count/bytes and decode count;
- zero projection, expert, layer, logits, token, and MLX compute dispatch;
- lifecycle and teardown state;
- `local_only_private_checkpoint_derived`, `redistributable: false`.

One attempt only. Preserve the first failure and stop. No automatic retry.
The payload and absolute local paths must remain outside Git.

## Mandatory stop

M1-C is not authorized here. M1-D through M1-G, T017-141, P1, P2,
golden-eight, Feature 018 integration, and output-head residency remain
blocked.

