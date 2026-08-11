# Feature 017 R7 original mismatch

## Status

The first checkpoint-free production-MLX complete-expert experiment remains a
numerical/behavioral failure under the frozen exact-f32 contract. This note
preserves the observation; it does not regenerate the independent fixture or
reclassify the candidate.

The original raw failure artifact hashes to
`191504851fd3ef8be04d78f91fab0be30db83117ee0c8b25a880736209e00f80`.
It was produced from source `366d3cd6c2f5379ad374ab88d2e4ae0760396f6`
with an experimental dirty worktree and no checkpoint access.

## Frozen identities

- Fixture: `glm52-runtime-expert-q8-0-v2`
- Fixture SHA-256:
  `16ca1e412dbf98d59e19b685b86549567de043ea7e728b254a952540aa783960`
- Independent generator Git SHA:
  `a9779097de029f26be1cb9fde3543cc517ff153e`
- Independent generator source SHA-256:
  `cf6a90f310bf048d2752156ba71cddb6d8a179ce1fed17b4a5831de8412e297e`
- Contract: exact f32 bits, `atol = 0`, `rtol = 0`

The activation and gate/up/down packed tensor hashes are recorded in
`f017-r7-original-mismatch-v1.json`. The expected gate, up, activated-hidden,
and final-output hashes remain those in the independent oracle.

## First retained divergence

| Field | Oracle | Production MLX candidate |
| --- | ---: | ---: |
| Complete-expert output index | 0 | 0 |
| f32 value | 427908.5 | 427909.0 |
| f32 bits | `0x48d0f090` | `0x48d0f0a0` |

- Absolute error: `0.5`
- Relative error: `1.1684741013557804e-6`
- Classification: `FAIL_NUMERICAL_BEHAVIORAL`
- First known divergent boundary: complete-expert final output
- Cause: unattributed

The original artifact retained only the first observed candidate element, so
this note does not claim a complete candidate vector or an earlier divergent
intermediate. Those must be measured only after the exact qualification
scaffold is proven.

## Non-actions

- The independent oracle was not edited.
- The failing fixture was not regenerated.
- No tolerance was introduced or changed.
- The production expert was not re-executed while creating this record.
- R8 remains blocked.
