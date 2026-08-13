# F017 M1-E Attempt 3 Evidence Review

**Verdict: M1-E ATTEMPT 3 ACCEPTED**

## Immutable admission

The accepted execution used compiled runtime and tooling
`7e4c3f37049444443164964aea2fc630752d17ce`, authorization execution head
`2f196e9c3de2e8275e8e0844a42270a376d9c519`, arm64 release executable
`05e0e590eda9ea54d95d3bb7b59bdc9dbec9b3ea15e0cf4626ea13f46a7afa9a`,
and immutable config
`8213c5fa1c59900a0590977079d0d88f5b55d0faa30e2fa262430271bc3cef2a`.
The exact-head qualification gate was Apple-native CI run `31720986490` at
repository head `541da1abdbb1767fba9917894adb07c9c93d0ab1`.

The final non-consuming preflight returned exactly `READY_TO_EXECUTE_M1_E`.
Measured-host admission passed on arm64 with 128 GiB physical memory, normal
memory pressure and thermal state, safe swap/storage, no competing inference,
and no port-1234 listener. Loaded `libmlx.dylib` and `libmlxc.dylib` hashes
matched their reviewed arm64 identities.

Attempts 1 and 2 remain immutable under evidence SHA-256
`346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119`
and `8912e523963cfa8822fe6472ec30be31a78c4c3648fba34caf6c41055efd7e00`.

## Bounded tensor and oracle evidence

One shard was opened and exactly three positional reads consumed 11,304,960
compressed bytes. No fourth payload was accessed.

| Role | Packed SHA-256 | Decoded-f32 SHA-256 |
|---|---|---|
| gate | `3822822b98505bb0c0447174b1f53d984ca3b78e95e9e118d61e5de84fa2fdc3` | `849081eda002797cdf0aacee5dfddaeb4b7f9f08d18f51a2343ef079317a01db` |
| up | `261011f1f3f084b6db48583711c14f20a9ae4e4e588b877b99db1aee0c2117af` | `4ceb3ddd33a2efa3b64857a44b92e1dfc3fe202c0eb26e18b2d18f4ac80a2d10` |
| down | `442acf3cf5210ade4faa0b38ef0f94aaca7b15571a180804ace52b94cccdf59d` | `f91987106198943c8a225b52dcf0099ba8f8b89d1ecad92c4a7c5c4964e20eae` |

The independent oracle finalized before candidate start and remained
immutable through teardown. Its package SHA-256 is
`e500f0f9edca67ae42b3302bdb4105ded044a8b42c755aa58abee9af7302dbff`.
The gate/up/activated-hidden/final reference hashes are respectively
`c81dda8c2127ab694981b447df4dd7f15eb23ca2257af021fbb8776342215ec9`,
`808988d579fd1e77fd8c45c2fbb5cc79a58260de5f79f7e867833b5a156782ed`,
`8f4414e53c027b18f704ef41b9b08b5c9272e31e5877371608baeb78d79f9fbd`,
and `ae1fa8e468418c8f0103a772ba4cf1380ed587435ace37d527642f8f0cda5213`.
The final bound-vector SHA-256 is
`05273dc57a7c8822f0cbf988d465debf1f4010004cd10299ff6e607f9ac6a3d4`.

## Repeat, numerical, dispatch, and lifecycle qualification

All ten ordinals recorded the same stage hashes:

- gate: `49334bc8ae7b1a7892f86c95ca85c727b6d21433abf36f374369ec5f096c461b`
- up: `4dff8d00be17389219bc3f7e32cf8487bca531a9d79d2d2543aa3f7a261234c4`
- activated hidden: `7aa9cbb88b46c54d797067adfa7e8edaa0a026d465ccfbd7d1dbe35b0e57a7af`
- final output: `289dbc1db4d25784b26b5255fc9f0da592c86df089325a0b33a7e6c99a43d10f`

| Boundary | Max absolute error | RMSE | Cosine similarity | Result |
|---|---:|---:|---:|---|
| gate | 0.00002765655517578125 | 0.000004637053632521214 | 0.9999999999982905 | PASS |
| up | 0.000031948089599609375 | 0.000004633751186784073 | 0.9999999999982029 | PASS |
| activated hidden | 0.000225067138671875 | 0.000017116376208529363 | 0.9999999999966809 | PASS |
| final output | 0.000053882598876953125 | 0.000013008547444591869 | 0.9999999999963376 | PASS |

Signed-zero mismatches were zero at every boundary. Classification is exactly
`numerically_qualified_greedy_not_applicable` and greedy applicability is
`not_applicable`.

Dispatch accounting is 10 gate + 10 up + 10 down = 30 native matvecs.
Qualification-scaffold, explicit-reference, fallback, and backend-error counts
are all zero. There was one conceptual expert, zero complete layers, zero
logits, and no router, second/shared expert, P1/P2, golden-eight, or Feature
018 execution.

Lifecycle reconciled: managed `14/14`, derived `30/30`, default CPU streams
`1/1`, owned streams `1/1`, zero active contexts, and singleton inactive.

## Evidence disposition

The banked public-safe artifact is
`docs/architecture/reviews/evidence/f017-m1-e-real-expert-attempt-3-v1.json`
with SHA-256
`0f85ee81205836a492a9dd44d71e56dc6ce46b22a5064f51c5f37dd561f292a9`.
It is byte-identical to the canonical private runner evidence, contains no
private absolute path, and passes the dedicated fail-closed validator,
duplicate-key parsing, repeat/oracle-order re-derivation, and lifecycle checks.

M1-F is now meaningful and is prepared separately as `PREPARED / NOT
AUTHORIZED`. It was not executed.
