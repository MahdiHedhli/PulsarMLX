# F017 Event-04 execution-readiness final review — Opus cycle 05

Use a fresh `claude-opus-5` session at high effort. Review exact committed
implementation bytes at `a2a8d3bc06ecf142f2ed0c7727662516e6429ebd`, tree
`3d7c5b36098abda8486b31c7361aae8574770e1f`. The contract/evidence head is
`526d7054c693b2d3eb81d3cfa1843d610ff1938b`; its implementation descendants
are byte-identical to the measured implementation. FULL_NATIVE run
`32823480546` passed workspace (`97726458287`), pinned Apple MLX
(`97726458378`), and aggregate (`97729508318`) with required native skips zero.
Work read-only in a detached worktree. Do not access original checkpoint
payloads, mint or execute Event 04, or execute P1 attempt 2.

Reconstruct cycle-04 `B-01-C04` and attack the repair rather than trusting its
disposition:

1. Cause `Path.is_file()`, `Path.is_symlink()`, and `Path.read_bytes()` to raise
   `PermissionError` while runtime accounting derives durable starts. No raw
   filesystem exception may cross the accounting module boundary.
2. Cause accounting derivation itself to raise `PermissionError` inside
   `_terminalize`, make the primary terminal root unwriteable, and require the
   controlled capsule in the separately bound fallback root. Repeat for both
   emergency and state roots.
3. Confirm the result binds a zeroed accounting observation plus
   `accounting_derivation.result = UNAVAILABLE`, retains the source exception
   class, and never claims success or fabricates a durable start.
4. Confirm the exact regression appears twice in pytest and twice in the full
   qualification (`terminal_root_fault_cases = 2`), and that CI gates the
   counter.
5. Re-run generator `--check`, 45 pytest cases, the runtime authority validator,
   exact-head 38-binding/30-closure measurement, full qualification, and the
   production-shaped no-access rehearsal.

Then rerun the complete execution-readiness attack: DID-01 through DID-12;
idempotent release; dynamic accounting; complete terminalization; 47/47
modeled failures over 201 executions with exact causal prefixes and no generic
fallback; both consumers materially using inherited descriptors for shards
2–6 with zero path reopen; 1,410 graph tensors and 399 non-access denials; all
11 formats; deterministic evidence; enforced memory gates; independent C7-N2
checks; generator `--check`; historical-worktree cleanup; numerical contract
V3; production-shaped no-access rehearsal; and exact-head CI.

Recompute unchanged numerical core and decoder SHAs. Verify original checkpoint
access zero, Event-04 authorization absent, Event-04 execution absent, P1
attempt 2 absent, attempts 1, retries 0, resume false, active generation NONE,
and historical ledger 175. Review the cycle-04 defense-in-depth findings and
state whether any becomes blocking or required. List each finding exactly once
as `BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH` with a stable ID.
Both blocking and non-blocking-required prevent acceptance. State material
disagreement. End with exactly one unconditional verdict:
`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_AUTHORIZATION`
or `REJECT`.
