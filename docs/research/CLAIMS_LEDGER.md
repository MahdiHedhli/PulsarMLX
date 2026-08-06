# Feature 002 Claims Ledger

**Status**: The independent CPU oracle support package is frozen, with zero
public Feature 002 claims. Two external Apple MLX producer attempts executed
the bounded real router but failed closed before independent evidence
admission; no router capability has been promoted.

There are zero public Feature 002 capability or performance claims. The table
below intentionally has no data rows. A row may be added only when its status
and evidence satisfy the
[Feature 002 evidence contract](../../specs/002-qwen-router-parity/contracts/research-evidence-v1.md).

Each future row must use a stable `F002-CNN` identifier, link committed
machine-readable evidence by repository-relative path, name the full clean
measured source commit and exact checkpoint/tensor/case/depth scope, use one of
`verified`, `provisional`, `rejected`, or `unsupported`, and include a nonempty
caveat. `verified` additionally requires clean-checkout reproduction, artifact
hashes, and package verification.

Future IDs use exactly two decimal digits. Evidence links use
`raw/002-router-parity/<experiment-id>.json` without parent traversal. Scope is
written as
`checkpoint=<repository>@<revision>;tensor=<name>;case=<id>;depth=<operation>`,
and the full commit must match the linked raw record.

`provisional` requires a passing linked raw record but lacks some package-level
promotion proof. `verified` additionally requires passing exact-scope
correctness, at least two matching clean reproduction records with distinct
process identities, identical model/tensor/input/oracle/output identity,
committed artifact hashes, clean-checkout reproduction, and no
`real_checkpoint_routing` exclusion. `rejected` retains and links a nonpassing
outcome that contradicts the proposed statement. `unsupported` identifies an
interpretation outside the evidence scope.

The synthetic fixture record's internal provisional boundary is not a public
claim, and its constructed failed and aborted records are not observed model
failures. The frozen CPU-oracle support record is an immutable reference input
and output, not Apple execution or parity evidence. These artifacts validate a
zero-row ledger but cannot promote a claim. Repaired, repeated, failed, and
aborted work receives a new experiment ID; linked raw history is never
rewritten or deleted.

| Claim | Evidence files | Commit | Scope | Status | Caveat |
| --- | --- | --- | --- | --- | --- |
