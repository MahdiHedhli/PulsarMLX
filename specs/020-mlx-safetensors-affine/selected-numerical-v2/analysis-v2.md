# Cross-artifact analysis v2, pre-implementation

Read-only analysis performed after setup-tasks/check-prerequisites; recorded
here after analysis. No extension hooks file. Sole-worker user constraint
supersedes skill parallel examples. Routine remediation already authorized.

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| A1 | HIGH | Initial bias t/2-15/128 not BF16 exact for large targets | Before generation changed prospective population to s=1/16,b=t/2-15/32 (signed equivalent B); exact representation test required |
| A2 | MEDIUM | Input low-bit cancellation cannot witness arbitrary packing permutation | Explicit independent packed-code witness required; real coverage claim limited |
| A3 | HIGH execution gate | Resource enforcement/measurements not implemented | T009 blocks T010 execution capability; no memory/qualification claim |

Coverage: FR01 T004/T010; FR02 T004/T005/T011; FR03 T005/T007/T012;
FR04 T006/T008; FR05 T007; FR06 T008; FR07 T009; FR08 T010;
FR09 T011/T012; FR10 T013; SC01 T012; SC02 T011/T012.
12/12 requirements/success criteria mapped, 13 tasks, no unmapped tasks.
No constitution conflict after A1 remediation; accepted source/proof artifacts
unchanged. No critical design gap for host generation/proof. Native capability
remains blocked by unimplemented tasks and exact-version review, not user permission.

## Implementation cross-artifact check before final review

The 39 IDs are materialized as two full-shape positives, 24 host refusals/guards
and 13 mutations (seven native, six host). Existing 363/32 regression schemas
are checked separately before new synthetic execution. A3 now has an explicit
allocation ledger, 64 MiB native allocator acceptance cap, 256 MiB reference
peak-RSS cap, 1 GiB inclusive native peak-RSS cap and sampled owned watchdog.
No instantaneous global RAM limit or measured compliance is claimed.
Selected adapter/entry/core/resource code is linked and compiles with pinned
native dependencies. Independent Rust/Python authority parsers require actual
final review; preliminary ACCEPT/0 cannot issue execution. All original real
snapshot reads and selected numerical observations remain zero.
Source-only validation: 28 Python tests; 7 Rust snapshot/preflight tests;
4 Rust review-authority tests; 1 selected C++ ownership-stub test; scoped
Clippy PASS. Workspace formatting check detects existing unrelated formatting
and is not a source-change mandate; changed Rust files formatted separately.
T010 final build/source review and T011/T012 execution remain open gates.

Final review 01 found B1 vacuous packing witness and B2 out-directory-only once guard. Both are execution blockers; no numerical observation occurred. Remediation above is prospective, keeps input/tolerances unchanged, and requires another exact review.

## Contract v3 framing continuation

See [framing-correction-v3.md](framing-correction-v3.md) and [contract v3](contracts/selected-numerical-v3.json). The real header refusal is retained; no packed real bytes or real numerical observations occurred. T004/T006/T010/T011/T012 reopen for the strict scope-field correction and41-case population. Numerical definitions and inputv2 are unchanged. No constitution conflict: original writer/artifacts and failed ledger preserved, no admission relaxation or claim from metadata.

## Observed contract v3 boundary

Source d9639737 passed exact review04 ACCEPT/0, full41+363/32 synthetic
qualification and requiredCI37184777213. The original selected-byte R1 attempt
then refused the unchanged prospective down nonzero-floor margin. Native real
execution did not occur; complete real expert numerical qualification remains
unmet. See [sanitized evidence](qualification.json). Preserve the refusal and
all prior attempts; do not retune input/budgets or relabel it as a native failure.
