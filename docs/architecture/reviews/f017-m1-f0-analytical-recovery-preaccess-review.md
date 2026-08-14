# F017 M1-F0 analytical recovery pre-access review

Status: **GO FOR ONE ACCEPTED-BOUNDARY EVIDENCE RECOVERY**

This review freezes the recovery mechanics and the route-stability rule before
the omitted rank-8/rank-9 values are observed. It does not authorize a new
route, a new input, expert computation, Q6_K qualification, or M1-F.

## Accepted identity reconciliation

- accepted M1-F0 final head: `df0f3a91244d944f0fe5a0f569b709ccfe631cc0`
- route artifact SHA-256: `980b6a78ae04b816e1f9e563790f5a2d123723292dd0432a0218972d0f80593e`
- accepted attempt-2 evidence SHA-256: `0eb0030f0345b8b2cabca4b7e690177603ca29e21b0cfade3e0639e356d1b8f9`
- accepted ranking SHA-256: `6a878c1db20997b16cff8efdb8659543c07974dcddd718957243c889d78a2ede`
- router-score SHA-256: `3b4ff6cac287f53004c7cc6ceedb13f2403a6ce4426e30155005158e0e004dc4`
- selected-ID SHA-256: `44eb8597e56fe57ef3c045dfa979e80f76e85afd053c89b48653244525cf41ca`
- routing-weight SHA-256: `e1e419537136ffb660775732aa2bfb17a6b16a941b2fbacb775aff0d77d9fd18`

The accepted 12-tensor allowlist, 139,217,920 compressed-byte budget,
666,430,464 decoded-byte budget, input package, decoder contracts, Q5_K
qualification, scaffold, selection contract, and numerical contract are taken
directly from the immutable attempt-2 execution config and evidence.

## Cumulative payload ledger before recovery

| event | payloads | immutable evidence |
|---|---:|---|
| Q5_K real-byte qualification | 1 | `13899cdd1d97c65ca0c6cf0ce24cb9fae26e7c1c0d4036ec7c00529af00bc39c` |
| M1-F0 attempt 1, rejected | 12 | `72deffb9d1baffa2378aca18662209a9a49f5da1709c1125f6d662c3af202244` |
| M1-F0 attempt 2, accepted | 12 | `0eb0030f0345b8b2cabca4b7e690177603ca29e21b0cfade3e0639e356d1b8f9` |
| total before recovery | **25** | reconciled |

Metadata/header reads are not tensor-payload reads. A successful recovery adds
exactly 12 payloads and therefore produces a cumulative count of 37.

## Frozen recovery gate

The recovery runner:

1. validates the immutable recovery config and separate authorization;
2. validates every accepted artifact and contract hash;
3. creates an exclusive `RECOVERY_STARTED` marker;
4. opens one accepted shard and reads exactly the accepted twelve ranges once;
5. verifies all packed and decoded identities;
6. executes the unchanged independent NumPy oracle once under instrumentation;
7. compares all seven accepted computation identities and the selected IDs;
8. exposes analytical values only after exact identity passes;
9. writes canonical LE f32/f64/u16 artifacts and componentwise score bounds;
10. refuses to overwrite either the start marker or output package.

An accepted hash mismatch is an immediate hard stop. No altered-arithmetic
rerun is allowed.

## Stability rule frozen before observation

The versioned route-stability contract derives componentwise candidate error
through the position-zero value path, attention residual, router normalization,
router projection, sigmoid, and bias addition. It requires:

`margin > B8 + B9`

and a predeclared safety factor of at least 4.0. A factor below 4.0 is not
admitted even if the strict non-overlap inequality happens to hold. No score or
rank-9 value was available when this rule was written.

## Independence and scope

The runner imports the accepted Python/NumPy preparer only. It does not import
Rust, FFI, MLX, candidate outputs, or Feature 018. Instrumentation observes the
accepted oracle's own calls without changing their operands or arithmetic.
Q/K score errors do not propagate into the position-zero value branch because
the sole visible attention weight is exactly one, as already frozen by the
M1-F0 numerical contract.

Verdict: **GO FOR ONE ACCEPTED-BOUNDARY EVIDENCE RECOVERY**
