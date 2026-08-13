# F017 M1-E Attempt 2 Authorization

**Status: AUTHORIZED FOR EXACTLY ONE M1-E ATTEMPT 2 / NOT EXECUTED**

This repaired authorization supersedes the earlier unexecuted packet. Attempt
1 remains consumed and rejected. Attempt 2 never crossed `EXECUTION_STARTED`
and remains unconsumed: real checkpoint access, oracle creation, tensor decode,
candidate MLX context/dispatch, and attempt-2 evidence are absent.

## Distinct repository identities

- compiled runtime SHA: `5c7694d6ba48640279e4725ea96104bc179a62cb`
- tooling SHA: `5c7694d6ba48640279e4725ea96104bc179a62cb`
- authorization execution-head SHA:
  `f8a9910ca1c9242c2638556b0daee6a11949a090`
- release executable SHA-256:
  `13900ecc2ea5b252c4a83b69ae04ee6b20916a7f3c0133c1b87c9a5c720b2bab`
- architecture/profile/features: `arm64` / `release` /
  `pulsar_native_mlx`
- trusted repository contract/version:
  `f017-trusted-repository-identity-v2` /
  `88faaf375d871a60462cbbddd5b27c186353d168eae2611b14cf485a24a78eaf`
- execution-config schema/version:
  `pulsarmlx.f017.m1e-execution-config` `3.0.0` /
  `764dfa0a8e1a66ccbaecb5860d814440b2208902717fe13b2ce953eb56de490e`
- runtime-drift classification SHA-256:
  `400ff607be3e4eb28b1d246c701abaf2140970bb4fdc269bcc1485f113a485d3`
- immutable private execution-config SHA-256:
  `a8905b8709aadf8d36bf94c2cb54c14a9ce5bcd31e7a1b184da33127af300f4e`

The authorization execution head is an exact reviewed descendant of the
compiled runtime. Its complete delta is docs/reviews only and is accepted by
the deterministic v2 classifier. The operator must use the clean detached
repository root at that exact execution head. This later authorization-status
commit is not substituted for that trusted root.

## Direct artifact and evidence bindings

- handoff path:
  `docs/architecture/reviews/f017-m1-e-attempt-2-handoff.md`
- handoff SHA-256:
  `ddefdc98a51dad94d87e5e011d377afea8f4f32982dd6368b6238f3e73690032`
- M1-E attempt-1 rejected evidence:
  `346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119`
- M1-A/B/C/D evidence:
  `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805` /
  `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770` /
  `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e` /
  `dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c`
- checkpoint/catalog/map:
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` /
  `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0` /
  `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`
- decoder contract v2:
  `9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84`
- corrected Python / Rust / specification IQ3 decoders:
  `5faff93b578028065854d1f3717951126404e1a5ccbe9b16f7f5dc8d5343ab68` /
  `c1606b39afff3a56334c8f56358c711dcbcb5f2df904d4e86612fd2a09b19161` /
  `10b2c1eeda4d2955fbc61df659d28a4b2c1b72eb2d730145e74bbad86b347621`
- corrected real-reference preparer:
  `841279fe5a1467f6e8deaaa0e22c59c1c2828bb67f16d5f48ad42dd198f6e224`
- activation fixture/payload:
  `a5946ba6f07d4be7c13da28549a0585b90a4ca8fa3824f52d2afd0f0b582f5c8` /
  `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- boundary/scaffold/expert Tier-B:
  `0b28cc94522c52cc21df3bce72084d07bdd22f92bd21f5f0dd9775066e675a1a` /
  `52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38` /
  `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2`

## Payload identities

- gate packed / decoded:
  `3822822b98505bb0c0447174b1f53d984ca3b78e95e9e118d61e5de84fa2fdc3` /
  `849081eda002797cdf0aacee5dfddaeb4b7f9f08d18f51a2343ef079317a01db`
- up packed / decoded:
  `261011f1f3f084b6db48583711c14f20a9ae4e4e588b877b99db1aee0c2117af` /
  `4ceb3ddd33a2efa3b64857a44b92e1dfc3fe202c0eb26e18b2d18f4ac80a2d10`
- down packed / corrected decoded:
  `442acf3cf5210ade4faa0b38ef0f94aaca7b15571a180804ace52b94cccdf59d` /
  `f91987106198943c8a225b52dcf0099ba8f8b89d1ecad92c4a7c5c4964e20eae`

## Preflight, authorization, and mandatory stop

The canonical config-only launcher validated the exact v3 config from the
trusted detached root and returned exactly:

`READY_TO_EXECUTE_M1_E`

That preflight did not create attempt state, an oracle/package, checkpoint
payload access, tensor decode, MLX candidate state, or attempt evidence. The
next operator must re-run that same immutable-config preflight and production
admission before the single `EXECUTION_STARTED` transition.

This packet authorizes exactly one conceptual layer-3/expert-15 attempt,
exactly three bounded tensor payloads, 10 complete repeats, and exactly 30
native matvec dispatches. No threshold or bound artifact may change. No
automatic retry is authorized. Stop after the first attempt-2 result and do
not execute M1-F, another expert, a complete layer, logits,
P1/P2/golden-eight, or Feature 018 integration.
