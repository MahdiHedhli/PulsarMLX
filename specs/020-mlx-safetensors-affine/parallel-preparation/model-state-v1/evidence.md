# Host evidence v1
Environment: Darwin 25.0.0 arm64, Python 3.14.7.
Exact commands: quickstart.md; both ordinary and -O unittest runs pass 16 tests
(0.224s and 0.230s in this observation). Full stdout/stderr and exit 0 receipts
are retained privately in attempt-02/host-results-03.json. Times are not performance claims.
Initial 14-test and 15-test runs passed. Independent review rejected the first
freeze: incomplete semantic config pins, conflated index/attention sparse state,
and overstated lease coverage. Repairs add exact semantic pins, separate sparse
roles/ownership and mutation tests, and explicitly documentation-only lease scope.
Both post-repair runs pass 16 tests; original review and provider failures retained.
No Rust/GPU/MLX/full-model checks run or claimed. real_reads=0, native_gpu_calls=0.

Scope: all new files confined to the three assigned prefixes. Source provenance
is source-pins.json; unchanged source/capsules are read as text, not executed.
Spec Kit prerequisite --paths-only succeeded without writing feature metadata.
Absent-file read errors and initial launcher failure remain preserved in audit.
Independent final verdict, exact capsule/source hashes and own-branch commit
are external receipts to avoid a self-referential reviewed source hash.
Integration awaits coordinator independent checks and storage/numerical adapters.

## Governance correction freeze cutoff
Cutoff: this documentation-only revision addressing coordinator finding
`model-state-governance-001`, after prior accepted commit
`8e1e6d21d982d09cec2f0f606ee559177e0a8455` and before its new independent review
or documentation commit. Only spec.md, tasks.md and this history change.
The accepted functional source, fixtures, tests, reference pins and frozen
integration contract remain unchanged; retained 16-test normal/optimized results
apply to those exact functional hashes. No new numerical test result is claimed.

Private audit root: `PulsarMLX-handoff/20261004-parallel-preparation/model-state/`.
The following attempt-02 evidence remains preserved, not superseded or rewritten:

1. `review-01.stdout.json`: provider/authentication failure before inference,
   empty modelUsage; no verdict.
2. `review-02.stdout.json`: actual claude-opus-5-5 REJECT for config semantic
   pins, sparse operand/state separation and overstated lease validation.
3. Those findings were repaired; `review-03.stdout.json` returned terminal
   ACCEPT/0, process exit 0, actual modelUsage claude-opus-5-5. Accepted source
   manifest SHA256: `6800e86d4dea8415cb460a66a9d3816b6b2bc5095d246a8abd5c5451e9ee901c`.
   Accepted capsule SHA256: `0e0c7e7c6d99d12f233e7bb49f742d870d2a36096183cf7d3195441ce1c0cf2a`.
4. Coordinator subsequently found missing explicit compliance checks in spec,
   tasks and the commit message under Constitution Governance lines 166–168.
   That additional finding withholds final readiness; it is not a provider
   rejection of the previously accepted package.

At this cutoff no verdict for the revised documentation is claimed. New exact
source/capsule hashes, unchanged functional hashes, the explicit review compliance
check and terminal ACCEPT/0, and the documentation commit with its own compliance
check/citation will be recorded in attempt-03. Coordinator must reverify final
ownership, hashes and compliance before readiness; integration approval remains
separate. Production limitations and real_reads=0/native_gpu_calls=0 are unchanged.
