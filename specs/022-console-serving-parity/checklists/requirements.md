# Specification Quality Checklist: PulsarMLX Console Serving Parity

**Purpose**: Validate the completeness and quality of the feature specification before
planning, and record honestly where it does not meet a template criterion
**Created**: 2026-11-14
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] CHK001 No implementation details (languages, frameworks, APIs). Met with
  justification, following the precedent of `specs/001-apple-silicon-mlx/`, whose
  checklist limits implementation prescription to what the owner mandates. The owner's
  decision is itself implementation-shaped: a Rust rebuild in a nested workspace, HTTP/1.0
  with the connection closed after each response, outbound access only through the system
  `curl`, and a fixed automation layout. The specification states these where they are
  externally observable or bind scope (FR-007, FR-074, FR-088, FR-089) and leaves crate
  choices and internal structure to `plan.md` and `research.md`.
- [x] CHK002 Focused on user value and business needs. Each user story names the person who
  benefits (API client developer, operator, dashboard user, agent developer, Responses
  client, engine developer, maintainer) and why the slice matters.
- [x] CHK003 Written for non-technical stakeholders. Met with justification. The reader is
  the repository owner, a technical reader, and parity with a pinned donor can only be
  stated in terms of routes, streams, files and exit codes. The terms table at the top of
  the specification defines the vocabulary it relies on, and each user story states who
  benefits and why in plain terms.
- [x] CHK004 All mandatory sections completed. User Scenarios & Testing (nine stories and
  edge cases), Requirements (functional requirements and key entities), Success Criteria
  and Assumptions are present. A Scope Boundaries section (out of scope and open items) is
  added, following the precedent of `specs/001-apple-silicon-mlx/spec.md`.

## Requirement Completeness

- [x] CHK005 No `[NEEDS CLARIFICATION]` markers remain. Questions the plan recorded in ADR
  0008 does not decide are recorded as open items OI-1 to OI-13 in a table and referenced
  from the requirements they affect, so that no requirement decides them silently. Each
  row gives its id in the consolidated register in [analysis.md](analysis.md). None blocks
  planning; each names the milestone it must be settled before.
- [x] CHK006 Requirements are testable and unambiguous. Each requirement either states an
  observable rule or binds a capability to the donor's observable behavior at `7e68a30f`,
  which the ledger, the reference corpus and the re-expressed donor tests make checkable.
  The exact per-capability behaviors live in `tasks.md` and `contracts/`, not in the
  specification; a reader who needs them must read those files.
- [x] CHK007 Success criteria are measurable. Every criterion is a count, a 100% rule or a
  zero rule (for example SC-001, SC-003, SC-005, SC-012).
- [x] CHK008 Success criteria are technology-agnostic (no implementation details). They are
  stated in terms of routes, ledger rows, scenarios, signals, exit codes, files and
  supported platforms. SC-016 names the official OpenAI and Anthropic Python clients
  because those clients are the thing being checked, not an implementation choice.
- [x] CHK009 All acceptance scenarios are defined. Every user story has Given/When/Then
  scenarios.
- [x] CHK010 Edge cases are identified. They cover disconnects while queued and mid-stream,
  engine failures, exclusive operations, shutdown, transport limits, context overflow,
  large numbers, template errors, split tool calls, run-config round trips, legacy names,
  ablation, MiniMax vision, hostile attachments, missing telemetry and write failures.
- [x] CHK011 Scope is clearly bounded. The out-of-scope list names every exclusion the
  plan recorded in ADR 0008 makes (real models and engines, donor engine binaries, Phase
  2, the donor launcher and setup, the MiniMax picture preprocessor, the refusal-ablation
  switch, self-update, real catalog entries) plus the no-touch paths.
- [x] CHK012 Dependencies and assumptions identified. Assumptions cover the donor pin, the
  soft size estimates, platforms, toolchain, `curl`, Node.js as a test tool, the manual
  reference job, the archived serving crate and the engine track's review of the seam.

## Feature Readiness

- [x] CHK013 All functional requirements have clear acceptance criteria. Approved
  deviations (FR-090 to FR-106, and the requirements marked PLAN-1 to PLAN-6) and the
  governance requirements state their own criteria; FR-107 is the rule for later
  deviations. Parity requirements (FR-007 to FR-083) take the donor's observable behavior
  as the criterion, resolved row by row in the ledger. That is clear but indirect: the
  criterion for a given capability is only fully visible once its ledger rows and
  contracts exist.
- [x] CHK014 User scenarios cover primary flows. The nine stories cover the OpenAI and
  Anthropic dialects with tool calls, safe start and stop, the dashboard, the Responses API,
  MCP and attachments, model management and monitoring, the backend seam and the parity
  measurement.
- [x] CHK015 Feature meets measurable outcomes defined in Success Criteria. Not applicable
  at M0; checked as not applicable, not as met. Nothing is implemented at M0; the criteria
  can only be assessed as milestones complete, and fully at close-out (M10).
- [x] CHK016 No implementation details leak into specification. Within the limits
  explained under CHK001, the specification does not name crates, modules, internal types
  or file layouts beyond the fixed names the specification publishes (binary, prefix,
  directories, ledger, register and name table).

## Notes

- First checked on 2026-11-14 against the plan the owner approved that day (recorded in
  ADR 0008), the repository constitution and the template.
- Rerun on 2026-11-14 after `plan.md`, `contracts/` and `tasks.md` existed, and after the
  decisions taken since were applied to the specification: the eight ledger dispositions
  (FR-084), the manual-only shim run and vendor-template checks with their committed
  records checked in blocking automation (FR-089), the test-harness switch prefix
  (FR-045), the BRAND-2 font route and web manifest rules (FR-099), the submit-and-pump
  form for concurrent generations (FR-027), the merge-base comparison of the frozen root
  files (FR-088, SC-004), the registration of plan-decided differences as PLAN-1 to PLAN-6,
  and the consolidated open-item register. CHK001 and CHK003 are met with the
  justification stated inline; CHK015 is not applicable at M0. No item is left unchecked.
- Constitution principle III: the specification describes every capability as planned and
  bounds any later claim to "qualified on synthetic backends". No statement describes
  anything as working or measured. The specification's Constitution Compliance section
  summarizes every principle and points to the check in `plan.md`.
- Every deviation id in the plan's deviation table (SEC-1 to SEC-7, PRIV-1, BRAND-1,
  BRAND-2, LIC-1, LIC-2, POL-1, PLAT-1 to PLAT-3, FIX-1) appears as a requirement (FR-090 to
  FR-106). The differences the plan decides outside that table are registered as PLAN-1
  to PLAN-6 and marked on FR-004, FR-005, FR-078, FR-108, FR-054 and FR-074. FR-107 is the
  rule for later deviations: any further difference needs the owner's approval. Proposals
  that no approved id covers, such as P-5 (DeepSeek picture pixel values, FR-066), stay
  under "Proposed, awaiting owner decision" in the register and are not approved.
- Some proposals made during planning are overridden by the plan (legacy name aliases, a
  bundled template fallback, building the MiniMax preprocessor, porting the
  refusal-ablation switch, blocking the differential job). The specification follows the
  plan in each case.
- This checklist is rerun at each milestone report.
