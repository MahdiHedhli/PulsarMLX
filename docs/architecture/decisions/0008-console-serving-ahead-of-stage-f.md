# ADR 0008: Build the PulsarMLX Console serving layer ahead of Stage F, on synthetic backends only

- **Status**: Accepted by the owner on 2026-11-14
- **Date**: 2026-11-14
- **Feature**: `specs/022-console-serving-parity`, branch `feat/022-console-serving-parity`
- **Relates to**: ADR 0001 (Rust owns the shipping runtime), ADR 0004 (qualify donor code before adoption)

## Context

PulsarMLX has no serving layer that runs on Apple Silicon. The inherited `crates/serve`
builds its server only for Linux with CUDA; on any other target its `main` reports that it
requires Linux and CUDA and exits. A
standalone Rust synthetic serving crate, `crates/serve-synthetic`, was merged and then
reverted at commit `005867d8` on 2026-09-20 because its own qualification gate was red on
the runner's toolchain; the work is kept at tag `archive/2026-09-21/feat/openai-serving`
(branch head `4e25f1b4`). The only component that puts real GLM-5.3 Flash tokens behind
an HTTP API is the Python/MLX research server, which is a research reference and not a
shipping path.

The [strategy](../../roadmap/PULSARMLX_STRATEGY.md) places serving last. Stage F, "product
surface", allows OpenAI-compatible serving "only after the local runtime is stable", and
the [optimization roadmap](../../roadmap/OPTIMIZATION_ROADMAP.md) puts OPT-08, persistent
serving, after native generation and streaming equivalence. The strategy's current
direction also says that it does not authorize serving runs. Two of its non-goals bear
directly on this decision: "No wholesale rewrite from scratch" and "No unqualified donor
dependency".

project-maya (`github.com/mw00/project-maya`, MIT) has what PulsarMLX lacks: a mature
serving layer in its `serve/` directory (OpenAI, Anthropic and Responses dialects, tool
calls, MCP, attachments, model management) and a browser dashboard, behind a narrow
engine seam that can be exercised without a GPU. On 2026-11-14 the owner approved a plan
to rebuild that serving layer and front end in Rust inside PulsarMLX without disturbing
the active Rust engine track. This ADR records the decisions in that plan that change
project direction or scope. The plan's technical content is carried into the feature's
Spec Kit artifacts under `specs/022-console-serving-parity/`.

## Decision

1. **The serving layer and dashboard are built now, in isolation, on synthetic backends
   only.** The product is named PulsarMLX Console, with the binary `pulsar-console`. Every
   engine in this increment is synthetic: a scripted in-process engine, a line-protocol
   child-process client driven by PulsarMLX-authored Rust fake engine binaries, and a test
   adapter shaped like the engine track's coordinator. Nothing in this increment serves a
   real model, and the strongest claim any part of it can earn is "qualified on synthetic
   backends". The dashboard shows a permanent "Synthetic engine: no real model" badge and
   `/health` reports the same. This ADR is the specific authorization, referred to from
   the strategy, for building and testing this serving layer ahead of Stage F. It does not
   authorize serving a real model: real-model serving acceptance remains gated exactly as
   Stage F and OPT-08 describe, and the engine sequence in the strategy is unchanged.

2. **project-maya at commit `7e68a30f` (v1.1.63) is the donor under ADR 0004.** It is
   qualified as a donor by the record
   [`docs/upstream/PROJECT_MAYA.md`](../../upstream/PROJECT_MAYA.md), with benefit
   recorded as a pre-adoption estimate and measured at close-out; sync rules are in
   [`PROJECT_MAYA_SYNC.md`](../../upstream/PROJECT_MAYA_SYNC.md). Each ADR 0004
   requirement is made concrete there: source and license review of the pinned commit;
   attribution through provenance headers on adapted and translated files, the license
   texts in `console/LICENSES/`, and a matching section in `NOTICE.md`; independent tests
   written from PulsarMLX contracts by a different author than the one who ported the
   behavior; compatibility analysis in the deviation register; and benefit as adapted
   lines against a clean-rewrite estimate plus feature coverage on a named checklist,
   estimated before adoption and measured at close-out. ADR 0004 asks for measured benefit
   before adoption, so this ordering is recorded as an exception in the feature plan, and
   the owner accepted it on 2026-11-14 (OPEN-27, settled). project-maya is never a runtime
   dependency: the product links no donor package and launches no donor process. Donor
   code enters only as adapted files (the Phase 1 dashboard) or as Rust reimplementations
   under the qualification record, and project-maya's own server runs only in a manual
   GitHub Actions reference job. No donor benchmark is presented as PulsarMLX evidence.
   project-maya is named wherever attribution or provenance requires it and is never used
   as product identity.

3. **The target is full behavioral parity with project-maya's `serve/` at the pinned
   commit.** Driven by equivalent fake engines, the Rust implementation must show the same
   externally observable behavior for every route, stream format, error, configuration key,
   environment variable and persisted file, including where project-maya differs from the
   OpenAI or Anthropic specifications. Parity is measured by the parity ledger,
   `console/parity/ledger.json`, with one row per donor test method. Each row has exactly
   one disposition from the closed set defined in
   `specs/022-console-serving-parity/contracts/parity-ledger.md`: a Rust test, a recorded
   scenario, a web logic test, a shim run, a vendor-template render, an approved
   deviation, "not applicable" with a reason from a closed list, or pending (allowed before
   close-out only). That set refines the five dispositions named in the plan by giving shim
   runs and vendor-template renders their own values. A checker fails the build on a
   dangling row. Every intended difference is an entry in
   `specs/022-console-serving-parity/contracts/deviations.md`. The deviations approved with
   the plan are SEC-1 to SEC-7, PRIV-1, BRAND-1, BRAND-2, LIC-1, LIC-2, POL-1, PLAT-1 to
   PLAT-3 and FIX-1, together with PLAN-1 to PLAN-6, differences that the plan decides
   outside its deviation table; any further deviation needs the owner's approval.

4. **The front end is delivered in two phases.** Phase 1, in this increment, adapts
   project-maya's no-build JavaScript dashboard and serves it from the Rust server. Phase
   2, later, is a complete rewrite of the front end in Rust compiled to WebAssembly against
   the written UI-to-server contract. Attaching a real engine is Phase 3, which needs its
   own approval. The phases are recorded in the
   [console roadmap](../../roadmap/CONSOLE_ROADMAP.md).

5. **The archived serving crate is superseded as a merge candidate and kept as a design
   reference.** `crates/serve-synthetic` at tag `archive/2026-09-21/feat/openai-serving` is
   not re-merged. Its security posture (Host allowlist, Origin, content-type and token
   handling), its limits and its raw-HTTP tests are the reference for the HTTP posture of
   SEC-1 and for request limits, from the first HTTP work package on. Because it is
   PulsarMLX's own code, parts of it, its
   security tests in particular, may be reused inside `console/`.

6. **Launching any project-maya engine binary is out of scope.** `maya-metal` and every
   other project-maya engine binary are a donor runtime. Launching one would need its own
   ADR 0004 qualification and its own decision. The line protocol that child-process
   engines speak is written down as a PulsarMLX contract, with project-maya's protocol cited
   as prior art.

7. **The work lives in the standalone `console/` workspace and touches no file the engine
   track edits or hash-binds.** `console/` is a nested Cargo workspace with its own
   `[workspace]`, `Cargo.lock` and pinned `rust-toolchain.toml` (1.97.1), and it is not a
   member of the root workspace. No crate in it depends by path on anything outside
   `console/`. The work may touch only `console/**`, `specs/022-console-serving-parity/**`,
   `docs/console/**`, `docs/roadmap/CONSOLE_ROADMAP.md`, `docs/upstream/PROJECT_MAYA.md`
   and `PROJECT_MAYA_SYNC.md`, this ADR, `NOTICE.md`, `.github/workflows/console.yml`, and
   three small edits to `docs/roadmap/PULSARMLX_STRATEGY.md`, `README.md` and
   `CONTRIBUTING.md`. It never touches the root `Cargo.toml`, root `Cargo.lock`,
   `.github/workflows/macos.yml`, anything under `crates/`, `experiments/`, `fixtures/`,
   `scripts/` or `docs/research/`, `.specify/feature.json`, `.gitignore`, the root
   `pyproject.toml` or `uv.lock`. `console/tools/check-boundary.sh` checks this before every
   commit and in CI, including that the blobs of the root `Cargo.toml`, `Cargo.lock` and
   `macos.yml` are byte-identical to those at the merge base with `main`.

8. **CI for the console is a separate, path-filtered workflow with small blocking jobs.**
   `.github/workflows/console.yml` runs every job from `console/` on the pinned toolchain
   and asserts the compiler version. Its blocking jobs are preflight on Linux (boundary,
   ignored-file, staged-content and attribution checks), Rust on Linux, Rust on macOS
   arm64, and web logic tests under Node with no packages. Reference capture, the live
   differential against project-maya, vendor-template checks, the shim runs of two donor
   test files, SDK client tests, the toolchain drift canary and the browser end-to-end
   suite are manual `workflow_dispatch` jobs; the blocking jobs check the committed records
   of the shim runs and vendor-template renders (see `contracts/parity-ledger.md`).
   Whether `console.yml` becomes a required check is not decided; it is the owner's call
   at merge time.

## Consequences

- The strategy's non-goals still hold. The console adds a surface PulsarMLX does not have
  beside the engine track and rewrites nothing the runtime already provides, so it is not
  the wholesale rewrite the strategy rules out; and project-maya enters as a qualified
  donor, not as a dependency.
- PulsarMLX gains a second Cargo lockfile, a second toolchain pin and a second workflow.
  The root commands in `CONTRIBUTING.md` and the constitution's
  `cargo test --workspace` do not build `console/`; the console commands are documented
  separately, and the nested workspace is recorded as a constitution exception in the
  feature plan.
- `macos.yml` is frozen and its change classifier treats `console/`, `specs/` and a new
  workflow file as code. Every push of the feature branch therefore also runs the full
  native qualification, about 35 minutes of GitHub macOS runner time, and the branch is
  green only when `main`'s native jobs are. Pushes are batched at the owner's checkpoints,
  which the feature plan lists.
- No file the engine track edits or hashes changes, but merging still changes the tree
  identity of `main`, and engine evidence is bound to tree identity. Merge order must
  respect the engine track's tree-bound evidence and is decided with the owner. The
  plan's default is a merge commit, and engine branches are never asked to rebase.
- The Rust-owned runtime ships JavaScript and CSS assets for Phase 1. They run only in the
  browser; no Python process is required to serve, consistent with ADR 0001. This is also
  recorded as a constitution exception in the feature plan.
- Parity binds PulsarMLX Console to project-maya's observable behavior at one pinned
  commit, including its departures from the OpenAI and Anthropic specifications.
  project-maya moves quickly; re-pinning is a separate decision, and the committed
  reference corpus keeps the gate working without the donor.
- The inherited `crates/serve` remains untouched and Linux-only. The archived
  `crates/serve-synthetic` is not re-merged, so its revert note's re-merge procedure no
  longer applies; what is reused from it lands inside `console/`.
- The increment is large, its size estimates are soft, and it is ordered in milestones M0
  to M10 that each end reviewable, so the work can stop cleanly after any of them.
- Nothing in this increment changes what PulsarMLX can claim about real models. A future
  claim that the console serves a real model requires the Phase 3 decision and the
  qualification Stage F and OPT-08 already require. What must happen first, before the
  server may start an engine that does not report synthetic provenance, is listed in
  [`docs/console/ALLOWING_NON_SYNTHETIC_ENGINES.md`](../../console/ALLOWING_NON_SYNTHETIC_ENGINES.md).

## Open items

These are not decided by this ADR. Every open item of the feature, with who decides it,
is listed in the register in
`specs/022-console-serving-parity/checklists/analysis.md`; the ids below are its ids.

- OPEN-13: whether `console.yml` becomes a required check on `main`.
- OPEN-14: the merge order of the feature branch relative to engine-track branches with
  tree-bound evidence.
- OPEN-20: the Phase 2 front-end framework and toolchain.
- OPEN-28: any future re-pin of project-maya beyond `7e68a30f`.

OPEN-27, whether donor benefit may be estimated before adoption and measured at
close-out, against ADR 0004's order, was settled on 2026-11-14, when the owner accepted
that ordering.
