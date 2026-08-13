# F017 M1-E Attempt 3 Authorization

**Status: AUTHORIZED FOR EXACTLY ONE M1-E ATTEMPT 3 / NOT EXECUTED**

Attempts 1 and 2 remain consumed and rejected. The original attempt-3 package
was not consumed: its preflight exposed `m1e_native_library_load` before any
checkpoint access. The loader remediation and subsequent identity-binding
correction are preserved in the append-only attempt ledger.

## Source, executable, and immutable config

- compiled runtime SHA: `7e4c3f37049444443164964aea2fc630752d17ce`
- tooling SHA: `7e4c3f37049444443164964aea2fc630752d17ce`
- authorization execution-head SHA:
  `2f196e9c3de2e8275e8e0844a42270a376d9c519`
- arm64 release executable SHA-256:
  `05e0e590eda9ea54d95d3bb7b59bdc9dbec9b3ea15e0cf4626ea13f46a7afa9a`
- trusted repository identity v2 SHA-256:
  `88faaf375d871a60462cbbddd5b27c186353d168eae2611b14cf485a24a78eaf`
- runtime-drift classification SHA-256:
  `4166ecb3d54d990a818d494b32684d182f7c3b94334b29086fc16ad6c4ff6558`
- execution-config schema: exactly `3.0.0`
- immutable execution-config SHA-256:
  `8213c5fa1c59900a0590977079d0d88f5b55d0faa30e2fa262430271bc3cef2a`
- handoff path:
  `docs/architecture/reviews/f017-m1-e-attempt-3-handoff.md`
- handoff SHA-256:
  `1dbe3c411528f8bb677fd26df662b54c378830c27407b05349292a995b33adf1`
- authorized launcher SHA-256:
  `c7be6fe622c94b05ee73c10b525f0ad891c0c286da53d184f1eb954760c5b158`
- updated real-reference preparer SHA-256:
  `f8e6f20d364d0c569875f841ec6edfc1e8e9f9997baa416b7eb8f1e409fe34e7`
- preparer-input contract SHA-256:
  `ad5768d026e5f6377e8243f4d01b50b416e50307d3bd1efd38ab437ba86709a5`

The launcher may construct its native loader environment only from the bound
production environment manifest and must verify both reviewed MLX dylib
hashes before starting preflight or candidate execution.

## Evidence and frozen expert boundary

- M1-E attempts 1/2 evidence:
  `346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119` /
  `8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00`
- M1-D accepted evidence:
  `dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c`
- expert: `blk.3.expert.15`
- tensor payloads: exactly gate/up/down; no router or fourth payload
- packed gate/up/down SHA-256:
  `3822822b98505bb0c0447174b1f53d984ca3b78e95e9e118d61e5de84fa2fdc3` /
  `261011f1f3f084b6db48583711c14f20a9ae4e4e588b877b99db1aee0c2117af` /
  `442acf3cf5210ade4faa0b38ef0f94aaca7b15571a180804ace52b94cccdf59d`
- decoded gate/up/down SHA-256:
  `849081eda002797cdf0aacee5dfddaeb4b7f9f08d18f51a2343ef079317a01db` /
  `4ceb3ddd33a2efa3b64857a44b92e1dfc3fe202c0eb26e18b2d18f4ac80a2d10` /
  `f91987106198943c8a225b52dcf0099ba8f8b89d1ecad92c4a7c5c4964e20eae`
- activation SHA-256:
  `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- decoder v2 SHA-256:
  `9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84`
- scaffold / Tier-B SHA-256:
  `52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38` /
  `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2`

## Execution boundary

The rebuilt config-only preflight returned exactly `READY_TO_EXECUTE_M1_E`
with zero checkpoint reads, decodes, oracle creation, native dispatches, or
attempt consumption. Exactly one conceptual expert, three reads totaling
11,304,960 compressed bytes, ten complete repeats, and thirty native matvec
dispatches are authorized. Automatic retry is forbidden under this numbered
attempt. Stop before M1-F, another expert, a layer, logits, P1/P2,
golden-eight, or Feature 018 integration.
