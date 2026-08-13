# F017 M1-F0 Attempt 1 Remediation Review

Attempt 1 is permanently `REJECTED / consumed`. It performed the exact twelve
bounded payload reads, decoded the allowlisted tensors, and completed ten
independent oracle computations. Before an oracle package or route could be
persisted, the evidence wrapper referenced a synthetic-route constant that was
not exported by the admission module. No expert computation, MLX dispatch, or
M1-F execution occurred.

The root cause is `EVIDENCE_VALIDATION`: the wrapper coupled a post-compute
substitution guard to another module's private constant surface. The fix owns
both forbidden route constants locally, asserts them in regression tests, and
does not alter the frozen oracle preparer, decoder, attention/router
arithmetic, selection contract, numerical contract, input, or access budget.

Attempt 2 is separately numbered and hash-binds the rejected attempt-1
evidence. Attempt 1 cannot be retried or relabeled.

Internal implementation review verdict:

`GO FOR NEXT M1-F0 ATTEMPT`

Independent-style adversarial delta review verdict:

`GO FOR NEXT M1-F0 ATTEMPT`

The review considered missing/renamed module constants, historical and
synthetic route substitution, config mutation, attempt-number reuse, and
ledger overwrite. The fixed guard is local and immutable; attempt 2 remains
limited to the same twelve tensors and zero expert/MLX computation.
