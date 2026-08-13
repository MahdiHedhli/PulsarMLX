# F017 M1-E Attempt 2 Handoff

**Status: PREPARED FOR REPAIRED ATTEMPT-2 AUTHORIZATION / NOT EXECUTED**

## Repository identity v2

- compiled runtime SHA: `5c7694d6ba48640279e4725ea96104bc179a62cb`
- tooling SHA: `5c7694d6ba48640279e4725ea96104bc179a62cb`
- compiled arm64 release executable SHA-256:
  `13900ecc2ea5b252c4a83b69ae04ee6b20916a7f3c0133c1b87c9a5c720b2bab`
- trusted repository identity contract/version:
  `f017-trusted-repository-identity-v2` /
  `88faaf375d871a60462cbbddd5b27c186353d168eae2611b14cf485a24a78eaf`
- execution-config schema/version:
  `pulsarmlx.f017.m1e-execution-config` `3.0.0` /
  `764dfa0a8e1a66ccbaecb5860d814440b2208902717fe13b2ce953eb56de490e`

The immutable execution config must bind the exact later authorization
repository head separately. It must prove that the compiled runtime is an
ancestor of that head and that the complete intervening delta is confined to
approved docs/reviews/evidence categories. Git ancestry is necessary but is
not sufficient: all execution-controlling repository artifacts remain bound
by direct SHA-256 identities. Runtime compute, lifecycle, decoder, runner,
path resolver, command/config interpretation, or attempt-consumption drift
requires a newly compiled runtime SHA.

## Accepted and rejected evidence

- M1-E attempt-1 rejected evidence:
  `346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119`
- accepted M1-A/B/C/D evidence:
  `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805` /
  `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770` /
  `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e` /
  `dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c`
- checkpoint/catalog/map:
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` /
  `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0` /
  `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`

Attempt 2 remains authorized-but-unexecuted and unconsumed. No attempt-2
checkpoint access, oracle creation, tensor decode, MLX dispatch, or public
attempt evidence exists.

## Decoder and expert bindings

- decoder v2:
  `9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84`
- corrected independent IQ3 decoder:
  `5faff93b578028065854d1f3717951126404e1a5ccbe9b16f7f5dc8d5343ab68`
- Rust candidate IQ3 decoder:
  `c1606b39afff3a56334c8f56358c711dcbcb5f2df904d4e86612fd2a09b19161`
- third specification decoder:
  `10b2c1eeda4d2955fbc61df659d28a4b2c1b72eb2d730145e74bbad86b347621`
- corrected real-reference preparer:
  `841279fe5a1467f6e8deaaa0e22c59c1c2828bb67f16d5f48ad42dd198f6e224`
- activation payload:
  `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- scaffold/Tier-B:
  `52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38` /
  `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2`

Attempt 2 remains the same layer-3/expert-15 boundary. Only these tensor
identities may be read:

| Role | Quantization | Packed SHA-256 | Correct decoded SHA-256 |
|---|---|---|---|
| gate | IQ2_XXS | `3822822b98505bb0c0447174b1f53d984ca3b78e95e9e118d61e5de84fa2fdc3` | `849081eda002797cdf0aacee5dfddaeb4b7f9f08d18f51a2343ef079317a01db` |
| up | IQ2_XXS | `261011f1f3f084b6db48583711c14f20a9ae4e4e588b877b99db1aee0c2117af` | `4ceb3ddd33a2efa3b64857a44b92e1dfc3fe202c0eb26e18b2d18f4ac80a2d10` |
| down | IQ3_XXS | `442acf3cf5210ade4faa0b38ef0f94aaca7b15571a180804ace52b94cccdf59d` | `f91987106198943c8a225b52dcf0099ba8f8b89d1ecad92c4a7c5c4964e20eae` |

The maximum is three payloads, one shard open, three positional reads, and
11,304,960 compressed bytes. Router, second/shared expert, complete layer,
logits, M1-F, P1/P2/golden-eight, and Feature 018 are prohibited.

## Non-consuming preflight and stop

The future operator must consume only the newly generated private immutable
v3 config. The runner must attest the embedded compiled SHA and executable
hash independently of repository HEAD, validate the exact authorization head,
prove ancestry and the reviewed delta classification, and hash every bound
artifact before returning exactly `READY_TO_EXECUTE_M1_E`.

Preflight must not access checkpoint payloads, create an oracle, decode a
tensor, initialize candidate MLX state, or consume attempt 2. A later
production authorization remains limited to one conceptual expert, 10
complete repeats, 30 native matvec dispatches, and mandatory stop before
M1-F.
