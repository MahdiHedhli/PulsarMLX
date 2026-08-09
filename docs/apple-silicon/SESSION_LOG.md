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

The non-recursive documentation attestation was committed as `b337d8c`
(`docs: attest offline router CI`) and pushed to `origin/main`. Its exact
follow-up GitHub Actions run
[31047832024](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31047832024)
also concluded `success`: `Apple MLX small-fixture validation` passed in 37
seconds and `Apple Silicon workspace baseline` passed in 1 minute 40 seconds.
This later run is reported here but does not recursively require another
attestation-only commit.

### T039–T041 fail-closed red tests and fixtures

The fail-closed safety slice began without model access. T039 added production-
seam-directed Rust tests for role occurrence and aliases, type, quantization,
dimensions, layout, range count/overflow, top-k, full-range identity, file-size
mutation, non-finite F32 data, symlink/hard-link mutation, resource admission,
and runner invocation. The final tests-first command was:

```sh
export PULSARMLX_MODEL_GGUF=''
cargo test -p mlx-backend --test router_contract -- --nocapture
```

It failed at compilation as intended because the tests require the new
production `with_admitted_router_tensor_f32` execution gate and
`RouterResourceAdmission` type that T042 must implement. Earlier in the same
red iteration, before replacing test-local runner helpers with that production
seam, 17 tests ran: 14 passed and three failed on the missing/duplicate role,
tensor-role alias, and F32/quantization stable-code gaps. The compile-red state
is therefore deliberate test-first evidence, not a claimed passing result.

T040 added bounded worker/protocol rejection tests and ran:

```sh
export PULSARMLX_MODEL_GGUF=''
PYTHONPATH=python uv run python -m unittest \
  python/pulsar_mlx_worker/tests/test_router.py -v
```

The run executed 19 test methods and produced 15 intentional failing subcases:
five file/canonical byte-count mutations returned `internal_worker_error`
instead of `invalid_byte_count`; six invalid device/fallback scalar types
returned `device_unavailable` instead of `malformed_request`; and four
syntactically malformed case IDs returned `unsupported_operation` instead of
`malformed_request`. All new shape, dtype, non-finite, fallback, stable-unknown
identity, and access-trap cases otherwise passed. The spies verified no router
runner or MLX array/scheduling surface was reached by rejected inputs.

T041 added seven bounded strict-JSON negative fixture descriptions and one
complete synthetic tie document containing both exact-cutoff and one-F32-logit-
ULP near-tie cases across all 128 experts. A review found and corrected one
initial non-finite mutation coordinate; the regenerated fixture now targets an
authoritative positive-zero cell. The exact check:

```sh
python3 fixtures/research/router-v1/golden/generate.py --check
```

reported 12 generated files byte-identical. Strict parsing, manifest byte
lengths and SHA-256 identities, exact/near-tie ordering, existing worker case
loading, byte bounds, and `git diff --check` passed. Independent read-only
reviews found no remaining high or medium issue in the Python tests or fixture
slice. No command in T039–T041 resolved, statted, opened, or executed an
external checkpoint; the NTFY hardware-pause gate remains ineligible.

### T042–T044 fail-closed router admission and tie policy

T042 implemented one production pre-execution seam that admits the exact
router descriptor, resource state, positional range, SHA-256 identity, byte
count, and finite F32 values before invoking a caller-supplied router runner.
Missing and duplicate tensor roles, aliases, wrong F32 type or quantization,
shape/layout/top-k mismatches, changed size or hash, short/overlong/overflowing
ranges, non-finite data, and failed disk/unified-memory/pressure admission now
return their frozen bounded codes without reaching that runner. A read-only
review identified that the public positional-read helper could otherwise try
an arbitrary allocation; it now rejects ranges larger than the complete
1,048,576-byte router tensor and reserves its bounded buffer fallibly.

T043 moved worker control, shape, dtype, finiteness, canonical/encoded byte
count, explicit-GPU, and no-fallback checks ahead of MLX array construction or
router-runner access. It shares the protocol's bounded identifier validator,
distinguishes malformed from stable-but-unsupported case IDs, and preserves
normal startup discovery and graceful shutdown.

T044 introduced an explicit `SyntheticFixture` versus `RealCheckpoint` scope
at both Rust and Python result-validation seams. Scope is never inferred from
a case-ID prefix. Synthetic results rank all 128 probabilities by probability
descending then expert ID ascending; an exact F32 equality across real ranks
eight and nine returns `comparison_failed`. Rust stores the scope in output,
comparison, and repeat identities so synthetic and real evidence cannot be
mixed. The committed exact-tie and representable near-tie fixture is consumed
only as an independent test expectation; the bounded MLX execution still
performs route selection on GPU and host policy validation only after evaluated
synchronization.

The following exact model-free checks passed with the external-model variable
empty:

```sh
export PULSARMLX_MODEL_GGUF=''
cargo test -p mlx-backend --test router_contract --no-fail-fast
cargo test -p mlx-backend --test router_worker_integration --no-run
cargo test -p mlx-backend --all-targets
cargo fmt -p mlx-backend -- --check
cargo clippy -p mlx-backend --all-targets -- -D warnings
PYTHONPATH=python uv run python -m unittest \
  python/pulsar_mlx_worker/tests/test_router.py -v
PYTHONPATH=python uv run python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
python3 fixtures/research/router-v1/golden/generate.py --check
python3 -m py_compile python/pulsar_mlx_worker/__main__.py \
  python/pulsar_mlx_worker/protocol.py \
  python/pulsar_mlx_worker/router.py \
  python/pulsar_mlx_worker/tests/test_router.py
git diff --check
```

Actual results were 21 Rust router-contract tests passing; the generated
worker integration compiling; 83 active `mlx-backend` all-target tests
passing with two explicit native integrations ignored; focused rustfmt and
strict Clippy passing; 23 focused router-worker tests and all 67 worker tests
passing; 12 generated files byte-identical; Python compilation and diff checks
passing. Independent read-only reviews found no remaining high or medium issue
in T042, T043, or T044. These checks used committed generated fixtures only;
Feature 002 still has not resolved, statted, hashed, opened, or executed an
external checkpoint, and no NTFY hardware-pause notification was sent.

### T045 retained model-free router fixture evidence

`validate-router-fixtures` now admits only the canonical committed manifest,
rejects duplicate JSON keys recursively, checks the exact ordered 11-file
inventory, byte lengths, SHA-256 identities, non-link containment, generator
identity, golden outputs, synthetic tie declarations, and seven negative
contracts. Before worker startup it proves inherited model descriptor 198 is
closed, explicitly passes an empty `PULSARMLX_MODEL_GGUF`, and rejects a worker
that advertises the model-slice operation. Both positive cases run through one
evaluated MLX GPU worker and are reconstructed and compared independently in
Rust under `SyntheticFixture` scope.

The retained evidence distinguishes execution depth honestly: two positive
cases are labeled MLX GPU execution plus host golden comparison; exact and
near tie cases are labeled host contract validation; negative records are
labeled fixture contract validation and point to the focused rejection tests
rather than claiming mutation execution. Every record states that it is
synthetic/model-free and not real-checkpoint evidence. Started workers are
always cleaned up, partial passing observations survive a later failure, and
failed or aborted evidence is written before the command returns nonzero. The
external evidence install is bounded, private-path checked, atomic, and
exclusive; an existing destination is never replaced.

The exact model-free validation commands included:

```sh
export PULSARMLX_MODEL_GGUF=''
cargo test -p mlx-backend --bin pulsar-mlx --no-fail-fast
cargo test -p mlx-backend --all-targets
cargo check -p mlx-backend --all-targets
cargo fmt -p mlx-backend -- --check
cargo clippy -p mlx-backend --all-targets -- -D warnings
cargo run -p mlx-backend --bin pulsar-mlx -- validate-router-fixtures \
  --manifest fixtures/research/router-v1/manifest.json \
  --evidence <external-temporary-directory>/router-fixtures.json
python3 -m json.tool \
  <external-temporary-directory>/router-fixtures.json
git diff --check
```

Actual results were 13 CLI tests passing; 87 active `mlx-backend` all-target
tests passing with two native tests ignored; package check, focused rustfmt,
strict Clippy, JSON parsing, and diff checks passing. The real command retained
two MLX/golden positive cases, two host-contract synthetic tie cases, seven
negative contracts, and 11 hashed manifest files. Worker cleanup was graceful
with exit code zero. The evidence was 13,250 bytes and reported `status` as
`passed`, `model_free` as true, and both `real_checkpoint_evidence` and
`external_checkpoint_accessed` as false. A separate forced-open descriptor-198
review case returned exit 2, retained bounded aborted evidence, and started no
worker. An independent read-only review found no high or medium issue. The
temporary evidence was inspected and removed. No checkpoint path or model byte
was accessed, and the T073 NTFY gate remains ineligible.

### T046–T047 fail-closed safety validation

T046 replayed the complete model-free router fixture boundary with
`PULSARMLX_MODEL_GGUF` explicitly empty. The exact focused commands were:

```sh
python3 fixtures/research/router-v1/golden/generate.py --check
cargo test -p backend --test routing_contract --no-fail-fast
cargo test -p mlx-backend --test router_contract --no-fail-fast
PYTHONPATH=python uv run python -m unittest \
  python/pulsar_mlx_worker/tests/test_router.py -v
PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend \
  --test router_worker_integration \
  real_python_worker_two_row_router_matches_committed_golden -- \
  --ignored --exact
cargo run -p mlx-backend --bin pulsar-mlx -- validate-router-fixtures \
  --manifest fixtures/research/router-v1/manifest.json \
  --evidence <external-temporary-directory>/router-fixtures.json
```

The generator reported 12 files byte-identical. Eight backend-neutral routing
tests, 21 Rust router-contract tests, 23 focused Python router tests, and the
one explicitly selected generated Rust-to-Python integration test passed. The
retained fixture command again recorded two evaluated MLX GPU positive cases,
two host-contract tie cases, seven fixture-contract negative cases, and all 11
manifest files. Its seven stable negative codes were, in manifest order,
`malformed_request`, `invalid_shape`, `invalid_layout`,
`model_tensor_mismatch`, `invalid_dtype`, `invalid_byte_count`, and
`invalid_byte_count`. Both positive cases requested and selected GPU, reported
no fallback, evaluated and synchronized, and matched the independent Rust
golden comparison. Cleanup was graceful with worker exit zero. The bounded
13,256-byte temporary evidence reported `model_free: true`,
`real_checkpoint_evidence: false`, and `external_checkpoint_accessed: false`;
it was inspected and removed rather than committed.

T047 then ran the exact model-free research, workspace, and Feature 001
regression gates:

```sh
scripts/research/setup.sh
python3 -m unittest discover -s scripts/research/tests -v
python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input fixtures/research/router-v1/evidence
python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity \
  --fixture-only
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
cargo test --workspace -- --list | rg ': test$' | wc -l
PYTHONPATH=python uv run python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
cargo test -p backend --all-targets
cargo test -p quant --test q8_0_reference
cargo test -p stream --test positional_source
cargo test -p stream --lib
cargo test -p mlx-backend --test worker_contract
cargo test -p mlx-backend --test tensor_contract
cargo test -p mlx-backend --test synthetic_moe
cargo test -p mlx-backend --test model_slice_client
cargo test -p mlx-backend --test real_model_contract
cargo test -p mlx-backend --bin pulsar-mlx \
  tests::committed_reference_result_matches_the_frozen_loader_contract \
  -- --exact
git diff --exit-code 8e10012 -- specs/001-apple-silicon-mlx
git diff --check
```

Research setup reported ready in offline mode. All 53 research tests passed in
3.736 seconds; the schema validator accepted its one fixture record. The
fixture-only verifier accepted one full-schema record, zero promoted claims,
and six generated artifacts; its candidate and sanitized SHA-256 were both
`c9205fb118429d39cca6339b8cba9d45aa60c01e0f96820d5dca56aaaffa119e`.

The workspace check passed. The workspace test command reported 204 active
tests passed, zero failed, and two explicit native integrations ignored across
45 harness result lines. Independent inventory listed 206 test cases, exactly
the 204 active plus two ignored cases. The complete Python worker discovery
passed all 67 tests. The requested Feature 001 Cargo regressions passed 120
tests with zero failures or ignores: backend 57, Q8_0 reference 14, positional
source 14, stream library 1, worker contract 12, tensor contract 7, synthetic
MoE 4, model-slice client 4, real-model contract 6, and the exact frozen CLI
reference 1. That exact CLI invocation filtered 12 unrelated tests.

The initially requested preservation comparison against quickstart commit
`5a43cf0` returned exit 1 because the later legitimate Feature 001 closing
commit `8e10012` updated its status and completion documents. The corrected
path-scoped comparison against `8e10012` passed, proving the
`specs/001-apple-silicon-mlx` artifacts are unchanged since that closing
commit; the 120 requested regressions provide behavioral preservation evidence
only for their exercised paths. Workspace commands reproduced the inherited
`unused_mut` warning in `crates/quant/src/iq.rs` and 13 macOS `serve` dead-code
warnings; no new failure was hidden as inherited debt. Diff checks passed and
the worktree remained clean after validation.

No T046 or T047 command resolved, statted, hashed, opened, or executed an
external checkpoint. No NTFY notification was sent, and local inference did
not need to pause.

### T048 failure coverage and selection review

The limitations and validation quickstart now distinguish host admission,
worker control admission, in-runner pre-array validation, positive MLX
execution, host-only tie validation, fixture-contract negative validation, and
real-checkpoint exclusions. An independent read-only review found two wording
overclaims: direct matrix/runtime-device checks had been described as occurring
before router-runner dispatch, and a path-scoped Feature 001 specification diff
had been described as proving the whole feature unchanged. Both were corrected
to their actual boundaries before completion.

The staged set contained only this session log, the known-limitations document,
the Feature 002 quickstart, and Feature 002 task state. It contained no Rust,
Python, Cargo, workflow, research-scanner, platform-selector, or inherited
execution-path change. The standardized staged safety scan passed, the staged
diff check passed, and an explicit selection-path diff was empty. Spec Kit
0.15.2 health, Codex integration status, and feature prerequisite resolution
also passed; prerequisites continued to resolve
`specs/002-qwen-router-parity` with its research, data-model, contract, and
quickstart artifacts.

This review did not execute the inherited Linux or CUDA runtime and makes no
runtime-parity claim. It verified that this safety slice did not alter their
selection behavior. No checkpoint was accessed and no NTFY notification was
sent.

### T049 fail-closed safety CI

The safety slice was committed in four focused commits and pushed to
`origin/main` without force:

- `09e021a` — `test(mlx): specify fail-closed router inputs`
- `75a5e84` — `feat(mlx): enforce fail-closed router admission`
- `1337d5f` — `feat(mlx): retain router fixture evidence`
- `d0b092e` — `test(mlx): close fail-closed router safety gate`

Push-triggered GitHub Actions run
[31052297102](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31052297102)
completed with conclusion `success` for full commit
`d0b092e7ba7bee054e869a2a2b13ecce0baa8d26`. `Apple MLX small-fixture
validation` passed in 48 seconds: 53 research tests, one schema record, the
fixture-only six-artifact package, 67 worker tests, the explicitly selected
generated router integration, native MLX device smoke, seven bounded tensor
fixtures, synthetic routed-MoE execution, and the final external-model
exclusion check all passed. `PULSARMLX_MODEL_GGUF` remained empty throughout
that job. `Apple Silicon workspace baseline` passed in 1 minute 13 seconds;
the exact workspace check succeeded and 45 test harnesses reported 204 passed,
zero failed, and two ignored tests.

Both required jobs ran on the workflow's `macos-15` arm64 boundary and every
step completed successfully. This fixture-only CI run did not access an
external checkpoint and does not authorize one by itself: the later T060,
T071, T072, and T073 gates remain required before T074 can touch the model.
No NTFY notification was sent.

### T050–T051 publication-contract red tests

The fixture-only publication slice began with production-seam tests and an
explicitly empty `PULSARMLX_MODEL_GGUF`. The exact commands were:

```sh
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts/research/tests/test_feature002_records.py
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts/research/tests/test_generators.py
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts/research/tests/test_verify_package.py
git diff --check
```

T050 ran six test methods and produced 15 intentional failure records. Two
expected-green subcases showed that retained failed and aborted observations
are not yet admitted with their bounded failure metadata. Nine mutation
subcases showed missing enforcement for the frozen model, protocol, and
artifact identities. Non-contiguous attempt indices, mathematically impossible
correctness metrics, overlap between a supported capability and an unsupported
interpretation, and verified promotion from a dirty post-run tree were also
accepted incorrectly. Four existing tensor/input/oracle cross-link mutation
subcases already failed closed as expected.

T051's generator suite ran five methods: four passed and one intentionally
failed because provenance sidecars still name raw sources by basename rather
than repository-relative package path. Its package/publication suite ran 16
methods: eight passed and eight red methods produced 18 intentional failure
records. The missing seams are package-relative claim-link containment,
complete sidecar provenance validation, duplicate logical experiment and claim
IDs, recursive private-identifier/secret-shaped-key rejection, reviewer-index
completeness, exact-scope claim enforcement, and refusal to promote provisional
linked evidence as verified.

An independent review found four medium test-design issues in the first draft.
The final tests make top-level failed/aborted state coherent with retained
attempts, cover protocol/artifact identity in addition to the inherited model
and existing cross-links, separate scope overclaim from verified promotion,
and mutate every required sidecar provenance field plus missing/absolute/parent
link escapes. Re-review passed with no remaining high or medium finding. The
final 34 failure records are deliberate tests-first evidence rather than
accidental setup errors, and `git diff --check` passed.

No command accessed a checkpoint, started model inference, or sent NTFY. These
red tests establish required behavior only; none of the missing production
seams is claimed implemented yet.

### T052 bounded evidence outcome fixtures

The direct fixture collection now contains three full-schema, model-free
records: one passing methodology record, one failed record with its terminal
attempt retained, and one aborted record with its terminal attempt retained.
The passing record is bound to the inherited Feature 001 model identity, actual
protocol and fixture-manifest hashes, real pre-fixture source commit
`b8eabcbdc4ba4bc23478b1f8d103dabf2c65f9e7`, and pinned llama.cpp oracle-source
revision `b06aa774c03dbbb624e726664b714a57d1f49815`. All three machine-readable claim
boundaries explicitly list `real_checkpoint_routing` as unsupported and label
their timings as deterministic policy data rather than measurements.

The experiment schema and structural validator now admit optional bounded
observation `failure` and `exclusion_rule_id` fields. Failed and aborted
terminal attempts report `fixture_contract_validation` duration rather than an
evaluated-router stage because they were neither evaluated nor synchronized.
A fourth full-schema excluded record lives only under `evidence/mutations/`.
It declares itself an expected semantic rejection: frozen v1 has no exclusion
rule, so it is not discovered as accepted fixture evidence and cannot support a
claim. T053 must add that semantic rejection rather than amend the protocol.

The exact model-free validation included:

```sh
find fixtures/research/router-v1/evidence -type f -name '*.json' \
  -print0 | xargs -0 -n1 jq -e .
PULSARMLX_MODEL_GGUF='' python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input fixtures/research/router-v1/evidence
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts/research/tests/test_validate_evidence.py
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts.research.tests.test_verify_package.PublicationBoundaryTests.test_fixture_only_package_cli_is_model_independent_and_read_only
PULSARMLX_MODEL_GGUF='' python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity \
  --fixture-only
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts/research/tests/test_feature002_records.py
python3 -m py_compile scripts/research/validate_evidence.py \
  scripts/research/tests/test_verify_package.py
git diff --check
```

All JSON parsed; the accepted collection reported three records; all 13 prior
validator tests and the one focused fixture-package test passed. The direct
package verifier reported three full-schema records, six deterministic
artifacts, and zero claims. Source/oracle revisions, protocol/artifact hashes,
scope exclusions, file bounds, non-link status, Python compilation, and diff
checks passed. T050's retained failed/aborted method is now green while 13
intentional T053 semantic failures remain.

One initial focused-unittest invocation incorrectly supplied the class method
as a second module name after a file path. It therefore ran the expected-red
T051 module and ended with one `ModuleNotFoundError`; the corrected fully dotted
selector above passed one of one. This was an invocation error, not a fixture
or implementation failure.

An independent review found placeholder commit provenance, an omitted
machine-readable real-routing exclusion, and an evaluated-stage label on
unevaluated terminal attempts. All three were corrected and re-review passed
with no remaining high or medium issue. No model path was resolved or opened,
no MLX/model execution occurred, and no NTFY notification was sent.

### T053 fail-closed evidence semantics

The Feature 002 validator now pins the exact model revision and SHA-256, frozen
protocol hash and seed, pinned oracle revision, and repository artifact
identities without resolving `$PULSARMLX_MODEL_GGUF`. Repository links are
canonical, bounded, regular, non-symlinked paths whose content hashes are
recomputed. Fixture records require the exact protocol and fixture-manifest
bindings. Raw attempt indices are contiguous per compatible series; repetition
counts cannot be pooled across condition or instrumentation boundaries;
summaries cannot pool process states; failed and aborted attempts retain
bounded failure identities; and evaluated comparison failures may retain their
GPU output and false correctness result.

Correctness validation now rejects non-finite or malformed scalars, widened
v1 logit tolerances, impossible `mean <= RMSE <= maximum` relationships,
contradictory mismatch counts, and nondeterministic passing hashes. Claim
boundaries require every FR-032 exclusion plus the earlier stable
`full_model_generation` and `token_throughput` spellings, reject supported and
unsupported overlap, and reject raw-v1 `verified` status because the raw schema
cannot prove committed/indexed clean-checkout reproduction. Verified promotion
remains a package-level responsibility. Frozen protocol v1 continues to reject
all exclusions because it declares no exclusion rule.

The final model-free validation commands were:

```sh
python3 -m py_compile scripts/research/validate_evidence.py \
  scripts/research/tests/test_validate_evidence.py \
  scripts/research/tests/test_feature002_records.py
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts.research.tests.test_validate_evidence \
  scripts.research.tests.test_feature002_records
PULSARMLX_MODEL_GGUF='' python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input fixtures/research/router-v1/evidence
PULSARMLX_MODEL_GGUF='' python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input fixtures/research/router-v1/evidence/mutations/f002-router-fixture-excluded-0001.json
PULSARMLX_MODEL_GGUF='' python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity --fixture-only
PULSARMLX_MODEL_GGUF='' python3 -m unittest discover \
  -s scripts/research/tests -v
git diff --check
```

Compilation passed. The focused suite passed 29 of 29 tests in 3.108 seconds;
the accepted fixture directory reported exactly three records; the excluded
mutation exited 1 with bounded `semantic_relationship` output and no traceback
or private path; and fixture-only package verification accepted three records,
zero claims, and six deterministic generated artifacts. Full research
discovery ran 79 methods and retained exactly 19 intentional red-contract
failures, all assigned to the still-incomplete T054/T055 publication,
sidecar, claim-link, and reviewer-index seams. `git diff --check` passed.

Two independent review rounds found and closed fixture-promotion laundering,
evaluated-failure loss, malformed-scalar tracebacks, mutable identity pins,
noncanonical artifact aliases, incomplete fixture links, cross-series count
pooling, cross-process-state summaries, inferred clean-process requirements for
auxiliary diagnostics, schema recursion/size exposure, and silently widened
tolerances. The final review reported no remaining high or medium finding.

No command accessed a checkpoint, resolved or opened a model path, executed
MLX/model code, consumed Apple GPU memory, or sent NTFY. Local inference did
not need to pause.

### T054 append-only evidence publication

The publication boundary now validates the complete existing JSON history
before accepting a candidate, rejects duplicate logical experiment IDs and
noncanonical filenames, and installs canonical sanitized bytes with an
exclusive hard-link commit point. Candidate and history reads are bounded,
regular-file-only, no-follow operations. Structural depth/node counts,
aggregate history size, local metadata, private identifiers and paths,
secret-shaped keys and values, malformed scalar types, and non-finite JSON all
fail closed with bounded messages. If an error occurs after the exclusive link,
publication either removes the destination or reports the installed record as
success; it never reports failure while its new record remains installed.

The final model-free validation commands were:

```sh
python3 -m py_compile scripts/research/publish_evidence.py \
  scripts/research/tests/test_verify_package.py
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts.research.tests.test_verify_package.PublicationBoundaryTests.test_candidate_sanitization_drops_only_declared_local_metadata \
  scripts.research.tests.test_verify_package.PublicationBoundaryTests.test_publish_is_append_only_and_refuses_overwrite \
  scripts.research.tests.test_verify_package.PublicationBoundaryTests.test_publish_rejects_duplicate_identity_under_an_existing_filename \
  scripts.research.tests.test_verify_package.PublicationBoundaryTests.test_publish_rejects_invalid_existing_history_without_changes \
  scripts.research.tests.test_verify_package.PublicationBoundaryTests.test_private_identifier_and_secret_shaped_keys_are_rejected \
  scripts.research.tests.test_verify_package.PublicationBoundaryTests.test_failed_validation_leaves_no_partial_publication \
  scripts.research.tests.test_verify_package.PublicationBoundaryTests.test_malformed_numeric_and_depth_errors_are_bounded \
  scripts.research.tests.test_verify_package.PublicationBoundaryTests.test_post_link_failure_never_reports_failure_with_an_installed_record \
  scripts.research.tests.test_verify_package.PublicationBoundaryTests.test_symlink_destination_is_rejected_without_touching_target
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts.research.tests.test_validate_evidence \
  scripts.research.tests.test_feature002_records
PULSARMLX_MODEL_GGUF='' python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity --fixture-only
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts.research.tests.test_verify_package
PULSARMLX_MODEL_GGUF='' python3 -m unittest discover \
  -s scripts/research/tests -q
git diff --check
```

Compilation passed; the nine focused publication methods passed in 0.052
seconds; and the 29 semantic-validator methods passed in 3.307 seconds. The
fixture-only package accepted exactly three records and regenerated six
artifacts with zero claims. The full publication module ran 19 methods and
retained exactly 15 intentional T055 claim-link, sidecar, claim-promotion, and
reviewer-index failures. Full research discovery ran 82 methods and retained
exactly 16 intentional T055 failures: those 15 package failures plus one
repository-relative sidecar-source failure. `git diff --check` passed.

Independent review passes found and closed malformed compact status types,
short and quoted credential assignments, compound and camel-case secret-key
aliases, full-record credential strings, and split-argument secret options.
Regression cases preserve legitimate direct token-ID identifiers. The final
independent review passed with no remaining high or medium finding; its focused
run also passed nine of nine methods. No model path was resolved or opened, no
checkpoint or MLX execution occurred, no Apple GPU memory was used, and no
NTFY notification was sent. Local inference did not need to pause.

### T055 deterministic publication package verification

The generators now consume bounded, duplicate-key-free, regular no-follow
records through single descriptors, semantically validate every full-schema
record, retain exact source-byte hashes, and reject symlinked ancestors and
mid-read mutation. Table output carries experiment/group identity, status,
scope, every required Type-7 timing statistic and undefined-value reason, and
the available correctness counts and error metrics. The bounded SVG labels
status, correctness, and scope and visually distinguishes non-passing records.
CSV, Markdown, SVG, sidecar, row, record, and aggregate input sizes are bounded;
multi-file generation uses exclusive writes and rolls back earlier outputs on
failure.

Provenance sidecars now use canonical repository-relative source paths for
repository inputs, safe basenames for external temporary fixtures, exact
source and output hashes, current generator hashes, frozen commands, and exact
sorted source-commit sets. Package verification fail-closes on malformed or
noncanonical sidecars, unsafe links, duplicate claim identities, mismatched
commits/scopes, invalid claim promotion, incomplete reviewer coverage, private
or secret values in publication Markdown, and fresh regeneration that differs
from committed generated bytes. The zero-claim and zero-real-output scaffold
remains valid. Default complete-package verification now checks the publication
index and committed regeneration in addition to raw records.

The final model-free validation commands were:

```sh
python3 -m py_compile scripts/research/generate_tables.py \
  scripts/research/generate_figures.py \
  scripts/research/verify_package.py \
  scripts/research/tests/test_generators.py \
  scripts/research/tests/test_verify_package.py
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts.research.tests.test_generators \
  scripts.research.tests.test_verify_package
PULSARMLX_MODEL_GGUF='' python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity --fixture-only
PULSARMLX_MODEL_GGUF='' python3 -m unittest -v \
  scripts.research.tests.test_validate_evidence \
  scripts.research.tests.test_feature002_records
PULSARMLX_MODEL_GGUF='' python3 -m unittest discover \
  -s scripts/research/tests -q
git diff --check
```

Compilation passed. The focused generator/publication suite passed 28 of 28
methods in 0.559 seconds. Fixture-only verification accepted exactly three
full-schema records, regenerated six byte-stable artifacts, and retained zero
claims. The semantic suite passed 29 of 29 methods in 3.460 seconds. Full
research discovery passed all 86 methods in 6.639 seconds, closing every
intentional T050/T051 red contract. `git diff --check` passed.

Independent review identified and closed aggregate and output bounds,
symlinked-ancestor handling, source-read races, incomplete timing columns,
ambiguous failed/aborted visualization, deterministically wrong committed
outputs, and private publication-document values. The final independent run
passed all 28 focused methods and reported no remaining high or medium issue.
No model path was resolved or opened, no checkpoint or MLX execution occurred,
no Apple GPU memory was used, and no NTFY notification was sent. Local
inference did not need to pause.

### T056 frozen fixture-derived publication outputs

Six small expected artifacts are now committed under
`fixtures/research/router-v1/expected/`: CSV and Markdown tables, one bounded
status-aware SVG, and one canonical provenance sidecar per generated output.
They derive only from the three checked-in full-schema methodology fixtures.
No mutation fixture, external candidate, model file, or local measurement was
an input. The artifact-only commit is `ed9846a` (`test(research): freeze fixture
publication outputs`).

The exact generation and reproduction commands were:

```sh
PULSARMLX_MODEL_GGUF='' python3 scripts/research/generate_tables.py \
  --raw-dir fixtures/research/router-v1/evidence \
  --output-dir fixtures/research/router-v1/expected/tables
PULSARMLX_MODEL_GGUF='' python3 scripts/research/generate_figures.py \
  --raw-dir fixtures/research/router-v1/evidence \
  --output-dir fixtures/research/router-v1/expected/figures
t056_tmp=$(mktemp -d "${TMPDIR:-/tmp}/pulsarmlx-t056.XXXXXX")
case "$t056_tmp" in
  */pulsarmlx-t056.*) ;;
  *) exit 1 ;;
esac
PULSARMLX_MODEL_GGUF='' python3 scripts/research/generate_tables.py \
  --raw-dir fixtures/research/router-v1/evidence \
  --output-dir "$t056_tmp/expected/tables"
PULSARMLX_MODEL_GGUF='' python3 scripts/research/generate_figures.py \
  --raw-dir fixtures/research/router-v1/evidence \
  --output-dir "$t056_tmp/expected/figures"
diff -ru fixtures/research/router-v1/expected "$t056_tmp/expected"
find fixtures/research/router-v1/expected -type f -print0 | sort -z | \
  xargs -0 shasum -a 256
rm -r -- "$t056_tmp"
scripts/research/check_staged.sh
git diff --cached --check
```

Both generation commands passed with four table-side and two figure-side
outputs. Independent temporary regeneration produced no `diff` output. The
six committed files total 15,638 bytes; their SHA-256 values are recorded in
their sidecars and were recomputed before staging. The staged safety scan and
cached diff check passed, and the artifact commit contains only those six
fixture-derived files.

No model path was resolved or opened, no checkpoint or MLX execution occurred,
no Apple GPU memory was used, and no NTFY notification was sent. Local
inference did not need to pause.

### T057 clean-checkout fixture reproduction

A detached temporary worktree at exact commit `d6f5820` reproduced the six
fixture-derived publication artifacts outside the checkout. The source
worktree was clean before generation and remained clean afterward. Recursive
name/byte comparison and an independently sorted SHA-256 manifest comparison
both produced no differences. The temporary checkout and generated output were
removed after the clean result; `git worktree list --porcelain` then named only
the primary worktree.

The reproduction commands were:

```sh
t057_root=$(mktemp -d "${TMPDIR:-/tmp}/pulsarmlx-t057.XXXXXX")
t057_checkout="$t057_root/checkout"
t057_output="$t057_root/output"
git worktree add --detach "$t057_checkout" HEAD
git -C "$t057_checkout" status --porcelain
(
  cd "$t057_checkout"
  PULSARMLX_MODEL_GGUF='' python3 scripts/research/generate_tables.py \
    --raw-dir fixtures/research/router-v1/evidence \
    --output-dir "$t057_output/expected/tables"
  PULSARMLX_MODEL_GGUF='' python3 scripts/research/generate_figures.py \
    --raw-dir fixtures/research/router-v1/evidence \
    --output-dir "$t057_output/expected/figures"
  PULSARMLX_MODEL_GGUF='' python3 scripts/research/verify_package.py \
    --feature 002-qwen-router-parity --fixture-only
  PULSARMLX_MODEL_GGUF='' python3 -m unittest -q \
    scripts.research.tests.test_generators \
    scripts.research.tests.test_verify_package
)
diff -ru \
  "$t057_checkout/fixtures/research/router-v1/expected" \
  "$t057_output/expected"
diff -u \
  <(cd "$t057_checkout/fixtures/research/router-v1/expected" && \
    find . -type f -print0 | sort -z | xargs -0 shasum -a 256) \
  <(cd "$t057_output/expected" && \
    find . -type f -print0 | sort -z | xargs -0 shasum -a 256)
git -C "$t057_checkout" status --porcelain
git -C "$t057_checkout" diff --exit-code
git worktree remove "$t057_checkout"
rm -r -- "$t057_output"
rmdir "$t057_root"
```

Both generators passed with six outputs total. Fixture-only verification
accepted three records, six artifacts, and zero claims. The clean-checkout
focused suite passed 28 of 28 methods in 0.583 seconds. Both `diff` commands,
both worktree-status checks, and the Git diff check were empty. The regenerated
SHA-256 values exactly match the six hashes recorded for T056.

No model path was resolved or opened, no checkpoint or MLX execution occurred,
no Apple GPU memory was used, and no NTFY notification was sent. Local
inference did not need to pause.

### T058 fixture-publication documentation

The five Feature 002 publication documents now index all three accepted
synthetic records and all six frozen expected artifacts, distinguish fixture
methodology from model-backed results, define the four claims-ledger states,
and retain a zero-row ledger. They record artifact commit
`ed9846ac9b120580b579eb669ff4370b918a5c91`, the clean-checkout reproduction at
`d6f5820050cdc59944a7b2af26b7b0c2c15767c6`, and the exact fail-closed fresh
generation, recursive byte comparison, independently sorted SHA-256
comparison, candidate-validation, and append-only publication patterns.

The documented boundary keeps experiment outcomes separate from public claim
states. Raw attempts remain immutable; every retry or amendment receives a new
experiment ID; a raw v1 record cannot promote itself; and raw publication must
be committed and pushed before result artifacts are generated. Constructed
fixture timings, errors, identities, failed states, and aborted states remain
test data rather than checkpoint observations.

Validation commands and actual results were:

```sh
PULSARMLX_MODEL_GGUF='' python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity --fixture-only
# passed: 3 full-schema records, 6 deterministic artifacts, 0 claims

PULSARMLX_MODEL_GGUF='' python3 -m unittest discover \
  -s scripts/research/tests -v
# passed: 86 of 86 tests in 7.538 seconds

PULSARMLX_MODEL_GGUF='' python3 - <<'PY'
from pathlib import Path
import re

files = [
    Path('docs/research/REPRODUCIBILITY.md'),
    Path('docs/research/RESULTS.md'),
    Path('docs/research/LIMITATIONS.md'),
    Path('docs/research/CLAIMS_LEDGER.md'),
    Path('docs/research/REVIEWER_INDEX.md'),
]
missing = []
for source in files:
    text = source.read_text(encoding='utf-8')
    for target in re.findall(r'\[[^]]+\]\(([^)]+)\)', text):
        if '://' in target or target.startswith('#'):
            continue
        target = target.split('#', 1)[0]
        if not (source.parent / target).resolve().is_file():
            missing.append((source.as_posix(), target))
if missing:
    for source, target in missing:
        print(f'missing link: {source} -> {target}')
    raise SystemExit(1)
print(f'local markdown links: passed ({len(files)} documents)')
PY
# passed: all local links resolved

awk 'BEGIN{inside=0} /^```zsh$/{inside=1; next} \
  /^```$/{if(inside){exit}} inside{print}' \
  docs/research/REPRODUCIBILITY.md | zsh -n
# passed

git diff --check
# passed
```

The required Reviewer Index headings each occur exactly once in contract order.
Independent reviews found no remaining high- or medium-severity issue after the
single-file publisher example and fail-closed reproduction block were
corrected.

No model path was resolved or opened, no checkpoint or MLX execution occurred,
no Apple GPU memory was used, and no NTFY notification was sent. Local
inference did not need to pause.

### T059 complete safe-gate replay

Every currently implemented model-free command in the Feature 002 quickstart
was replayed with `PULSARMLX_MODEL_GGUF` explicitly empty. The exact command
groups were:

```sh
export PULSARMLX_MODEL_GGUF=''
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
cat .specify/feature.json
sed -n '1,360p' specs/002-qwen-router-parity/spec.md
sed -n '1,360p' specs/002-qwen-router-parity/plan.md
specify version
specify check
specify integration status
.specify/scripts/bash/check-prerequisites.sh --json

scripts/research/setup.sh
python3 fixtures/research/router-v1/golden/generate.py --check
python3 -m unittest discover -s scripts/research/tests -v
python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input fixtures/research/router-v1/evidence
python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity --fixture-only

cargo test -p backend --test routing_contract
cargo test -p mlx-backend --test router_contract
cargo check --workspace --all-targets
cargo test --workspace --no-fail-fast
cargo test --workspace -- --list | rg ': test$' | wc -l

PYTHONPATH=python uv run python -m unittest discover \
  -s python/pulsar_mlx_worker/tests -v
PYTHONPATH=python uv run python -m unittest \
  python/pulsar_mlx_worker/tests/test_router.py -v
PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend \
  --test router_worker_integration \
  real_python_worker_two_row_router_matches_committed_golden -- \
  --ignored --exact
cargo run -p mlx-backend --bin pulsar-mlx -- validate-router-fixtures \
  --manifest fixtures/research/router-v1/manifest.json \
  --evidence <new-external-temporary-directory>/router-fixtures.json
python3 -m json.tool \
  <new-external-temporary-directory>/router-fixtures.json

python3 scripts/research/generate_tables.py \
  --raw-dir fixtures/research/router-v1/evidence \
  --output-dir <new-external-temporary-directory>/expected/tables
python3 scripts/research/generate_figures.py \
  --raw-dir fixtures/research/router-v1/evidence \
  --output-dir <new-external-temporary-directory>/expected/figures
diff -ru fixtures/research/router-v1/expected \
  <new-external-temporary-directory>/expected
diff -u <sorted-committed-sha256-manifest> \
  <sorted-regenerated-sha256-manifest>
git diff --check
test -z "$(git status --porcelain=v1 --untracked-files=all)"
```

Actual results were Spec Kit CLI 0.15.2 ready with Codex integration healthy;
research setup ready offline; all 12 golden files byte-identical; 86 of 86
research tests passing in 6.671 seconds; three evidence records accepted; and
fixture-only verification accepting three records, six artifacts, and zero
claims. The backend routing and Rust router-contract suites passed 8 of 8 and
21 of 21 tests.

The workspace check passed. Workspace tests passed 204 active cases with two
native MLX cases explicitly ignored; independent listing counted 206 total.
The inherited `unused_mut` diagnostic and 13 macOS `serve` dead-code warnings
were unchanged. Python worker discovery passed 67 of 67 tests in 0.896 seconds,
the focused router suite passed 23 of 23 in 0.662 seconds, and the explicitly
selected Rust-to-Python integration passed 1 of 1 in 0.24 seconds. The retained
synthetic command passed two evaluated MLX router cases, reported model-free
scope, and reported both real-checkpoint evidence and external-checkpoint
access as false. Its temporary evidence was parsed, reviewed, and removed.

Fresh generation produced four table-side and two figure-side outputs. The
recursive byte diff and independently sorted SHA-256 diff were empty. The
temporary output was removed; `git diff --check` passed; and the worktree was
clean afterward.

Immediately before active MLX evaluation, NTFY topic `Mahdi-Dev` acknowledged
the high-priority hardware-pause message. After every synthetic MLX check
passed, the topic acknowledged the completion message permitting local
inference to resume. The attached Python crash report was also inspected: it
records an earlier `worker_contract` child deliberately invoking `os.abort()`,
loads no MLX or Metal library, and is not an out-of-memory report. Commit
`c7ef8a56beda29307a809720a87c22d990f68d83` had already replaced that test
signal with `SIGTERM`; the current workspace replay produced no crash report.

No checkpoint path was resolved, statted, hashed, opened, or executed. Apple
GPU/unified memory was used only for the bounded synthetic MLX tests during the
notified window. No model result or claims-ledger row was created.

### T060 fixture-publication CI checkpoint

The ten focused T050-T059 commits were staged-scanned individually, remained
recoverable throughout, and were pushed without force to `origin/main` at
`f5263b856894bd772d41161c67edece8e08bfab5`. Immediately after the push,
local `HEAD` and `origin/main` were equal and the worktree was clean. The
pre-push commands were:

```sh
git status --short --branch
git diff --check
scripts/research/check_staged.sh
git log --oneline origin/main..HEAD
git push origin main
```

All commands passed. The standardized staged safety scan reported `passed` and
the push advanced `main` from `9840988` to `f5263b8` without rewriting history.

GitHub Actions run
[`31060882272`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31060882272)
completed with conclusion `success` for exact head
`f5263b856894bd772d41161c67edece8e08bfab5`. Every job in
`.github/workflows/macos.yml` passed:

- Apple Silicon workspace baseline, job `92488402369`: success in 1 minute 12
  seconds, including workspace check and workspace tests.
- Apple MLX small-fixture validation, job `92488402405`: success in 45 seconds,
  including research methodology, pinned environment, worker contract,
  Rust-to-worker integration, native device smoke, bounded tensor fixtures,
  synthetic routed MoE, evidence verification, and external-model exclusion.

This closes the fixture-publication checkpoint only. CI accessed no external
checkpoint and establishes no model-backed correctness or performance claim.
Local inference may continue until a later explicitly notified hardware window.

### T061 red worker timing contract

Five pure-Python tests now freeze the worker-side timing seam before T064:
positive integer monotonic nanoseconds, one evaluation plus synchronization
barrier around a minimally instrumented total, F32 dequantization represented
as `not_applicable` without a duration, five retained warm-ups plus thirty
retained measurements, and ordered retention of passed, failed, and aborted
attempts. Scripted clocks and an evaluation-boundary spy keep this red test
slice independent of MLX and hardware.

The exact commands and results were:

```sh
PULSARMLX_MODEL_GGUF='' PYTHONPATH=python uv run python -m unittest \
  python.pulsar_mlx_worker.tests.test_router.RouterTimingContractTests -v
# expected red: 5 tests, 5 errors, exit 1
# missing: RouterTimingRecorder and RouterTimingSeries

PULSARMLX_MODEL_GGUF='' python3 -m py_compile \
  python/pulsar_mlx_worker/tests/test_router.py
# passed

git diff --check -- python/pulsar_mlx_worker/tests/test_router.py
# passed
```

Every error is the intended absent T064 API rather than a numerical or
environment failure. The tests name the raw observation schema, clock identity,
stage statuses, device/evaluation envelope, output hash, failure payload, and
retention order required of the implementation.

No MLX module was evaluated, no GPU or model path was accessed, and no NTFY
hardware notice was needed. Local inference remained available.

### T062 red Rust timing-evidence contract

A new bounded Rust integration test freezes the cross-process timing payload
before T065. Four tests require the exact 5+30 single-row and two-row major
benchmarks, one complete clean-process replication for each, distinct
process/condition/instrumentation labels, evaluated and synchronized GPU
envelopes without fallback, identical canonical output hashes, positive stage
durations, F32 dequantization marked `not_applicable`, and the existing 1 MiB
response cap. The same parser admits the separate frozen 5+10 costly and 0+10
first-process policies without allowing either to replace a major series.

The exact red command and final formatting checks were:

```sh
PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend \
  --test research_evidence
# expected red: exit 101 before execution
# missing: RouterTimingSeries and validate_major_router_timing_series

rustfmt --edition 2021 crates/mlx-backend/tests/research_evidence.rs
cargo fmt -p mlx-backend -- --check
git diff --check -- crates/mlx-backend/tests/research_evidence.rs
# passed
```

The compiler reported only the two intentionally absent T065 API symbols; no
test subprocess, worker, Python interpreter, MLX device, or checkpoint was
opened. The initially drafted file needed targeted rustfmt; no unrelated crate
or repository-wide formatting change was made.

### T063 red timing-policy contract

Six model-free research tests now freeze policy enforcement across the
statistics and evidence-validator seams. They require grouping to separate
experiment, process, process state, stage, requested/selected device, memory
pressure, power, thermal, and interference dimensions; prevent postponed or
interfered batches from claiming clean results; require unfiltered summaries
and a declared rule for filtered summaries; enforce the synthetic 5+30 sample
policy; represent unavailable or inapplicable phases with bounded reasons; and
require a reason when the later independent batch is unavailable.

The exact commands and results were:

```sh
PULSARMLX_MODEL_GGUF='' python3 -m py_compile \
  scripts/research/tests/test_timing_policy.py
# passed

PULSARMLX_MODEL_GGUF='' python3 -m unittest \
  scripts/research/tests/test_timing_policy.py -v
# expected red: 6 tests, 7 failures including two interference subtests,
# exit 1

git diff --check -- scripts/research/tests/test_timing_policy.py
# passed
```

The red result exposes six missing policy surfaces: complete compatibility
grouping, sample-count enforcement, clean-batch interference rejection,
second-batch schema/reason support, structured phase statuses, and semantic
filtered-summary admission. Existing validation failed closed where the new
schema is absent; it did not fabricate a passing timing result.

No model, checkpoint, Python MLX worker, GPU, or hardware observation was used.
Local inference remained available without an NTFY pause.

### T064 worker timing implementation

The Python router now owns an actual worker-returned timing envelope for the
bounded projection-through-normalization operation. It uses
`time.perf_counter_ns()`, starts immediately before graph construction for the
complete router operation, performs exactly one final `mx.eval(...)` followed
by `mx.synchronize(gpu)`, and stops only after synchronization. The serialized
worker result keeps this minimally instrumented total separate from later
host-owned process, condition, repetition, and correctness labels.

The timing primitives also implement structured observed, unavailable, and
F32 `not_applicable` stages; strict minimal-versus-stage-instrumented
separation; positive-u64 duration checks; bounded and sanitized failed-stage
evidence; immutable observation snapshots; contiguous compatible-series
indices; stable successful output hashes; non-relabelable process-replication
identity; and ordered retention of passed, failed, and aborted attempts. The
frozen v1 worker type rejects excluded observations because it carries no
predeclared exclusion rule.

The exact model-disabled validation commands and actual results were:

```sh
PULSARMLX_MODEL_GGUF='' PYTHONPATH=python python3 -m py_compile \
  python/pulsar_mlx_worker/router.py \
  python/pulsar_mlx_worker/tests/test_router.py
# passed

PULSARMLX_MODEL_GGUF='' PYTHONPATH=python python3 -m unittest -v \
  python.pulsar_mlx_worker.tests.test_router.RouterControlContractTests \
  python.pulsar_mlx_worker.tests.test_router.RouterAdmissionContractTests \
  python.pulsar_mlx_worker.tests.test_router.RouterTiePolicyTests \
  python.pulsar_mlx_worker.tests.test_router.RouterTimingContractTests
# passed: 27 of 27 tests in 0.254 seconds

PULSARMLX_MODEL_GGUF='' PYTHONPATH=python python3 -m unittest -v \
  python.pulsar_mlx_worker.tests.test_router.RouterExecutionContractTests
# environment-selection failure: system Python lacked mlx; 5 tests reported
# 6 import/runtime errors before MLX initialization, exit 1

PULSARMLX_MODEL_GGUF='' PYTHONPATH=python uv run python -m unittest -v \
  python.pulsar_mlx_worker.tests.test_router.RouterExecutionContractTests
# passed: 5 of 5 native Apple MLX tests in 0.467 seconds

git diff --check
# passed
```

Immediately before the native regression, NTFY topic `Mahdi-Dev` acknowledged
the requested high-priority pause notice. The first command used Homebrew's
system Python and stopped before MLX initialization because that interpreter
does not contain the pinned package. The repository's existing `uv` environment
then completed all five native tests, after which the topic acknowledged a
resume notice. The run used only generated model-free fixture tensors; no
checkpoint path was resolved, statted, hashed, opened, or executed.

This establishes fixture-tested worker timing mechanics only. It is not a
latency benchmark or performance claim, does not complete the major benchmark
matrix, and does not establish real-checkpoint router correctness. Rust timing
deserialization and sample validation remain T065; benchmark orchestration and
host-owned labels remain T066.

### T065 Rust timing-evidence implementation

Rust now deserializes and independently validates the worker-owned minimal
timing envelope and the host-owned timing-series evidence model. The closed
types preserve monotonic-clock identity, positive stage durations, the exact
F32 dequantization `not_applicable` reason, device/evaluation/synchronization
state, stable failures, output hashes, and process, condition, replication,
instrumentation, case, and benchmark identities. The frozen `run_router`
protocol remains the exact three-field control-only request and admits only its
minimally instrumented execution result; stage-instrumented observations remain
a separately labeled evidence-series mode and cannot be substituted for that
result.

Sample validation now distinguishes required successful samples from retained
failed or aborted attempts. It enforces the 5+30 inexpensive/major, 5+10 costly,
and 0+10 first-process policies, contiguous kind-local attempt indices, warm-up
before measurement ordering, bounded all-attempt retention, and consistent
passing output identity. Generated fixture series are explicitly distinct from
real-checkpoint series. A completed major matrix requires exactly the two
single-row/two-row primaries and their independent clean-worker replications,
permits both primaries to share one persistent worker, and rejects every
unsuccessful or incomplete major series.

The validator also rejects unknown, missing, null, contradictory, private, or
secret-like timing fields; observed evaluated stages without both evaluation
and synchronization; invented failure codes/stages; and timing-stage failures
without matching unavailable stage evidence. Validated timing series have a
bounded serialization path, and the framed response test reparses and validates
the complete four-series major payload under the existing 1 MiB protocol cap.

The exact model-disabled validation commands and actual results were:

```sh
PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend --test research_evidence
# passed: 5 of 5 tests

PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend --lib
# passed: 10 of 10 tests

PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend --test router_contract
# passed: 21 of 21 tests

PULSARMLX_MODEL_GGUF='' cargo check -p mlx-backend --all-targets
# passed with no warnings

PULSARMLX_MODEL_GGUF='' cargo clippy -p mlx-backend --all-targets -- -D warnings
# passed with no warnings

git diff --check
# passed
```

The first compile exposed one partial-move error in the new series parser; it
was corrected before any test passed. A strict Clippy pass then exposed two
derivable `Default` implementations and one test-only type-complexity warning;
all three introduced issues were corrected locally without broad formatting or
lint cleanup. Independent review additionally found and drove fixes for
all-attempt accounting, evaluated-stage barriers, generated-series admission,
clean-worker identity, stable failure vocabulary, strict-schema regression
coverage, and validated serialization.

No checkpoint path was resolved, no model bytes were accessed, and no Python,
MLX, or GPU process ran. This is contract/fixture evidence only, so local
inference remained available and no NTFY hardware pause was requested.

A final post-commit read-only audit found two additional bounded-evidence edge
cases. The major-matrix validator now enforces observation-ID uniqueness across
all four series, not merely within each series. Timing-series admission also
checks the 1 MiB encoded ceiling before deserialization, while the public domain
type exposes serialization only through the same bounded `try_to_value` path.
Regression coverage constructs a schema-valid 1,024-attempt oversized candidate
and a cross-series duplicate-ID candidate; both fail closed. The focused
evidence suite remained green at 5 of 5 tests, and targeted formatting, diff,
and strict package Clippy checks passed. No model or hardware was accessed.

### T066 correctness-gated router benchmark orchestration

The host now has a model-neutral, event-driven state machine for the frozen
real-router validation schedule. Each single-row and two-row correctness gate
retains exactly five labeled warm-up attempts followed by ten labeled measured
attempts. All fifteen attempts must independently pass the complete oracle,
GPU-selection, no-fallback, evaluation, synchronization, memory-evidence, and
finite-value checks. Determinism is checked across the ten measured attempts;
each retains all canonical output hashes and comparison metrics, while the
complete 128-way logits/probabilities and selected-route output are serialized
once per gate. Whole-output and required `0..16` and `64..80` comparison
summaries are mandatory.

Timing cannot start until both correctness gates pass. The first-process policy
was corrected from the earlier impossible single-series `0+10` representation
to ten distinct fresh-process series, each exactly `0+1`. Every batch therefore
requires ten orchestration-issued primary first-read identities and ten for
each clean-worker cohort before its associated timing work can advance. The
primary schedule then admits the two 5+10 costly external-read series, two
5+30 minimally instrumented major series, two 5+10 stage diagnostics, and one
5+30 clean-process major replication per real case. A later independent batch
uses a new batch identity and the reversed two-row/single-row order.

Every correctness attempt and every raw timing observation is also indexed in
one append-ordered per-batch ledger. Its contiguous global index plus explicit
batch, case, process, source, and schedule-step identities proves the enforced
inter-series order without relying on the separately grouped evidence arrays.
Rejected observations remain in the same ledger with their source status and
orchestration disposition. The model-free primary and reversed-batch fixtures
each retain 260 ordered observations.

Passing costly and first-process observations retain the exact six external
boundaries, including observed file I/O, F32 decode, evaluated total, and
end-to-end command duration. Stage diagnostics retain all thirteen frozen
observed, unavailable, or F32-not-applicable boundaries. Global observation
identities must be unique across every series. Wrong order, identity, output,
or schedule state fails closed; worker-originated failures preserve their
validated code, stage, message, and original observation rather than being
collapsed into a generic orchestration failure.

Failed later batches are cloned into the terminal primary experiment, while a
public-safe unavailable reason is an explicit alternative. Duplicate later
dispositions cannot overwrite accepted evidence. A retained candidate that
would cross the 1 MiB response ceiling causes an explicit cap error and remains
held by the state machine; it is never replaced with truncated evidence. The
protocol and command contracts now describe the same 5+10 correctness policy
and truthful ten-series `0+1` first-process method.

The exact model-disabled validation commands and actual results were:

```sh
PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend --bin pulsar-mlx -- --nocapture
# passed: 16 of 16 tests

PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend --lib -- --nocapture
# passed: 10 of 10 tests

PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend \
  --test router_contract -- --nocapture
# passed: 21 of 21 tests

PULSARMLX_MODEL_GGUF='' cargo test -p mlx-backend \
  --test research_evidence -- --nocapture
# passed: 5 of 5 tests

PULSARMLX_MODEL_GGUF='' cargo check -p mlx-backend --all-targets
# passed with no warnings

PULSARMLX_MODEL_GGUF='' cargo clippy -p mlx-backend --all-targets -- -D warnings
# passed with no warnings

rustfmt --edition 2021 --check \
  crates/mlx-backend/src/bin/pulsar-mlx.rs \
  crates/mlx-backend/src/router.rs \
  crates/mlx-backend/tests/research_evidence.rs
# passed

git diff --check
# passed
```

An independent review first found that type-grouped arrays could not prove the
cross-series global order required by the frozen protocol. The ordered ledger
and its accepted, rejected, reversed-batch, uniqueness, contiguity, and response
cap tests were added before the task was marked complete. A second independent
review found no remaining technical T066 release blocker. No Python
worker, checkpoint path, model bytes, MLX device, GPU, or hardware observation
was used, so no NTFY pause was needed. Process IDs and the state machine are
correlation/design evidence only: T083 must still prove actual worker spawn,
single first read, shutdown, temporal batch separation, and real-checkpoint
execution before any model-backed correctness or performance claim is legal.

### T067 public-safe environment and resource evidence

Recovery began from clean local `main` at `6b7aa07`, seven commits ahead of
`origin/main`. The seven commits were coherent, and their focused Rust timing
tests passed, but the full research gate exposed intentionally red T063 policy
tests plus a stale protocol hash in the fixture records. They were therefore
not pushed as a knowingly failing stack. No commit was reset, rebased,
discarded, or force-pushed.

The repaired model-free evidence boundary now includes:

- explicit observed/unavailable envelopes with bounded sources or attempted
  methods;
- public-safe Git, UTC, macOS/build, arm64, Apple-chip, unified-memory, CPU,
  Python/MLX/Rust/Cargo, filesystem, GiB-rounded free-storage, pressure,
  active-power, thermal, load, benchmark-concurrency, and collector-scoped
  process-resource observations;
- mandatory operator workload classification and conservative one-/five-minute
  load admission at no more than `0.75 × logical CPU count`;
- storage-directory roles and symbolic locators, with model-looking file
  operands rejected before probing and each probed directory bound to the
  declared allowlisted symbolic-root value;
- independent before/after snapshots, transition detection, and a separate
  handoff for worker-supplied process-footprint and MLX active/cache/peak
  gauges plus backend/device/fallback/evaluation facts extracted from and
  agreed by every validated worker result rather than asserted by the caller;
- snapshot combination that fully revalidates both source snapshots and
  recomputes their admission decisions instead of trusting stored labels,
  including complete-snapshot timestamp, power, thermal, workload, version,
  CPU, storage, and resource type checks;
- exclusive atomic JSON installation, including pre-install failure and
  post-link directory-sync rollback and concurrent-writer regression coverage;
- a canonical projection from schema-valid raw observations to all frozen
  timing compatibility dimensions, used at the validator boundary; and
- fail-closed external timing stages with the shared worker/Rust vocabulary,
  structured observed/unavailable/not-applicable values, an observed minimal
  total, every diagnostic boundary, and the canonical F32 dequantization
  reason; and
- recursive rejection of credentials, secret-shaped fields, usernames,
  host/serial/UUID/MAC/IP/email/account identifiers, private paths/mounts, and
  private path forms embedded in URIs or diagnostic text.

The additive evidence envelope is version `1.1.0` and now has an explicit
`synthetic_fixture` versus
`external_checkpoint` scope. Synthetic conformance fixtures may omit real host
snapshots; external evidence cannot use warning text, a zero tensor offset, or
a fixture artifact to bypass paired environment/resource and sealed model,
real-input, and independent-oracle provenance requirements. A missing scope is
accepted only as a legacy synthetic fixture. A postponed capture remains
durable but exits nonzero so a documented benchmark flow cannot continue. The
experiment protocol is frozen as pre-access amendment
`f002-router-protocol-amendment-001` version `1.1.0`, SHA-256
`c4bc12eb294a5849cc1a88ec7e9820af5cd4387722536565697a30fdf8fe3863`.
It supersedes the local unpushed 1.0.0 timing method before any external model,
CPU-oracle, Apple, or real timing output; the constructed fixture package was
regenerated from its machine-readable sources.

Exact model-disabled validation completed as follows:

```sh
git diff --check
# passed

python3 -m py_compile \
  scripts/research/environment.py \
  scripts/research/statistics.py \
  scripts/research/validate_evidence.py
# passed

PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover \
  -s scripts/research/tests -v
# passed: 118 of 118 tests

python3 scripts/research/validate_evidence.py \
  --schema-dir schemas/research/v1 \
  --input fixtures/research/router-v1/evidence
# passed: 3 records

python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity \
  --fixture-only
# passed: 3 records, 6 regenerated artifacts, 0 public claims

PULSARMLX_MODEL_GGUF='' cargo test -q -p mlx-backend --bin pulsar-mlx
# passed: 16 of 16 tests

PULSARMLX_MODEL_GGUF='' cargo test -q -p mlx-backend --lib
# passed: 10 of 10 tests

PULSARMLX_MODEL_GGUF='' cargo test -q -p mlx-backend --test router_contract
# passed: 21 of 21 tests

PULSARMLX_MODEL_GGUF='' cargo test -q -p mlx-backend --test research_evidence
# passed: 5 of 5 tests

PULSARMLX_MODEL_GGUF='' cargo check -q -p mlx-backend --all-targets
# passed

rustfmt --edition 2021 --check crates/mlx-backend/src/bin/pulsar-mlx.rs
# passed
```

The collector and tests did not resolve, stat, hash, open, or execute the
checkpoint. They did not import the MLX runtime, initialize a device, launch a
Python worker, or execute GPU work. No hardware pause or NTFY message was
needed for this T067 model-free implementation. The next hardware-using step
is T068; it requires the requested `Mahdi-Dev` pause notification before the
generated MLX microbenchmark runs.

The complete recovered stack plus T067 was published at commit
`246e3da87d56d2f346f7b5c3547694005e5c89fe`. GitHub Actions run
`31075801331` (`macOS baseline`) passed on 2026-08-06: the Apple Silicon
workspace-baseline job passed in 1 minute 29 seconds and the native Apple MLX
small-fixture job passed in 42 seconds. The latter included the fixture-only
research methodology gate, pinned worker environment, Rust-to-worker generated
router integration, native MLX device smoke, tensor fixtures, synthetic routed
MoE fixture, and external-model exclusion check. This hosted result remains
fixture-only and is not local T068 latency evidence.

### T068 fixed generated-router microbenchmark harness

Before any local hardware-active run, the existing model-free
`validate-router-fixtures` command was extended with a protocol-fixed
single-row synthetic series. It uses the already admitted manifest and golden
output, runs exactly five retained warm-ups followed by thirty retained
measurements in one persistent worker, and does not accept caller-selected
counts. Every result must retain worker-derived `apple-mlx`/GPU/no-fallback/
evaluated/synchronized provenance, pass the complete golden comparison, and
match one complete-output hash. Raw timing observations and per-result memory
gauges remain in the external candidate; a failed result retains the exact
failure and all earlier observations. The evidence explicitly records that no
stage-sum claim is made.

The pre-hardware NTFY request to topic `Mahdi-Dev` was acknowledged at
`2026-08-06T06:01:45Z`. Its message asked the operator to pause local inference
for the model-free 5+30 MLX/GPU run and promised a resume notice. This was not
the later T073 external-checkpoint notification, and no checkpoint path was
resolved, statted, hashed, or opened.

The harness-only validation commands and actual results were:

```sh
PULSARMLX_MODEL_GGUF='' cargo test -q -p mlx-backend --bin pulsar-mlx
# passed: 19 of 19 tests

PULSARMLX_MODEL_GGUF='' cargo check -q -p mlx-backend --all-targets
# passed

PULSARMLX_MODEL_GGUF='' cargo clippy -q -p mlx-backend \
  --all-targets -- -D warnings
# passed

rustfmt --edition 2021 --check crates/mlx-backend/src/bin/pulsar-mlx.rs
# passed

PYTHONDONTWRITEBYTECODE=1 PULSARMLX_MODEL_GGUF='' \
  python3 -B -m unittest discover -s scripts/research/tests -q
# passed: 118 of 118 tests

git diff --check
# passed
```

These checks constructed only fake or committed generated fixture values; they
did not launch the MLX worker or use the GPU. Final T068 samples remain pending
until this exact harness is committed, pushed, green in CI, and run from a clean
source tree with the public-safe before/after collector.

The harness was committed and pushed as
`98ccdb9b8e781062b77fc4198b58021c3541b34f`. GitHub Actions run
`31076700023` passed both jobs: the native Apple MLX fixture job in 53 seconds
and the workspace job in 1 minute 27 seconds. The first collector invocation
produced no snapshot because its symbolic candidate root was not exported. A
fresh second attempt retained a postponed snapshot with
`runtime_identity_admission_failed` and
`resource_observation_admission_failed`: it used the system Python, which did
not expose the pinned MLX package, and a sequential macOS RSS sample was 16 KiB
above the earlier `ru_maxrss` sample. No MLX worker or GPU benchmark ran in
either attempt, and neither result was deleted or represented as an execution.

The collector was narrowly corrected to retain the conservative maximum of
the available `ru_maxrss` and later current-RSS samples, with regression
coverage, and the quickstart was corrected to invoke it through the pinned
`uv` environment. The focused environment suite passed 24 of 24 tests and the
complete research suite passed 119 of 119 tests. The fix was scanned,
committed, and pushed as
`c8c189731901d779f08042e8d585a461e58c3b91`; GitHub Actions run
`31077076397` then passed the native Apple MLX fixture job in 46 seconds and
the workspace job in 1 minute 38 seconds.

A third fresh external attempt captured an admitted before snapshot at
`2026-08-06T06:24:37.934561Z` from clean commit `c8c1897`. It observed arm64,
Apple M1 Ultra, 128 GiB unified memory, 20 logical CPUs, MLX 0.32.0, Python
3.12.13, normal memory pressure, nominal thermal state, no declared concurrent
workload, and more than the protocol minimum of GiB-rounded free storage. The
active power mode was explicitly unavailable from the unprivileged `pmset`
probe and was not fabricated. The exact benchmark command was:

```sh
PULSARMLX_MODEL_GGUF='' cargo run --release -p mlx-backend \
  --bin pulsar-mlx -- validate-router-fixtures \
  --manifest fixtures/research/router-v1/manifest.json \
  --evidence "$PULSARMLX_ROUTER_FIXTURE_EVIDENCE"
```

It exited zero and reported two evaluated MLX router fixture cases plus the
fixed single-row 5+30 microbenchmark passed. The external 58,335-byte candidate
retains exactly 35 observations and 35 result records: five warm-ups followed
by thirty measurements. All 35 records are `apple-mlx`, requested and selected
GPU, evaluated, synchronized, no-fallback, correctness-passed, and
golden-comparison-passed. Every observation and result has the same complete
output SHA-256; there are no failed timing observations; F32 dequantization is
explicitly not applicable; and `stage_sum_claimed` is false. The after snapshot
at `2026-08-06T06:25:27.946178Z` was also admitted, with no interference
reasons. Worker resources retain observed process footprint and MLX active,
cache, and peak memory; bytes read and process CPU time are explicitly
unavailable because the bounded worker protocol cannot report them reliably.

The candidate, snapshots, and resource handoff remain together outside Git.
They are generated fixture evidence only: they do not support a real-model,
checkpoint, token-generation, full-layer, throughput, or performance claim.
T069 must still validate the closed candidate contract and independently
reproduce its statistics before any timing summary is accepted. No checkpoint
path was resolved, statted, hashed, opened, or read. The completion/resume NTFY
to `Mahdi-Dev` was acknowledged at `2026-08-06T06:26:41Z`; local inference may
resume until the separate T073 checkpoint notification.

### T069 generated-candidate validation and T070 timing documentation

T069 first attempted an independent complete-output hash from the committed
golden values. That hash did not equal the runtime hash because the MLX
softmax, selected probabilities, and normalized weights differed from the
scalar golden by small tolerance-passing float32 amounts. The original
candidate therefore could not support an independent comparison by hash alone:
it retained producer metrics and component hashes but not the actual bounded
values needed to recompute them. Validation stopped rather than trusting
`golden_comparison_passed`. The original 58,335-byte candidate is preserved
outside Git with SHA-256
`97be50f3e5a657c0446e3a39e8e219de924a8991e814f0df14367f994f90815e`;
its combined environment SHA-256 is
`7b6011f73fe451cf4f68d75f096c2b2d9cce62c773449f3fc678845f778aa9c1`.

The producer was tightened to retain one canonical actual output and bind all
35 attempts to it without duplicating the arrays per attempt. The dedicated
closed candidate schema and validator now verify the complete manifest
inventory, recompute actual component/selected-ID/complete hashes, recompute
the golden comparison and producer metrics from retained values, require the
exact 5+30 timing/result bijection, reject component or stage-sum fields, reuse
the public resource extractor, and route the raw total through the canonical
timing projection, compatibility grouping, and Type-7 statistics helper.
Unavailable power mode is retained as an explicit compatibility tuple instead
of fabricated as normal. This work was scanned, committed, and pushed as
`42ab53e6f36ae5f94f0cd0ba92ca48f75238e1fb`. GitHub Actions run
`31078633852` passed the native Apple MLX fixture job in 38 seconds and the
workspace job in 1 minute 50 seconds.

Independent review of the initially implemented second-batch linkage found
three fail-open cases before any real evidence existed: execution identity and
admitted load drift were omitted from compatibility, duplicate JSON keys could
shadow a private value, and `single,two,single,two` interleaving could pass the
order check. The repaired validator compares the complete execution object,
all three before/after load averages, device and environment facts; rejects
duplicate keys before privacy validation; and requires one exact contiguous
case block per paired step. The original reviewer reran all prior exploits:
six execution mutations, admitted `1.0/0.5` to `14.0/14.0` load drift,
duplicate-key private shadowing, and interleaved order all failed closed. The
focused suite passed 13 of 13 tests, the research suite passed 145 of 145, and
three committed fixture records validated. The scanned repair was committed
and pushed as `49183bd96b612a2090f472aba4dee089755bf730`; GitHub Actions run
`31079042611` passed the native Apple MLX fixture job in 48 seconds and the
workspace job in 1 minute 43 seconds. This enforces the already frozen v1.1
method before external evidence and does not amend its content or SHA-256.

Because the earlier NTFY pause had been released, a replacement model-free
hardware request was sent and acknowledged at `2026-08-06T06:58:40Z`. A fresh
external attempt then captured an admitted before snapshot at
`2026-08-06T06:58:56.591687Z` from clean/equal commit `49183bd`. Memory pressure
was normal, thermal state nominal, load within the precommitted bound, no
material concurrent workload was declared, and unprivileged power mode was
explicitly unavailable. The corrected release command again passed two MLX
router fixture cases plus the fixed single-row 5+30 benchmark. Resource
extraction, the admitted after snapshot at `2026-08-06T06:59:42.469331Z`,
environment combination, and the exact dedicated validation command all
exited zero:

```sh
PYTHONDONTWRITEBYTECODE=1 PULSARMLX_MODEL_GGUF='' \
  PYTHONPATH=python uv run python -B \
  scripts/research/validate_generated_candidate.py \
  --candidate "$PULSARMLX_ROUTER_FIXTURE_EVIDENCE" \
  --environment "$PULSARMLX_ENVIRONMENT_EVIDENCE/combined.json" \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/generated-validation.json"
# passed
```

The replacement candidate is 63,218 bytes with SHA-256
`c2ebaf76ce976f3d7dffd03c123dd7624d83b52ace51e6af889f39052eb86ee3`.
The validation report SHA-256 is
`3adaab6cb9244050f6ea566b94e7383c9f437bb3c633c620c516574f594df8d5`;
the combined environment SHA-256 is
`a2971f1d14603f3da8810574fd0b5490194afea4ff49a4f146df5bcae7b0d951`.
The independently recomputed runtime complete-output hash is
`ae502f0820f6bbc869eb75b27cd16e302fc150a5c6665bc6e37ff568a46f3d8e`;
the independently recomputed scalar-golden complete hash is intentionally
different, `c3fee3b5e638fc906a8ce141943f7b2f31e2b988f0cf49a900c8dfe680c61f3d`.
All 128 logits matched exactly. The 128 full probabilities, eight selected
probabilities, and eight normalized weights had zero mismatches under their
frozen `1e-6` absolute/relative tolerances; maximum absolute errors were
`2.2351741790771484e-8`, `2.2351741790771484e-8`, and
`2.9802322387695312e-8`, respectively. Expert-ID and ordering mismatch counts
were zero.

The raw replacement samples remain external. For audit only, the independently
reproduced warm-up group (`n=5`) had median 1,698,750 ns and coefficient of
variation 0.0653674; the measurement group (`n=30`) had median 1,691,624.5 ns,
mean 1,641,823.67 ns, sample standard deviation 156,754.69 ns, minimum
1,214,166 ns, maximum 1,844,667 ns, p5 1,263,633.45 ns, p25 1,593,083.25 ns,
p75 1,729,521.25 ns, p95 1,792,121.05 ns, and coefficient of variation
0.0954760. Worker maxima were 67,371,008 bytes process footprint, 1,068,160
bytes MLX active memory, 152,716 bytes MLX cache memory, and 1,184,392 bytes
MLX peak memory. Worker bytes read and CPU time remained explicitly
unavailable. These generated-fixture observations are not checkpoint latency,
model inference, throughput, or a publishable performance claim.

Additional T069 gates passed: 76 Python worker tests, 13 generated-candidate
tests, 145 total research tests, 19 Rust CLI tests, 10 Rust library tests, 21
router-contract tests, 5 research-evidence tests, strict package Clippy,
package check, scoped rustfmt, fixture publication verification, and
`git diff --check`. The replacement completion/resume NTFY was acknowledged at
`2026-08-06T06:59:56Z`; local inference may resume. No checkpoint path was
resolved, searched, statted, hashed, opened, or read. T071 remains the exact
workspace/package/staged gate before the pre-access T072 attestation.

T070 also reviewed the frozen experiment protocol against the implemented
timing behavior. Run-history prose was intentionally kept in this session log
and `RESULTS.md`, not added to the normative protocol: changing that file would
invalidate its precommitted SHA-256
`c4bc12eb294a5849cc1a88ec7e9820af5cd4387722536565697a30fdf8fe3863` and
would require a formal amendment plus fresh experiment identities. The
protocol therefore remains byte-identical while the observed fixture behavior,
limitations, and task state are updated in their appropriate records.

### T071 timing milestone and T072 non-recursive CI attestation

The corrected timing-methodology closure was scanned with
`scripts/research/check_staged.sh`, committed as
`b9625709a06443fbf2a46c9fcd584746a683bd79`, and pushed to `origin/main`.
Before that commit, `git diff --check`, `cargo check --workspace --all-targets`,
and `cargo test --workspace --no-fail-fast` passed; the workspace test gate ran
216 tests successfully with zero failures and two ignored native integration
tests. The known `crates/quant/src/iq.rs` `unused_mut` and 13 macOS-unused
`serve` items remained warnings only. Focused `mlx-backend` library, CLI,
router-contract, and research-evidence suites passed 10, 19, 21, and 5 tests;
package check and strict package Clippy passed. The model-free research suite
passed 145 tests, three fixture records validated, fixture-only package
verification regenerated six artifacts, and the replacement generated
candidate validator passed. The normative protocol remained at SHA-256
`c4bc12eb294a5849cc1a88ec7e9820af5cd4387722536565697a30fdf8fe3863`.

[GitHub Actions run 31079793330](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31079793330)
completed successfully for that exact commit. The Apple Silicon workspace
baseline passed in 2 minutes 5 seconds, and Apple MLX small-fixture validation
passed in 1 minute 3 seconds, including the research methodology, bounded
worker, Rust-to-worker generated router, native device smoke, tensor fixture,
synthetic routed-MoE, and external-model-exclusion gates.

This documentation/task-state commit is the deliberately non-recursive T072
CI attestation. Its own CI conclusion is verified out of tree before T073 and
is not appended recursively. No checkpoint path has been resolved, searched,
statted, hashed, opened, or read.

### T073-T076 notified immutable router admission

The Feature 002 pre-access notification was acknowledged by `ntfy.sh` at
`2026-08-06T07:15:45Z` with response event ID `iu3HmKnew9Ct`. The requested
hardware pause therefore remained active throughout the first checkpoint
inspection. No duplicate notification was sent after recovery.

Before checkpoint access, the read-only inspector and its independent closed
validator were implemented, reviewed for descriptor/path races, and hardened
to bind the retained checkpoint file descriptor to the validated pathname,
reject unreviewed layer-0 router aliases, and publish external candidates via
directory-anchored no-overwrite writes with file and directory durability.
Commit `2168803dfdb759ab7352862babb77895a27fd8b6` passed GitHub Actions run
`31083819717`; both the Apple Silicon workspace baseline and Apple MLX
small-fixture validation jobs succeeded. A follow-up correction retained an
unavailable unprivileged desktop power-mode observation instead of requiring a
fabricated value. Its 24 focused tests and 170-test research suite passed, and
commit `c0501eb3aca38c13d326e01f25cd9bd8a87604fe` passed both jobs in GitHub
Actions run `31084309243`.

A fresh external `model_storage` before snapshot at
`2026-08-06T08:19:44.024089Z` was admitted from clean/equal commit `c0501eb`.
It observed normal memory pressure, nominal thermal state, no material
concurrent workload, 20 logical CPUs, load within the frozen per-CPU bound,
128 GiB unified memory, and more than the frozen storage minimum. The active
power mode was explicitly unavailable from the unprivileged
`pmset_live_lowpowermode` probe. Its public-safe SHA-256 is
`497120c2d1eeff283caf7c6e9f29d566577caa9a5ec988fd9e26bcbd9e83a987`.

The exact commands then executed against local-only symbolic paths were:

```sh
cargo run --release -p mlx-backend --bin pulsar-mlx -- inspect-router \
  --model "$PULSARMLX_MODEL_GGUF" \
  --evidence "$PULSARMLX_ROUTER_INSPECTION"

PYTHONDONTWRITEBYTECODE=1 python3 -B \
  scripts/research/validate_router_inspection.py \
  --input "$PULSARMLX_ROUTER_INSPECTION" \
  --environment "$PULSARMLX_ENVIRONMENT_EVIDENCE/before.json" \
  --output "$PULSARMLX_ENVIRONMENT_EVIDENCE/router-inspection-validation.json"
```

Both exited zero. The full checkpoint was admitted as the exact
`Qwen/Qwen3-30B-A3B-GGUF` revision
`e4d4bafdfb96a411a163846265362aceb0b9c63a`, Apache-2.0,
32,483,931,648 bytes, SHA-256
`4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c`.
The GGUF v3 inventory contained 579 tensors with 241 F32 and 338 Q8_0 entries.
Exactly one `blk.0.ffn_gate_inp.weight` was observed as F32 with GGUF dimensions
`[2048,128]`, reader/execution shape `[128,2048]`, absolute byte range
`1115085312..1116133888`, and complete range SHA-256
`98d82da676c9c2df99badbc8b05912471417ad60cc63ce719a25b54dca1d531c`.
All 262,144 decoded F32 values were finite. Typed metadata admitted 128 experts
and top-8 routing; absent scale metadata retained the architecture value 1.0,
and absent normalization metadata retained selected-probability
renormalization. Router bias, known correction bias, and unexpected layer-0
router-alias occurrence counts were all zero.

The external inspection candidate SHA-256 is
`0078285d853bbd73fb7f2123cb71a8a8c1c8112ab6f09c802aef2110e140c580`.
The independent validator bound it to the exact current clean commit and fresh
environment, rejected private fields and execution claims, and wrote a passing
external validation report. Neither external file is committed. Inspection
performed no MLX initialization, worker spawn, router projection, softmax,
top-k, router output, expert execution, network access, or automatic download.
This milestone is immutable checkpoint/tensor admission only and does not
promote a router-execution or model-inference claim.

The sealed admission and T073-T076 task state were committed as
`fe69e4a0949d0bbb0336d9e90b7a5f67065cda7c`. GitHub Actions run
`31084884347` passed both jobs for that exact commit: Apple MLX small-fixture
validation completed successfully in 42 seconds, and the Apple Silicon
workspace baseline completed successfully in 1 minute 15 seconds. This
documentation-only record is the deliberately non-recursive T077 CI
attestation. Its own CI conclusion is verified out of tree before the two
independently started CPU-only captures and is not appended recursively.

### T077 oracle dependency recovery and CI attestation

The first T077 CPU-oracle attempt completed both bounded `ffn_norm-0` capture
processes and their provenance record, but stopped before final bundle
publication when pinned `gguf-py` could not import its declared PyYAML runtime
dependency. The command exited 2 with the bounded reason
`gguf_reader_unavailable`; the requested final output directory remained
absent, and the failed attempt was retained outside Git. No Apple MLX router
output was produced or inspected.

The recovery adds a fail-before-model-I/O prerequisite gate for external
CPython 3.12.13, NumPy 2.4.5, PyYAML 6.0.3, tqdm 4.67.1, requests 2.32.5, and
the pinned `gguf-py` reader. Probe output is suppressed so a transitive import
failure cannot expose a private external path; only the bounded public shell
error is retained. A subprocess test injects a private-looking traceback and a
model-hash sentinel, then proves that neither is emitted or reached.

The recovery passed shell parsing, 13 focused oracle tests, 171 complete
research tests, three fixture evidence records, fixture-only package
regeneration of six artifacts, `git diff --check`, and the standardized staged
safety scan. It was committed as
`7a4378d6e19e3e42b4772a537ab692da052e9c96` and pushed without force.
[GitHub Actions run 31086701447](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31086701447)
passed for that exact commit: Apple MLX small-fixture validation completed in
56 seconds and the Apple Silicon workspace baseline completed in 1 minute 50
seconds. The external oracle environment was then reconciled to the exact
documented package versions and its bounded import preflight passed.

This scanned documentation-only commit is the final non-recursive CI
attestation before retrying T077. Its own CI result is verified out of tree and
will not be recursively appended. The pre-access NTFY hardware pause remains
active; no duplicate notification is required.

### T077-T081 independent CPU oracle freeze

The non-recursive prerequisite attestation was committed as
`f604eed4de976c7e08bd24fed50b9d8c69449556` and pushed without force.
[GitHub Actions run 31086950283](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31086950283)
passed for that exact commit: Apple MLX small-fixture validation completed in
57 seconds and the Apple Silicon workspace baseline completed in 1 minute 55
seconds. The branch was then clean, equal to `origin/main`, and descended from
every required methodology and admission commit before the T077 retry.

Two independently started CPU-only captures used the pinned clean llama.cpp
revision `b06aa774c03dbbb624e726664b714a57d1f49815`, direct token IDs `[0,1]`,
positions `[0,1]`, context/batch/ubatch of two, one thread, and no tokenizer.
Both captured the complete finite `[2,2048]` F32 output of `ffn_norm-0` with
canonical input SHA-256
`978205a61fb31d03a8627fd5b9c9319e4c32ef7af0d3d934ccaddda9defc68a7`.
Each capture proved one CPU scheduler split, synchronized target completion,
an armed abort guard, zero true abort callbacks, no callback node after the
target, and cancellation before router or expert execution. Their scheduler
input counts were both zero. The full capture bytes were identical, while the
two retained hidden rows were distinct.

The standalone scalar F32 oracle imported neither MLX nor PulsarMLX worker
code. It read the exact admitted F32 router range and produced all 256 logits,
all 256 full-softmax probabilities, pre-normalization selected probabilities,
and architecture-correct normalized top-8 weights. Row 0 selected
`[114,45,99,46,98,74,102,65]`; row 1 selected
`[73,95,114,99,102,46,108,106]`. Neither row had a rank-8/rank-9 cutoff tie.
The independent NumPy cross-check had zero mismatches; maximum absolute error
was `1.430511474609375e-6` and maximum relative error was
`2.903159876627318e-7`, below the precommitted `5e-4` combined tolerance.

The complete ten-file external bundle was verified read-only. Its candidate
SHA-256 is
`b27ab74a539b06bfdd48f9be5c4353d7987a972448cac74fb959c48f783d8b6a`,
bundle-manifest SHA-256 is
`14cfa011aa621ab64d016469521d4e2bad8c18fd88708728ad2728de54bdd7f6`,
oracle-document SHA-256 is
`e31e4337ddf2c7cf1bb6cfe721428e6baaeffec7e29aee0f77727969e756e645`,
and complete output-bundle SHA-256 is
`eba36f9149b61f0d408de3ec5ad6ba73d1ff45b98867a4da56cfc586109ee93f`.
The admitted tensor remained
`blk.0.ffn_gate_inp.weight`, F32 `[128,2048]`, byte range
`1115085312..1116133888`, SHA-256
`98d82da676c9c2df99badbc8b05912471417ad60cc63ce719a25b54dca1d531c`.
No tensor parsing, hidden-state discovery, or model loading is described as
router execution.

The complete bundle verifier and its reviewer fixes were committed as
`37e3668ba9f845bf954305da07712ad5e1169481`.
[GitHub Actions run 31090774079](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31090774079)
passed: Apple MLX small-fixture validation completed in 47 seconds and the
workspace baseline completed in 1 minute 38 seconds. A separate bounded
publisher was then implemented and independently reviewed. It pins the exact
candidate, input, output, NumPy, and canonical capture-provenance identities;
reconstructs every numerical output; rejects private paths, runtime identity,
model/tensor bytes, FIFOs, short reads, symlinks, unknown files, noncanonical
bytes, and coherent alternate outputs; and uses rollback plus a manifest-last
logical transaction. Its 18 focused tests and the complete 195-test research
suite passed. Commit `c67aaca604da48526aac18fbefcc8a7afdab7f52` was pushed,
and [GitHub Actions run 31093545740](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31093545740)
passed both jobs: the native small-fixture job completed in 59 seconds and the
workspace baseline in 1 minute 33 seconds.

From that clean/equal commit, the formal external verifier passed again and
the publisher installed byte-identical 148,909-byte records under
`fixtures/research/router-v1/real/` and
`docs/research/raw/002-router-parity/oracle/`, followed by the fixture manifest.
The record SHA-256 is
`3f570ce97f45902a1717d3770c6665d1023d8ccfc18266e25229bc1e86725133`;
the manifest SHA-256 is
`ba2165b985195ca34df1813189228c0763bef414f0e1040833c069b999e66816`.
The public package contains complete derived hidden states and oracle outputs,
but no checkpoint bytes, router weights, capture binaries, private paths, or
device/inode identities. It is a frozen CPU reference, not Apple execution,
MLX parity, performance, expert execution, a complete layer, or inference.
No Apple router output has been produced or inspected. The original
acknowledged NTFY hardware pause remains active for T082-T085; no duplicate
start notification is required.

### T082 non-recursive oracle-publication CI attestation

The scanned T077-T081 oracle-publication and task-state commit is
`db00c9ea0eb3cb93d32f223e515b1d313da69d8b`.
[GitHub Actions run 31093792748](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31093792748)
passed for that exact commit. Apple MLX small-fixture validation completed in
56 seconds, including the exact three-file CPU-oracle support inventory,
methodology validation, worker protocol, generated router integration, native
device smoke, tensor fixtures, synthetic routed-MoE, and external-model
exclusion. The Apple Silicon workspace baseline completed in 2 minutes 21
seconds, with workspace check and tests passing.

This documentation/task-state commit is the deliberately non-recursive T082
CI attestation. Its own CI conclusion is verified out of tree before the Apple
checkpoint command and is not appended recursively. The next gate requires
clean/equal `main`, unchanged checkpoint and router identities, the intended
MLX GPU with no fallback, normal resource/load/pressure/thermal admission, and
the still-active acknowledged operator pause. No Apple checkpoint router
output has yet been produced or inspected.

### Pre-T083 evidence-contract CI correction

The case-scoped determinism, real-oracle identity, promotion-identity, and
fresh-process `0+1` cohort corrections passed 202 local research tests, three
fixture records, fixture-only package regeneration of six artifacts,
`git diff --check`, and the standardized staged safety scan. They were
committed as `2d3dcb67613534531147671e4a6c144304efc77d` and pushed without
force.

[GitHub Actions run 31096623612](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31096623612)
then exposed one CI-only history dependency. The Apple Silicon workspace job
passed. The Apple MLX small-fixture job ran all 202 research tests and had one
failure: its fixture-only package subprocess could not validate the immutable
CPU-oracle verifier source because `actions/checkout` had provided only the
new head commit after that verifier changed. The oracle record correctly pins
the historical verifier SHA, but the shallow checkout could not execute the
required `git show <measured-commit>:<source>` fallback. The failure was not a
router, MLX, schema, privacy, model-access, or numerical result.

The bounded correction sets `fetch-depth: 0` only for the fixture-validation
job so immutable historical source hashes remain verifiable after later
tooling changes. No checkpoint access or Apple real-router execution occurred
during this correction; T083 remains incomplete and the acknowledged hardware
pause remains active.

[GitHub Actions run 31096864243](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31096864243)
then passed both jobs for exact head
`24ec7d9bc8b6bd9a94cd0c5fc2633d4a8f32d6d5`: Apple MLX small-fixture
validation succeeded with full immutable history available, and the Apple
Silicon workspace baseline succeeded. This confirms the history-retention CI
correction; it is not Apple real-router execution or model-performance
evidence.

### T083 pre-execution contract amendment and sanitizer gate

Before opening the checkpoint, an independent producer/schema/validator audit
found that the earlier evidence envelope could not truthfully retain several
failure paths and did not enforce the exact live schedule. No checkpoint file
was opened and no Apple real-router execution occurred during this work.

The frozen pre-execution amendment now binds the exact 260-observation schedule
per batch, full oracle outputs, canonical output hashes and numerical metrics,
request/resource/lifecycle joins, per-process read/cache behavior, Rust worker
memory semantics, planned-versus-attempted timing prefixes, terminal and
environment-admission failures, and the complete linked 260-by-2 reversed-batch
relationship. It distinguishes spawn failure, post-spawn/pre-request timestamp
failure, sent-but-unevaluated worker failure, evaluated invalid output,
evaluated correctness failure, later-batch failure, post-run interference, and
unavailable after-snapshot evidence. The protocol SHA-256 is
`c75d8d4d372bf54dffbd1687986f09d65b0eace68c89555630ddfcbfd662d423`.

The Rust command now retains a closed symbolic parent invocation, direct
process-state and condition attestations, and a complete internal candidate
bounded to 4 MiB including its final newline and 100,000 JSON value nodes. The
model-free sanitizer securely reads and rechecks exact candidate/environment
bytes, rejects links and credential-shaped/private data, recomputes oracle
comparisons and summaries, validates redundant producer joins, and atomically
installs target-first linked public records through an anchored directory
transaction. It does not import MLX or open model/oracle paths.

Actual model-free validation at this boundary:

- research discovery: 243 passed;
- Python worker discovery with `PYTHONPATH=python`: 89 passed;
- `cargo test -p mlx-backend --tests --no-fail-fast`: 127 passed, 2 ignored
  native opt-ins, 0 failed;
- `cargo check -p mlx-backend --all-targets`: passed;
- explicit native MLX device smoke and generated two-row Rust-to-worker router
  integration: 1 passed each;
- evaluated MLX tensor fixtures: 7 passed; evaluated synthetic routed-MoE:
  passed with no external checkpoint path in the environment;
- committed fixture evidence: 3 records passed and 6 generated artifacts were
  reproduced by the fixture-only package verifier;
- `git diff --check` and Python compilation: passed.

An earlier local worker-discovery invocation omitted `PYTHONPATH=python` and
reported seven import errors before running tests. The corrected documented
command above ran all 89 tests successfully; the import-only invocation is not
reported as a product test result. T083 remains incomplete until this amended
method is committed, pushed, green in CI, and the exact authorized real-router
command executes from that clean source commit.

### Pre-T083 clean-CI regression and bounded correction

The amended harness and sanitizer were committed in three focused commits,
ending at `a66960f5a960ad9bacab8945a356a47ee1d258f2`, and pushed with local and
remote `main` equal. [GitHub Actions run 31108422771](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31108422771)
then passed the Apple MLX small-fixture job in 2 minutes 25 seconds but failed
the Apple Silicon workspace job. Its `cargo test --workspace --no-fail-fast`
step had one failure among the 33 `pulsar-mlx` unit tests: the nonexistent-model
guard fixture supplied a nonexistent evidence directory. A dirty local source
tree had exercised the earlier cleanliness return, while clean CI correctly
reached the evidence-directory availability gate. This was a test-fixture
defect; no external checkpoint was opened and no Apple router output was
produced.

The bounded correction gives the test three distinct fresh external parent
directories, an existing empty evidence directory, and absent model/oracle
files, then directly exercises the post-clean-source gate. It now requires the
exact unavailable-oracle result, proves the checkpoint remains absent and no
candidate is written, and removes its temporary directories. The focused test
and all 33 `pulsar-mlx` unit tests passed locally. T083 remains gated on a new
clean/equal pushed commit and green CI.

The correction was committed as
`94425abaa01b09cfd29d1d17494712ad9efc479a` and pushed without force.
[GitHub Actions run 31109040268](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31109040268)
passed for that exact commit: Apple MLX small-fixture validation completed in
2 minutes 34 seconds and the Apple Silicon workspace baseline completed in
1 minute 24 seconds. Every step was green, including the research methodology,
worker integration, native MLX device smoke, tensor and synthetic routed-MoE
fixtures, evidence gates, workspace check, and workspace tests. This paragraph
is the non-recursive documentation-only CI attestation; its own CI conclusion
is verified out of tree before checkpoint access rather than appended again.

### First T083 execution and fail-closed post-processing correction

The documentation-only attestation commit was
`54ab326f92bd39818a8756d59498cde5b5891d27`.
[GitHub Actions run 31109331743](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31109331743)
passed for that exact commit: Apple MLX small-fixture validation completed in
1 minute 46 seconds and the Apple Silicon workspace baseline completed in
1 minute 36 seconds. Local and remote `main` were equal and clean before the
checkpoint was reopened.

The admitted Qwen file rehashed to
`4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c`,
the router byte range rehashed to
`98d82da676c9c2df99badbc8b05912471417ad60cc63ce719a25b54dca1d531c`,
and the independent external CPU oracle rehashed to
`e31e4337ddf2c7cf1bb6cfe721428e6baaeffec7e29aee0f77727969e756e645`.
There was one GGUF in the admitted directory. The public before snapshot
reported normal memory pressure, nominal thermal state, 96% system-wide free
memory, 370 GiB rounded free candidate-evidence storage, low unrelated
workload, and
an explicit local native MLX GPU smoke pass. Its source identity was the exact
clean commit above. The first capture invocation omitted the required process
binding for `$PULSARMLX_ROUTER_EVIDENCE`; it failed closed and wrote no output.
The corrected documented invocation retained an admitted snapshot.

The exact release `validate-router` command then returned zero and reported
that real MLX router correctness and the frozen timing schedule passed. Its
complete external internal-orchestration candidate is 2,903,766 bytes. The
candidate and before/after snapshots remain external and unmodified. No raw
Apple result was staged or published, and no numerical or performance claim is
promoted from this attempt.

The required resource-extraction step then rejected that retained candidate.
The collector had one shared 1 MiB/20,000-node input limit even though the
already frozen internal-candidate contract permits 4 MiB, 100,000 nodes, and
depth 64; its generic credential-field scan also rejected the protocol's
public `join_key`. This was a fail-closed post-processing defect, not an MLX or
numerical failure. The candidate was preserved, but it cannot be the published
T083 evidence because fixing the source changes the clean source commit bound
by the candidate and sanitizer.

The bounded model-free correction gives only the exact internal Apple-MLX
router identity the frozen expanded intake, keeps all combine operands at the
smaller limit, allows only the required public `join_key`, and rejects secret
values, other credential fields, duplicate keys, non-finite values, excess
depth, links, parent aliases, hard links, oversized input, and in-place
mutation. All 32 focused environment tests passed, including exact
newline-inclusive boundaries, and the retained real candidate passed a
non-public extraction probe. A fresh real attempt remains required after this
correction is committed, pushed, and green in CI; T083 therefore remains
incomplete.

Final model-free validation of the correction passed 32 focused environment
tests and the complete 254-test research suite. The exact retained candidate
passed a fresh extraction probe under the corrected intake. Committed fixture
validation still accepted exactly three records, fixture-only package
verification reproduced six artifacts with zero promoted claims, the protocol
SHA-256 remained
`c75d8d4d372bf54dffbd1687986f09d65b0eace68c89555630ddfcbfd662d423`,
and `git diff --check` passed.

### Second T083 execution and clean-replication role correction

The bounded collector correction was committed as
`70f782ab47b531ccb8a69f12156b83b1237584de` and pushed without force.
[GitHub Actions run 31111574542](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31111574542)
passed for that exact commit: Apple MLX small-fixture validation completed in
1 minute 41 seconds and the Apple Silicon workspace baseline completed in
1 minute 56 seconds. Local and remote `main` were equal and clean before the
next checkpoint run.

A fresh second T083 attempt at that exact source commit passed the exact
release `validate-router` command and its internal correctness-before-timing
gate. The retained external internal-orchestration candidate is 2,903,814
bytes with SHA-256
`8f2e0147c671f14580862cb293baf0808e2145f6c1b17e6e9555acc1eb3d57d3`.
The public-safe before and after snapshots were admitted; resource extraction
and environment combination passed; the intended MLX GPU was selected; and
the checkpoint, router range, and frozen independent CPU-oracle identities
remained unchanged. The candidate and environment records remain external.

The independent sanitizer then failed closed with a
`semantic_relationship` error: the passing router timing schedule matrix
differed from the frozen contract. It produced no installed public record,
staged no evidence, and promoted no correctness or performance claim. Review
of the untouched candidate found that each batch retained the correct 30
first-process `0+1` series but labeled all 30 as `primary`; the frozen matrix
requires ten primary first-process series followed by twenty
`clean_process_replication` first-process series associated with the two clean
major replications. The failed attempt is preserved externally and will not be
reused after the source correction.

The model-free correction carries the clean-replication role from the frozen
schedule into the live timing plan and retained series, admits that role only
for the same fresh-process/OS-cache-uncontrolled `0+1` contract, and validates
the expected role at both primary and clean schedule positions, including the
reversed later batch. Focused validation passed:

- `cargo test -p mlx-backend --test research_evidence`: 5 passed;
- `cargo test -p mlx-backend --bin pulsar-mlx`: 34 passed;
- `cargo check -p mlx-backend --all-targets`: passed;
- `cargo test -p mlx-backend --tests --no-fail-fast`: 128 passed, 2 ignored
  native opt-ins, 0 failed;
- `cargo check --workspace --all-targets`: passed with the previously recorded
  `quant` `unused_mut` warning and macOS-gated `serve` dead-code warnings;
- `cargo test --workspace --no-fail-fast`: 245 passed, 2 ignored native
  opt-ins, 0 failed, with the same inherited warnings;
- research discovery: 254 passed;
- committed fixture evidence: 3 records passed and fixture-only package
  regeneration reproduced 6 artifacts with 0 claims;
- `git diff --check`: passed.

The new assertions require ten primary plus twenty clean-replication
first-process series per batch, reject swapped roles in both schedule
positions, and reject a relabeled later-batch clean cohort. No checkpoint was
accessed while implementing or testing this correction. The frozen protocol,
tolerances, model identity, tensor identity, input, and independent oracle are
unchanged. T083 remains incomplete until a new clean-source attempt passes the
producer, sanitizer, evidence validator, and candidate package verifier.

The correction was committed as
`9f86f7f44b76b579ec95805fd3fb3ac26c220856` and pushed without force.
[GitHub Actions run 31114184383](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31114184383)
passed for that exact commit: Apple MLX small-fixture validation completed in
1 minute 58 seconds and the Apple Silicon workspace baseline completed in
1 minute 33 seconds. Every required fixture-only, native MLX, evidence, and
workspace step passed. This documentation-only update is the non-recursive
pre-T083 CI attestation; its own CI result is verified out of tree before the
next checkpoint run rather than appended recursively.

### T083 resource-admission stop condition

The non-recursive attestation's own
[GitHub Actions run 31114392419](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31114392419)
passed at exact commit `ed245542a827974f4c6822e68114f34aca70ee67`:
the Apple Silicon workspace baseline completed in 1 minute 35 seconds and the
Apple MLX small-fixture validation completed in 2 minutes 10 seconds. Local
and remote `main` were clean and equal. A third fresh external attempt
directory was created with absent candidate and environment destinations; both
earlier failed external attempts remained preserved.

The required quiet-window admission then failed before this attempt reopened
the checkpoint. The machine has 20 logical CPUs, so the frozen
`0.75 × logical CPU count` ceiling is `15.0` for both one- and five-minute load
averages. Initial observations were approximately 45 for both averages with
only 14% idle CPU. A separate read-only 4 minute 37 second monitor collected
ten samples: one-minute load remained 34.41–41.06, five-minute load remained
39.59–44.63, and CPU idle remained 11.20–26.68%. A further predefined
10-minute, twenty-sample monitor never admitted the host; one-minute load
remained 31.11–49.90, five-minute load remained 35.88–42.58, and CPU idle
fell as low as 9.79%. The rebound after an initial decline was consistent with
an ongoing material concurrent workload rather than a decaying build/test
tail, so the window was treated as non-admissible.

The collector was then invoked truthfully with
`--workload-category other_material`. It returned nonzero with
`environment admission postponed: inspect the retained snapshot` and wrote a
4,052-byte public-safe external before snapshot with SHA-256
`bf2443a1f49c8b52d187ba3c66b92ec11161079de4b23a4ba3608066a996f027`.
That snapshot observed one-minute load `48.16357421875`, five-minute load
`43.2705078125`, normal memory pressure, nominal thermal state, and the exact
reasons `load_average_1m_admission_failed`,
`load_average_5m_admission_failed`, and
`material_concurrent_workload_declared`. No internal-orchestration candidate,
after snapshot, combined environment, sanitizer output, or public raw record
was created for this attempt. No checkpoint file was resolved, statted,
hashed, or opened during this third attempt.

Minimal reproduction from a clean checkout, using a fresh external directory:

```sh
export PULSARMLX_ROUTER_EVIDENCE='<fresh-external-attempt>'
mkdir -p "$PULSARMLX_ROUTER_EVIDENCE/environment"
sysctl -n vm.loadavg
top -l 1 -n 0 | awk '/CPU usage/ {print}'
PULSARMLX_ROUTER_EVIDENCE="$PULSARMLX_ROUTER_EVIDENCE" \
  PYTHONPATH=python uv run python scripts/research/environment.py capture \
  --repository-root . \
  --storage-root "$PULSARMLX_ROUTER_EVIDENCE" \
  --storage-role candidate_evidence_storage \
  --storage-locator '$PULSARMLX_ROUTER_EVIDENCE' \
  --capture-phase before \
  --workload-category other_material \
  --benchmark-concurrency 1 \
  --output "$PULSARMLX_ROUTER_EVIDENCE/environment/before.json"
```

This is the protocol-defined resource-admission stop condition, not a router,
MLX, model, oracle, numerical, determinism, or sanitizer failure. T083 remains
open. The deepest committed verified Feature 002 boundary remains the genuine
real `ffn_norm-0` input and independent scalar/NumPy CPU router oracle. Two
earlier external `validate-router` commands reached complete real MLX router
execution and returned zero, but neither candidate completed the independent
sanitization/publication gate, so neither supports a verified public
correctness or performance claim.

Exact continuation point: after the material workload ends, begin a new
notified hardware window, require both load averages at or below `15.0`, use a
new external attempt rather than overwriting this postponed snapshot, recheck
the immutable model/router/oracle identities, and resume at T083 with the exact
Section 7 command in `specs/002-qwen-router-parity/quickstart.md`. Do not resume
from T084 and do not reuse either prior internal candidate.

### T097 exact-blocker notification

The blocker documentation was committed and pushed as
`16e9502b722ae5a0225f856fd13fe25e58d9550f`. Local `main`, `origin/main`, and
the GitHub `main` head all resolved to that exact commit with a clean worktree
and zero divergence before notification.

The required exact-blocker NTFY was acknowledged by `Mahdi-Dev` at
`2026-08-06T15:42:04Z` with event ID `XpxArb45zCUp`. It stated precisely that
model access did begin in two earlier authorized Feature 002 attempts, while
the fresh T083 attempt stopped before reopening the checkpoint because the
quiet-window gate failed. It also stated that T083 through T096 remain
incomplete, no Apple parity claim was admitted, and local inference may
resume. No checkpoint or model file was accessed while sending or recording
the notification. T097 is complete; T083 remains the first incomplete task.


### T083-T088 fresh candidate admission (2026-08-06)

Resumed after the earlier resource-admission blocker with a new Mahdi-Dev
hardware-window notification (`VD4TY5Xp9sGh`). Host admission passed with
one-minute load about 7.4 and five-minute load about 7.4, normal memory
pressure, and nominal thermal state. The immutable checkpoint SHA-256
`4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c` and the
frozen independent CPU oracle identities were rechecked before execution.

The exact release `validate-router` command on a fresh external evidence
directory returned the success message
`real MLX router correctness and frozen timing schedule passed` and retained
internal-orchestration candidate SHA-256
`b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4`
(2,904,454 bytes). Correctness summary: zero ID/order/numeric mismatches,
max abs error `1.239776611328125e-05`, MAE `2.8392920891443887e-06`, RMSE
`3.584568198272296e-06`, twenty deterministic measured hashes, evaluated
synchronized `apple-mlx`/`gpu`, no fallback.

Independent sanitization wrote two public records. Package verification
initially rejected schema-required public `host_*` timing field names as
private identifiers; a bounded privacy allowlist fix was committed as
`778028c` with regression coverage. After that fix, sanitizer, evidence
validation, and package verification accepted the candidate.

Append-only raw publication:

- `docs/research/raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-a.json`
  SHA-256 `b5925db8ba68d90a42507e00be6d3159457a2b97d9fc827f0200245cb20851fa`
- `docs/research/raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-b.json`
  SHA-256 `99346e8be81b4975cb355759be20872aefdea05baa9960f28aa272d970116801`

Generated tables/figures, provisional claims F002-C01 through F002-C03,
reviewer index, results, and limitations were updated and package verification
passed with `claim_count: 3`. T089 clean-checkout reproduction was started but
postponed when load rose above the frozen 15.0 ceiling; it remains the next
incomplete task. Prior rejected producer candidates were not reused.



### T089-T096 completion (2026-08-06)

After a quiet-window wait, a clean checkout at measured source
`04b3502aa5cfbe48cda66d1a5b0b07a45902f762` re-ran the exact release
`validate-router` command. The reproduction retained candidate SHA-256
`3dc290b5a02daf673eb00e7c47e9428cf3aa1b935401db2327c0e59c03a3e3f3` and
passed independent sanitization. Promotion identity and both case output
hashes exactly matched the primary candidate. Append-only raw records:

- `f002-router-real-3dc290b5a02daf673eb00e7c47e9428cf3aa1b935401db2327c0e59c03a3e3f3-batch-a.json`
  SHA-256 `0cc828bb77f2dca62d039c700a575ec123cef1367e1d942956f1a6fe8481c616`
- `f002-router-real-3dc290b5a02daf673eb00e7c47e9428cf3aa1b935401db2327c0e59c03a3e3f3-batch-b.json`
  SHA-256 `ce8e6d71d2a8a209d5119b3a6c886f3f1e65e2d75d4b8502a363dd44edc67a44`

Tables and figures were regenerated from all four real raw records. The SVG
generator bound was raised from 128 KiB to 256 KiB so dual-batch primary plus
reproduction packages remain a single static figure. Claims F002-C01 through
F002-C03 were promoted to package-level `verified`. Full package verification
passed with four records and three claims. Feature 002 is complete for the
bounded layer-0 router scope only.


### T092 capability documentation and final CI (2026-08-06)

T092 capability-claim surfaces were updated to match published Feature 002
evidence without expanding scope past the layer-0 router:

- `README.md` capability table now includes verified real layer-0 router parity
  and keeps experts/generation/serving unsupported.
- `docs/apple-silicon/COMPATIBILITY.md` adds a real `blk.0.ffn_gate_inp.weight`
  matrix row and records four published raw records plus claims F002-C01–C03.
- `docs/apple-silicon/BACKEND_DESIGN.md` and
  `docs/apple-silicon/KNOWN_LIMITATIONS.md` distinguish model-free CI fixtures
  from the admitted real Apple path and restate the router-only stop.

Final package verification on four raw records and three verified claims
passed. Workspace cargo tests reported 245 passed, 2 ignored, 0 failed.
Research discovery reported 255 passed. GitHub Actions for final main tip
`8fa9b07` completed successfully via workflow_dispatch as
[run 31128482900](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/31128482900)
(Apple Silicon workspace baseline and Apple MLX small-fixture validation both
success). Worktree remained clean with `HEAD == origin/main` after push.
T097 completion NTFY was sent; local inference may resume.

### Feature 003 single-expert MLP parity (2026-08-06)

Opened Spec Kit feature `003-real-expert-execution`. Implemented independent
CPU oracle and Apple MLX full MLP for routed expert 114 (Feature 002 top-8
rank-0) on the genuine `ffn_norm-0` row-0 activation with frozen routing
weight 0.20055663585662842. SwiGLU used SiLU = x*sigmoid(x). Q8_0 gate/up/down
slices admitted by exact byte ranges. Weighted output comparison: 2048
elements, 0 mismatches, max abs error 7.38e-08, RMSE 4.02e-09 under 5e-4
absolute-plus-relative tolerances. Tensor encoded SHA-256 identities matched.
Published raw oracle freeze and parity records under
`docs/research/raw/003-expert-mlp/`. Claim F003-C01 recorded as provisional
pending clean-checkout reproduction and package integration. No multi-expert
aggregation or generation was executed.

### Feature 004 top-8 aggregation (2026-08-06)

Executed all eight Feature 002 routed experts on CPU oracle and Apple MLX,
aggregated weighted down-projections. Parity passed (max abs 6.20e-08).
Recorded cold/warm I/O gauges over expert tensor ranges. Claim F004-C01.

## 2026-08-06 — Feature 005 MoE residual block

Unblocked residual stream capture via single-target `ffn_inp-0` CPU capture
(pinned llama.cpp `b06aa774…`). Dual-ask of `ffn_inp`+`ffn_norm` truncates the
scheduler graph before `ffn_norm` and was rejected as a capture strategy.

Verified `y = ffn_inp + top-8 MoE(ffn_norm)` CPU/MLX parity (max abs ~6.2e-8).
RMSNorm cross-check of residual vs F002 freeze: max abs ~8.5e-8. Claim F005-C01
published under `docs/research/raw/005-moe-block/`.

## 2026-08-06 — Feature 006 layer-out attempt (rejected)

Captured deterministic `l_out-0` and `ffn_moe_out-0` (sha
`ad16738a…19c2` for l_out). Compared against Feature 005 residual MoE block
and Feature 004 aggregate. Failed frozen 5e-4 tolerances (max abs ≈ 3.43e-3,
182 mismatches). Cosine similarity ≈ 0.999990. Rejected attempt preserved under
`docs/research/raw/006-layer-out/`. Deepest verified boundary remains Feature
005. F007+ not started.

## 2026-08-06 — Feature 007 pre-FFN residual capture formalization

Proved layer-0 graph boundary from pinned `qwen3moe.cpp`: `ffn_inp` is the
post-attention residual entering `ffn_norm`; no scale/bias/gate between them;
eps=1e-6 from checkpoint KV. Formal Spec Kit feature 007 packages the already
acquired `ffn_inp-0` capture with mandatory CPU RMSNorm → F002 `ffn_norm-0`
link (max abs ~8.5e-8, 0 mismatches). F002 freeze not regenerated.

Also confirmed llama fused MoE top-8 IDs match F002 exactly; F006 numerical gap
is confined to expert MLP/accumulation vs independent Q8_0 path.

## 2026-08-06 — Feature 008 F006 root cause

Froze F006 case; pairwise A/B/C: A≈B (~6e-8), B≠C (~3.4e-3). Captured llama
intermediates (logits, topk, weights, gate, up, swiglu, down, weighted, moe).
First divergence at expert gate/up Q8_0 matvec. Source: ggml mul_mat requantizes
F32 activations to Q8_0 for Q8_0 weights. Independent Q8_0×Q8_0 reproduction
matches llama within ~2e-7. Contract B: architecture oracle remains F003–F005;
llama bit-parity not claimed. F006-C02 recorded.


## 2026-08-07 — GLM-5.2 sprint open / disk admission block

- Fast-forwarded local main to F015 tip `493234a`.
- Created annotated tag `v0.2.0-qwen30b-e2e-research` (Qwen e2e research baseline).
- Spec Kit feature `016-glm52-full-execution` opened.
- Disk admission **failed**: ~346 GiB free after safe cleanup; need 500 GiB for
  `GLM-5.2-UD-IQ2_XXS` (~222 GiB / 6 shards). No download attempted.
- Evidence: `docs/validation/glm52-disk-admission.json`.
- Deferred: M2 Max, external RAID (policy).

## 2026-08-08 — GLM research baseline and P1 recovery

The original disk stop was later resolved without weakening its thresholds.
The six `UD-IQ2_XXS` shards were admitted by exact sizes and SHA-256 values,
and the architecture research path completed C01–C11. The eight-new-token
golden sequence is frozen at `v0.3.0-glm52-e2e-research`.

After a reboot, the unchanged legacy P1 result was recovered and published. It
matched the first generated token (`[9703, 21615]`) in 15146.448 seconds but
recorded 0 cache hits, 4104 misses, and 3934 evictions. Its legacy JSON does not
self-bind source commit or checkpoint identity, so it is retained as a bounded
golden-prefix observation rather than a throughput claim.

## 2026-08-08 — Cache diagnosis and P2 runtime gate

Exact catalog accounting and deterministic trace simulation established that
the global decoded LRU cycles through a 96.1875-GiB stack while P1 admitted only
8 GiB. The selected bounded policy protects the 10.6875-GiB decoded
shared-expert set under a 16-GiB logical cap; routed matrices remain transient.

The P2 runtime now retains compact evaluated MLX/f32 shared matrices, releases
non-resident matrices after synchronized evaluation, forbids inference-mode CPU
fallbacks, records routes and split storage/dequant/MLX/cache metrics, samples
current and peak RSS, and atomically checkpoints completed stacks. Model-free
tests and a tiny native MLX GPU matvec pass. These facts do not establish
real-checkpoint cache reuse; exactly two new tokens are the next Tier-3 gate.

Immediately before P2, a metadata-only remote check bound the already admitted
six local shard hashes to all six LFS etags at immutable upstream revision
`abc55e72527792c6e77069c99b4cb7de16fa9f23`. No checkpoint payload was
downloaded. The original acquisition record remains unchanged; the later
binding is append-only in `docs/validation/glm52-revision-binding.json`.

## 2026-08-09 — P2 superseded by decoder-priority finding

The clean P2 attempt at source `a34964e` was interrupted gracefully after
46m15s because it remained inside the first full stack when the experiment was
reprioritized. No atomic stack checkpoint existed and no token, parity, or
cache-reuse result was produced. RSS was 18112118784 bytes at the stop sample;
system memory remained 97% free. The traceback stopped inside scalar
`dequantize_row_iq2_xxs` while loading a routed up-projection.

The superseded record is retained at
`docs/research/glm52/raw/f016-inference-p2-superseded-0001.json`. The cache work
is preserved, but another P2 is prohibited until a whole-matrix vectorized
IQ2_XXS decoder passes exact f32-bit comparison and the bounded benchmark ladder
through P1 is committed.

The checkpoint-free decoder slice now keeps the scalar oracle unchanged and
adds an opt-in NumPy whole-block/whole-matrix path with exact `uint32` f32-bit,
signed-zero, deterministic, and malformed-input tests. A clean-source Tier-3
qualifier is prepared for four complete expert matrices at layers 3, 20, 40,
and 60 across four checkpoint shards. No real-matrix result is claimed until
that qualifier runs from its committed source revision.

The clean Tier-3 qualifier then passed at source `968cfac`. It compared four
complete 2048-by-6144 expert matrices from layers 3, 20, 40, and 60 across
shards 2–5, with zero f32-bit mismatches and deterministic repeat hashes. The
layer-3 benchmark retained three warmups and ten samples per decoder: median
scalar decode was 1.424142 seconds and median NumPy decode was 0.050588 seconds
(28.15× at the decode-only boundary). The result does not promote routed
expert, MoE, layer, or token performance claims.

The next checkpoint-free integration slice added explicit `scalar_reference`
and `numpy_vectorized` modes to the MLX expert backend. The vector mode uses a
single complete-matrix positional read only for IQ2_XXS, while other admitted
mixed quant formats retain their scalar reference decoder. Model-free tests
verify one-read matrix behavior, retained scalar row reads, truncated-input
failure, unknown-mode failure, and split/per-quant telemetry. Real MLX matrix
execution remains the next acceptance gate.

The committed real matrix boundary at source `d8af70b` passed on MLX GPU. The
vector path made one complete read versus 2048 scalar row reads, and both modes
produced bit-identical deterministic 2048-value matvec output. Median total
before cleanup was 0.090525 seconds vectorized versus 1.393479 seconds scalar
(15.39×). This completes matrix-granularity integration only; no complete
routed-expert claim is inferred.

The next rung completed the full layer-3 routed expert 15 at source `bbbbaae`.
Two independent scalar CPU-oracle passes were deterministic; the vector MLX
path had zero tolerance mismatches and the two MLX decoder modes were exactly
bit-identical. Median total fell from 4.365715 seconds to 1.706290 seconds
(2.56×). Split timing identified the still-scalar IQ3_XXS down projection as
the remaining expert hotspot. Top-8/shared MoE performance remains unmeasured.

The complete layer-3 top-8 plus shared MoE rung passed at source `c2337db`.
The dedicated CPU oracle repeated exactly; MLX matched within the frozen gate,
with exact top-8 routes and bit-identical decoder-mode outputs. Under warm
shared residency, median total fell from 36.309373 seconds to 14.062472 seconds
(2.58×). The retained process-first vector sample was 23.172902 seconds with
no cache hits; measured samples each reused all three shared matrices. Attention
and complete-layer performance remain the next boundary.

The complete position-0 layer-3 rung then passed at source `a78bc46`. The
architecture reference repeated exactly at the frozen attention midpoint and
post-attention route; vector MLX had zero tolerance mismatches and exact f32
bits against scalar-reference MLX across ten measured samples. Warm median
total fell from 53.230274 seconds to 31.687686 seconds (1.68×), with attention
essentially unchanged at about 18 seconds and MoE falling from 35.210090 to
13.648985 seconds. The result is bounded to one layer and does not establish
full-stack or token-generation performance. The architecture reference is not
promoted to an independent CPU oracle for complete attention because its dense
helper may use the shared MLX reference path.

The vectorized P1 rung then passed at clean source `2de160f`, reproducing the
exact golden prefix `[9703,21615]` on MLX GPU with zero CPU fallbacks. Total
wall time was 6294.014912 seconds; cold prompt and shared-warm generated-token
stacks were 3446.820720 and 2769.003203 seconds. The warm stack recorded all
228 guaranteed shared-matrix hits, zero evictions, and normal resource status.
This completes the decoder-priority ladder through P1; mixed-quant ranking and
reprofiling remain next, and P2 is still ineligible until those are committed.

## 2026-08-09 — Product architecture and Colibri qualification

After the P1 evidence was committed and pushed at `32230e1`, the product
direction was consolidated in `docs/roadmap/PULSARMLX_STRATEGY.md`. The shipping
runtime is planned as Rust-owned with no required Python process, while the
independently understandable Python/NumPy path remains the permanent oracle and
research environment. The target expert path keeps weights compressed through
stable unified-memory residency and eventually performs quantized compute in
Metal; neither the Rust-native runtime nor direct quantized Metal kernels are
claimed as current Feature 016 capabilities.

Colibri was reviewed at pinned revision
`8f512fc8c2f48ffa18cd624cd4a5bcaae4a4abfc` under Apache-2.0. Its Metal design,
tests, expert-store interface, and GLM/expert-cache call sites were classified
as design references or candidates for separately tested clean
reimplementation. No Colibri code was copied or adapted, no performance result
was adopted, and no endorsement is implied. Feature 016 remains focused on the
mixed-quant profile, cache re-evaluation, and P2 gate.

## 2026-08-09 — P1 mixed-quant ranking

A deterministic checkpoint-free generator ranked the quant formats actually
exercised by the committed vectorized P1 trace using the sum of recorded
storage-read, dequantization, contiguous-buffer, MLX-build, and MLX-matvec
seconds. It did not use the checkpoint's global tensor-count histogram.

Nine formats were exercised. IQ3_XXS ranked first at 1791.413883 seconds and
61.78% of the quantified component sum, followed by Q6_K at 475.307709 seconds
and Q5_K at 225.687310 seconds. The result identifies IQ3_XXS as the next
exact-bit decoder candidate; it does not claim IQ3_XXS acceleration or equate
instrumented component sums with P1 wall time. Cache re-profiling and P2 remain
incomplete.

## 2026-08-09 — IQ3_XXS exact-bit qualification

The next dominant decoder was implemented behind the existing explicit
`numpy_vectorized` mode while retaining the scalar Python decoder as the
oracle. Checkpoint-free randomized-block, signed-zero, malformed-input,
determinism, and one-read integration tests passed at source `be47a95`.

The clean real-checkpoint qualification then decoded four complete routed
down-expert matrices from layers 3, 20, 40, and 60 across four distinct shards.
Every vector output matched the scalar oracle at exact f32 bits with zero
mismatches and deterministic repeat hashes. For one 12,582,912-weight matrix,
10 measured samples after three warmups recorded median decode time of
0.075513 seconds vectorized versus 1.578598 seconds scalar, or 20.90× at the
decode boundary. The vector allocation observation retained raw RSS and
`tracemalloc` values. This does not establish a complete routed-expert, layer,
P1, or P2 speedup; the affected bounded ladder must now be rerun in order.

The first affected benchmark rung then passed at clean source `15a8aa2`. One
complete layer-3 expert-15 IQ3_XXS down matrix used one bounded vector read
instead of 6144 scalar row reads, followed by contiguous decode, synchronized
MLX GPU matrix build/eval, and matvec. Ten counterbalanced samples after three
warmups produced exact deterministic output across decoder modes. Median total
was 0.126149 seconds vectorized versus 1.559883 seconds scalar. This is a
matrix-boundary result only; complete-expert benefit remains the next gate.

The complete layer-3 routed expert then passed at clean source `a8a3d71`.
Gate and up remained vector IQ2_XXS while down used the new vector IQ3_XXS
path; all three matrices used one bounded read each. Two independent scalar
CPU-oracle executions were deterministic, the MLX result had zero tolerance
mismatches, and scalar/vector decoder modes were bit-identical and deterministic
across ten measured samples. Median total was 0.243532 seconds vectorized
versus 4.378363 seconds scalar (17.98×). This remains one routed expert; the
complete top-8 plus shared layer-3 MoE is the next measured gate.
