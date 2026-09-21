# F017 Event-04 execution-readiness final review — Opus cycle 06

Use a fresh `claude-opus-5` session at high effort. This is the sixth and final
budgeted cycle. Review exact committed implementation and generated-authority
bytes at measurement head `5869bb436acc7fca4c1a4c1e2d5a774eb8d91f45`,
tree `66d40a03e8f134034896e3f339b2e345e6dd7987`. Implementation sources last
changed at `1dfaa5c9ff76c55e131b2a4d8cd69cc19b505ed9`; the measurement head also
contains their matching generated V9 manifest. FULL_NATIVE run `32826372881`
passed at `3593212b77894e32f0ba63038c3c87e7d3afbd23`: workspace
`97735223503`, pinned Apple MLX `97735223501`, aggregate `97739141908`, and
required native skips zero. Work read-only in a detached worktree. Do not
access original checkpoint payloads, mint or execute Event 04, or execute P1
attempt 2.

Reconstruct and attack cycle-05 `B-01-C05`, `N-01-C05`, and `N-02-C05`:

1. Confirm `_valid` distinguishes true `FileNotFoundError` absence from any
   existing-but-unreadable, redirected, malformed, or wrongly typed durable
   artifact. A real `PermissionError` must propagate to `_terminalize` as an
   unavailable observation; it must never become a successful zero.
2. Run both committed regressions with real permission-denied directories and
   real durable-start bytes. Neither test may replace `derive`, `_valid`, or
   `bank_runtime_artifact`. One case must exercise generic emergency fallback;
   the other must exercise a modeled post-package-start failure.
3. Require `accounting_derivation = UNAVAILABLE` with the source exception,
   a zeroed observation explicitly marked unavailable, conservative package
   terminal evidence for the generic case, and a modeled failure capsule in
   fallback for the modeled case.
4. Confirm degraded accounting does not enter delta equality validation, but
   still validates the modeled failed-transition and last-completed identities.
   No modeled failure may escape `_terminalize`.
5. Confirm a successful package cannot bank `COMPLETE` unless package, primary,
   and secondary durable-start evidence each derives delta 1.
6. Confirm the exact implementation measurement head contains the matching
   generated runtime manifest and all 38 bound paths, closing `D-01-C05`.

Re-run generator `--check`, all 45 pytest cases, the runtime authority
validator, exact-head 38-binding/30-closure measurement, full qualification,
and production-shaped no-access rehearsal. Then rerun the entire
execution-readiness attack: DID-01 through DID-12; idempotent release; dynamic
accounting; complete terminalization; 47/47 modeled failures over 201
executions with exact causal prefixes and no generic fallback; both consumers
materially using inherited descriptors for shards 2–6 with zero path reopen;
1,410 graph tensors and 399 non-access denials; all 11 formats; deterministic
evidence; enforced memory gates; independent C7-N2 checks; historical-worktree
cleanup; numerical contract V3; rehearsal; and exact-head CI.

Recompute unchanged numerical core and decoder SHAs. Verify original checkpoint
access zero, Event-04 authorization absent, Event-04 execution absent, P1
attempt 2 absent, attempts 1, retries 0, resume false, active generation NONE,
and historical ledger 175. Review all carried defense-in-depth findings and
state whether any becomes blocking or required. List each finding exactly once
as `BLOCKING`, `NON_BLOCKING_REQUIRED`, or `DEFENSE_IN_DEPTH` with a stable ID.
Both blocking and non-blocking-required prevent acceptance. State material
disagreement. End with exactly one unconditional verdict:
`ACCEPT_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_AUTHORIZATION`
or `REJECT`.
