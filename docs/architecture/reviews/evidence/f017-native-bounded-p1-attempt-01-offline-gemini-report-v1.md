# F017 Attempt-1 Offline Forensics Review

## Invocation Context
- **Mechanism**: AGY CLI
- **Model**: `gemini-3.1-pro-high`
- **Effort**: High
- **Branch**: `feat/017-rust-native-inference-runtime`
- **Head Reviewed**: `59538ccb15ae4d13e42e2ab91d790fbb295c5524` (Clean detached worktree)

## Independently Rerun Tests
The following verification tasks and test suites were independently executed at the offline implementation head, without any mutation to the repository or opening of the checkpoint payload:
- **Rust Native CI (`cargo test`)**: Executed entire workspace test suite, confirming all parser, tokenization, Apple Metal/MLX bindings, positional read logic, and telemetry validations passed.
- **Python Research Tests (`pytest scripts/research/tests/`)**:
  - `test_f017_q6_oracle_lane_order.py` and `test_f017_iq3_oracle_lane_order.py`: Mechanically verified the Q6_K lane-order and IQ3_XXS grid-order defects in the Python decoder semantics.
  - `test_audit_f017_native_checkpoint_plan.py`: Confirmed the 1,809 tensor metadata plan passes static assertions for duplicates, overlap, alignment, out-of-bounds, and architecture mismatch without opening the shard payload (`checkpoint_shard_opens == 0`).
  - `test_f017_native_synthetic_family_v1.py` & `test_f017_independent_oracle.py`: Validated 11-format case coverage and full-graph semantics independently.
  - `test_validate_f017_failure_evidence_v3.py`: Validated forward v3 failure injection evidence structure, token mismatches, and receipt/terminal closure.
- **CI Attempt 1 Evidence (`validate_f017_attempt1_evidence.py`)**: Confirmed attempt-1's terminal failure, expected token `21615`, produced token `17351`, zero receipt counts, and that attempt-2 is not authorized.

## Findings & Severities

1. **[BLOCKING] Defective Expected Token Oracle**: The expected token `21615` is conclusively defective. Independent test execution confirms the presence of Q6_K lane-order and IQ3_XXS grid-order defects in the F016 Python provenance semantics. This disproves `21615` as a valid oracle.
2. **[BLOCKING] Attempt 1 & 2 Status**: Attempt 1 is immutable, terminal, and not retryable. No checkpoint mutations or unauthorized inference occurred. Readiness for attempt 2 authorization remains `NO`.
3. **[NON_BLOCKING_REQUIRED] Causation Status (`ROOT_CAUSE_HIGH_CONFIDENCE_NOT_PROVEN`)**: While the expected oracle `21615` is proven defective, this does not intrinsically prove that the native attempt-1 output `17351` is the correct answer. The lack of attempt-1 layer fingerprints prevents absolute proof of causation.
4. **[DEFENSE_IN_DEPTH] Robust Evidence Logging**: Forward v3 execution correctly persists immutable accounting snapshots, access census logs, and receipt-bound terminal evidence for token mismatches without overwriting previous logs. The 1,809 tensor metadata audit is air-tight and correctly rejects misaligned offsets or duplicates.

## Material Disagreements
- **None**: All principal claims established in the review request have been mechanically reproduced and verified. The reasoning against assuming `17351` is correct purely based on the oracle's failure is sound.

## Verdict
**ADVISORY_CONCUR**
