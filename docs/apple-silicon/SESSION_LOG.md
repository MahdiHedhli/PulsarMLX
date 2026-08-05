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

### Publication and CI result

The complete pre-report change set was reviewed in four staged groups. Each
group passed `git diff --cached --check` plus credential-prefix,
forbidden-file, model-weight, and large-diff checks before commit. A final
`upstream/main...HEAD` scan also passed, the retained `LICENSE` was unchanged,
and no model file, credential, private key, private machine identifier, cache,
or generated binary was committed.

Focused commits before the report:

- `530e3068563775672d7e75f7e9e5437b7f915408` —
  `build: prepare reproducible PulsarMLX workspace`;
- `aa9ae0524d215d0d5055ff18881cb8814ffec5fc` —
  `docs: initialize PulsarMLX project and upstream attribution`;
- `5c1370f2ac29bedd7418c26be3c3a86342467796` —
  `docs: bootstrap GitHub Spec Kit workflow`; and
- `733dce565c8b2700d500e8e14fdf36f7fac2dd47` —
  `ci: add macOS baseline validation`.

`git push -u origin main` succeeded without force. GitHub confirmed the public,
independent `MahdiHedhli/PulsarMLX` repository, default branch `main`, commit
`733dce5` at `origin/main`, and the preserved `upstream` remote. Private
vulnerability reporting is enabled.

The push-triggered run was not visible in the first immediate query. After
GitHub reported the workflow as active, the configured `workflow_dispatch`
trigger was invoked explicitly. GitHub subsequently showed both
[push run 30977591362](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/30977591362)
and [manual run 30977589181](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/30977589181)
for the same commit; both completed successfully. The jobs reported
`macos-15-arm64`, native `arm64`, macOS 15.7.7 build 24G720, rustc/Cargo 1.97.1,
and passed the exact all-target check and no-fail-fast test commands with 32
tests. They are Cargo baselines only, not MLX or model evidence.

### Implementation stop

No MLX package was installed during the initial audit, no Apple backend source
was added, no model weights were acquired, and no MLX operation or inference
was claimed. Development must stop after pre-flight publication and resume
only after the pre-flight report is reviewed and an explicit implementation
session begins. The next implementation session should take its requirements
from Spec Kit and use [BACKEND_DESIGN.md](BACKEND_DESIGN.md) as supporting
engineering guidance.

## Implementation session: setup checkpoint

The explicitly authorized implementation session began from clean commit
`372b9dd433f61e17048e75eda9505dd65e263275`. The Spec Kit prerequisites and
both committed checklists passed before source changes. No extension pre-hook
was registered.

Task T001 re-ran the exact baseline before implementation:

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
```

Both exited zero; the test command ran 32 tests with zero failures. The same
inherited `quant` `unused_mut` and 13 macOS `serve` dead-code warnings remained.
The sanitized environment, remotes, commit, exact commands, results, warnings,
and exclusions are committed in
`docs/validation/implementation-baseline.json`.

Tasks T002–T004 added empty backend-neutral `backend` and Apple worker-client
`mlx-backend` crates as additive workspace members. Focused
`cargo check -p backend -p mlx-backend --all-targets` passed. No inherited
workspace member, default, Linux/CUDA feature, or runtime selection changed.

Tasks T005–T006 added the native Python package policy and `uv.lock`. The lock
pins `mlx==0.32.0`, `mlx-metal==0.32.0`, and Darwin arm64 wheels only. The local
ignored environment selected native CPython 3.12.13; `uv sync --frozen` and a
subsequent offline frozen sync passed. Installed wheel metadata reported
`cp312-cp312-macosx_26_0_arm64` for MLX and
`py3-none-macosx_26_0_arm64` for MLX-Metal; the extension inspected as Mach-O
arm64. This setup evidence does not claim Metal availability, GPU selection,
evaluated work, numerical correctness, or inference.

## Implementation session: foundational contract checkpoint

Tasks T007–T009 added the required contract tests first. Each focused suite was
run before its implementation and failed with unresolved public API imports,
establishing the intended red state. Tasks T010–T014 then added only semantic,
backend-neutral Rust types:

- bounded errors with private-path redaction;
- explicit backend/device selection and immutable unavailable,
  available-unevaluated, and evaluated capability reports;
- checked tensor shapes, orientation, dtypes, layouts, dense/Q8_0 byte counts,
  synchronization, and bounded exact or absolute/relative comparisons; and
- quantization/model compatibility, validation/evidence lifecycle, independent
  memory gauges, and correctness-gated benchmark records.

Validation passed:

```sh
cargo test -p backend
cargo clippy -p backend --all-targets -- -D warnings
```

The focused test run executed 32 tests with zero failures, and strict focused
Clippy passed. The exact workspace check passed, and the exact no-fail-fast
workspace test gate then executed 64 tests with zero failures (the inherited
32 plus 32 new backend contract tests). The known inherited `quant` and macOS
`serve` warnings remained unchanged. The public API exports no CUDA handles,
Python objects, MLX arrays, device pointers, streams, or allocation mechanisms.
This checkpoint proves contract invariants only; no backend work was executed.

## Implementation session: US1 evaluated device checkpoint

Tasks T015–T023 added test-first bounded protocol, worker lifecycle, runtime
discovery, explicit MLX GPU probing, and the `pulsar-mlx device-smoke` command.
The worker uses exact MLX 0.32.0 in native arm64 CPython 3.12.13, emits NDJSON
only on its protocol stdout, negotiates protocol and capability limits, assigns
monotonic request IDs, and has bounded timeout/crash/EOF/cleanup handling.

On immutable code commit `4ff4301af56904d4125f72ebeddee60e13f706d0`,
the real device command selected `apple-mlx` and `gpu`, evaluated and
synchronized a nonsymmetric float32 matmul, and matched the independent scalar
oracle `[58, 64, 139, 154]` exactly. MLX active/cache/peak and process RSS are
recorded as independent gauges; no overlapping total is reported. The command
did not load a model, execute a quantized operation, generate tokens, serve a
request, or exercise Linux/CUDA.

Exact post-commit validation passed:

```sh
PYTHONPATH=python uv run python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
cargo test -p mlx-backend --test worker_contract
cargo run -p mlx-backend --bin pulsar-mlx -- device-smoke \
  --backend apple-mlx --device gpu \
  --evidence docs/validation/mlx-device-smoke.json
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
```

The Python suite ran 13 tests, the fake-worker suite ran 12, and the exact
workspace test gate ran 93 Rust tests, all with zero failures. The inherited
`quant` `unused_mut` and 13 macOS `serve` dead-code warnings remained. The
sanitized actual result is in `docs/validation/mlx-device-smoke.json`.

## Implementation session: US2 tensor and Q8_0 checkpoint

Tasks T027–T034 froze seven nonsymmetric fixtures, observed the strict scalar
and worker suites fail before implementation, then added panic-free Q8_0 row
decode/matvec, evaluated MLX tensor operations, a control-only `run_fixture`
protocol, and `validate-fixtures`. Fixture requests contain only bounded IDs,
device selection, and `allow_fallback=false`; tensors, weights, encoded bytes,
and base64 data do not cross NDJSON.

On immutable code commit `c53f21e7c98bfa2288690a3662c6f6e10857a685`,
all seven MLX cases were evaluated and synchronized on `gpu`. Elementwise,
matmul, embedding, residual, and Q8_0 dot matched exactly. RMS norm had maximum
absolute error `5.258477320246868e-08`; router softmax had maximum absolute
error `6.977297206667289e-08`, and its tied top-k IDs matched exactly. Both
were inside their predeclared tolerances. The strict Rust Q8_0 suite passed 14
cases covering complete blocks, signed extrema, two scales, exact sizes,
overflow, non-finite rejection, and unchanged destinations on error.

Exact validation passed:

```sh
cargo test -p backend
cargo test -p quant --test q8_0_reference
PYTHONPATH=python uv run python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
cargo test -p mlx-backend --test tensor_contract
cargo run -p mlx-backend --bin pulsar-mlx -- validate-fixtures \
  --manifest fixtures/mlx/manifest.json \
  --evidence docs/validation/mlx-tensor-fixtures.json
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
```

The backend suite ran 32 tests, strict Q8_0 ran 14, Python ran 21, the Rust
fixture contract ran 7, and the workspace gate ran 114 Rust tests, all with
zero failures. The existing `quant` `unused_mut` and 13 macOS `serve`
dead-code warnings remain. Linux/CUDA execution of the shared change is
pending and is not claimed safe by runtime evidence.

## Implementation session: US3 contract checkpoint

Tasks T039–T041 added focused contracts before implementation. The portable
source suite covers validated layouts, checked exact ranges, partial and
interrupted positional reads, zero-progress and truncation failures, ordered
all-or-error batches, owned payload lifetime, and a non-cloneable result type.
Its focused command failed only because the new additive source API was not
yet present. The scalar and worker routed-MoE suites likewise failed only on
the absent `RoutingPlan` and worker `moe` module.

```sh
cargo test -p stream --test positional_source
cargo test -p backend --test routing_contract
PYTHONPATH=python uv run python -m unittest \
  python/pulsar_mlx_worker/tests/test_routed_moe.py -v
cargo test -p stream --test linux_uring_preservation
```

The Linux-only preservation suite keeps the inherited `io_uring` API,
target selection, split routing, aligned payload windows, and payload-covered
EOF behavior explicit. On this macOS host its focused command passed with zero
tests executed due to the target gate. Desired rejection of a completion
shorter than the logical payload is encoded as an ignored Linux test because
the inherited implementation currently accepts it. No Linux runtime result or
cross-platform safety claim is made.

Task T044 implemented the backend-neutral scalar routing oracle. It rejects
invalid dimensions, cardinality overflow, and non-finite inputs; selects by
score descending with expert ID ascending for exact ties; normalizes only the
selected scores; emits an ascending deduplicated expert request plan; and
performs checked scalar weighted aggregation. Validation passed with 8 focused
routing tests, 40 total backend tests, and strict focused Clippy:

```sh
cargo test -p backend --test routing_contract
cargo test -p backend --all-targets
cargo clippy -p backend --all-targets -- -D warnings
```

Task T043 added an independent portable positional source without changing the
inherited Linux fetcher. It validates contiguous single/split layouts and every
batch range before reading, advances through partial reads, retries
`Interrupted`, rejects zero progress and post-open truncation, preserves input
order, and returns owned non-cloneable payloads. The focused suite passed 14
tests; the full stream package passed 15 active tests on macOS, with the
Linux-only preservation suite correctly selecting zero tests. Strict focused
Clippy also passed:

```sh
cargo test -p stream --test positional_source
cargo check -p stream --all-targets
cargo test -p stream
cargo clippy -p stream --all-targets -- -D warnings
```

Task T045 implemented the bounded synthetic routed-MoE MLX graph. The worker
fully validates fixture structure, split-shard bytes and SHA-256 identities,
expert ranges, routing and aggregation oracles, and the deduplicated fetch plan
before importing or accessing MLX. Native execution explicitly selected the
GPU, evaluated and synchronized the graph, preserved routes `[1, 2, 3, 1]`,
and returned `[2.0, 2.0, 4.069116592407227, 4.0378828048706055]`. The maximum
output absolute error was `4.759696965450644e-07`, within the committed
`1e-5` tolerance. All 7 focused tests passed:

```sh
python3 -m py_compile python/pulsar_mlx_worker/moe.py
PYTHONPATH=python uv run --frozen python -m unittest \
  python/pulsar_mlx_worker/tests/test_routed_moe.py -v
```

Task T046 connected that graph through a control-only
`run_synthetic_moe` request and the `validate-synthetic-moe` CLI. The request
carries only the fixture ID, `gpu`, and `allow_fallback=false`. The worker and
Rust client independently enforce the committed topology, routes, weights,
expert offsets, exact SHA-256 payload identities, scalar output oracle,
evaluated/synchronized lifecycle, and non-overlapping memory gauges. A real
end-to-end command wrote bounded temporary evidence and passed:

```sh
PYTHONPATH=python uv run --frozen python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
cargo test -p mlx-backend --test synthetic_moe
cargo clippy -p mlx-backend --all-targets -- -D warnings
cargo run -p mlx-backend --bin pulsar-mlx -- validate-synthetic-moe \
  --fixture fixtures/mlx/routed-moe-v1.json \
  --evidence /tmp/pulsarmlx-t046.Kdstqo/evidence.json
```

The Python suite ran 28 tests and the Rust synthetic protocol suite ran 4,
all with zero failures. The evaluated output and maximum error matched the
T045 results. Committed evidence is generated separately by T048.

Task T048 executed the exact committed-evidence command on immutable commit
`8abdfe0450e9cfa44ef7d6e52c58e7f58f74e4fd` and wrote
`docs/validation/synthetic-moe-v1.json`. It records native arm64 MLX 0.32.0,
explicit GPU selection with no fallback, evaluated and synchronized work,
routes `[[1, 2], [3, 1]]`, normalized weights, three exact expert payload
SHA-256 identities, the four-value actual output, comparison errors, and
independent memory gauges. The command exited zero:

```sh
cargo run -p mlx-backend --bin pulsar-mlx -- validate-synthetic-moe \
  --fixture fixtures/mlx/routed-moe-v1.json \
  --evidence docs/validation/synthetic-moe-v1.json
```

This is synthetic-only evidence; it does not establish a model loader,
tokenization, token generation, serving, or Linux/CUDA runtime behavior.

Tasks T047 and T049 recorded the exact portable-source and post-change
workspace results on implementation commit
`8abdfe0450e9cfa44ef7d6e52c58e7f58f74e4fd`. The focused positional suite ran
14 active tests with zero failures, covering exact single/split-shard bytes,
boundaries, invalid layouts and ranges, partial/interrupted/zero reads,
truncation, all-or-error batches, ordering, duplicate ranges, and owned payload
lifetime. The 32-bit allocation-width test was not compiled on this arm64
64-bit host.

The exact post-change workspace gates both exited zero:

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
```

The workspace test command executed 140 Rust tests with zero failures. The
inherited `quant` `unused_mut` and 13 macOS `serve` dead-code warnings remain.
The detailed results are in `docs/validation/portable-expert-source.json`;
they do not claim Linux `io_uring` or CUDA execution.

Task T050 established the exact shared-boundary status in
`docs/validation/linux-cuda-shared-boundary.json`. The named Linux preservation
command and inherited kernel selftest subcommand both exited zero on this
macOS host, but every relevant target was cfg-excluded: the former ran zero
tests and the latter emitted three zero-test results. No Linux, `io_uring`,
`O_DIRECT`, CUDA compile, or CUDA runtime claim follows from those exits.

Static comparison found the inherited engine, kernels, Linux-only stream
dependencies, selection, and defaults unchanged from the locally recorded
`upstream/main`. The additive positional source does not replace the inherited
Linux fetcher. The payload-short CQE assertion remains explicitly ignored and
unverified because the inherited fetcher currently accepts that case. A
supported Linux host and a Linux/NVIDIA/CUDA host or suitable CI are required
to advance this boundary; `cross_platform_safe` remains false.

### Native smoke CI boundary correction

The first post-US3 macOS baseline run exposed a packaging-boundary regression:
`cargo test --workspace --no-fail-fast` reached the native device integration
test on the arm64 runner, but the baseline job intentionally does not create a
project `.venv` or install MLX. The test failed with the explicit worker error
`the frozen project Python environment is unavailable; run uv sync --frozen`;
this was not an accelerator or numerical failure.

The native integration test is now marked ignored by default with its frozen
MLX prerequisite stated in the test metadata. It remains runnable explicitly
after `uv sync --frozen`, while the ordinary Cargo baseline continues to run
all Rust-only device identity, fallback, lifecycle, and comparison contracts.
The workflow commands and inherited Linux/CUDA behavior were not changed.
