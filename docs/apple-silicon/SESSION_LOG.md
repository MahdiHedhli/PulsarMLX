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

GitHub Actions run
[`31010989312`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31010989312)
then passed on the arm64 `macos-15` runner for commit `892fc30`. Runner
architecture verification, `cargo check --workspace --all-targets`, and
`cargo test --workspace --no-fail-fast` all completed successfully.

### US4 pre-download admission milestone

Tasks T051-T054 freeze the real-model admission boundary without acquiring,
opening, inventorying, or executing any model bytes.

T051 selects the independent oracle before any Apple real-model output. It
pins official llama.cpp `gguf-py` at commit
`b06aa774c03dbbb624e726664b714a57d1f49815`, component version 0.19.0, and a
strict Q8_0 expert-projection case. The exact UTF-8 prompt is transformed by a
specified SHA-256-based float32 probe adapter into 2,048 values; this is
transparently not Qwen tokenization, embedding, or prompt inference. The named
comparison is expert 0, output rows 0 through 15 of
`blk.0.ffn_gate_exps.weight`, with 16 float32 outputs, scalar left-to-right
accumulation, an independent NumPy self-check, and frozen absolute/relative
tolerances. The oracle command is specified but has not been executed.

T052 records official immutable Qwen repository revision
`e4d4bafdfb96a411a163846265362aceb0b9c63a`, exact filename
`Qwen3-30B-A3B-Q8_0.gguf`, public ungated access, Apache-2.0 license,
`qwen3moe` metadata, published size 32,483,931,648 bytes, and published
expected LFS SHA-256
`4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c`.
The size and digest are not local measurements; local identity and tensor
inventory remain unresolved by design until T055.

T053 admits only the same 16-row expert gate projection under conservative,
non-overlapping budgets. At observation time 224,489,091,072 disk bytes were
available; the acquisition/staging/output/headroom gate requires
134,761,081,856 bytes. The host has 137,438,953,472 unified-memory bytes; the
bounded process envelope plus mandatory 32 GiB system headroom requires
42,949,672,960 bytes. Both pre-download budget gates pass, but every disk,
pressure, allocator, mapping, and footprint observation must be rechecked at
execution time.

T054 reviewed inherited parsing, tokenization, Linux engine, CUDA kernels,
target-specific stream dependencies, selection, and defaults at commit
`892fc3000349bfd7e314bcf8c15f21084db82051`. The parser, tokenizer, engine,
kernels, and Linux-only stream dependency configuration remain identical to
the locally recorded `upstream/main`. Portable storage and Q8_0 reference
modules are additive, and the new routing oracle is not wired into inherited
selection. No observed regression triggered the stop rule. No suitable
Linux/CUDA runtime result exists, so `cross_platform_safe` remains false.

The next task is T055. The active implementation directive explicitly permits
a very large model download when the active task requires it and a smaller
fixture cannot validate the milestone. T055 requires the exact real artifact,
and its local identity and tensor inventory cannot be established from a
smaller fixture, so that condition authorizes acquisition of this exact public
artifact outside the repository. Before transfer, recheck disk and pressure;
after transfer, verify the complete local size and SHA-256 and inventory every
tensor role/type before executing anything.

### T055 external artifact identity and inventory

The active-task authorization condition was applied only to the exact public,
ungated Qwen artifact pinned by T051-T053. Fresh pre-transfer observations were
224,608,104,448 available disk bytes, 137,438,953,472 unified-memory bytes,
and 95% system-wide memory free. All admission margins still passed.

An initial resumable `curl` transfer was interrupted with exit 130 after its
throughput degraded; the 976,437,248-byte partial file remains outside the
repository and was not used for evidence. The official Hugging Face CLI 1.26.0
with `hf_xet` and `HF_XET_HIGH_PERFORMANCE=1` then downloaded the exact file
from immutable revision `e4d4bafd…` without authentication. This command exited
zero:

```sh
HF_XET_HIGH_PERFORMANCE=1 HF_HOME=<external-cache> \
  uvx --from huggingface_hub hf download \
  Qwen/Qwen3-30B-A3B-GGUF Qwen3-30B-A3B-Q8_0.gguf \
  --revision e4d4bafdfb96a411a163846265362aceb0b9c63a \
  --local-dir <external-dir>
```

The complete local file is outside Git. Independent `stat` and `shasum -a 256`
passes reported exactly 32,483,931,648 bytes and
`4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c`,
matching immutable published LFS metadata.

Pinned llama.cpp `gguf-py` 0.19.0 then opened the file read-only for metadata
and mmap inventory only. It reported little-endian GGUF, data offset 5,969,408,
579 tensors (241 F32 and 338 Q8_0), exact typed `qwen3moe` metadata, and exactly
one `blk.0.ffn_gate_exps.weight`. That tensor is Q8_0 with fastest-axis-first
dimensions `[2048, 768, 128]`, reader encoded shape `[128, 768, 2176]`,
201,326,592 logical elements, 213,909,504 encoded bytes, and a complete in-file
range beginning at byte 901,175,808. These values satisfy every tensor role and
quantization used by the frozen 16-row expert gate-projection slice.

No tensor was dequantized and neither the trusted oracle nor Apple slice was
executed. Post-acquisition observations were 187,187,339,264 available disk
bytes and 81% system-wide memory free. T055 therefore passes identity,
license, and required-inventory admission; T056 and T057 are next.

### T056-T057 real-model contract tests

The real-model slice now has intentionally failing Rust and Python contract
tests before production implementation. The Rust suite freezes immutable
artifact identity and license, typed GGUF metadata, the single admitted tensor
role and Q8_0 layout, every named memory budget, the one bounded execution
depth, path-redacted diagnostics, and the prohibition on automatic downloads.
This command exited 101 only because the new admission API did not yet exist:

```sh
cargo test -p mlx-backend --test real_model_contract
```

The worker suite uses a generated 34,816-byte Q8_0 stand-in with the exact
16-by-2,048 decoded shape. It freezes independent encoded, decoded,
activation, and scalar-output identities; rejects wrong names, shapes,
orientation, quantization, ranges, device fallback, and non-finite scales
before MLX scheduling; and requires evaluated work followed by explicit
synchronization and bounded memory gauges. This command exited 1 only because
the new worker module did not yet exist:

```sh
PYTHONPATH=python uv run --frozen python -m unittest \
  python/pulsar_mlx_worker/tests/test_model_slice.py
```

These are observed red tests, not passing capability claims. They use no model
weights, do not open the external artifact, and do not execute the trusted
oracle. T058 and T059 own the minimum implementations needed to turn them
green.

### T058 bounded model admission

The Rust admission layer now accepts only the frozen external Qwen artifact
descriptor, exact typed `qwen3moe` metadata, the unique layer-0 routed-expert
gate projection in its observed Q8_0 layout and byte range, every conservative
disk/unified-memory/allocator/footprint bound, and the single expert-0
rows-0:16 matvec depth. It rejects automatic acquisition and all depth
promotion. The layer performs no file access or execution; T060 owns checked
external-file inspection and command integration.

These focused commands exited zero:

```sh
cargo test -p mlx-backend --test real_model_contract
cargo clippy -p mlx-backend --all-targets -- -D warnings
```

The contract suite ran 6 tests with zero failures. This proves descriptor
admission and rejection behavior only; it does not prove that a local file was
parsed by this implementation or that either oracle executed.

### T059 bounded worker slice

The worker now implements only the admitted layer-0, expert-0, rows-0:16 Q8_0
gate-projection operation. It validates the complete request, exact
orientation, prompt adapter, device/no-fallback policy, encoded byte count,
and every float16 scale before accessing MLX. The implementation constructs
the no-transpose decode on MLX, evaluates both decoded weights and output,
synchronizes the GPU, reads back exactly 16 float32 values, and records
independent component, MLX allocator, RSS-proxy, and Darwin physical-footprint
gauges without summing overlapping measurements.

These commands exited zero:

```sh
PYTHONPATH=python uv run --frozen python -m unittest \
  python/pulsar_mlx_worker/tests/test_model_slice.py -v
PYTHONPATH=python uv run --frozen python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
```

The focused suite ran 8 tests and the complete worker suite ran 36, all with
zero failures. The generated stand-in's 16-value native MLX result matched its
independent scalar tuple exactly; its output SHA-256 was
`2b44d0a66f8c4d2be5e6bd28cd2f1df9d99acbbfdc99cab82accaa40489e6c18`.
This validates a generated exact-shape stand-in only. No GGUF file was opened,
no model weights were used, and neither real-model oracle ran.

### T060 external model command integration

The CLI now exposes only two strict real-model surfaces:

```sh
pulsar-mlx inspect-model --model ABSOLUTE_EXTERNAL_GGUF --evidence PATH
pulsar-mlx validate-model-slice --model ABSOLUTE_EXTERNAL_GGUF --evidence PATH
```

Both accept the single immutable Qwen filename and reject extra downloader,
token, payload, output-dump, and execution-depth arguments. Rust opens the
artifact read-only, hashes the complete file, parses a bounded GGUF header,
admits the exact tensor inventory and fresh model-volume/host budget, and
retains the same open file description. For execution, the worker inherits
that handle as fixed descriptor 198; NDJSON carries only `slice_id`, `device`,
and `allow_fallback`. Python performs an exact positional 34,816-byte read and
file-identity snapshots before and after the bounded operation. No private
external path or model bytes cross the control protocol.

The evidence path is checked against canonical, symlink, and hard-link model
aliases, the inherited descriptor must be a regular read-only file, and
evidence is installed by a same-directory atomic rename. Rust and Python
independently enforce exact component gauges, separate temporary-current and
temporary-peak caps, MLX allocator caps, mandatory positive Darwin physical
footprint, normal memory pressure, and the prohibition on a summed overlapping
total. Reference and candidate values must be canonical finite float32 values;
numeric validation uses the predeclared additive absolute-plus-relative rule.

The first read-only inspection was launched through the unoptimized debug
binary. Sampling showed it progressing entirely inside software SHA-256; it
was interrupted with exit 130 after about 18 minutes and replaced by the
reviewed release binary. The release command performed the complete identity
pass, header/tensor inspection, bounded-slice hash, and final complete
immutability recheck, then exited zero:

```sh
target/release/pulsar-mlx inspect-model \
  --model <external-model>/Qwen3-30B-A3B-Q8_0.gguf \
  --evidence /tmp/pulsarmlx-t060-inspect.json
```

It observed the exact 32,483,931,648-byte artifact and published SHA-256,
little-endian GGUF v3, data offset 5,969,408, 579 tensors (241 F32 and 338
Q8_0), the frozen typed `qwen3moe` metadata, and the exact admitted tensor.
The bounded encoded-slice SHA-256 was
`14e9e5efa5b8cc65f02c6445f3697e729a045408af25b579a2e1d007c336fadf`.
Fresh observations were 382,544,916,480 available bytes on the model volume,
137,438,953,472 unified-memory bytes, and normal pressure. The generated
evidence contained no private path.

Focused validation passed with 4 CLI unit tests, 4 Rust worker-client tests, 6
Rust model-admission tests, and 44 Python worker tests. The first Python
discovery invocation incorrectly supplied an import-root argument and failed
without running tests; the corrected command below ran all 44 with zero
failures. A new Clippy `filter_next` diagnostic was fixed locally; the final
focused strict-Clippy run exited zero.

```sh
cargo test -p mlx-backend --bin pulsar-mlx
cargo test -p mlx-backend --test model_slice_client
cargo test -p mlx-backend --test real_model_contract
PYTHONPATH=python .venv/bin/python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
cargo clippy -p mlx-backend --all-targets -- -D warnings
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
git diff --check
```

The exact workspace gates passed with the inherited `quant` `unused_mut` and
13 macOS `serve` dead-code warnings. T060 performed only read-only artifact
inspection: it did not dequantize weights, run the trusted reference, execute
the Apple slice, tokenize, route, generate, serve, or benchmark. T061 remains
the first permitted real-model numerical execution and must precede any Apple
real-model output.

### T061 trusted-reference execution

Before the first numerical model operation, an NTFY message to topic
`Mahdi-Dev` asked the operator to pause concurrent local inference. The server
acknowledged the notification. The source worktree was clean at commit
`fc77d57b8542757c238c637718712ba99fcc2ffd`; memory pressure was normal.

The preselected oracle contract remained byte-for-byte unchanged at Git blob
`fe3eed5c3bb3a86b67b06d30afe88504af420814`. Its 216 `oracle_shell_lines`
reconstructed to 10,261 UTF-8 bytes with SHA-256
`9ae200dd7d72b6b1d79dd46c880816b8f767f26d5f22475807407e218e728092`.
The exact LF-joined script ran through the pinned external CPython 3.12.13,
llama.cpp `gguf-py` 0.19.0 revision `b06aa774…`, and NumPy 2.3.2 environment:

```sh
set -o pipefail
jq -j '.exact_reproduction.oracle_shell_lines | join("\n"), "\n"' \
  docs/validation/models/qwen3-30b-a3b-q8_0-oracle.json |
  env PULSARMLX_ORACLE_ROOT=<external-oracle> \
      PULSARMLX_MODEL_GGUF=<external-model>/Qwen3-30B-A3B-Q8_0.gguf \
      /bin/zsh > <external-capture>/stdout.json \
      2> <external-capture>/stderr.txt
```

The command ran from `2026-08-05T15:12:38Z` to
`2026-08-05T15:13:04Z` and exited zero. Stdout contained exactly one 2,760-byte
JSON object; stderr was empty and no `ORACLE_STOP` occurred. The complete
artifact identity, typed metadata, tensor layout, and bounded encoded slice
matched admission. The encoded-slice SHA-256 was the same
`14e9e5ef…` observed independently by T060. Pinned Q8_0 decode produced a
131,072-byte float32 slice with SHA-256
`5aa54eb798fdf16d79b112a58338211fbab393b94161b9219b19c4700f46d91b`.

The canonical scalar left-to-right float32 matvec emitted exactly 16 finite
values with output SHA-256
`610357fb4919bf3906f869c81e13abaa46e6ab71dbe2741bc411037506045b51`.
Its independent NumPy float32 cross-check had zero mismatches under the frozen
`0.0002 + 0.0002 * abs(scalar)` rule; maximum absolute error was
`0.0000016093254089355469` and maximum reported relative error was
`0.0000016640896902432634`.

The sanitized committed result is
`docs/validation/models/qwen3-30b-a3b-q8_0-reference-result.json`. An
independent standard-library validator rederived the prompt activation,
float32 output checksum, every field mapping, self-check metrics, checksum
syntax, encoded-slice agreement, byte bound, and private-path exclusion. A
Rust unit test also loads the committed document through the exact private
schema parser used by `validate-model-slice`.

That Rust test initially exposed a JSON-number boundary: requiring parsed f64
decimals to be bit-identical to their source float32 values rejected one valid
serialized value before any model execution. The loader and worker readback
now reject non-finite or out-of-range values and canonicalize every accepted
value through finite float32 before checksum or comparison. The focused CLI,
client, and strict-Clippy suites then passed.

This is reference CPU evidence only. No Apple real-model output was viewed
before the oracle completed, and T061 did not run MLX or Metal. It does not
establish Qwen tokenization, routing, a full expert/layer/model, generation,
serving, giant-model inference, or performance. T062 is now eligible to run
the identical bounded slice on Apple MLX against this fixed result.

### T062 bounded real-model Apple MLX slice

The first Apple execution ran only after the T061 reference was committed.
It passed numerically, but review found that its generated evidence used
approximate aliases for several normative validation-contract fields and
recorded a debug Cargo command although the actual invocation used the release
binary. The valid first result remains in Git history at commit `5db6bdf`; the
generator was tightened in `f84a887`, then the exact documented command was
rerun from a clean worktree at source commit
`5db6bdf1069785aee8ed2682cd18110df9bbeb84`:

```sh
cargo run --release -p mlx-backend --bin pulsar-mlx -- \
  validate-model-slice \
  --model <external-model>/Qwen3-30B-A3B-Q8_0.gguf \
  --evidence docs/validation/qwen3-30b-a3b-q8_0-slice.json
```

The final command ran from `2026-08-05T15:24:28Z` through
`2026-08-05T15:27:50Z` and exited zero. It rehashed and read-only admitted the
complete artifact, inherited the same regular read-only file description,
read exactly 34,816 admitted bytes, decoded exactly 131,072 float32 bytes,
constructed the frozen 8,192-byte prompt activation, evaluated the 16-value
matvec on explicit MLX GPU, synchronized, and rehashed the complete open
artifact after execution. No fallback occurred.

All input identities matched the independent reference: encoded slice
`14e9e5ef…`, decoded slice `5aa54eb7…`, and activation `3821796e…`. The MLX
float32 output SHA-256 was
`7d6548f999b730da122756f8ed8d242bcb4eb4cbead7c3b764b56b5a3256f2f4`.
All 16 values passed the preselected additive
`0.0005 + 0.0005 * abs(reference)` rule with zero mismatches. Maximum absolute
error was `0.0000016093254089355469`; maximum reported relative error was
`0.0000017527402999126447`.

Observed non-overlapping gauges were 34,816 owned compressed bytes, 131,072
decoded-array bytes, 8,192 activation bytes, 64 output bytes, and 135,168
current/peak declared temporary bytes. MLX reported 274,496 active bytes, zero
cache bytes, and 274,496 peak bytes. The RSS proxy was 44,302,336 bytes;
Darwin `proc_pid_rusage:RUSAGE_INFO_V4` reported a 27,641,408-byte current and
peak physical footprint. Memory pressure remained normal and every frozen cap
passed. The external 32,483,931,648-byte file-size gauge is recorded
separately and no overlapping summed total is reported.

An independent validator recomputed the Apple output checksum and every error,
confirmed all exact artifact/prompt/tensor identities, checked every memory
cap and normative evidence field, and recursively rejected private paths. The
final record is `docs/validation/qwen3-30b-a3b-q8_0-slice.json`.

This verifies one bounded real-checkpoint intermediate only. It does not verify
Qwen tokenization or embeddings, routing, a full expert, a full transformer
layer, attention, logits, tokens, generation, serving, giant-model inference,
Linux/CUDA behavior, or performance. T063 must reconcile those boundaries in
the public compatibility and limitations documentation.

### T063 real-model support boundary and post-slice baseline

The public compatibility and limitations documents now classify the T062
result as one bounded real-checkpoint intermediate: one Q8_0 tensor, expert 0,
the gate projection, output rows 0 through 15, and one deterministic activation.
It is deliberately separate from synthetic routed-MoE evidence and does not
advance giant-model or production-serving support.

From a clean worktree at pushed commit
`31ee7e55daadb5d1d7b3d0e278b8ccac114836d9`, the exact post-slice gates ran:

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
cargo test --workspace -- --list | rg ': test$' | wc -l
```

Both workspace gates exited zero. The listing contained 155 tests: 154 active
tests passed, one native MLX integration smoke test remained explicitly ignored
by the general baseline, and zero failed. Output retained the inherited
`crates/quant/src/iq.rs` `unused_mut` warning and 13 macOS `serve` dead-code
warnings. No repository-wide warning cleanup was performed. The result covers
only targets selected on macOS; Linux/CUDA compilation and execution were not
run.

The exact workspace result is also attached to the committed bounded-slice
record. No model execution, benchmark, or additional hardware-sensitive work
was performed for T063.

### T064–T065 evidence-validation red phase

Two additive backend test targets now express the remaining evidence-publication
rules before implementation. `validation_records` requires a bounded actual
result in addition to a passing status, a known clean full commit, an
independent oracle, independently validated memory gauges, a legal verification
transition, and passed verified correctness prerequisites for a benchmark.
`compatibility_matrix` defines six exact, non-ordered evidence levels and proves
that scalar, evaluated MLX tensor, synthetic routed-MoE, bounded real-model,
giant-model, and production-serving evidence cannot imply one another.

The required red-phase commands were run exactly:

```sh
cargo test -p backend --test validation_records
cargo test -p backend --test compatibility_matrix
```

Both exited 101 at compile time as intended. The first reported six errors for
the not-yet-implemented typed evidence level, bounded actual-result summary,
and nested memory-gauge fields. The second reported seven errors for the
not-yet-implemented compatibility matrix API and the same validation fields.
`rustfmt --check` on both new test files and `git diff --check` passed. These
failures are the T066 implementation target, not a claim that the backend test
suite currently passes. No model or MLX execution occurred in this milestone.

### T066 reusable evidence and compatibility validation

The backend evidence contract now requires a bounded actual-result summary for
every executed validation case and validates any attached raw memory gauges
through the existing independent-gauge rules. A validation case may carry one
typed evidence level. The six compatibility levels are exact and non-ordered:
scalar fixture, evaluated MLX tensor fixture, synthetic routed-MoE, bounded
real-model slice, giant-model execution, and production serving.

A compatibility matrix must contain exactly one unique cell for each level.
Verified cells require supplied, executed, passed, explicitly verified evidence
whose typed level exactly matches the cell. Planned, unsupported, and blocked
cells require a bounded explanation. Existing benchmark admission continues to
require every named correctness prerequisite to be supplied, passed, and
verified. Diagnostics retain the shared bounded/redacted `ContractError` path.

Validation after implementation:

```sh
cargo test -p backend --test evidence_contract \
  --test validation_records --test compatibility_matrix
cargo test -p backend
cargo clippy -p backend --all-targets -- -D warnings
git diff --check
```

The three focused targets passed 8, 7, and 10 tests respectively. The complete
backend crate passed 57 tests with zero failures, and strict backend Clippy and
the diff check both exited zero. This is evidence-schema enforcement only; it
does not execute a backend, model, MLX, Linux, or CUDA workload.

### T067–T068 compatibility matrix and reviewer index

The public compatibility document now has one explicit six-level matrix for
architecture-independent f32 primitives, strict Q8_0 primitives, the synthetic
routed-MoE fixture, and the exact bounded Qwen3MoE/Q8_0 tensor prefix. Every
verified cell links a committed passing record. Generic Q8_0 fixtures remain
prerequisites rather than Qwen architecture evidence; only the exact bounded
real-checkpoint cell is verified for Qwen. Giant-model execution and production
serving remain independently unsupported.

`docs/validation/README.md` indexes all 11 committed validation JSON artifacts,
the embedded device case, and seven embedded tensor cases. It maps stable IDs
to immutable input locators, oracle/reference identity or an explicit absence,
actual status/result, exact command references, warnings, exclusions, and the
authoritative artifact. Frozen, admission-only, zero-test, unavailable, and
not-run states remain visibly non-executed or non-success states.

All 11 JSON documents passed `jq empty`. Every unique local JSON link in the
reviewer index exists, and the link inventory exactly matches the committed
validation JSON inventory. A private-path pattern check, Markdown whitespace
check, and `git diff --check` passed. This milestone only organizes committed
evidence; it does not rerun a model, MLX workload, Linux/CUDA command, or
benchmark.

### T069 explicit not-run benchmark record

The initial benchmark option is committed as `actual_status: not_run`. Although
passing synthetic and bounded real-checkpoint correctness records exist, no
benchmark input, timing boundary, cache policy, storage policy, or performance
hypothesis was selected for this correctness-first feature. No timing command
was executed.

`docs/validation/benchmark-initial.json` enumerates every constitution benchmark
field with `null`, zero, or an empty list as appropriate, records zero samples,
binds no correctness prerequisite to an unselected benchmark, and sets the
performance claim to `null`. It explicitly excludes latency, throughput,
speedup, bandwidth, memory-efficiency, thermal, power, Linux/CUDA, giant-model,
and serving claims. This satisfies the specification's permitted explicit
not-run branch without converting available correctness evidence into
performance evidence.

### T070 independent portable-source replay

From a clean worktree at commit
`0cf71ba8dd4ffc66c6e49c3dfa0cd9d23dbb04a7`, the exact command recorded by the
portable expert-source evidence was replayed independently:

```sh
cargo test -p stream --test positional_source
```

It ran on arm64 macOS 26.0 (build 25A354) with Rust 1.97.1 and Cargo 1.97.1,
exited zero, and reported 14 passed, zero failed, and zero ignored. This exactly
matched the source record's compared cardinalities. The replay commit is later
than the source evidence commit, but `git diff` confirmed that no file under
`crates/stream` changed between them. Cached build duration and nondeterministic
test-report ordering were deliberately not treated as correctness fields.

The sanitized result is `docs/validation/reproduction-check.json`. The replay
does not cover the inherited Linux `io_uring` implementation, the 32-bit-only
branch, MLX, model execution, serving, Linux/CUDA, or performance. The file
reserves a separate `final_story_validation` object for T072's exact workspace
and evidence-validator rerun.

### T071 public claim and command reconciliation

The README and feature quickstart now describe the exact verified boundary:
the historical post-slice workspace result, the T060 44-test Python worker
suite, portable positional storage, synthetic routed-MoE, and one external
Qwen3MoE Q8_0 gate-projection prefix. End-to-end checkpoint execution,
tokenization, routing over the checkpoint, complete experts/layers, generation,
serving, giant-model execution, performance, and Linux/CUDA runtime parity for
fork changes remain unsupported or unverified.

The three stale planned sections now contain the implemented portable-source,
synthetic-MoE, inspection, and bounded-slice commands. Reproduction commands
write evidence outside the repository so they do not overwrite committed
historical records. The model section retains immutable size/SHA-256, clean
worktree, provenance, tensor-layout, memory, no-fallback, synchronization, and
comparison stop conditions; it does not present the bounded prefix as model
inference.

Known limitations now distinguish the inherited non-Linux `serve` stub from
the separate validation CLI, explain the typed evidence/matrix validators and
their legacy-JSON boundary, link the independent replay, and retain the
explicit not-run benchmark. All changed local documentation links and command
paths exist, documented CLI subcommands exist, changed shell blocks passed
`zsh -n`, and `git diff --check` passed. No validation command or model was run
for this documentation-only reconciliation; T072 remains the final exact gate.

### T072 final US5 workspace and evidence gate

From a clean worktree at pushed commit
`e0b965233a7cd1aa111d8f061b5b125cfcb326e3`, the final story validation ran from
`2026-08-05T15:59:47Z` through `2026-08-05T16:01:00Z`. The typed evidence
targets passed 25 tests, and the committed trusted-reference loader test passed
one test with four unrelated CLI tests filtered out. All 13 committed
validation JSON documents parsed, the benchmark remained an explicit zero-
sample `not_run`, the portable replay still matched its source record, the
Qwen reference/slice identities and 16-value zero-mismatch result agreed, and
all 13 reviewer-index JSON links matched the inventory.

The exact workspace commands both exited zero:

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
cargo test --workspace -- --list | rg ': test$' | wc -l
```

The workspace listed 172 tests: 171 passed, zero failed, and the native MLX
device smoke remained explicitly ignored by the general command. Output
retained the inherited `crates/quant/src/iq.rs` `unused_mut` warning and 13
macOS `serve` dead-code warnings. No broad cleanup was performed.

The final result and every exact validator command are recorded in
`docs/validation/reproduction-check.json`. Linux/CUDA runtime behavior, an
external-model rerun, giant-model execution, production serving, and a
performance benchmark were not run during T072 and remain explicitly
unverified, unsupported, or not run as applicable. No unavailable evidence was
converted into success.

The workspace run also exposed a test-harness side effect: the
`nonzero_exit_and_process_crash_are_distinguished` fake worker deliberately
called Python `os.abort()`. macOS displayed its resulting Crash Reporter dialog.
The report identified `worker_contract` as the parent, Homebrew Python 3.14 as
the child, and no loaded MLX or Metal library. The test still passed its intended
classification assertion, but a focused follow-up must replace the abort-based
simulation before another general workspace run.

### Worker-contract macOS crash-dialog follow-up

The attached macOS report confirmed that the popup was produced by the test
harness rather than MLX or concurrent inference. It named the `worker_contract`
test binary as parent, Homebrew Python 3.14 as the approximately 114 ms child,
and `EXC_CRASH (SIGABRT)` with `abort -> os_abort` on the only thread. Its loaded
images contained Python, `_json`, and system libraries only—no MLX, Metal,
Accelerate, NumPy, or model runtime library. The repository's sole `os.abort()`
was the matching fake-worker case.

Commit `c7ef8a56beda29307a809720a87c22d990f68d83` now uses `SIGTERM` for the same
no-exit-code classification boundary. `WorkerClient` still reports
`ProcessCrashed`, so the behavior under test is preserved without invoking
macOS Crash Reporter. The focused test passed, the recent Python diagnostic-
report count remained 1 before and after, the full worker-contract target
passed 12 tests, and strict focused Clippy passed. No model or MLX work ran.

### T073 lockfile-backed Apple MLX fixture CI

The existing `macos-15-arm64` Cargo baseline job remains byte-for-byte
unchanged. A second `macos-15` job now asserts `arm64`, verifies the committed
US1–US3 evidence/fixture inputs, installs the official `setup-uv` action at the
immutable v8.1.0 action commit, pins uv 0.11.17 and CPython 3.12.13, and runs
`uv sync --frozen` from the committed lockfile.

The job runs the bounded Python worker suite, the explicitly ignored native
device smoke, seven tensor fixtures, and the synthetic routed-MoE fixture. It
writes generated evidence only under `RUNNER_TEMP` and validates pass/device
boundaries there. `PULSARMLX_MODEL_GGUF` is explicitly empty; the job contains
no inspect, model-slice, downloader, Hugging Face, GGUF, or external-path
command.

Local validation parsed the workflow YAML and every shell block, confirmed the
three prerequisite evidence records are passing at their exact scopes, checked
that the new job contains only small-fixture commands, and passed
`git diff --check`. This establishes workflow configuration only. T074 must run
the pushed workflow before any remote CI success is claimed.

### T074 pushed Apple MLX fixture CI result

Push-triggered GitHub Actions run
[`31023865090`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31023865090)
completed successfully at commit
`751eb7dabe5ed463c8133f0f93e69f6f99703d95`. Both jobs used the
`macos-15-arm64` image version `20260727.0256.1` on macOS 15.7.7 build
24G720 and passed their `arm64` assertions.

The unchanged workspace job passed `cargo check --workspace --all-targets`
and `cargo test --workspace --no-fail-fast`. Summing all 43 Cargo harness
summaries in the downloaded log gives 171 passed, zero failed, and one ignored.
The same inherited `quant` `unused_mut` warning and 13 macOS `serve` dead-code
warnings remained.

The fixture job resolved CPython 3.12.13, MLX 0.32.0, and mlx-metal 0.32.0
from the frozen uv environment. It passed 44 Python worker tests, one explicitly
selected native MLX device smoke, seven evaluated MLX tensor cases, and the
synthetic routed-MoE case. The initial and final assertions both confirmed that
`PULSARMLX_MODEL_GGUF` was empty. Generated records lived only under
`RUNNER_TEMP` and no workflow artifacts were uploaded.

The exact run/job identities, commands, results, and exclusions are recorded
in `docs/validation/ci-mlx-smoke.json`. Runner CPU/count, unified memory,
available disk, thermals, and power were not measured. No external checkpoint,
full or giant model, production serving, benchmark, Linux, CUDA, or `io_uring`
runtime workload ran, so no claim was promoted beyond the small-fixture CI
scope.

### T075 format and strict-Clippy diagnostics

Both requested diagnostics ran from a clean worktree at pushed commit
`8a21f2b`. They remain observations rather than merge gates:

- `cargo fmt --all -- --check` exited 1 and reported differences in exactly 25
  files, matching the pre-flight count. Every reported file is inherited from
  upstream; no newly added Rust file appeared. The reported hunks in
  `crates/quant/src/lib.rs` and `crates/stream/src/lib.rs` are outside the
  additive PulsarMLX module/export lines.
- `cargo clippy --workspace --all-targets -- -D warnings` exited 101 with
  Clippy 0.1.97. It emitted 25 primary diagnostics in six inherited files:
  four in `crates/tokenizer/src/lib.rs`, one in `crates/kernels/build.rs`, one
  in `crates/gguf/tests/hy3_header.rs`, eight in
  `crates/quant/src/cpu_dot.rs`, four in `crates/quant/src/iq.rs`, and seven in
  inherited regions of `crates/quant/src/lib.rs`.

The previously recorded kernels build-script
`clippy::needless_borrows_for_generic_args` and quant `unused_mut` reproduced.
The other diagnostics were newly surfaced by this complete diagnostic output,
but every cited line was unchanged from the upstream baseline. No diagnostic
named `backend`, `mlx-backend`, `q8_0_ref`, the portable positional source, or
their tests. Because inherited errors stopped workspace Clippy, this result is
only “no PulsarMLX-attributable failure reported,” not a strict-Clippy pass for
every new target. No formatting or lint cleanup was applied.

### T076 focused, workspace, and staged-safety gate

The final focused gate began from a clean worktree at pushed commit
`07a5268`. Every executed correctness command exited zero:

```sh
PYTHONPATH=python uv run python -m unittest discover -s python/pulsar_mlx_worker/tests -v
cargo test -p backend --all-targets
cargo test -p quant --test q8_0_reference
cargo test -p stream --test positional_source
cargo test -p stream --lib
cargo test -p mlx-backend --all-targets
cargo test -p mlx-backend --test device_smoke native_device_smoke_command_emits_evaluated_evidence -- --ignored --exact
cargo run -p mlx-backend --bin pulsar-mlx -- validate-fixtures --manifest fixtures/mlx/manifest.json --evidence <temporary-directory>/mlx-tensor-fixtures.json
cargo run -p mlx-backend --bin pulsar-mlx -- validate-synthetic-moe --fixture fixtures/mlx/routed-moe-v1.json --evidence <temporary-directory>/synthetic-moe-v1.json
```

Actual results were 44 Python tests; 57 backend tests; 14 Q8_0 reference
tests; 14 positional-source tests; one stream unit test; and 54 active
`mlx-backend` Rust tests with one native smoke ignored by the package-wide
command. Selecting that native smoke explicitly passed one test. The generated
temporary evidence reported seven passed evaluated MLX tensor cases and one
passed evaluated synthetic routed-MoE case with no fallback.

The de-duplicated evidence gate also passed 25 typed compatibility/evidence
tests and one committed-reference parser test. All 14 committed validation JSON
documents parsed; the zero-sample benchmark remained `not_run`; portable-source
replay and Qwen reference/slice identity checks remained matched; and the 14
reviewer-index JSON links exactly matched the 14-file inventory.

The named Linux-preservation target and release kernels harness were also
inspected. Each selected zero tests on macOS. Their exit-zero harness status is
recorded only as cfg exclusion, not Linux, `io_uring`, or CUDA runtime evidence.

The exact final workspace commands then passed:

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
git diff --check
```

The workspace test output contained 171 active passes, zero failures, and one
ignored native MLX smoke. The inherited quant `unused_mut` and 13 macOS serve
dead-code warnings remained. The separate explicit smoke above proves that the
ignored case passed in the pinned local environment; the ordinary workspace
command intentionally retains its opt-in boundary.

Static source review confirmed no fork changes under `crates/engine`,
`crates/kernels`, `crates/tokenizer`, `crates/gguf`, or
`crates/stream/Cargo.toml` relative to `upstream/main`. The only shared-source
diffs remain additive backend workspace membership, Q8_0 exports, portable
positional-source exports, and the macOS build gate above the Linux-only serve
handler. No inherited Linux or CUDA selector, engine, kernel, tokenizer, GGUF,
or stream dependency behavior was changed.

The staged review passed `git diff --cached --check`. Staged names and content
contained no credential/token marker, private home path, private-key header,
model-weight file, cache, virtual environment, Python bytecode, macOS metadata,
or generated binary. Tracked-file review likewise found no GGUF,
safetensors, `.env`, cache, or generated binary. The ignored local `.venv`,
`target`, and Python cache directories remained unstaged. This sanitized
review records only categories and outcomes; it contains no credential value
or private path.

### T077 literal validation-quickstart replay

Every currently supported shell command in
`specs/001-apple-silicon-mlx/quickstart.md` was executed from clean pushed
commit `31a8bf9`. Safe and small-fixture blocks ran first; the external-model
block ran only after the requested operator notification. The source-of-truth
reads completed; Specify
0.15.2 reported a healthy Codex integration and prerequisite set; the native
host reported arm64 macOS 26.0; the system Python was arm64 3.14.6; and the
filesystem reported 356 GiB available at the prerequisite snapshot.

The exact workspace check and test passed with 171 active tests, zero failures,
and one ignored native smoke. `uv sync --frozen` completed, MLX resolved to
0.32.0, 57 backend tests passed, and strict backend Clippy passed. The two
documented diagnostics retained their non-gate results: rustfmt exit 1 for the
same 25 inherited files and strict workspace Clippy exit 101 on inherited
debt. No cleanup was applied.

The executable small-fixture blocks all passed: 44 Python worker tests, 12 Rust
worker tests, the evaluated GPU device command, 14 strict Q8_0 tests, 7 Rust
tensor-contract tests, 7 evaluated MLX tensor fixtures, 14 positional-source
tests plus its check and stream unit test, the evaluated synthetic routed-MoE
fixture, evidence/matrix/benchmark reads, and the explicitly selected native
device test. Fresh generated records were written only below a temporary
directory outside Git.

Before the external-model block, an acknowledged NTFY message to topic
`Mahdi-Dev` asked the operator to pause local inference. The exact external
artifact remained 32,483,931,648 bytes with SHA-256
`4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c`;
the source was clean and memory pressure was normal. Read-only inspection
admitted the exact Qwen3MoE Q8_0 tensor inventory without execution.

The bounded slice then ran from `2026-08-05T16:35:16Z` through
`2026-08-05T16:38:40Z`. It read 34,816 encoded bytes, selected MLX GPU with no
fallback, evaluated and synchronized 16 values, and matched the frozen
reference with zero mismatches. Maximum absolute error was
`1.6093254089355469e-6`; maximum relative error was
`1.7527402999126447e-6`. The result retained the exact encoded, decoded,
activation, and reference-output identities. A completion NTFY message then
released the hardware for local inference.

This was a bounded real-checkpoint prefix replay, not tokenization, routing, a
complete tensor/expert/layer/model, logits, tokens, generation, serving,
giant-model inference, Linux/CUDA validation, or a benchmark. Temporary model
evidence contained no private path and was not committed; the existing
historical evidence records were not overwritten. The quickstart now reflects
the current backend count and the pushed small-fixture CI result while retaining
all model admission and unsupported-stage stop instructions.

### T078 final Spec Kit reconciliation

Feature `001-apple-silicon-mlx` is complete at 78 of 78 tasks. The requirements
checklist remains 16 of 16 complete and the design-readiness checklist remains
40 of 40 complete. FR-001 through FR-024 and SC-001 through SC-012 resolve
through the final specification assessment and plan traceability table. The
constitution recheck passed at the declared bounded scope with no exception:
unavailable Linux/CUDA runtime evidence, a zero-sample benchmark, and all
deeper model levels remain explicit rather than being promoted to success.

The reviewer index and filesystem inventory match at 14 of 14 committed JSON
records. The latest pushed pre-reconciliation verification, GitHub Actions run
[`31026431975`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31026431975)
at commit `5a43cf0`, completed successfully in both arm64 macOS jobs. The Cargo
job passed the exact workspace check and reported 171 active tests passed, zero
failed, and one ignored. The frozen-environment fixture job passed 44 Python
worker tests, one explicitly selected native MLX device smoke, seven tensor
cases, and the synthetic routed-MoE case with the external-model variable
empty.

After the reconciliation edits, these focused and exact release commands all
exited zero:

```sh
cargo test -p backend --test evidence_contract --test validation_records --test compatibility_matrix
cargo test -p mlx-backend --bin pulsar-mlx committed_reference_result_matches_the_frozen_loader_contract
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
git diff --check
```

The focused backend command passed 25 tests and the committed-reference parser
passed one. The exact workspace run again summarized 43 harnesses, 171 active
passes, zero failures, and one ignored native smoke. The inherited quant
`unused_mut` and 13 macOS serve dead-code warnings remained. Specify health and
Codex integration checks passed; all 14 validation JSON documents parsed; all
edited local Markdown links resolved; and the quickstart shell blocks passed
`zsh -n`. No model command ran during T078.

The completed feature verifies only the evaluated Apple MLX device path,
bounded tensor semantics, strict admitted Q8_0 references, portable exact
storage, one synthetic routed-MoE fixture, and one 16-row Qwen3MoE Q8_0
gate-projection prefix against its frozen CPU oracle. It does not verify
checkpoint tokenization or routing, a complete tensor/expert/layer/model,
logits, tokens, generation, serving, full or giant model inference, benchmark
performance, custom Metal, or Linux/CUDA runtime parity. No implementation for
any of those excluded levels began during reconciliation.

There is no next incomplete task in feature 001. The recommended next bounded
milestone is a newly specified feature for the same immutable checkpoint's
layer-0 router projection and deterministic top-8 expert IDs and normalized
weights, gated by an independent frozen CPU oracle and exact tensor/memory
admission. Before any external-model access, notify NTFY topic `Mahdi-Dev`.
The exact continuation instruction is:

```text
Use $speckit-specify to define a bounded Qwen3MoE layer-0 router parity
feature for the same immutable checkpoint. Preserve feature 001's verified
scopes and exclusions. Then run $speckit-plan and $speckit-tasks and review
their gates before implementation; do not run $speckit-implement against the
completed specs/001-apple-silicon-mlx task list.
```

## Feature 002: Qwen3MoE Layer-0 Router Parity

### T001 safe baseline

Feature 002 began from clean, pushed commit `4e1ca2c`. The active Spec Kit
metadata resolved to `specs/002-qwen-router-parity`; all 16 requirements-
checklist items were complete; and the reviewed task list contained 97 unique,
contiguous tasks. No external checkpoint was resolved, opened, hashed, or
executed during this baseline.

The exact Spec Kit checks passed:

```sh
specify version
specify check
specify integration status --json
.specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

Specify reported version 0.15.2 on arm64 Darwin with Python 3.12.13. Codex was
the healthy default integration with zero missing or modified managed files and
no findings. Prerequisites returned the Feature 002 directory and its research,
data-model, contracts, quickstart, and task artifacts.

The exact safe workspace baseline passed:

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
PYTHONPATH=python uv run python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
```

`cargo check` exited zero. The workspace test executed 43 harnesses with 171
active passes, zero failures, and one intentionally ignored native MLX smoke.
The Python worker suite passed 44 tests. The inherited quant `unused_mut` and 13
macOS serve dead-code warnings remained unchanged; they are observations, not
Feature 002 failures. The former `os.abort()` worker-test side effect did not
recur because current `main` uses signal termination instead.

### T002–T004 offline setup

The initial Feature 002 setup remained entirely offline. The new idempotent
`scripts/research/setup.sh` verifies committed Cargo, uv, and active-feature
metadata; refuses an unignored scratch root; and creates only ignored local
cache, candidate, log, oracle-build, and temporary directories below
`.pulsarmlx-local/research-work/`. Two consecutive executions both exited zero
with the same bounded ready message. `sh -n` and `zsh -n` also passed.

`.gitignore` now excludes the dedicated local research-work, candidate-output,
oracle-build, external-model, cache, log, and secret roots. Seven representative
scratch paths were ignored, while six representative versioned paths under
`specs/`, `schemas/`, `fixtures/`, and `docs/research/` remained trackable.

Six publication documents were created with status-only content:
`EXPERIMENT_PROTOCOL.md`, `REPRODUCIBILITY.md`, `RESULTS.md`, `LIMITATIONS.md`,
`CLAIMS_LEDGER.md`, and `REVIEWER_INDEX.md`. Each states that neither Feature
002 implementation nor real-router results exist. The claims ledger contains
zero claim rows. All local links resolved and `git diff --check` passed. No
model path, checkpoint, network download, MLX model operation, measurement, or
capability promotion occurred.

### T005–T008 planned-failure evidence

The four foundational test contracts were written and executed before their
implementations. Their focused red runs failed only at the planned missing
module or command boundary:

```sh
python3 -m unittest scripts/research/tests/test_statistics.py -v
python3 -m unittest discover -s scripts/research/tests \
  -p 'test_validate_evidence.py' -v
python3 -m unittest scripts/research/tests/test_generators.py -v
python3 -m unittest scripts/research/tests/test_verify_package.py -v
```

The statistics suite ran eight tests and reported eight expected failures
because `statistics.py` did not exist. The validator suite ran 13 tests and
reported 18 expected failures including subtests because
`validate_evidence.py` did not exist. The generator suite ran four tests and
reported four expected failures because the table and figure modules did not
exist. The publication suite ran five tests and reported five expected failures
because the publisher and package verifier did not exist. These failures froze
the intended Type-7 statistics, grouping, closed-schema, semantic, privacy,
non-finite, repetition, deterministic generation, provenance, append-only,
sanitization, and atomic-publication contracts; they are not reported as
passing validation. No model or MLX operation ran.

### T009–T012 schema, statistics, and validator gate

Two draft-2020-12 version-1 schemas now close the research experiment and
router-parity objects. A bounded synthetic positive record plus three compact
mutation descriptors cover unknown-field, private-value, and incompatible-
condition failures. All six JSON documents parsed successfully. The positive
record is fixture-only and contains no real measurement or model bytes.

The dependency-free statistics implementation uses positive integer
nanoseconds, Hyndman-Fan Type-7 percentiles, sample standard deviation,
explicit coefficient-of-variation null reasons, and compatibility keys that
prevent pooling different cases, conditions, instrumentation modes, commits,
or batches. The fail-closed validator checks schema identity, closed structure,
immutable identities, private and non-finite values, repetitions, raw-summary
agreement, observation grouping, correctness relationships, and bounded router
claim scope with stable error codes that do not echo private values.

The green gate was:

```sh
python3 -m unittest \
  scripts/research/tests/test_statistics.py \
  scripts/research/tests/test_validate_evidence.py -v
python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input fixtures/research/router-v1/evidence/f002-router-fixture-0001.json
```

The focused suites passed 21 tests: eight statistics tests and 13 validator
tests. The validator accepted exactly one positive record. Python compilation,
JSON parsing, and `git diff --check` passed. T007 and T008 remain only at their
already recorded planned-red boundary until their dependency-ordered T014 and
T015 implementations; they are not misreported as green.

The preceding pushed documentation commit `4e1ca2c` completed successfully in
GitHub Actions run
[`31033183126`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31033183126).
The Phase 1 setup commit `423b0e4` completed successfully in run
[`31033532161`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31033532161).
Both used the existing arm64 macOS workflow; neither accessed an external
model. These actual conclusions were recorded in this next focused milestone
as required by the CI-attestation policy.

### T013 schema/statistics publication checkpoint

The schema/statistics/validator slice was staged alone and passed the required
secret, private-path, model-artifact, binary, cache, large-file, and inherited
Linux/CUDA-selection review. Commit `aeeb5af` (`test(research): freeze evidence
schema and statistics`) was pushed to `origin/main` without force.

GitHub Actions run
[`31035040229`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31035040229)
completed successfully for exact commit
`aeeb5afa9942601652a1b6f9ea941c4490ae63bf`. The existing arm64 macOS baseline
workflow passed both its Cargo workspace and frozen-environment fixture jobs.
The run did not receive, locate, or access an external model. This CI result
was learned after the T013 push and is being carried into the next focused
methodology commit under the non-recursive attestation rule.

### T014–T020 frozen methodology implementation

The dependency-free table and figure generators now derive deterministic
Markdown, CSV, bounded static SVG, and per-output source sidecars from raw JSON;
two independent temporary generations compare byte-for-byte. Candidate
publication validates full evidence records, removes only declared local
metadata, rejects private or secret values, installs with exclusive atomic
append-only semantics, and refuses symlink or overwrite targets. The read-only
package verifier checks the zero-claim ledger/reviewer structure and regenerated
six fixture artifacts twice without writing publication output into the tree.

The safe shell layer now provides idempotent ignored setup, filesystem-blind
lexical validation of explicitly supplied external paths, and a standardized
staged-index scanner. Its focused suite passed 9 tests covering idempotence,
symlink refusal, non-creation of supplied model paths, absolute/disjoint path
rules, and positive and negative staged-scan cases. `sh -n`, `dash -n`, and
`zsh -n` passed for all three shell entrypoints.

The version-1 experiment protocol now freezes direct token IDs `[0,1]`,
positions `[0,1]`, context/batch/ubatch `2`, one thread, the single-row and
two-row case IDs, the two-row/16,384-byte bound, numeric tolerances, exact two-
benchmark matrix, 5/10 and 5/30 policies, clean-process replication, timing and
cache labels, grouping, interference, exclusion, amendment, retention,
privacy, resources, and stop conditions. Reproducibility, empty results and
limitations, the zero-row claims ledger, reviewer index, and unsealed model and
artifact manifest placeholders were completed without presenting expectations
as observations.

The exact model-free replay was:

```sh
PULSARMLX_MODEL_GGUF='' scripts/research/setup.sh
PULSARMLX_MODEL_GGUF='' python3 -m unittest discover \
  -s scripts/research/tests -v
PULSARMLX_MODEL_GGUF='' python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input fixtures/research/router-v1/evidence
PULSARMLX_MODEL_GGUF='' python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity \
  --fixture-only
```

Setup passed; all 41 research tests passed; the validator accepted one
full-schema synthetic methodology record; and package verification reported
one record, zero claims, and six byte-identical regenerated artifacts. The same
commands were added to the arm64 macOS fixture job with
`PULSARMLX_MODEL_GGUF` explicitly empty. No checkpoint was resolved, statted,
hashed, opened, or executed and no MLX model operation ran.

### T021 pre-commit validation

These exact gates exited zero against the complete methodology worktree:

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
PYTHONPATH=python uv run python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
python3 -m unittest discover -s scripts/research/tests -v
git diff --check
```

`cargo check` passed. The workspace test again executed 43 harnesses with 171
active passes, zero failures, and one intentionally ignored native MLX smoke.
The Python worker suite passed 44 tests and the research suite passed 41. The
inherited quant `unused_mut` and 13 macOS serve dead-code warnings remained
unchanged. Python compilation, all research JSON parsing, POSIX/zsh syntax, and
`git diff --check` also passed. The complete 27-file methodology slice was then
staged and `scripts/research/check_staged.sh` passed its whitespace, secret,
private-path, machine-identifier, model/tensor, cache/log, symlink, binary,
object-mode, per-file/aggregate-size, file-count, and inherited Linux/CUDA-
selection gates. The final staged diff check passed after recording this task
state.

### T022 frozen-methodology commit and CI attestation

Commit `1cb9d39` (`docs(research): freeze router publication methodology`)
was pushed to `origin/main` without force. GitHub Actions run
[`31037215729`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31037215729)
completed successfully for exact commit
`1cb9d39a6d55527fbbe1e90db7e77d921deeea59`.

Both required jobs passed: `Apple Silicon workspace baseline` completed its
Cargo check and test steps, and `Apple MLX small-fixture validation` completed
the new Feature 002 model-empty methodology step plus the inherited bounded
worker, native MLX device, tensor, and synthetic routed-MoE fixture steps. The
run did not receive or access an external checkpoint. This result completes
the frozen-methodology checkpoint; the CI outcome for this attestation-only
commit is intentionally reported out of tree under the non-recursive
attestation rule.

### T023–T025 router contracts at the test-first boundary

The documentation-only T022 attestation commit `8777893` subsequently passed
both jobs in GitHub Actions run
[`31037373794`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31037373794).
The worktree and `origin/main` were equal before the next implementation slice
started.

Three independent, model-free contracts were then written before their
implementations. The initial red-phase revision of
`crates/mlx-backend/tests/router_contract.rs` defined five
Rust tests for exact complete-F32 tensor admission, all 128 logits and
probabilities per row, ordered top-8 IDs, selected and normalized values,
canonical hashes, complete comparison metrics, and ten-repeat identity. Its
focused command exited 101 solely at the intended missing
`mlx_backend::router` import.

The initial red-phase revision of
`python/pulsar_mlx_worker/tests/test_router.py` defined three generated-data
tests for single-row and two-row evaluated GPU execution, complete outputs,
full-softmax then selected-probability renormalization, explicit evaluation and
synchronization, deterministic repetition, and CPU/fallback rejection before
MLX access. Its focused discovery stopped at the intended missing
`pulsar_mlx_worker.router` module.

The initial red-phase revision of
`scripts/research/tests/test_router_oracle.py` defined seven stub-only tests
for exact pinned-source identity, two identical captures, bounded cancellation,
sequential scalar-F32 accumulation, an injected independent NumPy cross-check,
source-import independence, and prohibition of model auto-download. All seven
failed at the single intended T034 boundary because `router_oracle.py` did not
yet exist. The exact commands were:

```sh
cargo test -p mlx-backend --test router_contract
PULSARMLX_MODEL_GGUF='' PYTHONPATH=python uv run python -m unittest \
  python/pulsar_mlx_worker/tests/test_router.py -v
PULSARMLX_MODEL_GGUF='' python3 -m unittest \
  scripts/research/tests/test_router_oracle.py -v
```

No command resolved, statted, hashed, opened, or executed an external
checkpoint. The Rust and Python failures are required red-phase evidence, not
passing capability claims.

### T026 generated complete-router fixture

The fixture candidate now defines two model-free cases at the exact
`[N,2048] × [2048,128]` shape with 128 experts and top-8 selection. Two
complete, finite, distinct one-hot hidden rows are stored as bounded JSON. The
complete expert-major F32 matrix is represented by an exact formula and
canonical hash rather than by committing its 1,048,576 generated bytes.
Independent standard-library scalar arithmetic retains complete logits and
full-softmax probabilities, ordered IDs, selected probabilities, normalized
weights, and canonical hashes for the one-row and two-row cases.

`python3 fixtures/research/router-v1/golden/generate.py --check` reported four
byte-identical generated files. A separate temporary-directory generation also
matched every byte. JSON parsing and an independent audit covered all 4,096
finite hidden values, all 262,144 recipe-derived weights, 384 retained logits
across the two overlapping cases, all selection/normalization relationships,
and every stored hash. No external artifact was located or accessed and no raw
weight buffer was written into the repository.

### Crash recovery and T027–T036 offline router completion

The host restarted after the generated-fixture slice and before its green
implementation milestone had been reconciled. Recovery found `main` at
`8777893`, equal to `origin/main`, with no merge, rebase, or cherry-pick in
progress. Fourteen modified tracked files and fifteen untracked files were
preserved in place. Static inspection found no truncated source and no staged
content. The newest changes mapped to T027 through T036 rather than to an
unrelated prior session, so they were reviewed and validated instead of reset,
cleaned, stashed, or recreated.

The recovery review identified and fixed two material oracle-provenance gaps
before any task credit or commit: checkpoint consumers had reopened a path
without enough binding to the originally admitted bytes, and reusable native
build directories could admit stale state. The repaired tooling creates fresh
attempt-owned overlay/build directories, hashes the exact capture source,
build inputs, tools, logs, and helper, checks full SHA-256 plus device/inode/size
around each capture consumer, has the helper independently recheck its admitted
identity, and surrounds the Python reader with read-only no-follow,
descriptor-bound full-hash admissions. Bounded JSON parsing now rejects
duplicate keys.

The worker no longer relies on an undocumented stable sort for ties. It builds
an explicit MLX lexicographic rank for probability descending then expert ID
ascending, and tests the all-equal case. Requested/selected GPU and no-fallback
fields are derived from validated MLX GPU, Metal, and sanitized device evidence
before tensor scheduling. Safe future command parsers remain lexical-only and
perform zero filesystem I/O before their task gates; canonical, symlink,
hard-link, and containment validators are separately tested for later gated
execution.

The following exact model-free commands passed with
`PULSARMLX_MODEL_GGUF=''`:

```sh
export PULSARMLX_MODEL_GGUF=''
python3 fixtures/research/router-v1/golden/generate.py --check
cargo test -p mlx-backend --test router_contract
cargo test -p mlx-backend --lib
cargo test -p mlx-backend --bin pulsar-mlx
PYTHONPATH=python uv run python -m unittest \
  python/pulsar_mlx_worker/tests/test_router.py -v
python3 -m unittest scripts/research/tests/test_router_oracle.py -v
cargo test -p mlx-backend --test router_worker_integration \
  real_python_worker_two_row_router_matches_committed_golden -- \
  --ignored --exact
PYTHONPATH=python uv run python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
python3 -m unittest discover -s scripts/research/tests -v
python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input fixtures/research/router-v1/evidence
python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity --fixture-only
```

Actual results were four byte-identical generated files; 6 Rust router-contract
tests; 9 focused worker-router tests; 12 oracle tests; one explicit
Rust-to-real-Python generated-worker integration; 53 complete worker tests; and
53 complete research tests, all passing. Evidence validation accepted one
fixture record. Fixture-only package verification accepted that record and
byte-regenerated six publication artifacts with zero promoted claims. The
focused `mlx-backend` library and CLI suites passed 9 tests each. No worker or
oracle process remained after validation.

The recovered T034 oracle tooling was additionally hardened without checkpoint
access. A real run now retains both complete capture byte files, both callback
records, and both canonical marker-delimited scheduler traces reconstructed
only from normalized parsed CPU split fields, so raw diagnostic lines,
suffixes, and private paths cannot enter the bundle. It assembles and
revalidates the entire candidate in a fresh hidden sibling directory,
fsyncs every artifact and the directory, and uses macOS `renamex_np` with
`RENAME_EXCL` (or Linux `renameat2` with `RENAME_NOREPLACE`) as the only final
visibility transition. The model-free publication test proved complete-bundle
success, overwrite refusal without destination mutation, and incomplete-bundle
failure with the requested destination absent. Shell syntax, Python bytecode
compilation, strict no-header C++ syntax, 12 focused oracle tests, 53 research
tests, and four-file generated-fixture regeneration all passed.

This completion is only the generated model-free complete-router seam. The
pinned live llama.cpp headers/API, external GGUF inventory, genuine
`ffn_norm-0` capture, independent real oracle, and real Apple comparison remain
unexecuted and unverified at their later gates.

### T037 pre-stage workspace and preservation gates

Spec Kit 0.15.2 reported a healthy Codex integration and resolved the active
feature to `specs/002-qwen-router-parity`; the requirements checklist remained
16/16 complete. The exact workspace commands passed:

```sh
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
cargo test --workspace -- --list | rg ': test$' | wc -l
git diff --check
```

The check emitted only the recorded inherited `quant` `unused_mut` warning and
thirteen macOS `serve` dead-code warnings. The workspace inventory listed 187
tests; the exact run passed 185 active tests, failed zero, and left two explicit
native fixture integrations ignored in the ordinary workspace invocation. The
Feature 002 generated router integration passed separately as recorded above.

A targeted diff gate confirmed no changes under the root workspace manifest or
the inherited `engine`, `kernels`, `serve`, `stream`, `quant`, or `gguf` trees.
The implementation changes are additive inside `mlx-backend`, the Python MLX
worker, research tooling/fixtures, documentation, and the fixture-only macOS
workflow. The standardized staged scan passed separately before each of the
first three focused commits:

- `eb00753` — `feat(mlx): add generated complete-router path`;
- `3f49a35` — `feat(research): add independent router oracle tooling`; and
- `03c8456` — `ci: exercise generated router bridge`.

Each staged scan covered whitespace, secrets, private paths and identifiers,
model/tensor/binary/cache/large-file exclusions, and Linux/CUDA selection
changes. The documentation/task-state slice then passed the same scan. With
that fourth result, the exact workspace, focused, preservation, diff, and
staged-safety gates required by T037 are complete.

Every recovery and validation command above kept the external-model variable
empty or used committed generated data only. Feature 002 has not resolved,
statted, hashed, opened, or executed the external checkpoint, and the NTFY
hardware-pause notification is not yet eligible.

### T038 pushed router-core CI attestation

The four focused T038 commits were pushed to `origin/main` without force:

- `eb00753` — `feat(mlx): add generated complete-router path`;
- `3f49a35` — `feat(research): add independent router oracle tooling`;
- `03c8456` — `ci: exercise generated router bridge`; and
- `2d331f2` — `docs: record offline router milestone`.

GitHub Actions run
[31047672003](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31047672003)
executed for exact head SHA `2d331f2043157165a5017d9e94b6f60aac0697b9`
and completed successfully. Its `Apple Silicon workspace baseline` job passed
the exact workspace check and test commands. Its `Apple MLX small-fixture
validation` job passed the fixture-only boundary and research checks, the
lockfile-backed worker tests, the explicit Rust-to-real-Python generated-router
integration, native MLX device/tensor/routed-MoE fixtures, and bounded evidence
verification. Both jobs concluded `success`; no external checkpoint or model
weight was accessed. T038 is therefore complete and the fail-closed T039–T049
safety slice is eligible to begin.
