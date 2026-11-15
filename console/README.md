# PulsarMLX Console workspace

**Status (2026-11-14):** skeleton only. Nothing in this directory serves anything yet.

This directory will hold PulsarMLX Console: a Rust serving layer and dashboard rebuilt
from the serving layer of project-maya (the donor, pinned at commit `7e68a30f`), driven
only by synthetic engines in this increment. The feature is specified in
[`../specs/022-console-serving-parity/`](../specs/022-console-serving-parity/) and the
decision to build it ahead of strategy Stage F is recorded in
[ADR 0008](../docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md).

## Claim status

| Item | Status |
| --- | --- |
| Cargo workspace with one member, `console-pyjson` | Present. The crate is empty apart from one test that proves the workspace builds and its test harness runs. |
| Python-compatible JSON writer (package API-01) | Planned (milestone M1). Not implemented. |
| HTTP server, dialects, engines, dashboard | Planned (milestones M1 to M9). Not implemented. |
| Parity ledger, [`parity/ledger.json`](parity/ledger.json) | Present. 913 rows, one per donor test method, every row `pending`. |
| Boundary, hygiene and toolchain checks, [`tools/`](tools/) | Present. Meant to be run locally before each commit; they have not yet run in CI. |
| CI, [`../.github/workflows/console.yml`](../.github/workflows/console.yml) | Written. It has not run on GitHub yet. |
| Real model serving | Out of scope for this increment. When built, the work can at most be described as "qualified on synthetic backends". |

Nothing here may be described as working until its command, environment, input and
result are recorded, as constitution principle III requires.

## A separate workspace

`console/` is a standalone, nested Cargo workspace with its own
[`Cargo.toml`](Cargo.toml), `Cargo.lock` and [`rust-toolchain.toml`](rust-toolchain.toml)
(Rust 1.97.1 with rustfmt and clippy). It is **not** a member of the root workspace, so
the root commands in [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
(`cargo check --workspace`, `cargo test --workspace`) and the `macOS baseline` workflow
never build it. A green root build says nothing about this directory.

Run cargo from this directory, never from the repository root with `--manifest-path`:
rustup reads `rust-toolchain.toml` from the current directory upward, so the pin applies
only when the working directory is `console/` or below. Keep the target directory outside
the repository, because the root `.gitignore` drops any directory named `target`,
`debug` or `release`, and because builds share the machine with engine qualification
runs. Without rustup the pin file is ignored, so check the compiler first; the script
fails unless `rustc -V` reports exactly the pinned version:

```sh
cd console
bash tools/check-toolchain.sh
# Any directory outside the repository will do.
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$HOME/.cache/pulsar-console-target}"
nice -n 10 cargo fmt --check
nice -n 10 cargo clippy --locked --all-targets -- -D warnings
nice -n 10 cargo test --locked
```

Before each commit, from the repository root:

```sh
console/tools/check-boundary.sh
console/tools/check-hygiene.sh
```

Both take `--base REF` (default `origin/main`) and `--committed` (check only
`merge-base..HEAD`, as CI does). Each prints one line per check and exits non-zero on
any failure.

| Tool | What it checks |
| --- | --- |
| [`tools/check-boundary.sh`](tools/check-boundary.sh) | Every changed path is on the allowlist below; root `Cargo.toml`, `Cargo.lock` and `.github/workflows/macos.yml` equal the merge base byte for byte; nothing under `console/` or the feature directory is ignored by git or uses a `.gitignore` trap name; no manifest under `console/` points outside it and no `.cargo/` directory exists there; no reserved engine-track name is used. |
| [`tools/check-toolchain.sh`](tools/check-toolchain.sh) | `rustc -V`, run from `console/`, reports exactly the channel pinned in `rust-toolchain.toml`. It prints one line and exits non-zero on a mismatch or when `rustc` is missing. |
| [`tools/check-hygiene.sh`](tools/check-hygiene.sh) | Added content has no submodule or other non-regular Git object, binary file, symbolic link, file over 1 MiB, more than 16 MiB in total, model and tensor extension or whitespace error; added lines have no credential-shaped value, home-directory path, UUID, machine identifier, literal `host` or `user` JSON value or AI attribution; commit messages in the range have no attribution lines. Rare justified exceptions to the heuristic line gates (credential assignment, bearer token, UUID, machine identifier, identity JSON) use a same-line allow marker whose id is listed in [`tools/hygiene-allow.txt`](tools/hygiene-allow.txt). |
| [`tools/list_donor_tests.py`](tools/list_donor_tests.py) | Lists the donor's test methods by parsing them as text; it regenerates the parity ledger. See [`parity/README.md`](parity/README.md). |

## Non-interference rules

The engine track works in the same repository, and some of its evidence is bound to file
hashes. This work therefore follows these rules, which `check-boundary.sh` enforces where
a machine can:

- **Paths this work may touch:** `console/**`, `specs/022-console-serving-parity/**`,
  `docs/console/**`, `docs/roadmap/CONSOLE_ROADMAP.md`,
  `docs/roadmap/PULSARMLX_STRATEGY.md`, `docs/upstream/PROJECT_MAYA.md`,
  `docs/upstream/PROJECT_MAYA_SYNC.md`,
  `docs/architecture/decisions/0008-console-serving-ahead-of-stage-f.md`, `NOTICE.md`,
  `README.md`, `CONTRIBUTING.md` and `.github/workflows/console.yml`.
- **Never touched:** the root `Cargo.toml` and `Cargo.lock`,
  `.github/workflows/macos.yml`, anything under `crates/`, `experiments/`, `fixtures/`,
  `scripts/` or `docs/research/`, `.specify/`, `.gitignore`, the root
  `pyproject.toml` and `uv.lock`.
- **No path dependency outside `console/`.** Every third-party dependency is pinned with
  `=` in `[workspace.dependencies]` and recorded with its license in the feature's
  `research.md`.
- **No trap names.** The root `.gitignore` silently drops directories named `models`,
  `weights`, `checkpoints`, `logs`, `dist`, `env`, `debug`, `release` and `target`, and
  files such as `*.log`, `*.key`, `*.pem`, `secrets.*`, `credentials.json`, `mcp.json`,
  `*.trace.json`, `*.bench.json` and `*.prof*`. Do not use those names anywhere under
  `console/`. Test data lives in `testdata/` or `tests/data/`, never in a `fixtures/`
  directory at the console root, and generated fixtures are built in code.
- **No binary files, no vendor chat templates, no model weights.**
- **Reserved names** stay with the engine track: the packages `mlx-expert-ranges`,
  `mlx-expert-mlp`, `expert-residency-core`, `packed-affine-adoption`, `serve`,
  `pulsar-serve` and `pulsar-serve-synthetic`, and the directories `experiments/`,
  `crates/serve-synthetic` and `docs/serving/`.
- **project-maya is data, not a runtime.** Its code is never executed on a development
  machine; it runs only in a manual GitHub Actions reference job, which arrives with a
  later work package. No project-maya engine binary is launched in this increment.

What the rules guarantee: no file the engine track edits or hashes changes. What they do
not guarantee: the tree identity of `main` changes when this work merges, like any commit,
so the merge order is decided with the owner (OPEN-14 in the open-item register,
[`checklists/analysis.md`](../specs/022-console-serving-parity/checklists/analysis.md)).

## Layout

Only the files in the claim table exist today. The planned layout, from the feature
[`plan.md`](../specs/022-console-serving-parity/plan.md):

| Path | Planned content |
| --- | --- |
| `crates/` | `console-pyjson`, `console-core`, `console-tokenizer`, `console-prompt`, `console-engine`, `console-http`, `console-responses`, `console-mcp`, `console-attach`, `console-media`, `console-manage`, `console-host`, `console-launch`, `console-web` and the `pulsar-console` binary; test-only `console-fake-engines`, `console-testkit`, `console-conformance`, `console-web-e2e` and `xtask`. |
| `web/` | Phase 1 dashboard, adapted from the donor's JavaScript, with neutral product identity. |
| `conformance/` | Scenarios, recorded references and the reference pin. |
| `parity/` | The parity ledger. |
| `tools/` | Boundary, hygiene and toolchain checks and the donor test lister. |
| `LICENSES/` | Full license texts: the donor's now, and each third-party text with the change that imports its component. |
