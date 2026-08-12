# F017 M1-C Evidence Review

## Verdict

**M1-C ACCEPTED**

Exactly one authorized real-tensor payload was read. The attempt stopped after
local fixture validation; no second tensor, numerical tensor execution, MLX
compute, projection, expert, layer, or logits boundary ran.

## Frozen bindings

- runtime source: `b29202171a279cd3bb2ac2cf4dc6b3be7486019e`;
- capture tooling source: `23e0bcfe6ca033b1bb0fa988cc759d8720cb1252`;
- accepted M1-A evidence SHA-256:
  `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`;
- accepted M1-B evidence SHA-256:
  `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770`;
- checkpoint-set SHA-256:
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`;
- catalog SHA-256:
  `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0`;
- tensor-map contract SHA-256:
  `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`.

## Admission

The arm64 M1 Ultra used the reviewed MLX native 0.31.2 and MLX C 0.6.0
artifacts with matching hashes. Host telemetry was measured immediately before
the attempt: 79,417,966,592 available bytes against a 17,179,869,184-byte
floor, normal pressure, negligible swap, normal thermal/performance status,
no competing inference, and no listener on port 1234.

## Boundary result

| Field | Result |
| --- | --- |
| Tensor | `output_norm.weight` |
| Shard | `GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf` |
| Offset | 535,291,744 |
| Length | 24,576 bytes |
| Shape/type | `[6144]`, little-endian F32 |
| Payload SHA-256 | `5ed2cdb29cd2c920a2b2b0d3fc5a0f0912593924ce7e2fd7ff8ca994803b8e77` |
| Positional reads | 1 |
| Tensor payloads | 1 |

All 6,144 values are finite. The observed range was -0.01519775390625 to
1.515625, the mean was 1.205369383096695, and no signed zero was present.

## Predetermined questions

1. **Exactly one tensor payload?** Yes: one shard open, one positional read,
   one 24,576-byte payload.
2. **Exact reviewed shard/range?** Yes.
3. **Payload SHA stable?** Yes. Capture, fixture replay, decoded-output hash,
   and final evidence agree.
4. **F32 interpretation independently reproducible?** Yes. The independent
   Python little-endian reader and Rust `quant::row_to_f32` F32 lane produced
   identical IEEE-754 bits for all 6,144 values.
5. **Shape/type exact?** Yes: `[6144]`, F32, little-endian.
6. **Quant decode zero?** Yes; raw F32 interpretation is recorded separately
   and `quant_decode_count` is zero.
7. **Compute zero?** Yes. MLX/model dispatch, projection, expert, layer, and
   logits counts are all zero.
8. **No adjacent tensor?** Yes. The read length equals the cataloged tensor
   extent; no range widening occurred.
9. **Private payload remained local?** Yes. Only hashes, metadata, and
   diagnostics are public; the payload and absolute path remain outside Git.
10. **Is one real projection meaningful?** Yes, subject to separate M1-D
    authorization and its frozen activation/numerical contract.

## Evidence

Public evidence is
[`evidence/f017-m1-c-real-tensor-v1.json`](evidence/f017-m1-c-real-tensor-v1.json),
SHA-256 `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e`.
The private capture package is identified by artifact name
`PulsarMLX-f017-m1-c-evidence.PNktu5`; no absolute path is published here.

T017-140 is complete. The M1-D packet is prepared but not authorized. T017-141
and P1 remain blocked.
