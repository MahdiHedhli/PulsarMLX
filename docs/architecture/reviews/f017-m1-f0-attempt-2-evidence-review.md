# F017 M1-F0 Attempt 2 Evidence Review

Verdict: `M1-F0 ATTEMPT 2 ACCEPTED`

Attempt 2 consumed exactly one authorization and read the exact 12-tensor
layer-3 attention/router allowlist: one shard open, 12 positional reads,
139,217,920 compressed bytes, and 666,430,464 decoded bytes. Expert payloads,
expert dispatches, MLX candidate dispatches, M1-F execution, and route
substitution were all zero/false.

The independent oracle package SHA-256 is
`ad4ab9d8f1c40e5bf8886ed404f1e07115560c10c53226dcc5497d8b6785388f`.
All ten repeats reproduced identical attention output, attention residual,
router input, router scores, ranking, selected-ID bytes, and routing-weight
bytes. Numerical qualification is `PASS`, non-finite count is zero, signed-zero
policy passes, and no post-observation retuning occurred.

The selected IDs are `[166, 78, 26, 186, 163, 199, 233, 177]` with ID-byte
SHA-256 `44eb8597e56fe57ef3c045dfa979e80f76e85afd053c89b48653244525cf41ca`.
Routing-weight SHA-256 is
`e1e419537136ffb660775732aa2bfb17a6b16a941b2fbacb775aff0d77d9fd18`.
The route is neither the forbidden historical route nor the synthetic fixture.

Public accepted evidence SHA-256:
`0eb0030f0345b8b2cabca4b7e690177603ca29e21b0cfade3e0639e356d1b8f9`.
Route artifact SHA-256:
`980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e`.

Attempt 1 remains immutable and rejected with evidence SHA-256
`72deffb9d1baffa2378aca18662209a9a49f5da1709c1125f6d662c3af202244`.
The append-only ledger records 24 route-discovery payload reads across both
attempts plus the earlier single-payload Q5_K qualification, for 25 cumulative
checkpoint payload reads.

M1-F is `PREPARED / NOT AUTHORIZED` and was not executed.
