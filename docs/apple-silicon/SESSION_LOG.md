# Apple Silicon session log

## 2026-08-05 — pre-flight and repository bootstrap

Scope: inspect the host and source tree, preserve inherited work, establish the
independent PulsarMLX identity, validate the narrow macOS baseline, bootstrap
documentation and Spec Kit, add minimal CI, commit, and push. The explicit
stop point is before any MLX backend implementation.

### Read-only audit

The session began with read-only diagnostics before any installation or file
modification. The audit recorded:

- workspace: `/Users/mhedhli/Documents/Coding/PulsarMLX`;
- host: macOS 26.0 build 25A354 on a native arm64 Mac Studio with Apple M1
  Ultra and 128 GiB unified memory;
- storage: 1.8 TiB filesystem, 1.6 TiB used, 210 GiB available (89% full);
- selected developer tools: standalone Xcode Command Line Tools 26.2 and Apple
  Clang 17.0.0; full Xcode was not selected;
- Git 2.50.1 and GitHub CLI 2.92.0, authenticated to GitHub without recording
  credentials or token scopes;
- Homebrew Rust/Cargo 1.97.1 targeting `aarch64-apple-darwin`, with no
  `rustup` installation;
- Python 3.14.6 with no active virtual environment and no importable MLX
  package; and
- CMake 4.3.2 and pkg-config 3.0.5 available, with Ninja absent.

No secrets, hardware identifiers, or authentication material were recorded.
The complete commands and sanitized results are in
[../preflight/ENVIRONMENT.md](../preflight/ENVIRONMENT.md).

### Preserved repository state

The initial worktree was clean on local `main` at `12c2406`, two commits ahead
of upstream `183a54b`. The only remote was then named `origin` and pointed to
`https://github.com/giannisanni/pulsar.git`. Existing work was preserved
without reset, clean, stash, checkout, rebase, or history rewrite:

| Commit | Preserved work | Verification in this session |
| --- | --- | --- |
| `a5901d5` | `docs/apple-silicon/UPSTREAM_ARCHITECTURE.md` source and seam audit | `git show --check a5901d5` passed; runtime claims remain explicitly unverified. |
| `12c2406` | macOS workflow and the Linux cfg gate above `handle_chat` | `git show --check 12c2406` and the local Rust baseline passed. |

Ignored content was inventoried rather than removed: an untracked/ignored
`Cargo.lock` of about 40 KiB and approximately 936 MiB under `target/`.
Detailed crate, license, documentation, platform-assumption, and test
inventories are in
[../preflight/REPOSITORY_STATE.md](../preflight/REPOSITORY_STATE.md).

### Baseline validation

The preserved `#[cfg(target_os = "linux")]` immediately above `fn handle_chat`
was confirmed. Its signature and body were not altered during this session.

| Exact command | Actual outcome |
| --- | --- |
| `cargo check --workspace --all-targets` | Passed, exit 0. Emitted one inherited `unused_mut` warning in `crates/quant/src/iq.rs` and 13 macOS serve dead-code warnings. |
| `cargo test --workspace --no-fail-fast` | Passed, exit 0. Ran 32 tests: 32 passed, 0 failed. Engine, kernels, and Linux-gated server targets each ran zero tests on macOS. |
| `cargo fmt --all -- --check` | Failed, exit 1. Reported differences in 25 pre-existing upstream Rust files; no files were formatted. |
| `cargo clippy --workspace --all-targets -- -D warnings` | Failed, exit 101. Stopped at `crates/kernels/build.rs:41` on `clippy::needless_borrows_for_generic_args`; no broad cleanup was made. |

The green checks prove the native macOS workspace baseline selected by cfg.
They do not prove MLX, Linux/CUDA, server, `io_uring`, or model-inference
behavior. Exact details are in
[../preflight/BASELINE_VALIDATION.md](../preflight/BASELINE_VALIDATION.md).

### Independent repository identity

The authorized GitHub account created the public independent repository
`MahdiHedhli/PulsarMLX`; `gh repo view` reported `isFork: false`. The original
remote was renamed, not deleted, producing this layout:

```text
origin    https://github.com/MahdiHedhli/PulsarMLX.git
upstream  https://github.com/giannisanni/pulsar.git
```

HTTPS is consistent with the authenticated GitHub CLI configuration. The
upstream commit graph remains intact; no squash, history rewrite, force-push,
or duplicate repository creation occurred.

At this drafting checkpoint, GitHub reported no default branch for the new
repository and the local branch still tracked `upstream/main`, so creation was
confirmed but publication was not yet complete. Final push and default-branch
status must be recorded only after GitHub confirms them.

### Documentation, Spec Kit, and CI checkpoint

At the time this log entry was drafted:

- the three pre-flight evidence documents existed;
- `README.md` and the root workspace repository URL had local identity edits;
- this backend design, limitation register, and session log were being added;
- the `specify` command was not yet installed and no Spec Kit feature
  directory existed; installation, initialization, constitution, feature
  specification, plan, tasks, research, contracts, and quickstart remained in
  progress for this pre-flight session; and
- `.github/workflows/macos.yml` existed locally with a `macos-15` arm64 check,
  but no GitHub Actions run had verified it.

This is a chronological checkpoint, not the final pre-flight result. The final
state—including generated Spec Kit artifacts, staged secret review, commit
hashes, push status, CI runner limitations, blockers, and continuation
instruction—belongs in `docs/preflight/PREFLIGHT_REPORT.md` after those actions
are actually complete.

### Spec Kit completion checkpoint

After the read-only audit, the session installed GitHub Spec Kit 0.15.2 as an
isolated `uv` tool from the official v0.15.2 tag and initialized the existing
repository with the Codex skills integration:

```sh
uv tool install specify-cli \
  --from git+https://github.com/github/spec-kit.git@v0.15.2
specify init --here --force --integration codex \
  --integration-options='--skills' --script sh
```

`specify version`, `specify check`, and `specify integration status --json`
passed. Initialization did not create a nested Git repository or replace
upstream source files. The committed project scaffold uses `.specify/`, the
official generated Codex skills under `.agents/skills/`, and active feature
`specs/001-apple-silicon-mlx`.

The generated and populated artifacts include the project constitution,
feature specification, implementation plan, Phase 0 research, data model,
backend/worker, tensor/quant, expert-source, and evidence contracts, validation
quickstart, requirements and design-readiness checklists, and implementation
tasks. The selected reference design is one persistent Python worker with
`mlx==0.32.0`, strict Q8_0 parity, additive positional expert reads, synthetic
routed-MoE validation, and a gated external Qwen3-30B-A3B Q8_0 candidate. These
are planning decisions, not executed capabilities.

The installed 0.15.2 scaffold does not contain an
`.specify/scripts/bash/update-agent-context.sh` hook; an attempted invocation
reported `no such file or directory`. No substitute script was invented. The
version's available prerequisite, plan, task, integration, and health checks
are used instead.

The final read-only Spec Kit analysis found 24 functional requirements, 12
success criteria, and 78 unique sequential tasks (39 marked as parallelizable)
across five independently checkpointed user stories. Every FR and SC is
explicitly represented in the plan's stage traceability; task IDs are complete
from T001 through T078; no unresolved clarification/template marker remains.
The trusted real-model oracle and exact reachable graph depth remain a declared
pre-US4 admission gate, not a blocker for the earlier device, tensor, storage,
quantization, or synthetic milestones. No implementation was performed by the
analysis step.

### Implementation stop

No MLX package was installed during the initial audit, no Apple backend source
was added, no model weights were acquired, and no MLX operation or inference
was claimed. Development must stop after pre-flight publication and resume
only after the pre-flight report is reviewed and an explicit implementation
session begins. The next implementation session should take its requirements
from Spec Kit and use [BACKEND_DESIGN.md](BACKEND_DESIGN.md) as supporting
engineering guidance.
