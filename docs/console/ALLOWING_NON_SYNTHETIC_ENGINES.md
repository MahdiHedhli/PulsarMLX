# Allowing non-synthetic engines

- **Status**: Normative note, dated 2026-11-14. The provenance type and the single guard
  function exist (ENG-01), the scripted engine reports synthetic provenance (ENG-02), and
  the turn driver calls the guard on every path that admits an engine (ENG-10); the
  refusal at process start is implemented by API-08 in `pulsar_console::start`, and the M1
  binary `pulsar-console` serves the scripted engine only.
- **Requested by**: the owner, on 2026-11-14, after checkpoint 1 of feature
  [`022-console-serving-parity`](../../specs/022-console-serving-parity/).
- **Maintained by**: every task that adds, moves or removes an enforcement point of the
  synthetic-only rule (see "Where the rule is enforced").

## What this note is

PulsarMLX Console's server, `pulsar-console`, refuses to start an engine that does not
report synthetic provenance. The owner decided this on 2026-11-14, settling open item
OPEN-29 (the `OPEN-` ids are registered, with who decides each, in the
[register of open items](../../specs/022-console-serving-parity/checklists/analysis.md#9-register-of-open-items)).
The rule carries out decision 1 of
[ADR 0008](../architecture/decisions/0008-console-serving-ahead-of-stage-f.md), which the
owner accepted on 2026-11-14, and its mechanism is specified in section 5.1, "The
synthetic-only guard", of the
[backend seam contract](../../specs/022-console-serving-parity/contracts/backend-seam.md#51-the-synthetic-only-guard).
This note is the single place that lists what must be done before the server may start
any other engine.

As of 2026-11-14 the provenance type, `console_core::engine::Provenance`, and the single
guard function, `console_core::engine::require_synthetic`, exist in `console-core::engine`
with the tests that pin them (ENG-01, commit `6200f4ac`). As of 2026-11-15 the scripted
engine of `console-engine::fake` and every test double built on it report synthetic
provenance, and the scripted engine's default model name is `pulsar-console-synthetic`
(ENG-02, commit `c86cf84f`). A test-only engine that reports a provenance that is not
synthetic, `NotSyntheticEngine`, exists behind the `test-support` Cargo feature of
`console-engine` for the refusal tests; no configuration key, command-line flag or
environment variable can select it, and the guard refuses it. As of 2026-11-15 the turn
driver (ENG-10, commit `4e7c438a`) calls the guard on every path that admits an engine
(first start, restart, model switch, context reload, and the start after an idle unload,
a death or a caught engine panic), in its single admission step `Host::admit`
(`console/crates/console-core/src/turn/host.rs`). The request lifecycle driver of
`console-http::inference` (API-07, commit `f6c42bb4`) adds no enforcement point and
admits no engine: a request reaches an engine only through the turn driver, and a start
that the guard refuses during a request is answered 503 `server_error` with the refusal
line (proposal P-26, awaiting the owner's decision; the donor answers nothing there). As
of 2026-11-15 the refusal at process start is implemented by API-08 (commit `5b327fa8`)
in `pulsar_console::start`, which reaches the guard only through `TurnDriver::start`, and
the M1 binary `pulsar-console` serves the scripted engine only: it runs the turn driver
behind the chat completions route, and its `main` names no other engine. Before its ready
line it prints a start-up line that says the engine is synthetic and no real model is
served (lead decision LD46). Besides the guard, its call in the turn driver, the process
start and that line, only the M0 repository checks (`console/tools/check-hygiene.sh` and
`console/tools/check-boundary.sh`) exist. The table in "Where the rule is enforced" tracks
each enforcement point as it lands. Until a row there says otherwise, read every statement
below about code as planned.

## Why the rule exists

The increment that builds PulsarMLX Console is authorized by ADR 0008 ahead of Stage F,
on synthetic backends only: a scripted in-process engine, a line-protocol client driven
by PulsarMLX-authored fake engine binaries, and a test adapter shaped like the engine
track's coordinator. The strongest claim any part of it can earn is "qualified on
synthetic backends", as defined in the
[console roadmap](../roadmap/CONSOLE_ROADMAP.md#status-vocabulary). The
[constitution](../../.specify/memory/constitution.md#iii-verified-claims-only) allows a
capability to be described as working only with its recorded command, environment, input
and result, and it requires synthetic, small real-model and giant-model coverage to be
labeled separately (principle VIII).

A real model behind this server would be a real-model serving claim. The
[strategy](../roadmap/PULSARMLX_STRATEGY.md#stage-f-product-surface) allows
OpenAI-compatible serving only after the local runtime is stable (Stage F), and the
[optimization roadmap](../roadmap/OPTIMIZATION_ROADMAP.md#concrete-work-register) puts
OPT-08, persistent serving, after native generation and streaming equivalence. Neither
gate is met, and ADR 0008 does not lift them. A synthetic label on a real engine would be
a false claim on every surface that shows it: the dashboard badge, `/health`, the model
name and the logs. The guard makes the server's behavior match what the project may say.

## What you must not do

None of the following is a way to lift the rule. Each one is a defect, whoever makes it
and for whatever reason.

- Do not delete, disable or weaken the guard, except as step 2 of the engineering change
  below after every owner decision in the next section is recorded.
- Do not add a command-line flag, environment variable, configuration key, Cargo feature,
  `cfg` attribute, build profile or test-only constructor that bypasses the guard, and do
  not add a path that admits an engine (a new engine kind, a new start, restart, switch or
  reload path) without calling it. None may exist in this increment. Whether a later
  increment adds one is for the owner's Phase 3 approval to decide (item 8 of the next
  section).
- Do not make an engine that is not synthetic report synthetic provenance. This includes
  a line-protocol engine that declares synthetic provenance in its start-up lines while
  running a real model.
- Do not put the Python/MLX research server, or any other real runtime, behind the
  line-protocol client or an in-process adapter. The research server is a reference, not a
  shipping path (ADR 0001, and the strategy's non-goal "No production Python hot path").
- Do not point the line-protocol client at a project-maya engine binary, such as
  `maya-metal`, directly or through a wrapper script or executable. Those binaries are a
  donor runtime; launching one is out of scope under ADR 0008 decision 6 and would need its
  own qualification under
  [ADR 0004](../architecture/decisions/0004-donor-code-qualification.md). Whether launching
  actively refuses known project-maya engine names is open item OPEN-24, decided by the
  owner before ENG-15.
- Do not commit model weights, a real model's tokenizer files or vendor chat templates.
  Deviation LIC-1 (the `SEC-`, `LIC-`, `PLAN-`, `PLAT-` and `POL-` ids are registered in the
  [deviation register](../../specs/022-console-serving-parity/contracts/deviations.md#lic-1))
  forbids vendor templates in the repository, constitution principle XI forbids weights
  other than a tiny licensed fixture reviewed for provenance and size, a real tokenizer
  carries its vendor's license like the template does, and
  [`console/tools/check-hygiene.sh`](../../console/tools/check-hygiene.sh) rejects model,
  tensor and binary file extensions.
- Do not add a real entry to the model catalog, or use `pulsar-console fetch` to download a
  real model, without the owner's approval (PLAT-3.3).
- Do not make a crate under `console/` depend on an engine-track crate, such as
  `crates/backend`, and do not relax `console/tools/check-boundary.sh` to allow it. ADR 0008
  decision 7 forbids path dependencies outside `console/`.
- Do not delete, weaken, skip, mark ignored, move behind a feature or the manual job, or
  rewrite the tests that pin the refusal in order to make an engine start (seam contract
  section 5.1, rule 5). They are named in "How to tell whether the rule still holds".
- Do not change the dashboard badge, the health and status fields, the start-up line that
  says the engine is synthetic or the model-name rule so that they say less than the truth
  about the engine behind the server. As built in M1, following the donor, a run config's
  `model_name` names the model when it is present, and `pulsar-console-synthetic` is only
  the default (lead decision LD53), so a configured name can remove the word "synthetic"
  from the `model` field of answers. Whether it may is owner item OPEN-62; the start-up line
  says that the engine is synthetic whatever the name.
- Do not describe the result as more than its evidence supports, in code comments,
  documents, commit messages or release notes.

## Decisions only the owner can make, before any code

No code that lifts the rule is written until every item below is decided and recorded.
The lead does not decide them, and neither does whoever picks up the work.

The owner is the PulsarMLX project owner, who approved the plan behind ADR 0008 and
accepted that ADR. The owner's decisions are recorded in ADRs under
`docs/architecture/decisions/` and in the register of open items; the lead's decisions are
the LD rows of section 3 of
[`checklists/analysis.md`](../../specs/022-console-serving-parity/checklists/analysis.md#3-lead-decisions).
A decision that is not recorded there has not been made.

1. **The Stage F and OPT-08 conditions.** The conditions of Stage F in the strategy and of
   OPT-08 in the optimization roadmap are met. Changing those gates is a change to the
   strategy and the optimization roadmap themselves, made by the owner there, not something
   an ADR about the console can waive. The strategy's
   [non-goals](../roadmap/PULSARMLX_STRATEGY.md#explicit-non-goals-and-stop-doing-list)
   still apply.
2. **The engine boundary.** Open item OPEN-21: whether the engine attaches as a
   line-protocol executable or through the in-process runtime adapter, and whether an
   engine may attach at the event level and which server duties it then takes over (seam
   question Q10; the `Q` ids are listed in section 14 of the seam contract). The choice
   decides which engine conformance profile becomes required. If the in-process runtime
   adapter is chosen, the new ADR also replaces ADR 0008 decision 7, which forbids any path
   dependency from `console/` on the engine track, and settles the merge order with the
   engine track's tree-bound evidence (OPEN-14).
3. **The engine track.** The engine track's agreement to the attachment and its review of
   the revised seam contract (FR-039; seam question Q12, open item OPEN-30) are recorded.
   Reaching the engine track goes through the owner.
4. **Donor qualification, if any.** If the engine is, contains or launches donor code, its
   qualification under ADR 0004: source and license review, attribution, independent
   tests, compatibility analysis and measured benefit.
5. **Licenses, file locations and catalog entries.** The licenses of the model, its
   tokenizer and its chat template; where those files live on the operator's machine
   (never in the repository); and any real entry in the model catalog, which needs the
   owner's approval (PLAT-3.3).
6. **Evidence.** What evidence the real-model claim needs and on which hardware, in the
   terms of the constitution's principles III, VII and VIII.
7. **Merge and CI.** The consequences for merging and CI: changes to the console workflow,
   `.github/workflows/console.yml`, any new required check, and how this interacts with
   OPEN-13 (whether that workflow is a required check on `main`) and OPEN-14 (the merge
   order relative to engine-track branches whose evidence is bound to tree identity). It
   also states how the console boundary changes: the new ADR's file, and any other path the
   work touches outside `console/**`, `specs/022-console-serving-parity/**` and
   `docs/console/**`, is outside what ADR 0008 decision 7 allows and what
   `console/tools/check-boundary.sh` admits, so the allowlist in that script and the
   matching list in `console/README.md` change together or the ADR lands outside the
   console change.
8. **Approval of Phase 3.** Attaching a real engine is Phase 3 of the
   [console roadmap](../roadmap/CONSOLE_ROADMAP.md#phase-3-real-engine-attachment-later-needs-its-own-approval),
   which needs the owner's own approval; ADR 0008 does not authorize it. The approval
   records the decisions above, which engine, which model and which claims are allowed,
   and what replaces PLAN-1 (the permanent synthetic badge) and PLAN-2 (the default model
   name). The form of that record (the lead expects a new ADR under
   `docs/architecture/decisions/`) is the owner's call. A proposed or draft record that the
   owner has not accepted is not an approval. Below, "the new ADR" means that record,
   whatever form the owner gives it.

## The engineering change, in order, once the owner has decided

Each step names the files and symbols it touches. The work-package ids (`ENG-`, `API-`,
`WEB-`, `OPS-`, `PRM-`, `CNF-`) are those of the feature's
[`tasks.md`](../../specs/022-console-serving-parity/tasks.md). A step marked "planned"
refers to code that does not exist yet; update the marking here when it lands.
Milestones M0 to M10 and the owner checkpoints are those of `tasks.md`. The engine track is
PulsarMLX's Rust engine work outside `console/`, whose evidence ADR 0008 keeps untouched.

1. **Revise the seam contract.** In
   [`contracts/backend-seam.md`](../../specs/022-console-serving-parity/contracts/backend-seam.md)
   and in the provenance type of `console-core::engine` (`console_core::engine::Provenance`,
   ENG-01; the seam version is `SEAM_VERSION`, now 0.2), add the provenance value for the
   approved engine, with whatever identity and evidence fields the new ADR requires, and
   bump the seam version. The revised seam is offered to the engine track for review,
   through the owner, and is not frozen until that review is recorded.
2. **Change the guard.** Change the single guard function in `console-core`
   (`console_core::engine::require_synthetic`, ENG-01) so that it admits exactly the
   provenance the new ADR approves, under the conditions that ADR sets (for example whether
   an explicit operator setting is required). Every other non-synthetic provenance, and an
   engine that declares none, is still refused.
3. **Make every surface tell the truth.** The health and status fields of `/health` and
   `/v1/status` (planned, API-06), the dashboard badge (planned, WEB-07), the model-name
   rule (`console_engine::fake::DEFAULT_MODEL_NAME`, ENG-02, and the run config's
   `model_name` that takes its place when present, LD53 and OPEN-62), the start-up line of
   LD46 (`pulsar_console::SYNTHETIC_ENGINE_LINE`, API-08; in M1 a constant that names the
   scripted engine), the start-up narration and the logs (planned, ENG-08 and API-17) all
   report the real engine as what it is. PLAN-1
   (the permanent synthetic badge) and PLAN-2 (the default model name
   `pulsar-console-synthetic`) change accordingly; what replaces them is decided in the new
   ADR.
4. **The engine itself.** It passes the engine conformance suite (planned, ENG-18) in the
   profile that OPEN-21 makes required. It uses the model's own tokenizer and its own chat
   template at run time; the template comes from the model directory or an explicit
   configuration path, never from the repository (LIC-1), and the tokenizer files likewise
   stay outside the repository (decision 5). It reports usage counts
   from the backend, as section 9 of the seam contract requires.
5. **Security review.** Review the engine environment and launch path for a real engine,
   including the engine-environment denylist of SEC-7 and the launch specification
   (planned, ENG-15).
6. **Tests.** Keep the refusal tests for every provenance that is still not allowed. Add
   tests that the approved provenance starts only under the conditions the new ADR sets, is
   refused otherwise, and is reported by every surface of step 3.
7. **Documents.** Each change that carries out steps 1 to 6 updates, in that same change,
   every document the step makes untrue: this note, the seam contract, the deviation
   register (PLAN-1 and PLAN-2 change), ADR 0008 (marked as amended or superseded by the
   new ADR where it says nothing serves a real model), the console paragraph under Stage F
   in the [strategy](../roadmap/PULSARMLX_STRATEGY.md#stage-f-product-surface), the
   [console roadmap](../roadmap/CONSOLE_ROADMAP.md),
   [`console/README.md`](../../console/README.md), the "Synthetic backends only" text of
   the [donor record](../upstream/PROJECT_MAYA.md), the status row in the
   [README](../../README.md), the feature's `spec.md`, `plan.md`, `tasks.md` and
   [quickstart](../../specs/022-console-serving-parity/quickstart.md), and the register of
   open items.
8. **Evidence.** The run record the new ADR asks for, written in the claim vocabulary of
   the constitution: commit, environment, model identity, command and result, with
   excluded tests and failed checks reported beside the successful evidence.

## How to tell whether the rule still holds

ENG-01 has filled in its test names and the guard's symbol below, ENG-10 the test names
and the call site of the turn driver, and API-08 the tests of the refusal at process start;
everything else in this section is planned. The remaining test names are filled in here by
the M3 line-protocol tasks when they land. Run the commands from `console/` on the pinned
toolchain, as the
[per-task gate](../../specs/022-console-serving-parity/tasks.md#per-task-gate-before-commit)
does.

1. **The refusal tests pass.** `cargo test --locked` passes, and it includes the guard
   tests of ENG-01, the eight tests of `console/crates/console-core/tests/eng01_guard.rs`
   (listed by `cargo test --locked -p console-core --test eng01_guard -- --list`), the
   nine turn-driver tests of ENG-10 in
   `console/crates/console-core/tests/eng10_admission.rs` (listed by
   `cargo test --locked -p console-core --test eng10_admission -- --list`):
   `the_first_start_refuses_an_engine_that_is_not_synthetic`,
   `a_restart_refuses_an_engine_that_is_not_synthetic`,
   `a_context_reload_refuses_an_engine_that_is_not_synthetic`,
   `a_model_switch_refuses_an_engine_that_is_not_synthetic`,
   `the_start_after_an_idle_unload_refuses_an_engine_that_is_not_synthetic`,
   `the_start_after_a_death_refuses_an_engine_that_is_not_synthetic`,
   `a_failed_restart_keeps_the_context_and_the_next_turn_starts_again`,
   `synthetic_engines_pass_every_admission_path` and `every_start_goes_through_the_guard`.
   Each refusal test asserts that the refused engine was shut down, that the operation
   failed with the refusal line, and that the engine's generate was never called; the
   turn-path refusals first pass the context rule (`TurnDriver::context_budget`), as a
   request does. The process-start tests of API-08,
   `pulsar-console::api08_refusal::process_start_refuses_an_engine_that_is_not_synthetic`
   and `::process_start_refuses_an_engine_that_declares_no_provenance`, run the binary's
   entry function in a child process; in process,
   `pulsar-console::api08_start::an_engine_that_is_not_synthetic_is_refused_in_process_too`
   also asserts that the refused engine was shut down and never asked to generate, and
   `pulsar-console::api08_start::nothing_listens_while_the_refused_engine_is_admitted`
   that nothing accepted connections on the configured port while it was admitted. None
   of them is marked ignored or skipped. Confirm with `cargo test --locked -- --list`
   that each named test is listed, and that none carries `#[ignore]` or a `cfg` that
   removes it.
2. **There is one guard.** A search for the guard's symbol, `require_synthetic`, under
   `console/crates/` finds exactly one definition, in `console-core`
   (`console/crates/console-core/src/engine/guard.rs`), and a call on every path that
   admits an engine: first start, restart, model switch and context reload. In the turn
   driver that call is in one place, the admission step `Host::admit` in
   `console/crates/console-core/src/turn/host.rs`, which every admission path of the
   driver reaches. At process start `pulsar_console::start` (API-08) reaches the guard
   only through `TurnDriver::start`, so it adds no call site of its own. Every call site
   of the guard is unconditional: no `if`, `cfg` or Cargo feature, environment variable,
   configuration key or command-line flag decides whether the guard runs, as a reading of
   each call site found by the search confirms.
3. **The binary refuses.** Start the server's entry point against a test engine that
   reports a non-synthetic provenance. The shipped `pulsar-console` binary cannot select
   such an engine. Its `main` names only `pulsar_console::scripted_factory`, and the
   test-only engine of ENG-02 sits behind the `test-support` Cargo feature of
   `console-engine`. The build that ships, `cargo build --locked -p pulsar-console`, does
   not enable the feature and does not compile that engine. A build of the whole workspace,
   and every test build, does enable it, through `console-testkit` and the tests' own
   dependencies: the engine is then compiled into `console-engine` as code the binary
   cannot reach, and the guard would refuse it if it were reached. The API-08
   tests therefore run the entry function `pulsar_console::run` in a child process of
   their own test executable (`console/crates/pulsar-console/tests/api08_refusal.rs`, child
   mode `refusal_child`), with that engine handed in directly:
   `pulsar-console::api08_refusal::process_start_refuses_an_engine_that_is_not_synthetic`
   (declared provenance) and
   `pulsar-console::api08_refusal::process_start_refuses_an_engine_that_declares_no_provenance`.
   List them with `cargo test --locked -p pulsar-console --test api08_refusal -- --list`.
   Each expects exactly one line on standard error, naming the engine kind (`scripted`),
   what the engine reported and the path `docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`,
   then exit status 1, with no engine line and no ready line on standard output, so no
   request is served. That nothing accepts connections on the port while the refused
   engine is admitted is shown in process by
   `pulsar-console::api08_start::nothing_listens_while_the_refused_engine_is_admitted`.
   From M3 the same check is also made with a fake line-protocol engine that does not
   declare synthetic provenance in its start-up lines (added by the M3 line-protocol
   tasks).

## Where the rule is enforced

| Enforcement point | File or symbol | Task that builds it | Status |
| --- | --- | --- | --- |
| Provenance type in the engine descriptor; it can express "not synthetic" (another provenance, or none), and synthetic is the only value accepted | `console/crates/console-core/src/engine/descriptor.rs`: `console_core::engine::Provenance` (`Synthetic`, or `NotSynthetic { declared: Option<DeclaredProvenance> }`; `Provenance::not_synthetic` never yields `Synthetic`) and the field `EngineDescriptor::provenance`; pinned by `console-core::eng01_guard::the_guard_refuses_every_provenance_that_is_not_synthetic`, `console-core::eng01_guard::the_guard_refuses_an_engine_that_declares_no_provenance` and the unit test `console-core::engine::descriptor::tests::provenance_display_is_one_escaped_line` | ENG-01 | implemented (ENG-01, commit `6200f4ac`), qualified on synthetic backends only; the seam is draft 0.2 until the engine-track review (Q12) |
| The single guard function, called before any engine serves a request | `console/crates/console-core/src/engine/guard.rs`: `console_core::engine::require_synthetic(&EngineDescriptor) -> Result<(), ProvenanceRefused>`; the refusal line is the `Display` of `ProvenanceRefused`, and `ProvenanceRefused::to_failure` gives the failure for restart, switch and reload; pinned by the eight tests of `console-core::eng01_guard`: `the_guard_admits_synthetic_provenance_for_every_kind`, `the_guard_refuses_every_provenance_that_is_not_synthetic`, `the_guard_refuses_an_engine_that_declares_no_provenance`, `the_guard_refuses_whatever_else_the_descriptor_says`, `the_guard_source_has_no_bypass` (a source-level pin: no environment read, conditional compilation, feature switch or configuration lookup in the guard file, and a single admitting arm for `Provenance::Synthetic`), `the_refusal_line_names_kind_report_and_note`, `the_refusal_line_text` and `a_refusal_at_restart_is_a_poisoned_start_failure_with_the_same_line` | ENG-01 | implemented (ENG-01, commit `6200f4ac`); called by the turn driver (ENG-10, commit `4e7c438a`), which the process start of API-08 (commit `5b327fa8`) goes through |
| Call of the guard on every admission path (first start, restart, model switch, context reload, and the start a turn makes after an idle unload, a death or a caught engine panic); a refused engine is closed and serves nothing | `console/crates/console-core/src/turn/host.rs`: the admission step `Host::admit` on the engine's driver thread. It is the only place an engine is started (`EngineFactory::start`), and it calls `console_core::engine::require_synthetic` unconditionally before the instance is kept; a refused instance is shut down at once and the operation fails with `ProvenanceRefused::to_failure`. A refused or failed start keeps the context from before it, so the next request passes the context rule and its turn reaches the guard again. It is reached from `TurnDriver::start` (first start), `TurnDriver::restart`, `TurnDriver::reload_context`, `TurnDriver::switch_engine` (the model switch's entry point) and `Host::prepare` (the donor's `ensure_engine`, which restarts after an idle unload, a death or a caught panic). Pinned by `console-core::eng10_admission::the_first_start_refuses_an_engine_that_is_not_synthetic`, `console-core::eng10_admission::a_restart_refuses_an_engine_that_is_not_synthetic`, `console-core::eng10_admission::a_context_reload_refuses_an_engine_that_is_not_synthetic`, `console-core::eng10_admission::a_model_switch_refuses_an_engine_that_is_not_synthetic`, `console-core::eng10_admission::the_start_after_an_idle_unload_refuses_an_engine_that_is_not_synthetic`, `console-core::eng10_admission::the_start_after_a_death_refuses_an_engine_that_is_not_synthetic`, `console-core::eng10_admission::a_failed_restart_keeps_the_context_and_the_next_turn_starts_again`, `console-core::eng10_admission::synthetic_engines_pass_every_admission_path` and `console-core::eng10_admission::every_start_goes_through_the_guard` (a source-level pin: one engine start, after it one guard call, before the instance is kept, and no environment read, conditional compilation or feature switch in the file) | ENG-10 | implemented (ENG-10, commit `4e7c438a`), qualified on synthetic backends only; the seam is draft 0.2 until the engine-track review (Q12) |
| Process start: refusal line on standard error and a non-zero exit status | `console/crates/pulsar-console/src/lib.rs`: `pulsar_console::run` and `pulsar_console::start`. The engine is started only through `console_core::turn::TurnDriver::start`, whose admission step `Host::admit` calls `require_synthetic`. A refusal prints the failure's message as one line on standard error and exits 1, before the listener is bound, so nothing is served. The message is the `Display` of `ProvenanceRefused`: `[console] refusing to start: engine <kind> reports provenance <reported>; this build serves synthetic engines only. See docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`. `console/crates/pulsar-console/src/main.rs` passes only `pulsar_console::scripted_factory`; nothing in the library reads a flag, an environment variable or a configuration key that selects an engine. Pinned by `pulsar-console::api08_refusal::process_start_refuses_an_engine_that_is_not_synthetic` and `pulsar-console::api08_refusal::process_start_refuses_an_engine_that_declares_no_provenance`. Each runs the entry function in a child process of the test executable with `NotSyntheticEngine` handed in (child mode: the test `refusal_child`) and asserts the one guard line, exit 1, no engine line, no ready line, and no line about binding the port on standard error (the port probe of the start, which binds and releases the port, runs before the engine is admitted; the listener itself is never bound). In process, `pulsar-console::api08_start::an_engine_that_is_not_synthetic_is_refused_in_process_too` also asserts that the refused engine was shut down and never asked to generate. `pulsar-console::api08_start::nothing_listens_while_the_refused_engine_is_admitted` asserts that nothing accepted connections on the configured port while the engine was being admitted | API-08 (M1 start path), kept by API-17 | implemented (API-08, commit `5b327fa8`), qualified on synthetic backends only |
| Start-up line that says the engine is synthetic, printed before the ready line (lead decision LD46) | `console/crates/pulsar-console/src/lib.rs`: the constant `pulsar_console::SYNTHETIC_ENGINE_LINE`, `[console] engine: scripted, synthetic provenance - no real model is served`, printed on standard output by `pulsar_console::start` once the listener is bound and before the ready line. In M1 it is a constant that names the scripted engine, the only engine the binary can run; it is a log line, not the ready-line marker proposed under PLAN-1. Pinned by `pulsar-console::api08_start::the_default_start_prints_the_engine_line_then_the_ready_line` (in process) and `pulsar-console::api08_process::the_ready_line_names_the_bound_port_under_port_zero` (the built binary, which asserts that the line comes before the ready line) | API-08; API-17 builds it from the engine descriptor once a second engine kind exists | implemented (API-08, commit `5b327fa8`), qualified on synthetic backends only |
| Scripted engine reports synthetic provenance and the default model name `pulsar-console-synthetic` | `console-engine::fake`: `mock_descriptor` in `console/crates/console-engine/src/fake/mock.rs` builds `EngineDescriptor::new(EngineKind::Scripted, Provenance::Synthetic)` for `FakeFactory`, `FakeEngine` and every test double built on them; `DEFAULT_MODEL_NAME` in `console/crates/console-engine/src/fake/mod.rs`. The refusal test engine `fake::doubles::NotSyntheticEngine` (`console/crates/console-engine/src/fake/doubles/not_synthetic.rs`) reports `Provenance::NotSynthetic`, from its first start or, built with `after_synthetic_starts`, after a given number of synthetic starts, for the restart, model-switch and context-reload paths. It exists only with the `test-support` feature; no configuration key, command-line flag or environment variable can select it, and any `generate` on it gets the guard's refusal. Pinned by `console-engine::fake::mock::tests::fake_descriptor_is_synthetic_with_the_donor_info`, `console-engine::fake::factory::tests::fake_engine_is_synthetic_and_passes_the_guard`, `console-engine::fake::tests::fake_default_model_name_is_the_decided_one`, `console-engine::eng02_seam::fake::every_double_but_one_is_synthetic_and_admitted`, `console-engine::eng02_seam::fake::the_not_synthetic_double_is_refused_before_it_serves`, `console-engine::eng02_seam::fake::the_decided_names_hold`, `console-engine::fake::doubles::not_synthetic::tests::fake_not_synthetic_engine_is_refused_by_the_guard`, `console-engine::fake::doubles::not_synthetic::tests::fake_not_synthetic_engine_never_serves_even_without_the_guard` and `console-engine::fake::doubles::not_synthetic::tests::fake_not_synthetic_after_synthetic_starts_serves_then_is_refused` | ENG-02 (PLAN-2) | implemented (ENG-02, commit `c86cf84f`), qualified on synthetic backends only |
| Coordinator-shaped test adapter and blocking runtime adapter report synthetic provenance | `console-engine::runtime` | ENG-19 (checked by ENG-18) | planned |
| Line-protocol declaration of synthetic provenance in the engine's start-up lines; an engine that declares another provenance, or none, counts as not synthetic | `console-engine::line` codec and client (ENG-04, ENG-06); the fake engine binaries make the declaration (ENG-05) | M3 line-protocol tasks (ENG-04, ENG-05, ENG-06; checked by ENG-18); the form of the declaration is open item OPEN-58 and is recorded here by those tasks | planned |
| Synthetic marker on the server's own ready line (proposed under PLAN-1; not decided, OPEN-35) | `pulsar-console` start-up narration | API-17 | proposed, not decided |
| Health and status fields report the synthetic backend | `console-http::routes::monitor` (`/health`, `/v1/status`); field names open under OPEN-35 | API-06 (PLAN-1) | planned |
| Permanent "Synthetic engine: no real model" badge | `console/web/` chat, monitor, models and settings views (and the sidebar edits of WEB-07) | WEB-07 (PLAN-1) | planned |
| Model catalog ships with no real entries; real entries need the owner's approval | catalog manifest | OPS-14 (PLAT-3.3) | planned |
| Vendor templates never committed; no bundled fallback | template provider and start-up selection | PRM-02, PRM-08, CNF-11 (LIC-1) | planned |
| No crate under `console/` depends by path on anything outside it (ADR 0008 decision 7) | `console/tools/check-boundary.sh`, path-deps check; ENG-19 adapter depends on nothing outside `console/` | M0 tooling; ENG-19 | check committed in M0; ENG-19 planned |

A change that adds, moves or removes an enforcement point updates this table, and the
rest of this note where it is affected, in the same change. This is part of the
[per-task gate](../../specs/022-console-serving-parity/tasks.md#per-task-gate-before-commit)
in `tasks.md`. Every row of the table above is an enforcement point.

The seam contract stays a draft, and ENG-01 stays unticked, until the engine track's
review of it is recorded (FR-039 in the
[feature specification](../../specs/022-console-serving-parity/spec.md); seam question
Q12, open item OPEN-30). Who on the engine track reviews it, and in what form, is not
decided; reaching the engine track goes through the owner. The shape of the provenance type
may change with that review. The rule itself does not.

## Record of changes to this note

- 2026-11-14: written at the owner's request after checkpoint 1; nothing implemented yet.
- 2026-11-14: ENG-01 (commit `6200f4ac`) recorded the provenance type and the guard,
  `require_synthetic`, with the tests that pin them; no call site exists yet (ENG-10,
  API-08).
- 2026-11-15: ENG-02 (commit `c86cf84f`) recorded the scripted engine's synthetic
  provenance and default model name, and the test-only `NotSyntheticEngine` for the refusal
  tests, with the tests that pin them; still no call site of the guard (ENG-10, API-08).
- 2026-11-15: ENG-10 (commit `4e7c438a`) recorded the call of the guard on every admission
  path of the turn driver, in its single admission step `Host::admit`, with the nine tests
  that pin it. The refusal at process start (API-08), the line-protocol declaration of
  provenance, the health and status fields and the badge are still planned.
- 2026-11-15: API-08 (commit `5b327fa8`) recorded the refusal at process start
  (`pulsar_console::run` and `pulsar_console::start` through `TurnDriver::start`), pinned
  by the two spawned-process tests and the two in-process tests, and the start-up line of
  lead decision LD46 (`pulsar_console::SYNTHETIC_ENGINE_LINE`); the model-name rule now
  records that a run config's `model_name` replaces the default name (LD53, owner item
  OPEN-62). The line-protocol declaration, the health and status fields and the badge are
  still planned.
