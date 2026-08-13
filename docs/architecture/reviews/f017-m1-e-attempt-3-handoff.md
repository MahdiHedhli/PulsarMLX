# F017 M1-E Attempt 3 Handoff

**Status: PREPARED AFTER LOADER REMEDIATION / NOT AUTHORIZED / NOT EXECUTED**

## Published source and preparer identities

- compiled runtime SHA:
  `7e4c3f37049444443164964aea2fc630752d17ce`
- execution-tooling SHA:
  `1da693665e5635ad404d472f395a4a407dd348fc`
- arm64 release executable SHA-256:
  `05e0e590eda9ea54d95d3bb7b59bdc9dbec9b3ea15e0cf4626ea13f46a7afa9a`
- trusted repository identity contract:
  `f017-trusted-repository-identity-v2` /
  `88faaf375d871a60462cbbddd5b27c186353d168eae2611b14cf485a24a78eaf`
- updated independent preparer SHA-256:
  `f8e6f20d364d0c569875f841ec6edfc1e8e9f9997baa416b7eb8f1e409fe34e7`
- preparer input contract SHA-256:
  `ad5768d026e5f6377e8243f4d01b50b416e50307d3bd1efd38ab437ba86709a5`
- execution-config schema 3.0.0 SHA-256:
  `e940bd33d1c772b4ad88d869ea90464095f7d6c729a2dd53fc5171b5fbd3a0f7`

The immutable config must bind an exact later authorization head that is a
reviewed docs/reviews/evidence-only descendant of the compiled runtime. All
execution-controlling artifacts remain directly content-hash bound.

The canonical launcher must also derive its dyld library directory only from
the bound production environment manifest and verify both reviewed dylib
hashes before launching either preflight or candidate execution.

## Immutable scope

- attempt: `3`
- execution-config schema: `3.0.0`
- preparer input contract: `f017-m1e-real-reference-preparer-input-v3`
- expert: `blk.3.expert.15`
- conceptual expert count: `1`
- tensor payload count: `3` (`gate`, `up`, `down` only)
- complete production repeats: `10`
- expected native matvec dispatches: `30`
- automatic retry: `false`
- mandatory stop: before M1-F

Attempts 1 and 2 remain consumed and rejected under evidence SHA-256
`346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119`
and `8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00`.

## Numerical continuity

- decoder contract v2:
  `9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84`
- activation payload:
  `732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149`
- exact scaffold:
  `52472419faec0f88a5e8c3e289fc106aee76cffe3feee13631a56d23f8ad4e38`
- expert Tier-B:
  `44168eb92df8c3da81feeb024e7f5d57cd501ce43e2271294f41c25489a087e2`
- corrected final oracle:
  `ae1fa8e468418c8f0103a772ba4cf1380ed587435ace37d527642f8f0cda5213`
- corrected final bound vector:
  `05273dc57a7c8822f0cbf988d465debf1f4010004cd10299ff6e607f9ac6a3d4`

No threshold, decoder, expert, activation, scaffold, or Tier-B semantic may
change as part of the schema-v3 preparer remediation.
