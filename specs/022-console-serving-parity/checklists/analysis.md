# Cross-Artifact Analysis Checklist: PulsarMLX Console Serving Parity

**Purpose**: Record the cross-artifact analysis that the constitution requires before
implementation, and hold the single register of open items for this feature
**Created**: 2026-11-14
**Feature**: [spec.md](../spec.md)

**Note**: This checklist is written by hand. It stands in for the `$speckit-analyze`
command, as plan exception E5 in [plan.md](../plan.md#constitution-exceptions) records. It
analyzes the M0 files as they stand on 2026-11-14, after the review pass, the fix pass and
the polish pass that applied lead decisions LD17 to LD27 (section 3), on branch
`feat/022-console-serving-parity` (cut from `main` at `aaf076f1`), with the M0 change set
still uncommitted. Nothing in this increment is implemented. Every result below is about
documents, the empty workspace skeleton and three check scripts; none of it is evidence
that any console behavior works. It is re-recorded whenever `tasks.md` or a contract
changes materially, and at each milestone report.

## 1. Summary verdict

**The artifacts are consistent enough to go to owner checkpoint 1, and to start M1 after
that checkpoint, provided the items listed below are settled first.** The inventory
re-derived after the polish pass agrees with every count the documents state: 110
functional requirements, 17 success criteria, 131 tasks in 11 milestones, 23 deviation ids
(17 from the plan's table and PLAN-1 to PLAN-6), 18 proposals (P-1 to P-18) kept apart
from them, and 913 ledger rows that match the pinned donor's test methods one for one. The
register holds 57 open-item ids: 48 open (28 for the owner, 20 for the lead) and 9 settled
since the documents were drafted. Every requirement group maps to tasks and every task
traces to a requirement group. The task graph has no cycle, and no task has a hard
dependency on a later milestone. Every relative link resolves. All 27 lead decisions are
reflected in the documents. All 101 findings of the review pass are closed or declined
with the decline accepted, and every residual finding of this analysis is closed
(section 8).

What must be settled before M1, and only this:

- **At owner checkpoint 1 (owner):**
  - Accept or amend ADR 0008, which is still "Proposed". The strategy pointer and the
    donor record both depend on it.
  - Decide **OPEN-27**: ADR 0004 asks for measured benefit before adoption; here an
    estimate precedes adoption and the measurement follows at close-out (plan exception
    E6). Is this ordering accepted?
- **Inside M1, before the named package closes (owner):** **OPEN-03**, the exact synthetic
  default model name (ENG-02, API-08, API-17); until it is decided the working default is
  `pulsar-console-synthetic` (LD27). **OPEN-04**, the `Host` allowlist on non-loopback
  binds (API-03). **OPEN-29**, what the server does if an engine reports a provenance
  other than synthetic (seam question Q9), before ENG-01 freezes the seam.
- **Inside M1, needing the owner's help (ENG-01):** the seam draft must be offered to the
  engine track, and its review recorded, before ENG-01 freezes version 1.0 (FR-039). Who
  reviews it and in what form is seam question Q12 (OPEN-30), a lead item, but reaching
  the engine track goes through the owner. ENG-01's code can land before that; its task
  cannot be ticked, and the seam stays a draft, until the review is recorded.
- **Not a precondition, but it shapes M1 output (owner):** proposals P-1 to P-3 of
  **OPEN-15** concern the transport and the request-error text built in M1 (API-02, with
  the error model of API-01). Until the owner decides them, those packages keep the
  donor's behavior where they can and record `pending` rows where they cannot, as the
  register says.

Lead items due inside M1 remain lead work, not preconditions: OPEN-30 (seam details,
settled by ENG-01 before the freeze). The owner item OPEN-06 is due before OPS-11 in M7
(LD26).

The OPEN-29 sentence and the two bullets after it were added on 2026-11-14, after the M0
commits, when the checkpoint list was re-derived from the register: OPEN-29 was in the
register with its due point but missing from this summary, and the engine-track review
was in ENG-01's definition of done but not listed here.

## 2. Scope and method

**Files analyzed.** The 42 paths in `git status --short` before this file was added (44
after the polish pass, which added this file and `console/tools/check-toolchain.sh`): the
feature directory (spec, checklist, plan, research, data model, quickstart, tasks, the
seven `tasks/*.md` detail files and the five contracts), ADR 0008, the console roadmap,
`docs/upstream/PROJECT_MAYA.md` and `PROJECT_MAYA_SYNC.md`, the four small edits
(`README.md`, `NOTICE.md`, `CONTRIBUTING.md`, the strategy pointer), `console.yml`, and
everything under `console/`. The approved plan of 2026-11-14 is the reference for
decisions. That plan, and the planner and review records, are planning documents outside
the repository; where this file relies on them it says so.

**How the inventory was derived.** With small Python scripts kept outside the repository
and run with an isolated interpreter (`python3 -I`), reading files as text:

- Requirements: lines matching `^- \*\*(FR-\d+)` and `^- \*\*(SC-\d+)` in spec.md, with
  the `####` heading above each as its group.
- Tasks: task lines matching `^- \[( |x)\] <ID>( \[P\])? \[M<n>\]` in tasks.md, where `<ID>`
  is GOV, API, ENG, PRM, RSP, OPS, WEB or CNF followed by two digits; the ids in each
  entry's "Depends on" and "Seams" text; a depth-first search over "Depends on" for cycles;
  a comparison of each prerequisite's milestone with the task's own.
- Deviation ids, `P-` refs and `OPEN-` ids: every match of
  `(SEC|PRIV|BRAND|LIC|POL|PLAT|FIX|PLAN)-\d+(\.\d+)?`, `P-\d+` and `OPEN-\d+` in the 42
  files, against the headings, index and sub-item tables of `contracts/deviations.md`.
- Links: every relative Markdown link target outside code blocks, resolved from the
  linking file, and every `#fragment` checked against the target's headings.
- Ledger: `console/parity/ledger.json` loaded as JSON and compared with an independent
  listing of the pinned donor's tests. The donor was read only as text: a script outside
  the donor checkout parsed each `serve/test_*.py` with Python's `ast` module, keeping
  `test*` functions at module level and directly inside module-level classes, as
  `contracts/parity-ledger.md` section 4 defines. No donor code was imported or run.
- Names: crate names in tasks.md, plan.md, spec.md and research.md against the approved
  plan's crate list; the product name, binary name and environment prefix by text search.

**Commands run in the repository** (read-only for the repository; the build used a
target directory outside it):

| Command (from) | Result on 2026-11-14 |
| --- | --- |
| `console/tools/check-boundary.sh` (root) | passed: 42 changed paths, merge base `aaf076f1`; allowlist, frozen blobs, ignored files, path dependencies and reserved names all ok |
| `console/tools/check-hygiene.sh` (root) | passed: 42 files, 21,603 added lines, every gate ok |
| `cargo fmt --check` (`console/`) | passed |
| `cargo clippy --locked --all-targets --offline -- -D warnings` (`console/`) | passed, no warnings |
| `cargo test --locked --offline` (`console/`) | 1 unit test passed, 0 doc tests (the skeleton crate's name check only) |
| `rustc -V`, `cargo -V` | both 1.97.1, from a package-manager install without `rustup` |

The commands were run again after the polish pass; section 11 records the results. The
negative paths of the two scripts were exercised in a throwaway clone outside the
repository (finding R-05); `quickstart.md` section 4 records each case and that it fired.

## 3. Lead decisions

The lead made 27 decisions on 2026-11-14: LD1 to LD16 after the documents were first
drafted, and LD17 to LD27 after this analysis was first recorded. The labels LD1 to LD27
exist only in this file; the other documents state each decision in
words, as "decided by the lead on 2026-11-14", without a label. None of them adds an owner
decision: each applies a rule of the approved plan to a case the plan does not name, or
settles a choice the plan leaves to the lead. One departs from the plan's wording: LD17
moves the Preact, htm and Lucide texts, which the plan lists among the M0 contents of
`console/LICENSES/`, to WEB-01, and the owner is informed of it at checkpoint 1. All are
settled.

| Id | Decision, in words | What it settled | Where it is applied |
| --- | --- | --- | --- |
| LD1 | The two donor test files that run unchanged against the Rust artifacts through a shim (`serve/test_engine_contract.py`, `serve/test_stop.py`) and the vendor-template renders run only in the manual reference job; blocking CI checks only their committed records. The ledger dispositions are `rust-test`, `scenario`, `web-test`, `shim`, `vendor-render`, `deviation`, `not-applicable` and `pending`. This refines the plan's evidence table, which put the shim under blocking CI. | Where the shim runs; the closed disposition set | spec FR-084, FR-089; tasks R10 and gate step 4; parity-ledger 2 and 3.2 (L1 closed); data-model; research 18; ADR 0008; PROJECT_MAYA; `console/parity/README.md`; `console.yml` header; quickstart |
| LD2 | Test-harness switches read by the product or its tests use the `PULSAR_CONSOLE_` prefix. The control variables of the fake engines and the fake MCP server keep the donor fakes' names, because they are a test-double interface, not product identity. | The prefix of switches (exact names settled by LD22) | spec FR-045; tasks R5; naming 3.10 and N5; research |
| LD3 | There is one fake vision encoder binary, in `console-fake-engines`, built by ENG-14 and used by RSP-18. | The duplicate encoder in two planner records | tasks R11, ENG-14, RSP-18; research Decision 9 |
| LD4 | PRM-04 does not depend on PRM-02, not even as a seam. | PRM-04's place in M1 | tasks R12 and the PRM-04 note |
| LD5 | A dependency on a later milestone is a seam (a trait with an inert default); a task is ticked only when its full definition of done holds. | How later-milestone needs are expressed and when checkboxes are ticked | tasks "How to read" and R13 |
| LD6 | Hardware-specific parts that land before M9 are built behind traits with fixtures and labeled unverified; the real readers stay in M9. | ENG-08, ENG-15, ENG-14, RSP-18 and OPS-07 hardware branches | tasks R23; deviations PLAT-1 |
| LD7 | No `uuid` crate; ids are random hexadecimal drawn from operating-system randomness. | Id generation | tasks R8, API-01; research 21 and dependency table |
| LD8 | No `hyper` anywhere, including test-only fixture servers. | Test fixtures and the WebDriver client choice | tasks R2, B1; research dependency table (WebDriver client excluded if it pulls `hyper`) |
| LD9 | The outbound `curl` facade lives in `console-core` (module `outbound`), is written by RSP-10, its first consumer, and is reused by RSP-17 and OPS-16. | Which package builds the facade, and the task graph around it | tasks R17, RSP-10, RSP-17, OPS-16; deviations PLAN-6; research Decision 10 |
| LD10 | Under BRAND-2 no font or PNG file is shipped: `/fonts/<name>` answers 404 and the web manifest lists SVG icons only; both are sub-items of BRAND-2. | Font route and manifest icons | spec FR-099; deviations BRAND-2.4 and BRAND-2.5; tasks R14, WEB-02 |
| LD11 | Extra reviewers for API-07, ENG-10, PRM-03, PRM-12, PRM-15, ENG-06, ENG-11, RSP-05, OPS-05, OPS-08, OPS-16, WEB-06, WEB-09 and CNF-09 (the plan names these by function), and also API-17, CNF-04, CNF-11, CNF-19, OPS-09 and RSP-07. | Which packages get an extra reviewer | plan.md Execution Model; tasks "Highest-risk packages" and each task's Risk line (all 20 checked) |
| LD12 | The server assigns the request id; ENG-01's task text follows `contracts/backend-seam.md`. | Request-id ownership at the seam | tasks R27, ENG-01 |
| LD13 | ENG-01 settles how multi-conversation engines fit the single-owner seam before freezing it. Guidance: the engine instance stays owned by one driver thread; for more than one concurrent generation the token-level trait offers a submit-and-pump form with request-id-tagged events, and the blocking generate form is the single-conversation case. | The design direction for the seam (details stay open as OPEN-30) | spec FR-027; backend-seam Q1; tasks R27, ENG-01; research Decision 17; roadmap Phase 3 |
| LD14 | The frozen-blob check compares the root `Cargo.toml`, `Cargo.lock` and `macos.yml` with the merge base, as `check-boundary.sh` implements it, not with a moving `main` tip. | The comparison point of the non-interference check | spec FR-088, SC-004; plan II and Non-Interference; tasks gate step 5; ADR 0008; console README |
| LD15 | The six differences that the plan decides outside its deviation table are registered as PLAN-1 to PLAN-6, each citing its plan section as the approval basis: the synthetic badge and health report (PLAN-1), a synthetic default model name (PLAN-2), embedded assets with no filesystem path served (PLAN-3), license notices reachable from the About page (PLAN-4), the always-available in-house schema validator (PLAN-5), and HTTPS MCP through the curl facade (PLAN-6). Planner proposals that no approved id covers stay under "Proposed, awaiting owner decision" and are never described as approved. | Register ids for plan-decided differences; the status of P-1 to P-17 | deviations (PLAN section and index); spec FR-002, FR-004, FR-005, FR-054, FR-074, FR-078, FR-108; ADR 0008; PROJECT_MAYA; tasks |
| LD16 | One register of open items, in this file, lists every open item from every document with a stable id, who decides it and where it came from; each document may keep a local list that points here. | Open-item numbering and ownership | Section 9 of this file; pointers in spec, tasks, research, data-model, plan, quickstart, all five contracts, ADR 0008, roadmap, PROJECT_MAYA, PROJECT_MAYA_SYNC, console README, LICENSES README, `console.yml` |
| LD17 | License texts of third-party components are added in the same change that imports the component: Preact (MIT), htm (Apache-2.0) and Lucide (ISC) with WEB-01; the DeepSeek reference encoder notice with PRM-07, which commits the five DeepSeek fixture pairs together with that notice. M0 ships the project-maya MIT text only. The owner is informed at checkpoint 1. | OPEN-26 (now a lead item); finding F052 | tasks GOV-05, WEB-01, PRM-07 and open items; LICENSES README; PROJECT_MAYA (module map, third-party table, Attribution, open items); plan IX, structure and M0 row; roadmap M0 row; console README layout |
| LD18 | CI fetches crates that are not already cached with `cargo fetch --locked` at run time; nothing is vendored. | OPEN-47 | research 29; quickstart section 3; `console.yml` (unchanged, already does this) |
| LD19 | The toolchain pin is enforced on hosts without `rustup` by `console/tools/check-toolchain.sh`, which reads the channel from `console/rust-toolchain.toml` and fails unless `rustc -V` reports exactly that version. It is part of the per-task gate, the console subsection of `CONTRIBUTING.md`, `console/README.md` and quickstart; `console.yml` keeps its own assertion. | OPEN-51; finding F021 | the new script; tasks gate step 1 and GOV-06; CONTRIBUTING; console README; quickstart sections 2 and 3; research Decision 15 and item 33; plan Technical Context and E1; `rust-toolchain.toml` comment; `console.yml` step names |
| LD20 | Provenance headers: a four-line comment on files adapted from the donor; a one-line module comment on Rust tests and test doubles translated from donor tests or fakes; no donor copyright lines on Rust modules reimplemented from the contracts, which may cite a "Behavior reference"; WEB-01 adds a check that every file under `console/web` carries a `Provenance` line or is listed as PulsarMLX-original. | OPEN-54 | PROJECT_MAYA Attribution (the rule) and module map; contracts README rule 7; tasks WEB-01 |
| LD21 | The donor's export of each engine setting under both a `MAYA_` and a `STRATA_` name to the engine child is not reproduced; names in a run-config `env` block pass through to the child verbatim, once. | OPEN-32 | naming rule 3, section 3.4 and N3; research Decision 16; tasks API-15 |
| LD22 | Test-only settings and test-harness switches take the mechanical names `PULSAR_CONSOLE_<old suffix>`, as listed in `contracts/naming.md`. | OPEN-33 | naming 3.5, 3.10 and N5; tasks R5 and open items; research Decision 16 |
| LD23 | Everything the server sends is observable unless it is on the volatile list (generated ids; timestamps and `created` fields; the `Date` header; the value of the `Server` header until the owner decides P-1; timing and rate figures; uptime; process ids; ports; temporary paths), which is normalized before comparison. The HTTP version token, status line, header names, header order where the donor's order is deterministic, JSON key order and stream framing are observable. CNF-04 implements it. | OPEN-37 | parity-ledger section 1.1 and L2; deviations P-1; tasks CNF-04 |
| LD24 | Residual Unicode-table differences between Python's regex module and the Rust regex crates are accepted when a test names and pins them; PRM-04 records them. | OPEN-46 | tasks PRM-04; research 28 |
| LD25 | `check-hygiene.sh` has no file-count limit. | OPEN-56; the declined part of finding F070 | `check-hygiene.sh` header comment |
| LD26 | API-15 (M1) resolves every persisted file relative to the directory of the run config passed with `--config`, as the donor does. The default directory when no config is given, and whether an importer for project-maya run configs exists, remain owner item OPEN-06, due before OPS-11 (M7). | Narrows OPEN-06; residual R-12 | spec OI-5; research 10; data-model Persisted Files; tasks API-15 and open items |
| LD27 | PLAN-2 (a synthetic default model name) is delivered by ENG-02, asserted by the tests of API-08, and kept by API-17 when the full command line lands. Until the owner fixes the exact name (OPEN-03), the working default is `pulsar-console-synthetic`. | Residual R-01 | tasks ENG-02, API-08, API-17 and open items; research 15; deviations PLAN-2; naming 3.9 and N6; spec OI-2 |

## 4. Inventory

| Item | Source | Derived here | Stated in the documents | Agrees |
| --- | --- | --- | --- | --- |
| Functional requirements | spec.md | 110 (FR-001 to FR-110, no gap, no duplicate) | groups as listed in section 5 | yes |
| Success criteria | spec.md | 17 (SC-001 to SC-017) | — | yes |
| Spec open items | spec.md | OI-1 to OI-13, each with a register id | — | yes |
| Tasks | tasks.md | 131, all unticked: GOV 6, API 20, ENG 19, PRM 16, RSP 19, OPS 22, WEB 11, CNF 18 | 131 (6 governance, 125 packages) | yes |
| Tasks per milestone | tasks.md | M0 6, M1 18, M2 15, M3 12, M4 11, M5 7, M6 13, M7 18, M8 12, M9 7, M10 12 | Counts table and approved plan section 8 | yes |
| Merged and roadmap ids | tasks.md | PRM-01, OPS-01, CNF-05, CNF-06 and WEB-P2-01 to WEB-P2-03 absent from task lines | stated as merged or roadmap-only | yes |
| Deviation ids | deviations.md | 23 headings and 23 index rows in the same order: SEC-1 to SEC-7, PRIV-1, BRAND-1, BRAND-2, LIC-1, LIC-2, POL-1, PLAT-1 to PLAT-3, FIX-1, PLAN-1 to PLAN-6 | 17 plan-table ids plus PLAN-1 to PLAN-6 | yes |
| Deviation sub-items | deviations.md | 64, no duplicate; every sub-item cited elsewhere is defined | — | yes |
| Proposals | deviations.md | P-1 to P-18, all under "Proposed, awaiting owner decision"; every `P-` reference elsewhere is in range | — | yes |
| Contracts | contracts/README.md | 4 written (backend-seam, naming, parity-ledger, deviations) plus the index; later contracts listed as planned with their packages | — | yes |
| Ledger rows | ledger.json | 913 rows, sorted by id, 44 donor files, fields exactly `id`, `file`, `class`, `method`, `subsystem`, `disposition`; all `pending`; no null class | 913 rows, all pending (GOV-06); schema in parity-ledger 3 and 3.1 | yes |
| Donor test methods | pinned donor, listed independently | 913 unique in 44 files; the same id set as the ledger | 913 and 44 everywhere they appear | yes |
| Open-item ids | all M0 files | OPEN-01 to OPEN-57 each cited at least once; none out of range; 48 open (28 owner, 20 lead), 9 settled | — | yes; OPEN-56 was added by this analysis and OPEN-57 by the polish pass |
| Lead-decision labels | all M0 files | none outside this file | — | yes |

## 5. Coverage: requirement groups and tasks

Every functional requirement maps to at least one task, and every one of the 131 tasks
appears in at least one row below. Task entries in tasks.md do not cite requirement ids
(only FR-039 is cited, twice), so this mapping is derived here from each requirement's
text and each task's title, target and definition of done; it is the traceability record
until tasks cite requirements themselves.

| Requirement group | Requirements and the tasks that deliver them |
| --- | --- |
| Parity, scope and claims (FR-001 to FR-006) | FR-001: every parity package, measured by API-19, CNF-09, CNF-12, PRM-17. FR-002: GOV-06 (register), CNF-04 (deviation annotations), CNF-12 (checker). FR-003: GOV-01, GOV-04, gate step 7. FR-004 (PLAN-1): API-06, WEB-07. FR-005 (PLAN-2): ENG-02 (definition of done), asserted by API-08, kept by API-17 (LD27). FR-006: API-18, ENG-13, ENG-16, OPS-19, OPS-20, WEB-08, CNF-16, and the pre-M9 parts in ENG-08, ENG-15, ENG-14, RSP-18, OPS-07. |
| Transport and wire foundations (FR-007 to FR-010) | FR-007: API-02. FR-008, FR-009: API-01. FR-010: API-03. |
| Request validation and sampling (FR-011, FR-012) | FR-011: API-04, ENG-03. FR-012: API-04, PRM-11. |
| OpenAI Chat Completions (FR-013) | API-08, PRM-16. |
| Anthropic Messages (FR-014) | API-09, PRM-16. |
| Prompt construction (FR-015 to FR-021) | FR-015: PRM-02, PRM-03. FR-016: PRM-08. FR-017: PRM-04, PRM-08. FR-018: PRM-06. FR-019: PRM-07. FR-020: PRM-05, PRM-11. FR-021: ENG-17. |
| Output processing (FR-022 to FR-026) | FR-022: PRM-09, PRM-10. FR-023: PRM-12. FR-024: PRM-13, API-13. FR-025: PRM-14, PRM-15. FR-026: PRM-16. |
| Backend seam, scheduling and supervision (FR-027 to FR-039) | FR-027: ENG-01, ENG-19. FR-028: ENG-01, ENG-03. FR-029: ENG-01, ENG-10. FR-030: API-07, ENG-10. FR-031: ENG-02, ENG-05, ENG-06, ENG-19. FR-032: ENG-04, ENG-06. FR-033: ENG-07. FR-034: ENG-09. FR-035: ENG-10. FR-036: ENG-11. FR-037: ENG-08, ENG-12, ENG-15. FR-038: ENG-18. FR-039: ENG-01. |
| Monitoring, discovery, admin and lifecycle (FR-040 to FR-050) | FR-040: API-05, API-06, OPS-17. FR-041: API-11. FR-042: API-13, API-14. FR-043: API-10. FR-044: API-15. FR-045, FR-046: API-15, OPS-02. FR-047: API-15, ENG-15. FR-048: API-10, RSP-11. FR-049: API-16. FR-050: API-17. Route inventory for the group: API-20. |
| Responses API (FR-051 to FR-056) | FR-051: RSP-03, RSP-04. FR-052: RSP-01, RSP-06. FR-053: RSP-05, RSP-07. FR-054 (PLAN-5): RSP-02. FR-055: RSP-03. FR-056: RSP-01. |
| MCP (FR-057 to FR-060) | FR-057: RSP-09, RSP-10, RSP-11. FR-058: RSP-11. FR-059: RSP-10. FR-060: RSP-08. |
| Attachments and media (FR-061 to FR-066) | FR-061: RSP-12. FR-062: RSP-13, RSP-14, RSP-15. FR-063: RSP-16. FR-064: RSP-17. FR-065: RSP-18, ENG-14. FR-066: RSP-19. |
| Model management and launch (FR-067 to FR-074) | FR-067: OPS-03, OPS-04, OPS-05, OPS-06, OPS-07. FR-068: OPS-08, OPS-09, OPS-10. FR-069: OPS-12, OPS-13. FR-070: OPS-14, OPS-15. FR-071: OPS-11, OPS-16. FR-072: OPS-21. FR-073: OPS-22. FR-074 (PLAN-6): RSP-10, reused by RSP-17 and OPS-16. Integration of the group: OPS-23. |
| Telemetry (FR-075 to FR-077) | FR-075: OPS-17. FR-076: OPS-18. FR-077: OPS-19, OPS-20, ENG-13, ENG-16, CNF-16. |
| Dashboard, Phase 1 (FR-078 to FR-083) | FR-078 (PLAN-3): WEB-01, WEB-02, API-12. FR-079: WEB-06, WEB-09, WEB-10, WEB-11. FR-080: WEB-01, WEB-04. FR-081: WEB-07, WEB-08. FR-082: WEB-05, CNF-15, WEB-11. FR-083: WEB-04, WEB-06, CNF-15. |
| Conformance, governance and non-interference (FR-084 to FR-089) | FR-084: GOV-06, API-19, CNF-12. FR-085: CNF-01, CNF-02, CNF-03, CNF-04, CNF-07, CNF-08, CNF-09, CNF-18, CNF-19, CNF-20. FR-086: CNF-13, CNF-14. FR-087: CNF-08, CNF-10, ENG-05, RSP-08. FR-088: GOV-06. FR-089: GOV-06, CNF-01, CNF-10, CNF-11, CNF-17. The analysis itself: GOV-03. |
| Approved deviations (FR-090 to FR-107) | FR-090 (SEC-1): API-02, API-03. FR-091 (SEC-2): WEB-02, WEB-03. FR-092 (SEC-3): WEB-03. FR-093 (SEC-4): RSP-17. FR-094 (SEC-5): OPS-22. FR-095 (SEC-6): API-04, PRM-06. FR-096 (SEC-7): ENG-15, OPS-15, OPS-16. FR-097 (PRIV-1): API-10, WEB-10. FR-098 (BRAND-1): API-17, OPS-03, WEB-01, GOV-06 (naming.md). FR-099 (BRAND-2): WEB-01, WEB-02. FR-100 (LIC-1): PRM-02, CNF-11. FR-101 (LIC-2): RSP-19. FR-102 (POL-1): ENG-03, OPS-05. FR-103 (PLAT-1): API-18, ENG-13, ENG-16, OPS-19, OPS-20. FR-104 (PLAT-2): OPS-18, WEB-07. FR-105 (PLAT-3): OPS-11, OPS-16. FR-106 (FIX-1): ENG-06, ENG-07, ENG-12. FR-107: GOV-06 (register rule), CNF-12. |
| Provenance and licensing (FR-108 to FR-110) | FR-108 (PLAN-4): GOV-05, WEB-01. FR-109: GOV-04, GOV-05, WEB-01. FR-110: GOV-02 (research.md table) and every package that adds a dependency. |

**Result.** 18 of 18 groups covered, 110 of 110 requirements mapped, 131 of 131 tasks
traced (checked by script against the task list). No gap remains: FR-005, mapped by
subject only when first recorded (R-01), is now in ENG-02's definition of done.

## 6. Consistency checks

| Check | How | Result |
| --- | --- | --- |
| Each deviation id defined once | Headings and index rows of deviations.md compared | Holds: 23 ids, each with one heading and one index row, in the same order. |
| Deviation ids referenced consistently | Every id and sub-item match in the 42 files checked against the register | Holds: no unknown id, no undefined sub-item, no leftover temporary `E-1` to `E-6` refs. The PLAN order is the same in spec, deviations, ADR 0008, PROJECT_MAYA and tasks. |
| Approved set stated the same way | Text search for the approved list in spec FR-002, plan, ADR 0008, PROJECT_MAYA, tasks, requirements checklist | Holds: each names the 17 table ids plus PLAN-1 to PLAN-6 and keeps proposals apart. |
| Proposals not described as approved | P-5, P-11 and P-15 traced through spec FR-066, research Decision 9, data-model, plan V, tasks R28 and WEB-02 | Holds. research Decision 9 is now headed as conditional on P-5 (R-06 closed). |
| Open-item ids | Every `OPEN-` reference in the 42 files read in context against section 9 | Holds: each id is used with the meaning recorded here; spec OI-12 maps to OPEN-13 and OPEN-14, and OI-13 to OPEN-15. |
| Names | Text search for the product name, binary, prefix, crate names and switch prefixes | Holds: "PulsarMLX Console", `pulsar-console`, `PULSAR_CONSOLE_`; every crate name is in the plan's list or is a binary inside `console-fake-engines`. The only "Pulsar Console" is a quoted planner placeholder in tasks R14. Detail files still use `CONSOLE_*` switch names; naming 3.10 maps them (R-02). |
| Links | All relative links and their fragments resolved (354 when first recorded; 364 in 31 files after the polish pass) | Holds: every target exists; the only target that did not exist before this file was this file. |
| Counts | Section 4 | Holds. |
| Task graph has no cycle | Depth-first search over "Depends on" | Holds. |
| No hard dependency on a later milestone | Milestone of every prerequisite compared with the task's | Holds: zero. Every "Seams" entry points to a later milestone, as R13 requires. |
| `[P]` markers | A task is `[P]` exactly when it has no prerequisite in its own milestone | Holds for all 131. |
| Dependency prose matches the entries | Spot checks of the "Dependency graph by milestone" text (PRM-04, RSP-10, RSP-17, OPS-16, ENG-14, RSP-18, API-07) | Holds for the cases checked; the whole text was not compared line by line. |
| Lead decisions applied | Section 3, each decision traced to the files named there | Holds for LD1 to LD27. |
| Constitution check complete | plan.md Constitution Check compared with the 12 principles of the constitution | Holds: 12 rows, each marked PASS (design) or N/A with a reason, and stated as a design commitment. Principle VIII's support matrix is produced by CNF-12 and published by CNF-17 (R-04 closed). |
| Exceptions complete | plan.md Constitution Exceptions compared with the constitution's Governance section (scope, evidence, risk, removal condition, approval) | Holds for E1 to E6; reviewer approval of E1 to E5 is pending at checkpoint 1, and E6 (donor benefit estimated before adoption and measured at close-out, against ADR 0004's order) is pending the owner's decision OPEN-27. |
| Constitution compliance in spec and tasks | Search for a compliance section | Both have one. tasks.md's section points to plan.md's Constitution Check and says which gate step enforces which principle (R-03 closed). |
| Workflow order | Constitution workflow steps 1 to 3 against the record | The requirements checklist is complete (no unchecked item) and was rerun after plan, contracts and tasks existed; the analysis (this file) exists before any M1 code. |
| Non-interference | `check-boundary.sh` and `check-hygiene.sh` on the working tree | Both pass (section 2). The root `Cargo.toml`, `Cargo.lock` and `macos.yml` equal the merge base. |
| Skeleton builds | fmt, clippy and tests from `console/` | Pass on 1.97.1 (section 2). GOV-06 says "an empty nested workspace"; it holds one placeholder crate with one test, which is what lets cargo build it. |

## 7. Review pass and fix pass

Five reviewers read the M0 files before the fix pass, each through one lens: governance
(constitution, plan and project rules), accuracy (claims against the pinned donor and the
repository), consistency (between documents and with the lead decisions), tooling and CI
(the two check scripts and the workflow), and owner voice (what the owner-facing documents
say in the owner's name). They raised 101 findings. Seven fixers then edited the files by
group; two findings (the missing register and analysis) were left to this file. Many
findings describe the same root cause seen from different lenses: the P-5 pixel-value
proposal stated as a requirement (four findings), the missing register (three), the old
five-value disposition set (eleven) and the unregistered plan-decided differences (seven).

| Lens | Blocker | Major | Minor | Nit | Total | Closed | Still open | Declined, accepted |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Governance (F001 to F022) | 2 | 6 | 11 | 3 | 22 | 21 | 0 | 1 |
| Accuracy (F023 to F038) | 0 | 6 | 8 | 2 | 16 | 16 | 0 | 0 |
| Consistency (F039 to F065) | 1 | 15 | 10 | 1 | 27 | 27 | 0 | 0 |
| Tooling and CI (F066 to F079) | 0 | 6 | 6 | 2 | 14 | 14 | 0 | 0 |
| Owner voice (F080 to F101) | 1 | 7 | 13 | 1 | 22 | 22 | 0 | 0 |
| **Total** | **4** | **40** | **48** | **9** | **101** | **100** | **0** | **1** |

Two parts of findings were declined by fixers and the decline is accepted here; the
findings themselves are counted by their remaining state. F017: setting ADR 0008 to
Accepted is the owner's act at checkpoint 1, not a fixer's. F018 (also F074): the shared
files `README.md`, `NOTICE.md`, `CONTRIBUTING.md` and the strategy are left out of the
workflow path filter, because plan section 9 says an engine push never runs `console.yml`
and the engine track edits those files; the workflow header says how they are checked.
F070: a 512-file limit was not ported, because the scan covers a whole multi-milestone
branch, not one commit; the lead confirmed that there is no count limit (LD25). The six
findings still open after the fix pass were closed in the polish pass, as their rows say.

"Re-checked" below means this analysis verified the current text itself; "fix pass"
means it relies on the fixer's report.

| Id | Sev. | Topic | Status | Basis |
| --- | --- | --- | --- | --- |
| F001 | blocker | Spec stated proposal P-5 (pixel values) as a requirement | closed | re-checked FR-066, research Decision 9 (nit R-06) |
| F002 | blocker | Register and recorded analysis missing | closed | this file |
| F003 | major | Spec, PROJECT_MAYA, research not aligned with LD1 | closed | re-checked |
| F004 | major | Plan-decided differences not registered (LD15) | closed | re-checked |
| F005 | major | tasks.md marked settled points "Lead to confirm" | closed | re-checked |
| F006 | major | Extra-reviewer list missing six packages; ids attributed to the plan | closed | re-checked plan.md and tasks.md |
| F007 | major | Donor called qualified; benefit measured after adaptation, against ADR 0004 order | closed in the polish pass | pre-adoption estimate in PROJECT_MAYA; ADR 0008 decision 2 and plan IX reworded; plan exception E6; owner decision OPEN-27 |
| F008 | major | Planned WebDriver client may pull `hyper` (LD8) | closed | re-checked research (made conditional); detail file R-02 |
| F009 | minor | Frozen blobs "compared with main" | closed | re-checked |
| F010 | minor | Three M0 definitions of done could not hold | closed | re-checked GOV-02, GOV-05, GOV-06 |
| F011 | minor | Requirements checklist incomplete and not rerun | closed | re-checked |
| F012 | minor | Quickstart status contradicted a recorded run | closed | re-checked |
| F013 | minor | fmt and Clippy claimed on macOS | closed | re-checked plan E1 |
| F014 | minor | No support matrix for principle VIII | closed in the polish pass | CNF-12 and CNF-17 (R-04) |
| F015 | minor | llama.cpp notice missing from the attribution plan | closed | re-checked LICENSES README |
| F016 | minor | Roadmap overstated Phase 2 and Phase 3 approval | closed | re-checked |
| F017 | minor | Strategy donor section and "specific authorization" wording | closed in the polish pass | pointer fixed ("once accepted"); one sentence added to the strategy's Donor qualification section (R-08); decline of ADR acceptance accepted |
| F018 | minor | Path filter omits governance files | declined, accepted | four console-only documents added; shared files declined (see above) |
| F019 | minor | No constitution-compliance check in spec or tasks | closed in the polish pass | spec fixed; tasks.md section added (R-03) |
| F020 | nit | "Nothing ... MUST serve" | closed | re-checked |
| F021 | nit | Command forms differ; no `rustc -V` advice | closed in the polish pass | one command form everywhere and the toolchain script in every local list (R-11, LD19) |
| F022 | nit | No implementation strategy section | closed | re-checked |
| F023 | major | Sprite's `i-maya` logo mark omitted | closed | re-checked |
| F024 | major | PROJECT_MAYA disposition and approved lists stale | closed | re-checked |
| F025 | major | ADR 0008 disposition and approved lists stale | closed | re-checked |
| F026 | major | Register used temporary E-1 to E-6 refs | closed | re-checked |
| F027 | major | tasks.md left LD3, LD4, LD7 to LD10 open; facade seam reversed | closed | re-checked |
| F028 | major | naming N5 left the switch prefix open | closed | re-checked |
| F029 | minor | CorsOptIn method count | closed | re-checked: 8 in the donor, deviations and tasks |
| F030 | minor | Telemetry citation and Mac RAM claim | closed | re-checked PLAT-2 text |
| F031 | minor | Mac support omitted the MiniMax Metal engine | closed | re-checked |
| F032 | minor | Wrong donor locations in naming | closed | fix pass; one row spot-checked against the donor |
| F033 | minor | Nested-workspace precedent "exists twice" | closed | re-checked |
| F034 | minor | Class method counts | closed | re-checked in tasks.md; the four counts in `tasks/ops.md` corrected against the donor in the polish pass |
| F035 | minor | Condensed definitions of done dropped conditions | closed | fix pass; tasks.md states the detail file still applies |
| F036 | minor | PRM-04 listed PRM-02 as a seam | closed | re-checked |
| F037 | nit | Two citations near the behavior | closed | fix pass |
| F038 | nit | One citation off by one | closed | fix pass |
| F039 | blocker | Spec made proposal P-5 a requirement | closed | same as F001 |
| F040 | major | PLAN-1 to PLAN-6 kept as E-1 to E-6 | closed | re-checked |
| F041 | major | Register missing | closed | this file |
| F042 | major | Settled items still open; R17 and R2 differed from decisions | closed | re-checked |
| F043 | major | Task graph did not follow LD9 | closed | re-checked by script |
| F044 | major | ENG-01 followed the async design; engine-assigned id | closed | re-checked |
| F045 | major | LD13 guidance missing from backend-seam Q1 | closed | re-checked |
| F046 | major | WEB-02 built P-11 and a `devdir` override | closed | re-checked |
| F047 | major | BRAND-2 sub-items for fonts and manifest missing | closed | re-checked BRAND-2.4, BRAND-2.5 |
| F048 | major | data-model gave five dispositions | closed | re-checked |
| F049 | major | research left LD1 and LD7 points open | closed | re-checked items 18 and 21 |
| F050 | major | research Decision 9 presented P-5 as decided | closed | re-checked (nit R-06) |
| F051 | major | P-15 presented as part of the model | closed | re-checked data-model and plan V |
| F052 | major | LICENSES README deferred plan 7.4 texts | closed in the polish pass | settled by LD17; LICENSES README and GOV-05 agree |
| F053 | major | plan.md extra-reviewer list | closed | re-checked |
| F054 | major | Gate steps 4 and 5 stale | closed | re-checked |
| F055 | minor | FR-084 five values; no register pointer | closed | re-checked |
| F056 | minor | PROJECT_MAYA open item on shim placement | closed | re-checked |
| F057 | minor | parity-ledger L1 still open | closed | re-checked |
| F058 | minor | parity README five values | closed | re-checked |
| F059 | minor | naming N5 and missing switch rows | closed | re-checked section 3.10 |
| F060 | minor | GOV-02 and GOV-06 wording | closed | re-checked |
| F061 | minor | Separate CNF-15 contract; `fixtures` name | closed | re-checked contracts README |
| F062 | minor | Pre-M9 hardware list incomplete | closed | re-checked PLAT-1 |
| F063 | minor | ADR 0008 manual jobs and register pointer | closed | re-checked |
| F064 | minor | Quickstart stale observation and flags | closed | re-checked |
| F065 | nit | Roadmap stated planner details as plan | closed | re-checked ("proposed") |
| F066 | major | parity README dispositions | closed | re-checked |
| F067 | major | Boundary check missed single-quoted paths and `.cargo/` config | closed | code read; both negative paths exercised in the polish pass (R-05) |
| F068 | major | Allow marker excused every line gate | closed | code read: only five heuristic gates are excusable |
| F069 | major | Credential gate fired on ordinary Rust code | closed | code read; pattern narrowed |
| F070 | major | check_staged rules not ported (modes, total size, whitespace, `*.trace`) | closed | code read and run; file-count part declined and settled by LD25 |
| F071 | major | NUL past 8000 bytes; GNU grep stopped at NUL | closed | code read: explicit NUL check and `grep -a` |
| F072 | minor | `+++` content lines taken as file headers | closed | code read |
| F073 | minor | SIGPIPE under `pipefail` hid attribution | closed | fix pass |
| F074 | minor | Path filter omitted console-only documents | closed | re-checked `console.yml` |
| F075 | minor | Workflow comment on the reverted workflow's pin | closed | re-checked (the plan's own wording is a planning record and unchanged) |
| F076 | minor | plan.md compared with `main` | closed | re-checked |
| F077 | minor | LICENSES rule contradicted by the project-maya text | closed | re-checked rule wording |
| F078 | nit | Bearer gate case-sensitive | closed | code read: case-insensitive flag |
| F079 | nit | Trap did not exit on INT or TERM | closed | code read |
| F080 | blocker | Spec required unapproved P-5 in the owner's name | closed | same as F001 |
| F081 | major | Ready-line synthetic marker required | closed | re-checked FR-050 (now a proposal under PLAN-1) |
| F082 | major | Five-value disposition set in owner documents | closed | re-checked |
| F083 | major | Shim placement and manual-job lists | closed | re-checked |
| F084 | major | PLAN-1 to PLAN-6 unnamed; SC-008 overclaimed | closed | re-checked SC-008 and FR-002 |
| F085 | major | Register missing; duplicated items | closed | this file |
| F086 | major | Roadmap Phase 2 details as commitments | closed | re-checked |
| F087 | major | "The approved plan" cited as authority outside the repository | closed | fix pass; spec defines the plan and ADR 0008 records it; PROJECT_MAYA reworded in the polish pass (R-10) |
| F088 | minor | ADR compared with `main` | closed | re-checked |
| F089 | minor | Misused requirement keyword; "every statement" | closed | re-checked |
| F090 | minor | Strategy overstated M0; "serving shell" | closed | re-checked the strategy; plan E2 says "serving layer" since the polish pass (R-09) |
| F091 | minor | ADR "full plan is carried"; SEC-5 and SEC-7 reference | closed | fix pass |
| F092 | minor | Undefined checkpoint labels in spec | closed | re-checked spec; ADR 0008 now says the feature plan lists the checkpoints |
| F093 | minor | CONTRIBUTING terms and duplication | closed | re-checked |
| F094 | minor | NOTICE present tense | closed | re-checked |
| F095 | minor | README "built ahead" | closed | re-checked |
| F096 | minor | FR-099 missing LD10 sub-items | closed | re-checked |
| F097 | minor | FR-027 had no submit-and-pump room; roadmap restated the seam | closed | FR-027 re-checked; the roadmap links the seam contract since the polish pass (R-09) |
| F098 | minor | Spec did not state LD2 | closed | re-checked FR-045 |
| F099 | minor | console README "Present. Run locally"; personal path | closed | re-checked |
| F100 | minor | "Both supported host platforms" | closed | re-checked |
| F101 | nit | "Adapted" stretched to translated tests | closed | re-checked |

## 8. Residual findings of this analysis

These held on the files as they stood after the fix pass. None blocked checkpoint 1. The
last column records what the polish pass did.

| Id | Sev. | File | Finding | Fix | Status after the polish pass |
| --- | --- | --- | --- | --- | --- |
| R-01 | minor | `specs/022-console-serving-parity/tasks.md` | PLAN-2 (FR-005, synthetic default model name) has no task whose definition of done delivers it. deviations.md names API-17 as its package, research item 15 says it blocks API-08, and the scripted engine itself is ENG-02; no entry mentions it. | Add it to ENG-02's (or API-17's) definition of done with a PLAN-2 note, and align research item 15 and the PLAN-2 Packages line. | Closed by LD27: ENG-02, API-08 and API-17 name PLAN-2 in their definitions of done; research 15 and the PLAN-2 entry agree; working default `pulsar-console-synthetic` until OPEN-03. |
| R-02 | minor | `specs/022-console-serving-parity/tasks/*.md` | Detail files keep planner text that binding decisions or lead decisions supersede: a `hyper` server and client and a "shared outbound TLS client" (responses.md), `hyper` fixture servers (ops.md, conformance.md), the `uuid` crate (prompt.md), an unconditional WebDriver client, `console/web/fonts/`, `console/web/LICENSES/` and `CONSOLE_*` switch names (web.md), and old method counts (ops.md). Each file's header says a binding decision overrides it, but most of these are lead decisions recorded as reconciliations, which the header does not name. | Extend each header to "a binding decision or a reconciliation in tasks.md overrides", or mark the superseded lines. | Closed: all seven headers now say that a binding decision or a reconciliation in tasks.md overrides any conflicting sentence. The superseded planner lines themselves are unchanged, by design, except the four method counts in `tasks/ops.md` (F034). |
| R-03 | minor | `specs/022-console-serving-parity/tasks.md` | The constitution requires tasks to include a constitution-compliance check; tasks.md has none beyond the per-task gate. | Add a short section that points to plan.md's Constitution Check, as spec.md does. | Closed: tasks.md has a "Constitution compliance" section that points to plan.md and maps gate steps to principles. |
| R-04 | minor | `specs/022-console-serving-parity/tasks.md` | plan.md row VIII promises a support matrix in the M10 parity report and says the packages that fill it are named in tasks.md; none is named. | Name them (for example CNF-12 and CNF-17) in their definitions of done. | Closed: CNF-12 produces the support matrix and CNF-17 publishes it in the M10 parity report; plan.md row VIII names both. |
| R-05 | minor | `specs/022-console-serving-parity/quickstart.md` | GOV-06's definition of done needs `check-boundary.sh` to fail on a staged change to a never-touched path; the fixed negative paths of both scripts have not been exercised and no run is recorded. | Before ticking GOV-06, run and record the negative cases (frozen file, single-quoted path dependency, `.cargo/` directory, submodule, late NUL, `+++` content line). | Closed: the cases of the Fix column and further cases (16 in all, listed in quickstart section 4, including the late NUL and the `+++` content line) were run in a throwaway clone, and each fired. One defect was found and fixed: a staged submodule (gitlink) without a checked-out directory was not scanned in working-tree mode; `check-boundary.sh` now lists staged changes too. |
| R-06 | nit | `specs/022-console-serving-parity/research.md` | Decision 9 is headed "Decision" while its resampling and format choices depend on proposal P-5. The text says so. | Retitle the decision as conditional on P-5, or split the conditional part out. | Closed: Decision 9 is headed "Images (conditional on proposal P-5)". |
| R-07 | nit | `specs/022-console-serving-parity/contracts/deviations.md` | research item 4 lists a proposed explicit model-family override in config (PRM-05) that has no `P-` row. | Add it as a P-row or drop it from research item 4. | Closed: proposal P-18 added; research item 4 cites it. |
| R-08 | nit | `docs/roadmap/PULSARMLX_STRATEGY.md` | The strategy's Donor qualification section still lists only Pulsar, ssd-llm and Colibri; the new donor appears only in the Stage F pointer. | The allowlist permits only the dated pointer here, so either accept this or have the owner approve a second edit. | Closed: one sentence added to the strategy's Donor qualification section, linking the donor record; nothing else in that file changed. |
| R-09 | nit | `specs/022-console-serving-parity/plan.md` | plan E2 says "serving shell" where every other document says "serving layer"; the roadmap's Phase 3 restates the seam instead of linking `contracts/backend-seam.md`. | Use "serving layer"; add the link. | Closed: plan E2 says "serving layer"; the roadmap's Phase 3 links `contracts/backend-seam.md`. |
| R-10 | nit | `docs/upstream/PROJECT_MAYA.md` | It says work-package ids are "those of the approved plan and of tasks.md"; the plan defines no package ids. | Say they are those of tasks.md. | Closed: PROJECT_MAYA names the plan once as not published in this repository, then says "that plan", and says work-package ids are those of tasks.md. |
| R-11 | nit | `CONTRIBUTING.md` | Command forms differ from the per-task gate in tasks.md (`--all`, `--workspace`), which is equivalent in a virtual workspace; CONTRIBUTING gives no `rustc -V` check for hosts without `rustup`. | Use one form; add the version check once OPEN-51 is settled. | Closed: one command form in CONTRIBUTING, the gate, console README, quickstart and `console.yml`, with the toolchain script (LD19) in each local list. |
| R-12 | nit | `specs/022-console-serving-parity/spec.md` | spec OI-5 places the run-config directory default (OPEN-06) at M7; research item 10 says it blocks API-15, which is in M1. | Settle which is right and align both. | Closed by LD26: API-15 resolves persisted files relative to the `--config` directory in M1; the default directory and importer stay OPEN-06, due before OPS-11 (M7); spec OI-5 and research 10 agree. |

## 9. Register of open items

This is the single register of open items for feature 022. Every open item in every
document is listed here once, under a stable id; documents that keep a local list point
here, and this register is authoritative where they differ. "Owner" items need the
repository owner's decision; "Lead" items are settled by the lead and recorded in the
named contract. A proposed default, where one was proposed, is not a decision: until an
item is decided, packages keep the donor's behavior or stop short of the open point.
"Before" gives the package or milestone the item must be settled by.

Short source names: spec = spec.md (OI table); tasks = tasks.md; research = research.md
(numbered open items); data-model, plan, quickstart = the files of those names; seam,
naming, ledger, deviations = the four contracts; ADR = ADR 0008; roadmap =
CONSOLE_ROADMAP.md; PM = PROJECT_MAYA.md; SYNC = PROJECT_MAYA_SYNC.md.

### Owner decisions

| Id | Statement | Sources | Proposed default | Before |
| --- | --- | --- | --- | --- |
| OPEN-01 | Whether the donor's sealed-reasoning prefix `maya-r1:` is accepted on input; only the product prefix is emitted. | spec OI-1, FR-055; research 3; tasks B2, R6, open items; naming N1, 3.9; seam Q11; deviations BRAND-1.6; data-model | The Responses planner proposed accepting it; until decided it is not accepted (tasks R6). | RSP-03 (M5) |
| OPEN-03 | The exact default model name of the scripted engine; it must contain "synthetic" (PLAN-2). | spec OI-2, FR-005; research 15; naming N6; deviations PLAN-2; tasks open items | the lead's working default `pulsar-console-synthetic` (LD27), used until the owner decides | ENG-02, API-08, API-17 (M1) |
| OPEN-04 | How the `Host` allowlist behaves on non-loopback binds, and the proposed `allowed_hosts` key. | spec OI-3, FR-090; deviations SEC-1.1 | key `allowed_hosts` (proposed) | API-03 (M1) |
| OPEN-05 | Whether `pulsar-console supervise` or plain serving is the documented default entry point. | spec OI-4, FR-071; research 9 | `supervise` as default, unsupervised serving reporting restarts as unavailable (research) | OPS-11 (M7), API-17 |
| OPEN-06 | The default run-config directory when no config is given, and whether an importer for project-maya run configs exists. Persisted files are resolved relative to the directory of the run config passed with `--config` (LD26). | spec OI-5, FR-044; research 10; data-model Persisted Files; tasks API-15, open items | a fixed per-user application-support folder was suggested (research); not decided | OPS-11 (M7) |
| OPEN-07 | Whether template `raise_exception` and DeepSeek encoder assertion failures map to 400 instead of the donor's uncaught error. | spec OI-6; research 4; deviations P-8 | 400 (P-8) | PRM-08 (M2) |
| OPEN-08 | Whether the donor's built-in savings price table (as of 2026-10) ships verbatim, with its date, or empty. | spec OI-7, FR-072; research 8; data-model | none recorded | OPS-21 (M7) |
| OPEN-09 | An untagged `ERR` in multi-conversation mode: reproduce the donor's wait, or deliver it to the single in-flight request (FIX-1 covers only the untagged stop). | spec OI-8, FR-033; research 5; tasks open items, ENG-07 | none recorded | ENG-07 (M3) |
| OPEN-10 | Whether an optional engine start (`READY`) timeout is added; the donor waits forever. | spec OI-9, FR-037; research 4; deviations P-6 | optional, off by default (P-6) | ENG-06 (M3) |
| OPEN-11 | Whether the manual vendor-template job may fetch and render the GLM-5.3 template (no license text in the donor) and the MiniMax Community License template and fixtures, test-only with hashes recorded. | spec OI-10, FR-100; research 6 | if not, those ledger rows become deviations (research) | CNF-11 (M10) |
| OPEN-12 | Whether accessibility gaps the donor leaves open are fixed in Phase 1 or deferred to Phase 2. | spec OI-11, FR-079; research 4 | none recorded | WEB-10 (M8) |
| OPEN-13 | Whether `console.yml` (its summary job) becomes a required check on `main`, and how a required check behaves when the path filter skips the workflow (not yet checked on GitHub). | spec OI-12, FR-089; research 1, 36; tasks R18; plan; ADR; roadmap; `console.yml` header; console README | none; decided at merge time (plan section 9) | merge |
| OPEN-14 | The merge order of the feature branch relative to engine-track branches whose evidence is bound to tree identity. | spec OI-12; research 2; plan; ADR; roadmap; README.md | a merge commit, engine branches never asked to rebase (plan section 10 default merge policy) | pull request |
| OPEN-15 | Planner proposals that no approved id covers: P-1 to P-5, P-7 and P-9 to P-18 (Server header, both length and chunked framing, malformed-request detail, reader detail text, picture resampling and formats, whitespace-free vision temporary directory, backend labels, macOS watchdog, ETag, 304 and HEAD, CSP report-only switch, debug global, `safetensors` format label, MLX not-startable listing, refusing revision `main`, a literal-parity reload setting, an explicit model-family override); also the JSON Schema meta-validation wording (PLAN-5), and the advisory savings lock (research 4). | deviations "Proposed, awaiting owner decision"; spec OI-13, FR-066; research 4, Decision 9; data-model; plan V; tasks R28, WEB-02; PM; ledger 1.1 | each as described in its P-row; until decided the donor's behavior, or `pending` rows | each implementing package |
| OPEN-16 | Whether to reproduce or fix `/props` reporting `model_path` as a literal fallback for pack or GGUF configs. | research 5 | none recorded | API-11 (M4) |
| OPEN-17 | Whether a private read-only mirror of project-maya at `7e68a30f` is kept for the manual reference job. | research 7; plan section 12 (risk table) | none; the plan notes a mirror would remove the dependency on upstream | CNF-08 (M10) |
| OPEN-18 | The form and name of the SEC-4 media-source opt-in (run-config key, environment variable or both). | research 11; deviations SEC-4.2 | `media_sources: ["data", "http", "file"]` (proposed) | RSP-17 (M6) |
| OPEN-19 | Whether an opt-in to disk persistence of resumable answers exists at all, its name and its retention. | research 12; deviations PRIV-1.2; data-model | none recorded; persistence is off by default either way (PRIV-1) | API-10 (M4), WEB-10 |
| OPEN-20 | The Phase 2 framework (Leptos, Dioxus or Yew) and the handling of built WebAssembly output. | research 13; ADR; roadmap Phase 2 and open items | Leptos, or a neutral spike among the three (research) | Phase 2 (WEB-P2-01) |
| OPEN-21 | The Phase 3 engine boundary: line-protocol executable or in-process runtime adapter; whether an engine may attach at the event level and which server duties it then takes over. | research 14; seam Q10 | both supported; the choice decides which conformance profile becomes required | Phase 3 |
| OPEN-22 | The Prometheus metric prefix that replaces `maya:` (`llamacpp:` is kept). | research 16; naming 3.9; deviations BRAND-1.6 | `pulsar_console:` (proposed) | API-06 (M4) |
| OPEN-23 | The neutral product logo (SVG only under BRAND-2). | research 17; PM sprite row | none recorded | WEB-01 (M8) |
| OPEN-24 | Whether launching actively refuses known project-maya engine binary names. | tasks R24, open items | none recorded; no document, default or test launches one either way | ENG-15 (M3) |
| OPEN-25 | Which engine variable names Turbo and the settings profiles write into a run-config `env` block, and how the dashboard shows names such as `MAYA_EXPERT_RAM_GB`. | tasks open items; naming N4 | none recorded | OPS-05, OPS-06, WEB-09 (M7, M8) |
| OPEN-27 | Whether the owner accepts this ordering: ADR 0004 asks for measured benefit before adoption; here an estimate precedes adoption and the measurement follows at close-out (plan exception E6). | PM Measured benefit and open items; plan E6; ADR decision 2 and open items; review finding F007 | none; the pre-adoption estimate is recorded in PM | owner checkpoint 1 |
| OPEN-28 | Any re-pin of project-maya beyond `7e68a30f`. | ADR; roadmap; SYNC; ledger 4.1 | none; a re-pin is a separate decision (plan section 12) | any re-pin |
| OPEN-29 | What the server does if an engine reports a provenance other than synthetic: refuse to start or report it. | seam Q9 | none recorded | seam freeze (ENG-01) |
| OPEN-57 | Which named feature checklist the close-out coverage figure uses. Split from the earlier OPEN-27 in the polish pass. | PM Measured benefit and open items | the donor README feature list (a suggestion in PM, not decided) | CNF-17 (M10) |

### Lead decisions

| Id | Statement | Sources | Proposed default | Before |
| --- | --- | --- | --- | --- |
| OPEN-02 | The exact product sealed-reasoning prefix string; the rename itself is decided. | naming N1, 3.9; deviations BRAND-1.6 | `pcr1:` (proposed) | RSP-03 (M5) |
| OPEN-30 | Seam details ENG-01 settles before freezing: Q1 (multi-place engines, along the lines of the lead's submit-and-pump guidance, LD13), Q2 to Q8, and Q12 (which engine-track reviewer accepts the draft, and in what form). | seam section 4, Q1 to Q8, Q12; data-model Usage; spec FR-027, FR-039; tasks R27, ENG-01, open items; research Decision 17; roadmap Phase 3 | LD13 guidance for Q1; drafts in backend-seam.md for the rest | ENG-01 freeze (M1) |
| OPEN-31 | Whether the Responses limit names keep `GLM_` in their suffix. | naming N2, 3.2 | drop it (RSP planner proposal) | RSP-01 (M5) |
| OPEN-34 | The `/props` `build_info` value ("Strata <version>" or a product string). | naming N7 | a product string (API planner proposal) | API-11 (M4) |
| OPEN-35 | Values marked "Rename decided, value proposed" in naming 3.6 to 3.9 and 4.3 (service field, `/api/version`, DOM event, CSS names, download names, `clientInfo`, User-Agent, `--engine` value, temporary prefixes, quant labels), and the concrete PLAN-1 badge and health fields and ready-line suffix. | naming 3.6 to 3.9, 4.3; deviations PLAN-1, BRAND-1.6 | the values in naming; `synthetic: true` and `backend` in `/health` and `/v1/status` (API planner) | each owning package |
| OPEN-36 | How upstream-skipped donor methods are resolved (whether independent tests or SDK tests may satisfy them), and whether the donor's baseline pass and skip results are stored separately or only as `upstream_skipped`. | research 18, 20; ledger L4 | none recorded | API-19 assigns owners (M1); CNF-12 (M10) |
| OPEN-38 | Format and location of the `shim_record` and `vendor_record` files, and how the manual run id is recorded. | ledger L3; research 18 | none recorded | CNF-10, CNF-11, CNF-12 (M10) |
| OPEN-39 | The numbering scheme for later owner-approved deviations, beyond PLAN-1 to PLAN-6. | research 19; data-model DeviationEntry | none recorded | the first later deviation |
| OPEN-40 | Whether `console-web` uses the `http` and `bytes` crates or the transport's own types. | research 22, dependency table | `http` and `bytes` (WEB planner proposal); not adopted by the plan | WEB-02 (M8) |
| OPEN-41 | Whether an opt-in development mode serves dashboard assets from a directory; PLAN-3 says no filesystem path is ever served in the product. | research 23, Decision 11; deviations PLAN-3; tasks R28, WEB-02 | not adopted; WEB-02 builds no `devdir` module (tasks R28) | WEB-02 (M8) |
| OPEN-42 | Whether `check-hygiene.sh` applies the `check_staged.sh` word rules (`cuda`, `nvidia`, `target_os linux`) to console paths, given that the M9 ports need those words. | research 24 | none recorded | M9 |
| OPEN-43 | Whether timing-sensitive multi-conversation and fair-slice tests run in the default blocking jobs or in a scaled-time job. | research 25 | none recorded | ENG-07, ENG-11 (M3) |
| OPEN-44 | The ownership split of GLM-5.3 product facts (pack detection, template choice, memory constants) between `console-prompt` and `console-manage`. | research 26 | the split research describes, to be confirmed | PRM-05 (M2), OPS-04 (M7) |
| OPEN-45 | Whether the engine conformance binary exposes the engine-only `LOGP` command. | research 27 | none recorded | ENG-18 (M3) |
| OPEN-48 | Whether the Responses and MCP contract documents go to the owner before RSP-06 and RSP-11 start. | research 30 | none recorded | RSP-06 (M5), RSP-11 (M6) |
| OPEN-49 | `preact.js` provenance: accept on recorded hash, or compare once against the upstream Preact 10.29.8 and htm 3.1.1 releases (needs a network step). | research 31; PM open item 3 | keep byte-identical with a recorded hash | WEB-01 (M8) |
| OPEN-50 | The local browser driver for the manual end-to-end suite (`safaridriver` needs a one-time administrator enable). | research 32 | none recorded | WEB-06 (M8) |
| OPEN-52 | Whether the pinned `libc` exposes the macOS process-statistics calls the supervision sampler needs. | research 34 | a small `extern` declaration or another crate if not | ENG-08 (M3), OPS-18 (M4) |
| OPEN-53 | Installing the Windows standard library for the cross type-check in the Linux job. | research 35; tasks GOV-06 | none recorded | API-18 (M9) at the latest |
| OPEN-55 | Whether the console creates or only maintains the donor's `run-<STEM>.sh` and `.bat` launcher scripts. | data-model Persisted Files | none recorded | the packages that rewrite or remove them |

### Settled since the documents were drafted

| Former open point | Settled by | Former sources |
| --- | --- | --- |
| Where the two shim files and vendor-template renders run; the disposition set | LD1 | PM open item 5; parity-ledger L1; research 18; data-model |
| Prefix of test-harness switches | LD2 | naming N5 (prefix part); tasks R5 |
| One fake vision encoder | LD3 | tasks R11 |
| PRM-04 dependency on PRM-02 | LD4 | tasks R12 |
| Ticking tasks that have later-milestone seams | LD5 | tasks R13 |
| Hardware code before M9 | LD6 | tasks R23 |
| Id generation and the `uuid` crate | LD7 | research 21; tasks R8 |
| `hyper` in test fixtures | LD8 | tasks R2 |
| Which package builds the curl facade | LD9 | tasks R17 |
| `/fonts/<name>` and manifest icons | LD10 | tasks R14 |
| Extra reviewers for the six planner-rated packages | LD11 | earlier tasks open item |
| Who assigns the request id | LD12 | tasks R27; seam |
| Direction for multi-conversation engines | LD13 (details remain OPEN-30) | seam Q1 |
| Merge base or `main` tip for frozen blobs | LD14 | plan, ADR, spec, tasks |
| Register ids for plan-decided differences | LD15 | deviations temporary refs |
| One open-item register | LD16 | every document |
| License-text timing for Preact, htm, Lucide and DeepSeek, and committing the DeepSeek fixture pairs (OPEN-26) | LD17 | PM open item 3; LICENSES README; tasks GOV-05, open items; NOTICE.md |
| How CI fetches crates (OPEN-47) | LD18 | research 29 |
| Local toolchain enforcement without `rustup` (OPEN-51) | LD19 | research 33; plan Technical Context; quickstart section 2 |
| Provenance header format (OPEN-54) | LD20 | PM open item 2 |
| Dual `MAYA_`/`STRATA_` export to the engine child (OPEN-32) | LD21 | naming N3 |
| Exact names of test-only settings and test-harness switches (OPEN-33) | LD22 | naming N5, 3.5, 3.10; tasks R5, open items; research |
| What counts as observable (OPEN-37) | LD23 | ledger L2; deviations P-1 |
| Residual Unicode-table differences (OPEN-46) | LD24 | research 28; tasks PRM-04 risk |
| A file-count limit in `check-hygiene.sh` (OPEN-56) | LD25 | review finding F070 (declined part) |
| Run-config directory when `--config` is given (part of OPEN-06; the rest stays open) | LD26 | spec OI-5; research 10; residual R-12 |
| Which task delivers PLAN-2, and a working default name (part of OPEN-03; the exact name stays open) | LD27 | residual R-01 |

## 10. Checklist

### Inventory and counts

- [x] CHK001 Requirements and success criteria are enumerated without gaps or duplicates.
  FR-001 to FR-110 and SC-001 to SC-017.
- [x] CHK002 The task count matches the stated total and the milestone counts. 131 tasks;
  the per-milestone counts match the Counts table and the approved plan.
- [x] CHK003 The ledger matches the pinned donor. 913 rows, the same ids as an independent
  listing of the 44 donor test files, every row `pending`, fields as the contract defines.
- [x] CHK004 Counts stated across documents agree (913, 44, 131, 125, 17 plus 6).

### Coverage

- [x] CHK005 Every functional requirement maps to at least one task. Mapped in section 5;
  FR-005 is in ENG-02's definition of done since the polish pass (R-01).
- [x] CHK006 Every task traces to a requirement group. All 131 checked by script.
- [x] CHK007 Every user story is delivered by named milestones. The milestone table in
  tasks.md covers US1 to US9.
- [x] CHK008 Every approved deviation has a task whose definition of done delivers it. Met
  for all 23 ids; PLAN-2 is delivered by ENG-02, asserted by API-08 and kept by API-17
  (LD27).

### Consistency

- [x] CHK009 Each deviation id is defined once and referenced consistently.
- [x] CHK010 No planner proposal is described as approved. P-5, P-11, P-15 and P-18 are
  stated as proposals everywhere; research Decision 9 is headed as conditional on P-5.
- [x] CHK011 Names agree across documents (product, binary, prefix, crates).
- [x] CHK012 Every relative link and anchor resolves.
- [x] CHK013 Every `OPEN-` id used in a document is in the register with the same meaning.
- [x] CHK014 The lead decisions LD1 to LD27 are reflected in every document they affect.
- [x] CHK015 Task detail files agree with the binding and lead decisions. Superseded planner
  lines remain in the detail files by design; each file's header now says that a binding
  decision or a reconciliation in tasks.md overrides any conflicting sentence (R-02).

### Task graph

- [x] CHK016 The dependency graph has no cycle.
- [x] CHK017 No task has a hard dependency on a later milestone; later needs are seams.
- [x] CHK018 `[P]` markers agree with the dependencies.

### Governance

- [x] CHK019 plan.md's Constitution Check covers all twelve principles, each as a design
  commitment, not as evidence.
- [x] CHK020 Every departure from the constitution or standing project direction is a
  recorded exception. E1 to E6 are recorded; E6 (donor benefit estimated before adoption
  and measured at close-out) awaits the owner's decision OPEN-27.
- [x] CHK021 Specification and tasks each carry a constitution-compliance check.
- [x] CHK022 Nothing is described as working or measured. The skeleton's single test and
  the check-script runs are recorded as what they are; every feature claim is planned.
- [x] CHK023 Non-interference holds on the working tree: both check scripts pass, and the
  root `Cargo.toml`, `Cargo.lock` and `macos.yml` equal the merge base.
- [x] CHK024 The analysis exists before any M1 code (plan exception E5, GOV-03).

### Readiness

- [x] CHK025 The open items are consolidated in one register with stable ids and deciders,
  and every document's local list points here.
- [ ] CHK026 The items that must be settled before M1 are settled. Not yet: accepting ADR
  0008 and OPEN-27 at checkpoint 1, and OPEN-03 (working default in place) and OPEN-04
  inside M1.
- [ ] CHK027 M0 can be ticked in full. Not yet: GOV-03 is complete only once this file is
  committed with the rest of M0, and the owner's checkpoint 1 review of the documents that
  speak in the owner's name is pending. GOV-05 no longer waits on an open item (LD17), and
  GOV-06's negative checks are recorded (R-05).

## 11. Notes

- Recorded on 2026-11-14 against the working tree described in section 2. The approved
  plan, the planner records and the review and fix records are planning documents outside
  the repository; the decisions this file relies on are restated in spec.md, plan.md,
  tasks.md, the contracts and ADR 0008.
- Re-run after the polish pass on 2026-11-14, with 44 changed paths (this file and the
  new `console/tools/check-toolchain.sh` included): `check-boundary.sh` passed (merge base
  `aaf076f1`, every check ok); `check-hygiene.sh` passed (44 files, 22,426 added lines,
  every gate ok); `check-toolchain.sh` printed its `ok` line for `rustc` 1.97.1; from
  `console/`, `cargo fmt --check`, `cargo clippy --locked --all-targets -- -D warnings` and
  `cargo test --locked` passed (1 unit test); a link check kept outside the repository
  resolved all 364 relative links and their anchors in the 31 new and changed
  Markdown files. These are runs on an uncommitted tree, not evidence for a commit.
- Committed later on 2026-11-14 as eight commits, `a713aecd` to `1a2db9b9`. At `1a2db9b9`,
  with a clean working tree: `check-boundary.sh --committed` passed (44 changed paths,
  every check ok); `check-hygiene.sh --committed` passed (44 files, 22,455 added lines, 8
  commit messages, every gate ok); `check-toolchain.sh` printed its `ok` line; from
  `console/`, the same three `cargo` commands passed (1 unit test). The eighth commit adds
  an interpreter guard to the three check tools, after `sh console/tools/check-hygiene.sh`
  was found to stop part-way with a syntax error; the tools are bash scripts and the
  workflow starts them with bash, so no result above changes. Nothing has been pushed, so
  no CI run exists for these commits.
- The donor checkout was read only as text, with `ast` from a script kept outside it. No
  donor code was imported or executed, and nothing was fetched from the network.
- Rerun this analysis when tasks.md or a contract changes materially, after the owner's
  checkpoint 1 decisions, and at each milestone report. Items settled later move from
  section 9 to its "Settled" table with the decision and its date; ids are never reused.
