# F017 M1-E Attempt 3 Authorization

**Status: AUTHORIZED FOR EXACTLY ONE M1-E ATTEMPT 3 / NOT EXECUTED**

This is a fresh authorization. Attempts 1 and 2 are consumed and rejected;
neither is retried or relabeled by this packet.

## Source, executable, and config binding

- compiled runtime SHA: `71476f0d469214c96d803ce4917c43c4562a7183`
- tooling SHA: `71476f0d469214c96d803ce4917c43c4562a7183`
- authorization execution-head SHA:
  `32377ed50d25ba09b7147d1789b8f926ecebfe39`
- arm64 release executable SHA-256:
  `9dc126e7391e1d0e2a87883c269792eeff41b72827fb6848066b128e963c350b`
- trusted repository identity v2 SHA-256:
  `88faaf375d871a60462cbbddd5b27c186353d168eae2611b14cf485a24a78eaf`
- runtime-drift classification SHA-256:
  `fe757dde688c9e5e33012df306ed70b2b11d5f82e2c90c90dc736f546c7046dc`
- execution-config schema: exactly `3.0.0`
- immutable execution-config SHA-256:
  `ce451e77215b3d3f99e69e96e50af1a2f0d9b3d9b7bbe3435fcd64cbec53d9d5`
- handoff path:
  `docs/architecture/reviews/f017-m1-e-attempt-3-handoff.md`
- handoff SHA-256:
  `ed13318ab7d86e26c035740265039beacc694f1c009323136ee8b17b19b6f901`
- updated real-reference preparer SHA-256:
  `f8e6f20d364d0c569875f841ec6edfc1e8e9f9997baa416b7eb8f1e409fe34e7`
- preparer-input contract SHA-256:
  `ad5768d026e5f6377e8243f4d01b50b416e50307d3bd1efd38ab437ba86709a5`

## Evidence and model binding

- M1-E attempts 1/2 evidence:
  `346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119` /
  `8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00`
- M1-A/B/C/D evidence:
  `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805` /
  `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770` /
  `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e` /
  `dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c`
- checkpoint/catalog/map:
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee` /
  `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0` /
  `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`
- expert: `blk.3.expert.15`; exactly gate/up/down payloads
- activation payload SHA-256:
  `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- decoder v2 SHA-256:
  `9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84`
- scaffold / Tier-B SHA-256:
  `52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38` /
  `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2`
- packed gate/up/down SHA-256:
  `3822822b98505bb0c0447174b1f53d984ca3b78e95e9e118d61e5de84fa2fdc3` /
  `261011f1f3f084b6db48583711c14f20a9ae4e4e588b877b99db1aee0c2117af` /
  `442acf3cf5210ade4faa0b38ef0f94aaca7b15571a180804ace52b94cccdf59d`
- decoded gate/up/down SHA-256:
  `849081eda002797cdf0aacee5dfddaeb4b7f9f08d18f51a2343ef079317a01db` /
  `4ceb3ddd33a2efa3b64857a44b92e1dfc3fe202c0eb26e18b2d18f4ac80a2d10` /
  `f91987106198943c8a225b52dcf0099ba8f8b89d1ecad92c4a7c5c4964e20eae`

## One-attempt boundary

The canonical config-only preflight returned exactly
`READY_TO_EXECUTE_M1_E` with zero checkpoint reads, tensor decodes, oracle
creation, MLX contexts/dispatches, or attempt consumption. Execution is
authorized for one conceptual expert, three bounded payloads, 10 complete
repeats, and exactly 30 native matvec dispatches. No loose CLI overrides,
threshold changes, or automatic retry are authorized. Stop after the first
attempt-3 result and before M1-F, another expert, a layer, logits,
P1/P2/golden-eight, or Feature 018 integration.

