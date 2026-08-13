# F017 M1-E Config-v3 Preparer Internal Review

**Verdict: GO FOR M1-E ATTEMPT 3**

## Reviewed delta

The review is limited to the M1-E independent-preparer/config compatibility
surface introduced after attempt 2. Runtime expert arithmetic, decoder v2,
activation bytes, scaffold semantics, and Tier-B semantics are unchanged.

- The preparer accepts exactly execution-config schema `3.0.0`; schema v2,
  future/unknown versions, missing or duplicate versions, mixed documents,
  and unknown execution-controlling fields fail before any payload open.
- Runtime/tooling/authorization/executable/ancestry fields are validated as
  identity inputs. `oracle_semantic_projection()` excludes them from every
  numerical oracle input.
- The preparer remains Python/NumPy-only and imports neither Rust FFI nor MLX;
  it consumes no candidate decoded matrices, stage outputs, or metrics.
- Decoder v2 and the corrected IQ3 identity remain directly bound. The
  historical defective down-decoded identity remains rejected.
- Attempt 3 binds both immutable rejected-attempt evidence hashes and cannot
  be confused with attempts 1 or 2.
- The immutable config SHA-256 is
  `ce451e77215b3d3f99e69e96e50af1a2f0d9b3d9b7bbe3435fcd64cbec53d9d5`.

## Implementation result

The config-only preflight returned exactly `READY_TO_EXECUTE_M1_E` and left
attempt 3 unconsumed. The canonical native synthetic integration used the
updated preparer, then completed one conceptual expert, 10 deterministic
repeats, and 30 native matvec dispatches with zero production
scaffold/reference/fallback/errors and reconciled lifecycle state.

