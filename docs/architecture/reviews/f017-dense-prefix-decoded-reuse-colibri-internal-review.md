# F017 Dense-Prefix, Decoded-Reuse, and Colibrì Internal Review

## Review surface

The review covered provenance repair, the seven-use-case decoded-reuse matrix,
the pinned external-source audit, dense-prefix minimality and P-MIN lineage,
the independently reconstructed 40-tensor inventory and byte budgets, Q4_K and
Q6_K qualification packages, source-backed residency, the independent oracle,
typed config/evidence/attempt schemas, private hidden-state retention, the
representative M1-F0 handoff, and M1-F/M1-G/P1 non-authorizing scaffolds.

## Findings

- The reviewed baseline `8031020f...` is an ancestor of the carried-forward
  implementation head; stale `dd52d38` remains non-authoritative.
- Reuse is safe only under a mixed, use-case-specific policy. Candidate gates
  do not inherit oracle decode/import coverage.
- Colibrì is pinned, hash-bound, Apache-2.0, and non-copied. Its custom formats
  are not GGUF decoder oracles.
- Independent regressions cover near-tie thresholds, f32 accumulation order,
  top-2 analytical retention, silent no-work accounting, and memory lifetime.
- Layers 0–2 remain dense. The P-MIN token-9703 input is pre-existing and
  anti-cherry-picking. The exact inventory remains 40 tensors.
- Q4_K and Q6_K each have a deterministic one-payload qualification package;
  neither is real-byte qualified yet.
- The 27-GiB floor is contract-derived and conservative; aggregate decoded
  volume is not presented as peak residency.
- The NumPy oracle and retained hidden-state contracts are prepared, independent,
  and fail closed. No real gate is authorized.

No historical evidence was rewritten, no false-PASS path was found, and the
real-payload ledger remains 57.

## Verdict

`GO FOR DENSE-PREFIX PACKAGE ADVERSARIAL REVIEW`
