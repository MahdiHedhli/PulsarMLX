# Plan v1
Python 3 stdlib only, bounded host unittest; no install, runtime backend or storage.

## Constitution gates
Correctness first: independent scalar oracle, prospective tolerance, mutation
controls. Claims limited to synthetic contracts; no performance statement.
Preserve Linux/CUDA by isolated additive files (cross-platform runtime unverified).
No Rust changes: workspace Cargo/GPU tests excluded under explicit host-only
scope. Attribution retained via references and source hashes; no weights copied.
No custom kernel or MLX execution. Spec, plan, tasks, analysis precede code.
Pre-design and post-design gates: PASS for bounded preparation only.

## Workflow adaptation
User explicitly selects this nested owned directory. Spec Kit setup/normal
prerequisite scripts persist .specify/feature.json; do not run those mutations.
Use equivalent manual artifacts and read-only prerequisite paths check. No
extensions.yml or AGENTS.md found. No agents spawned. This is an ownership
adaptation, not a constitution or quality waiver.

## Research and design
See research.md, data-model.md, interface-v1.md, tensor-role-coverage-v1.md.
Implement independent fixture generator and oracle first, then a bounded state
harness using the retained stdlib candidate only for numerical primitives.
The oracle imports no implementation helpers; recomputes from full chronological
history and value-major state. Candidate uses incremental suffix/cache state.
Full text-model graph is specified, not executed at checkpoint geometry. Tiny
boundary computations exercise embedding/head, routing/MLP and mHC separately
from preprojected attention-state fixtures; no full-model parity claim.

## Phases
1. Pin read-only source/config and agree interface and coverage.
2. Bank independent deterministic fixture definitions and oracle.
3. Implement state harness and semantic probes, targeted tests and mutations.
4. Inspect scope, validate, freeze source/capsule, independent review and repairs.
5. Exact own-branch commit and private handoff for coordinator, no integration.

Bounds: one head, key=2, value=3, kernel=3, seven projected channels,
<=8 tokens/context, <=4 layers per executable request, <=2 contexts in tests;
full topology is metadata-only. Sparse pool=2/topk=2 (actual config 4/2048).
Request commit copies bounded state atomically; outputs unpublished until commit.
