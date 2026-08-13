# F017 M1-E Attempt 2 Handoff

**Status: PREPARED FOR ATTEMPT-2 AUTHORIZATION / NOT EXECUTED**

## Immutable binding

- runtime/tooling SHA: `942f23505e5829e55bc9b6611bd08d3c93481672`
- attempt-1 rejected evidence:
  `346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119`
- execution-config SHA-256:
  `4778a2694fd4a80feb5789ee3641dcd13fea3b2ba1d144dc150dde8af7d14cd7`
- decoder contract/version: `f017-m1e-iq2-iq3-decoder-v2` /
  `9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84`
- corrected independent IQ3 decoder:
  `5faff93b578028065854d1f3717951126404e1a5ccbe9b16f7f5dc8d5343ab68`
- Rust decoder:
  `c1606b39afff3a56334c8f56358c711dcbcb5f2df904d4e86612fd2a09b19161`
- third specification decoder:
  `10b2c1eeda4d2955fbc61df659d28a4b2c1b72eb2d730145e74bbad86b347621`
- real-reference preparer:
  `841279fe5a1467f6e8deaaa0e22c59c1c2828bb67f16d5f48ad42dd198f6e224`
- activation payload:
  `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- scaffold/Tier-B:
  `52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38` /
  `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2`

Accepted M1-A/B/C/D evidence remains bound at
`aa0e4802…a805`, `9f9bd444…5770`, `343548af…041e`, and
`dc5c4900…a53c`. Checkpoint/catalog/map remain
`d7d1e6a8…afee`, `0f042510…77f0`, and `ea0786f0…223`.

## Exact expert boundary

Attempt 2 is the same one-expert boundary, layer 3 / expert 15. Only these
three already-reviewed tensor identities may be read:

| Role | Quantization | Packed SHA-256 | Correct decoded SHA-256 |
|---|---|---|---|
| gate | IQ2_XXS | `3822822b98505bb0c0447174b1f53d984ca3b78e95e9e118d61e5de84fa2fdc3` | `849081eda002797cdf0aacee5dfddaeb4b7f9f08d18f51a2343ef079317a01db` |
| up | IQ2_XXS | `261011f1f3f084b6db48583711c14f20a9ae4e4e588b877b99db1aee0c2117af` | `4ceb3ddd33a2efa3b64857a44b92e1dfc3fe202c0eb26e18b2d18f4ac80a2d10` |
| down | IQ3_XXS | `442acf3cf5210ade4faa0b38ef0f94aaca7b15571a180804ace52b94cccdf59d` | `f91987106198943c8a225b52dcf0099ba8f8b89d1ecad92c4a7c5c4964e20eae` |

The maximum remains three payloads, one shard open, three positional reads,
and 11,304,960 compressed bytes. Router, second/shared expert, complete layer,
logits, M1-F, P1/P2/golden-eight, and Feature 018 are prohibited.

## One-attempt execution contract

The future operator must consume only the private immutable config with the
exact config hash above. Require exactly `READY_TO_EXECUTE_M1_E`, then
production-reviewed measured-host admission, before the exclusive attempt-2
`EXECUTION_STARTED` transition. Finalize and validate the independent oracle
before candidate start. Execute one conceptual expert with 10 complete
repeats and exactly 30 native matvec dispatches. Require exact per-stage repeat
integrity, frozen Tier-B qualification, zero fallback/reference/scaffold/error,
and full lifecycle reconciliation. Stop after the first result and do not
execute M1-F.
