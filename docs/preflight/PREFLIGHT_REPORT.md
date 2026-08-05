# PulsarMLX Pre-flight Report

## Executive result

**Ready for bounded implementation after this report is reviewed.**

The independent PulsarMLX repository, upstream attribution, exact macOS Cargo
baseline, Spec Kit source of truth, repository hygiene, pre-report
documentation, and Apple Silicon CI are established and published. Local and
remote baseline checks pass. No MLX backend source was implemented, no MLX
package was installed, no model weight was acquired, and no inference claim
was made.

The next session must begin with the Spec Kit task list and stop after the first
independently validated device milestone or any declared stop condition.

## Machine environment

The read-only host snapshot was captured before installation or modification:

| Item | Observed result |
| --- | --- |
| Working directory | `/Users/mhedhli/Documents/Coding/PulsarMLX` |
| Host | Mac Studio, Apple M1 Ultra, native arm64, no Rosetta translation |
| Unified memory | 128 GiB (137,438,953,472 bytes) |
| macOS | 26.0 build 25A354 |
| Storage | 1.8 TiB total, 1.6 TiB used, 210 GiB available, 89% full |
| Developer tools | Xcode Command Line Tools 26.2 selected; macOS SDK 26.2; Apple clang 17.0.0; full Xcode not selected |
| Git | 2.50.1 (Apple Git-155) |
| GitHub CLI | 2.92.0; authenticated as `MahdiHedhli` over HTTPS; token values/scopes omitted |
| Rust | rustc 1.97.1, host `aarch64-apple-darwin`, Homebrew sysroot; `rustup` absent |
| Cargo | 1.97.1 |
| Python | 3.14.6, native arm64, no active project/Conda virtual environment |
| MLX | Absent from the active Python interpreter; not installed during preflight |
| Native utilities | CMake 4.3.2, pkg-config 3.0.5, `cc`/`clang`/`c++` available; Ninja absent |

The later authorized Spec Kit tool installation is isolated from the project
Python environment and is recorded in
[ENVIRONMENT.md](ENVIRONMENT.md).

## Repository state

Initial state:

- clean local `main` at `12c2406`, two commits ahead of upstream base
  `183a54b`;
- the only remote was upstream Pulsar under the name `origin`;
- ignored content was `Cargo.lock` (about 40 KiB) and `target/` (about 936 MiB);
- no staged, modified, deleted, standard untracked, or other ignored source
  work was discarded; and
- preserved prior-session commits were inventoried and verified rather than
  reset, stashed, cleaned, rebased, or rewritten.

Published state:

```text
main      tracks origin/main
origin    https://github.com/MahdiHedhli/PulsarMLX.git
upstream  https://github.com/giannisanni/pulsar.git
```

The upstream base remains an ancestor and no history was squashed, rewritten,
or force-pushed. The implementation/specification baseline was pushed through
commit `733dce565c8b2700d500e8e14fdf36f7fac2dd47`. The worktree was clean and
equal to `origin/main` at that post-push checkpoint. This report and its post-CI
status reconciliation form a final documentation-only commit; that commit's
push and clean/equal verification are necessarily recorded in the final
handoff rather than self-referenced here.

Detailed source, crate, license, cfg, Linux/CUDA/`io_uring`, documentation,
test, and CI findings are in
[REPOSITORY_STATE.md](REPOSITORY_STATE.md).

## Baseline validation

Local commands and actual results:

| Exact command | Actual result |
| --- | --- |
| `cargo check --workspace --all-targets` | Pass, exit 0 |
| `cargo test --workspace --no-fail-fast` | Pass, exit 0; 32 passed, 0 failed |
| `cargo fmt --all -- --check` | Fail, exit 1; differences in 25 pre-existing upstream Rust files; no files formatted |
| `cargo clippy --workspace --all-targets -- -D warnings` | Fail, exit 101; first error at `crates/kernels/build.rs:41`, `clippy::needless_borrows_for_generic_args` |
| `git diff --check` | Pass before focused commits |

The passing commands emitted one inherited `unused_mut` warning at
`crates/quant/src/iq.rs:133` and 13 dead-code warnings from Linux-oriented serve
helpers compiled on macOS. Engine, kernel, and Linux-gated server test targets
ran zero tests on macOS. The green result does not validate CUDA, `io_uring`,
the Linux server, or MLX.

The required `#[cfg(target_os = "linux")]` is immediately above
`fn handle_chat` in `crates/serve/src/main.rs`. It was already present in the
preserved `12c2406` commit; its signature and body were not changed in this
session.

The final pre-commit rerun again passed the exact workspace commands with 32
tests. [GitHub Actions run 30977589181](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/30977589181)
also passed both commands and ran 32 tests on the published commit.

Full results are in
[BASELINE_VALIDATION.md](BASELINE_VALIDATION.md).

## GitHub Spec Kit

- CLI: GitHub Spec Kit `specify` 0.15.2, installed from the official v0.15.2
  tag with the existing `uv` 0.11.17 tool manager.
- Initialization: completed in the existing repository with Codex integration,
  shell scripts, and generated agent skills; no nested Git repository.
- Health: `specify check` passed; `specify integration status --json` returned
  `status: ok`, zero missing/modified/invalid managed files; the prerequisite
  script found all feature documents and `tasks.md`.
- Workflow: installed `speckit` Full SDD Cycle v1.0.0 with specification and
  plan review gates.
- Active feature: `specs/001-apple-silicon-mlx`, recorded by
  `.specify/feature.json`.
- Constitution: version 1.0.0 with all 12 required project principles.
- Feature artifacts: specification, plan, research, data model, four interface
  contracts, quickstart, two quality checklists, and 78 sequential tasks across
  five user stories.
- Read-only analysis: 24 functional requirements and 12 success criteria are
  represented in the plan traceability; task IDs T001–T078 are unique and
  complete; no unresolved clarification/template marker remains.

The selected design is a persistent Python worker pinned to `mlx==0.32.0`, an
explicit evaluated-GPU proof, strict Q8_0 reference parity, additive exact
positional expert storage, synthetic routed-MoE validation, and a gated
external Qwen3-30B-A3B Q8_0 candidate. None is reported as implemented.

The generated 0.15.2 scaffold has no `update-agent-context.sh` hook. The
attempted hook command failed with `no such file or directory`; no substitute
was invented, and the version's available health, integration, prerequisite,
plan, and task tooling passed.

## Documentation created

- [README.md](../../README.md): experimental status, project identity,
  inherited/verified/planned/unsupported capability boundaries, baseline and
  Spec Kit continuation commands.
- [NOTICE.md](../../NOTICE.md): upstream Pulsar location, author/contributor and
  MIT attribution, derivative scope, and non-endorsement statement.
- [CONTRIBUTING.md](../../CONTRIBUTING.md): correctness-first, Spec Kit-driven,
  test/evidence, compatibility, and secret/weight contribution rules.
- [SECURITY.md](../../SECURITY.md): experimental support scope and private
  GitHub vulnerability-reporting path.
- [ENVIRONMENT.md](ENVIRONMENT.md): sanitized host/tool snapshot and authorized
  Spec Kit installation.
- [REPOSITORY_STATE.md](REPOSITORY_STATE.md): preserved work, Git history,
  remotes, crate architecture, platform assumptions, coverage, and verification
  boundaries.
- [BASELINE_VALIDATION.md](BASELINE_VALIDATION.md): exact Cargo, rustfmt, and
  Clippy results.
- [UPSTREAM_ARCHITECTURE.md](../apple-silicon/UPSTREAM_ARCHITECTURE.md):
  preserved prior-session source and backend-seam audit.
- [BACKEND_DESIGN.md](../apple-silicon/BACKEND_DESIGN.md): supporting staged
  Apple/MLX design and stop conditions subordinate to Spec Kit.
- [KNOWN_LIMITATIONS.md](../apple-silicon/KNOWN_LIMITATIONS.md): observed
  unsupported and unverified boundaries.
- [SESSION_LOG.md](../apple-silicon/SESSION_LOG.md): chronological audit,
  bootstrap, validation, Spec Kit, publication, and CI handoff.
- [Spec Kit feature directory](../../specs/001-apple-silicon-mlx/spec.md): source
  of truth for feature requirements, plan, research, contracts, quickstart,
  checklists, and tasks.

## CI status

`.github/workflows/macos.yml` runs the exact required Cargo commands on
GitHub's standard `macos-15` Apple Silicon runner, asserts `arm64`, records
macOS/Rust/Cargo identity, and deliberately does not gate on broad upstream
rustfmt or Clippy debt.

Confirmed run:

- run: [30977589181](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/30977589181);
- event: manual `workflow_dispatch`; no automatic run appeared after the
  initial push, and dispatch occurred after GitHub reported the workflow active;
- conclusion: success in 1 minute 8 seconds;
- commit: `733dce565c8b2700d500e8e14fdf36f7fac2dd47`;
- image: `macos-15-arm64`, release `20260727.0256`;
- environment: arm64, macOS 15.7.7 build 24G720, rustc/Cargo 1.97.1, host
  `aarch64-apple-darwin`; and
- result: exact check passed; exact test command passed with 32 tests.

Runner limitation: the standard hosted Apple Silicon runner validates the Cargo
baseline, not parity with the local 128 GiB M1 Ultra. It does not install MLX,
run device/model fixtures, acquire weights, test Linux/CUDA/`io_uring`, or
provide giant-model correctness, memory, storage, or performance evidence.

## Commits

Preserved prior-session commits:

- `a5901d52f6fe1792476ce4975e1ed39db8f82805` —
  `docs: map upstream architecture and Apple Silicon seams`
- `12c24069e6c8ff4c8dde4670e46ef5842e30aafd` —
  `build: establish macOS workspace baseline`

Focused commits created and pushed in this session before the report:

- `530e3068563775672d7e75f7e9e5437b7f915408` —
  `build: prepare reproducible PulsarMLX workspace`
- `aa9ae0524d215d0d5055ff18881cb8814ffec5fc` —
  `docs: initialize PulsarMLX project and upstream attribution`
- `5c1370f2ac29bedd7418c26be3c3a86342467796` —
  `docs: bootstrap GitHub Spec Kit workflow`
- `733dce565c8b2700d500e8e14fdf36f7fac2dd47` —
  `ci: add macOS baseline validation`

No commit was amended, squashed, rebased, or force-pushed. The documentation-only
commit containing this final report is intentionally not self-referenced by
hash; its pushed identity is verified in the final handoff.

## GitHub repository

- Identity: `MahdiHedhli/PulsarMLX`
- URL: <https://github.com/MahdiHedhli/PulsarMLX>
- Visibility: public
- Repository kind: independent (`isFork: false`)
- Default branch: `main`
- Description: “Experimental Apple Silicon and MLX runtime for oversized
  Mixture-of-Experts models, derived from Pulsar.”
- Push: `git push -u origin main` succeeded without force; local `main` tracks
  `origin/main`.
- Upstream: preserved as `https://github.com/giannisanni/pulsar.git`.
- Security: private vulnerability reporting is enabled.

## Known limitations

- MLX is not installed in the active project environment and no MLX backend,
  device operation, tensor proof, model load, serving path, or inference exists.
- Linux/CUDA/`io_uring` build and runtime parity was not executed on this Apple
  host. Shared future changes cannot be labeled cross-platform-safe without
  suitable evidence.
- macOS-selected engine, CUDA-kernel, and Linux server targets have zero runtime
  tests; the 32-test baseline covers portable cfg-selected behavior.
- Repository-wide rustfmt and strict Clippy are not green because of documented
  upstream debt; neither is a CI gate.
- Disk use was already 89% at inspection. Recheck headroom before any external
  model acquisition or conversion.
- The standard CI runner is resource-constrained and is not a giant-model or
  local-host performance proxy.
- The real-model oracle, exact reachable output boundary, immutable local
  checksum, tensor inventory, and memory budget are deliberate mandatory US4
  gates, not current capabilities.

## Blockers

There is **no blocker to starting the bounded T001/US1 implementation sequence
after operator review**.

Observed diagnostic failures are non-blocking upstream debt and reproduce with:

```sh
cargo fmt --all -- --check
cargo clippy --workspace --all-targets -- -D warnings
```

The first exits 1 with differences across 25 upstream files. The second exits
101 first at `crates/kernels/build.rs:41`. Do not broaden the first Apple
milestone to clean either issue.

The following later gates block only the claims they protect:

- absence/failure of native arm64 MLX/Metal evaluated-device proof blocks US1
  success and all later MLX claims;
- unavailable Linux/CUDA hardware blocks a cross-platform-safe label for shared
  changes, but must be recorded as unverified rather than fabricated; and
- unresolved oracle, provenance, compatibility, checksum, disk, or memory
  admission blocks US4 before any model execution.

## Recommended next action

Implement only the first Spec Kit increment: T001–T014 setup/foundational
contracts followed by T015–T026 User Story 1. The bounded outcome is an explicit
persistent-worker contract and either a correctly evaluated MLX GPU smoke proof
or a truthful blocked record. Stop for review at the US1 checkpoint; do not
start tensor, storage, model, performance, or Metal optimization work in that
session unless separately authorized.

## Exact continuation command

```sh
cd /Users/mhedhli/Documents/Coding/PulsarMLX
codex 'Use $speckit-implement for specs/001-apple-silicon-mlx. Start at T001, stop after the first independently validated Apple baseline/device milestone, and do not bypass any stop condition.'
```

## Stop point

Pre-flight inspection, independent repository creation, attribution,
documentation, Spec Kit planning, hygiene, local validation, focused baseline
commits, baseline publication, and Apple Silicon CI are complete. This report
closes the documentation; its commit/push identity is verified in the final
handoff. This session stops here and does not begin MLX backend implementation.
