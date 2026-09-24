# Feature 020, Slice 2C: synthetic expert-plane composition (plan)

**Status: plan draft 3 (2026-09-24), with contract `1.0.0-draft.3`.** Prepared
before any composition code exists. Draft 2 folded in the planner's resolutions
of the draft-1 open questions (§10). Draft 3 replaces only the Slice 2B
regression requirement (§6.2) with the planner's decision. The generator, the manifest and the
fixtures are byte-identical to draft 1. Nothing here is authorized until the
owner gives the GO in §10.

The slice composes things that are already qualified and adds nothing
numerical. It takes one expert plane of a synthetic stacked affine tensor. The
plane goes through the Slice 1 catalog, Slice 1 module resolution and Slice 1
checked selection. It then goes into the Slice 2B bridge's existing import and
`quantized_matmul`. The new parts are exact checks only: selection identity,
byte identity, refusal ids, and a bitwise A-vs-B relation.

Related files:

| Role | Path | sha256 |
|---|---|---|
| Contract (new) | `contracts/native-composition-v1.json` | recorded in the commit that adds it |
| Generator and selection oracle (new) | `scripts/research/f020_native_composition_fixtures_v1.py` | `e4214ffb…` |
| Generator test (new) | `scripts/research/tests/test_f020_native_composition_fixtures_v1.py` | |
| Fixture manifest (new) | `fixtures/native-composition/manifest.json` | `bae476dd…` |
| Fixture listing (new) | `find checkpoints mutations standalone -type f \| LC_ALL=C sort \| xargs shasum -a 256 \| shasum -a 256`, run inside `fixtures/native-composition` | `2d314e23…` |
| Inherited contract | `contracts/native-primitives-v1.json` (Slice 2B, `9bf6a810`, merged by `274da684`) | `76959ccb…` |

The following are frozen and are not edited:

- the Slice 2B package:
  - contract `76959ccb…`;
  - plan `24a06db0…`;
  - pins `02e963a0…`;
  - generator `28078a6d…`;
  - manifest `472b5b64…`;
  - case listing `ed0c2e73…`;
- the Slice 1 contracts: `numerics-v1.json` and `catalog-contract.md`;
- every existing evidence file;
- the five frozen F017 files;
- `crates/stream`.

## 1. What is composed

| Stage | What | Copies |
|---|---|---|
| P0 load | `Checkpoint::open`; `QuantizationConfig::from_config_json`; `hash_shards`; one immutable backing buffer per shard (optionally a prefix window) | the backing (fixture load) |
| P1 resolve | `classify_module`, giving an `AffineTriple`. 4-bit vs 8-bit comes from the default plus the explicit override. | none |
| P2 select | composition refusals, then `AffineTriple::expert_slice(index)`, then borrow the three ranges | none (borrows) |
| P3 plane | `SelectedPlane`: one index, one binding, private fields | none |
| P4 check | S-IDENTITY, S-RANGES, S-BYTES against the manifest oracle | none |
| P5 stage | the Slice 2B `HostTensor`s. The packed U32 weight is copied byte for byte and never unpacked. | exactly `plane_bytes` per component |
| P6 native | the existing `bridge::quantized_matmul`, unchanged | as in Slice 2B |
| P7 compare | A, B, C | B's own staging from the standalone file |

**Combos.** The slice covers two combinations:

- 4-bit g64 BF16, resolved by the default;
- 8-bit g64 BF16, resolved by an override on a 4-bit default.

**x.** x is float32 with `transpose=true`. M_eff is 1 (vector family on every
architecture) or 32 (matrix family on every architecture). The ambiguous band
6–31 is avoided on purpose, so each case names one kernel family on every
host.

## 2. File-scope plan for the integration owner

The rule for all changes is additive. The only existing Slice 2B files that
change are listed below, and every change to them preserves behaviour.

| File | Change |
|---|---|
| `crates/mlx-native-affine/Cargo.toml` | Add `mlx-affine` and `safetensors-catalog` as normal (path) dependencies; `mlx-affine` is currently a dev-dependency (see §2.1). Add `[[test]] name = "composition_qualification"`, `test = false`, so that the Slice 2B step's `cargo test -p mlx-native-affine` does not run it. That the Slice 2B step's test set and behaviour are unchanged must be proven (§6.2). |
| `crates/mlx-native-affine/src/lib.rs` | Add `pub mod compose;` and `pub mod frozen_compose;`. The crate stays `#![forbid(unsafe_code)]` and MLX-free. |
| `src/compose.rs` (new) | All selection logic. See §2.2. |
| `src/frozen_compose.rs` (new) | The Slice 2C frozen identities: contract, manifest, generator, listing, case count 31, report schemas, and the composition refusal order. `frozen.rs` stays byte-identical. |
| `src/bin/qualify/main.rs` | Accept `--mode compose` and dispatch it to a new module. `qualify` and `selftest` are unchanged. |
| `src/bin/qualify/compose_run.rs` (new) | The compose child. See §3. It reuses `bridge`, `native`, `ffi`, `provenance` and the E4 canary unchanged. |
| `src/harness.rs` | One identified, behaviour-preserving move (authorized; §2.3). Regression is proven by §6.2. |
| `tests/composition_qualification.rs` (new) | The parent. See §4. |
| `acceptance/composition_gates_v1.py` (new) | Imports `exact_gates_v1.decide_qmm` and `mlx_affine_qmm_reference_v1.exact_case` as modules and applies them to A and B. `exact_gates_v1.py` is not edited. Its hard-coded Slice 2B manifest hash sits only in its `run()`. |
| `.github/workflows/macos.yml` | A new step after the Slice 2B step. See §6. |
| `docs/architecture/reviews/evidence/` | New append-only records. See §7. |

### 2.1 Linking Slice 1 into the child (identified shared-code change)

Composition must run the Slice 1 catalog and resolution. So `mlx-affine` and
`safetensors-catalog` become normal dependencies, and the `qualify` binary
links them. Neither crate links MLX or calls `mlx_set_error_handler`, so the
error-handler coexistence policy still holds.

`mlx-affine` also contains R1 (`reference_qmm`). R1 is linked but must never be
called from the child. A static test enforces this:

- `compose.rs` and `src/bin/qualify/**` name only `mlx_affine::{module, spec, error}` items and `safetensors_catalog` items;
- they never name `reference`, `reference_qmm`, `decode`, `dequantize_rows` or `unpack_codes`.

The existing static test is extended to the newly linked crates. That test
asserts one handler call site and that no linked crate installs one.

Independence of the child from R1 and from the production decoder is required
at two levels. Both are required checks of the composition parent target, so
they run inside the required CI step:

1. **Static (source).** A test reads every source file of the child's code
   paths: `src/compose.rs`, `src/frozen_compose.rs` and every file under
   `src/bin/qualify/`. It fails if any names `reference_qmm`, `reference::`,
   `mlx_affine::reference`, `decode::`, `mlx_affine::decode`,
   `dequantize_rows`, `unpack_codes`, `qmm_reference` or `dq_reference`. It
   also fails on a glob import from `mlx_affine`
   (`use mlx_affine::*`, `use mlx_affine::{...*...}`), so no alias can bring
   those names in.
2. **Binary (symbols).** The parent runs `nm -a` (macOS `nm`) on the built
   `qualify` executable, the exact file it launches. The raw, mangled symbol
   table must contain no symbol with any of these substrings:
   - `10mlx_affine13reference_qmm`
   - `10mlx_affine9reference`
   - `10mlx_affine6decode`

   These substrings match the path component in both legacy and v0 Rust
   mangling. The release profile has no `strip`, and `lto = "thin"` removes
   unreferenced functions. Two controls guard against a vacuous pass:
   - **positive control:** the same table must contain at least one
     `10mlx_affine6module` symbol, proving it is not stripped and that the
     pattern style matches the build;
   - **negative control:** the same scan run on the parent test executable
     itself (`std::env::current_exe()`), which does call
     `mlx_affine::reference_qmm`, must find `10mlx_affine13reference_qmm`.

   Any hit in the child, a missing positive control, or a missing negative
   control is a FAIL. The parent records the symbol counts and the `nm`
   version in the summary.

### 2.3 Harness extraction (authorized, behaviour-preserving)

Exactly three blocks of the body of `harness::accept_report`
(`crates/mlx-native-affine/src/harness.rs`, the function starting at line 199
at base `12b06367`) move, verbatim, into three new `pub fn`s in the same file.
`accept_report` then calls them in the same positions:

| New function | Moved block, in original order |
|---|---|
| `require_exit_zero(run: &ChildRun) -> Result<(), ReportError>` | the `match &run.outcome { ChildOutcome::Exited(0) => {}, other => ChildFailed }` check |
| `require_clean_teardown(report: &Value) -> Result<(), ReportError>` | the `cleanup.errors` check (`Cleanup`), the `cleanup.result_handles.balanced` check (`HandleCensus`), the `handles` census check (`live_array_handles_after_context_drop`, `live_arrays_in_context_at_drop`, `double_free_attempts`, giving `HandleCensus`), and the `test_fault` null check (`TestFault`) |
| `require_case_id_set(report: &Value, want: &BTreeSet<String>) -> Result<(), ReportError>` | the `cases` array extraction, the per-id counts and the `missing`/`unexpected`/`duplicated` computation (`CaseSet`) |

What stays in `accept_report`, unchanged and in place: the report read
(`Missing`), the parse (`Unparsable`), the schema check (`Schema`) against
`frozen::CHILD_REPORT_SCHEMA`, the hash echo against the three Slice 2B frozen
constants (`HashEcho`), and `completed` (`Incomplete`).

`ReportError`, its variants and their payload strings do not change, and the
order of the checks does not change. `accept_compose_report` (new) calls the
three helpers and does its own schema, hash-echo and completed checks against
`frozen_compose.rs`. No other function in `harness.rs` changes. The existing
`harness.rs` unit tests stay unchanged and must pass. The regression proof is
§6.2.

### 2.2 `compose.rs` (library, MLX-free)

- **`Backing`.** Per shard it holds:
  - the file name;
  - an immutable `Box<[u8]>`, read through the catalog's admitted descriptors, either the whole file or a prefix window;
  - the full-file sha256, taken from `Checkpoint::hash_shards` provenance.

  It also holds the payload-inclusive `source_identity`: the sha256 of the `shasum` listing of the shards, in C-locale order.
- **`SelectedPlane<'b>`.** All fields are private. It holds:
  - the identity fields of contract `plane_identity`;
  - three `&'b [u8]` borrows.

  The only constructor is `select_plane`. There is no setter, no builder and no component-wise constructor (I-PLANE-SINGLE-INDEX).
- **`select_plane(checkpoint, backing, triple, index_path)`** is E-SELECT. It evaluates C-R-SOURCE-BINDING, C-R-MODULE-BINDING, C-R-INDEX-RANK, C-R-INDEX-RANGE, C-R-OVERFLOW and C-R-BACKING in contract order. Then it calls `triple.expert_slice(index_path)` (Slice 1, reused and not re-implemented), then `resolve_range` for each component. A Slice 1 `IndexOutOfBounds` or `Overflow` that arrives despite the pre-checks is mapped to the same ids, with the Slice 1 variant recorded.
- **`compose(dir, config_text, module, index_path, windows)`** is E-COMPOSE. It opens the checkpoint (C-R-CATALOG on failure), hashes the shards, loads the backing, calls `classify_module` (C-R-RESOLVE on failure, recording the variant and `implied_bits`), then calls `select_plane`.
- **`resolve_range(backing, shard, begin, len)`** is E-RANGE. It uses checked `u64` addition and `usize::try_from`, gives C-R-OVERFLOW or C-R-BACKING, and returns a borrowed slice.
- **`SelectionRecord`.** The serializable identity, ranges and sha256 of a plane, which the child reports.
- **`stage(plane) -> [HostTensor; 3]`.** Copies exactly the borrowed bytes into Slice 2B `HostTensor`s with shapes `[N, K*bits/32]` and `[N, K/group]`.
- **Unit tests.** Put them in the composition test target, not in `#[cfg(test)]` inside `compose.rs`, so that the Slice 2B step's test inventory does not change.
- **Sealed-plane interface test (required).** A test in the composition target shows that a `SelectedPlane` cannot be built from components of different experts, modules or sources through any public interface. It has three parts:
  1. **API audit.** Read `compose.rs` and assert:
     - `SelectedPlane` has no `pub` or `pub(crate)` field;
     - it derives or implements neither `Default` nor `Clone`;
     - the only public functions that return a `SelectedPlane` (directly or inside `Result`) are `select_plane` and `compose`, and each takes exactly one index path and one triple, or one module path;
     - there is no public function or method that takes a `ByteSlice`, `TripleSlice`, raw range or `&[u8]` component and returns or modifies a plane;
     - there is no `&mut self` method on `SelectedPlane`.
  2. **Every public entry, run.** E-COMPOSE and E-SELECT are driven with every mixing the fixtures allow:
     - weight and companions from two modules through `AffineTriple::new` must give C-R-MODULE-BINDING;
     - a triple from one source with a backing from another must give C-R-SOURCE-BINDING;
     - for every accepted case, the three reported ranges must be the oracle's ranges of the ONE requested index, with no component from another index.
  3. **No `compile_fail` doctests.** They would add to the Slice 2B step's doctest inventory, which §6.2 requires to stay unchanged.

  Mutation controls stay at the selection-record level through the test-only child path (planner resolution 5).

## 3. The compose child (`--mode compose`)

The child keeps the Slice 2B start sequence unchanged: the R-NAX environment
assertion first, then ABI verification, the single error handler, the default
device set to GPU, provenance (E3) and the E4 canary.

It then reads the frozen Slice 2C files, requiring the contract, generator and
manifest hashes from `frozen_compose.rs`, and opens one `NativeContext`. It
runs every manifest case in manifest order, with the three `seq-aba-*` cases
consecutive, then runs the E4 canary again, tears down, and writes the report
atomically.

Per case, the child does the following:

1. **Record counters.** Take `ffi::call_counts()` as `c0`.
2. **Compose.** Run E-COMPOSE, E-SELECT or E-RANGE, as `composition.entry`
   says, with any `backing.windows` and `triple_components` from the manifest.
   On a refusal, record the id and `call_counts() - c0`. The contract requires
   this to be `(0, 0)` for the whole case, which ends here.
3. **Mutation cases only.** Build the plane normally. Then pass its
   `SelectionRecord` through the test-only mutator: it replaces ranges or
   identity fields as `composition.mutation` specifies, reads the mutated bytes
   from the backing and hashes them. Run the checks, and record which checks
   report a mismatch and whether the mutated ranges and sha256 equal the
   manifest's. No native call follows. For `override_ignored_at_resolution`,
   E-COMPOSE runs with the mutated config file instead, and the expected
   outcome is C-R-RESOLVE.
4. **Selection checks.** Run S-IDENTITY, S-RANGES and S-BYTES against
   `oracle`. On any mismatch in a non-mutation case, record FAIL. The plane is
   not executed.
5. **Stage and compare inputs.** Stage A. Load B with `fixture::load_case` on
   the standalone file. Run S-STAGED-EQUAL, which compares x, w, scales and
   biases bytes, dtypes and shapes.
6. **Run A, then B.** Each goes through `bridge::quantized_matmul(ctx, x, w, s,
   b, bits, group)` with `bits` and `group` taken from the plane identity for A
   and from `params` for B. Record the outputs (files and sha256), each
   `OpStats`, and the array census.

   For an inherited-refusal case, A and B must both return
   `BridgeError::Refused(expected)` with `numerical_before_decision == 0` and
   `imports_before_decision == 0`.
7. **Check the source.** Run S-SOURCE-UNCHANGED: re-hash every backing buffer
   and shard file, and the standalone file.

The array census needs no change to the bridge. The child derives it from the
staged `HostTensor`s and the bridge's fixed call sequence for F32 x and BF16
metadata: four imports, two `astype`s and one QMM. It records the counter
deltas as a cross-check: exactly 4 imports, and the numerical-call delta as the
bridge counts it. The integration owner pins the expected numerical delta from
the bridge source before the first run, not from an observation. The parent
compares the census with `expected.array_census`.

The A-vs-B relation (N-COMP-AB) and N-COMP-ABA are decided by the parent from
the output bytes. The child reports and does not decide.

## 4. The parent (`tests/composition_qualification.rs`)

The parent follows Slice 2B's `native_qualification_of_the_frozen_population`
closely and reuses its library pieces:

- `harness::run_child`, `child_env` and `frozen_timeout` (1800 s, SIGKILL, reap, TIMEOUT, no retry);
- `fixture::parse_manifest` and `load_case`. The Slice 2C manifest is schema-compatible: it has top-level `generator_sha256`, and every case has `id`, `family`, `op` and `params`. Standalone files use the Slice 2B case encoding.

It runs in this order:

1. **Validate before.** Check the generator (`--check`), the contract,
   manifest and listing hashes, every checkpoint and standalone file hash, and
   the six Slice 2B hashes.
2. **Run and accept the child.** Run `qualify --mode compose` once. Accept the
   report with `accept_compose_report`: exit 0, schema, hash echo (including
   the Slice 2B contract), completed, cleanup and handle census, no test fault,
   and a case-id set exactly equal to the manifest's 31.
3. **Decide from the report.** Re-decide every S-check from the reported
   `SelectionRecord` against the manifest. The parent does not trust the
   child's verdicts. Enforce the counter deltas for refusals and mutations.
4. **Build C.** Compute the Rust binary64 R1 (`mlx_affine::reference_qmm`) and
   the exact Python R1 on every standalone file. Both references are listed on
   all 14 executed cases.
5. **Apply the gates.** Run G-QMM-RUST (with `gates::g_qmm_rust`) and
   G-QMM-EXACT (with `acceptance/composition_gates_v1.py`, via
   `exact_gates_v1.decide_qmm`) on A and on B separately. Run G-R1-SELF-QMM,
   N-QMM-SHAPE-DTYPE, N-COMP-AB (byte equality of the A and B output files),
   N-COMP-ABA and N-COMP-ARRAYS.
6. **Validate after.** Validate again, then write `summary.json` with the gate
   counts and the failures list.

The Slice 2B `accept_report` and the Slice 2B parent test are not edited, apart
from the optional helper extraction in §2. The 363-case Slice 2B qualification
must still pass at the same candidate (contract C9).

## 5. Copy and lifetime accounting; refusal instrumentation

**Copies.** The child reports every host buffer and native array per stage, as
the contract's `copy_and_ownership.accounting_method` defines:

- borrows as `(shard, begin, len)`;
- staging copies as `(role, bytes)`;
- MLX arrays as `(role, op, dtype, shape)`.

The parent checks three things:

- staging bytes equal `plane_bytes`;
- the census equals `array_census`;
- no float array has the weight's logical shape.

**Lifetimes.** `SelectedPlane<'b>` borrows `Backing`. The staged `HostTensor`s
are owned per case. `NativeArray<'ctx>` handles are dropped inside the case,
so the context has zero live arrays between cases (as in Slice 2B).

**Refusals come before native numerical execution.** This rests on three
layers of evidence:

1. **Structural.** Every C-R decision is made in the library crate, which does
   not link MLX. It cannot issue an MLX-C call.
2. **Ordering.** The child calls the bridge only after `compose` returns `Ok`
   and every S-check passes.
3. **Counters.** The child reports `ffi::call_counts()` deltas: whole-case
   `(0, 0)` for C-R refusals and mutations. For inherited refusals it reports
   the existing `OpStats` counters, `numerical_before_decision` and
   `imports_before_decision`, which must both be 0. The parent enforces both.

## 6. CI

Add a new step in the macos native job, after `Qualify F020 Slice 2B native
primitives …`: `Qualify F020 Slice 2C synthetic expert-plane composition
(frozen synthetic population, runner GPU)`.

- **Commands.** It runs `cargo test -p mlx-native-affine --release --test
  composition_qualification -- --test-threads=1 --nocapture` with its own
  output directory, then a post-check of `summary.json`: PASS, 31 cases, gate
  counts, child `EXIT_STATUS 0`, timeout 1800, `mlx_version` 0.31.2 and
  `MLX_ENABLE_TF32` 0.
- **Missing prerequisites.** Handled as in the Slice 2B step: a missing
  prerequisite, a build without MLX (`NOT RUN` panics under
  `PULSAR_REQUIRE_NATIVE_MLX=1`), a missing `summary.json` or a missing child
  report fails the step.
- **Required (owner GO).** The step is REQUIRED in the native small-fixture
  job `apple-mlx-small-fixtures`, using the doctor procedure in
  `scripts/ci/f017_measurement_scope_v1.py`:
  - commit X adds the step;
  - commit Y adds its exact name to `REQUIRED_EXTRA_STEP_NAMES` and advances
    `RESOLUTION_BASE` and `RESOLUTION_WORKFLOW_SHA256` to X;
  - the resolution's earlier required blocks, including the Slice 2B step,
    stay contained byte for byte.
- **Existing steps.** The Slice 2B required step's body is not changed. The
  new test target has `test = false`, so that step runs the same tests as
  before. This is proven, not assumed (§6.2).

### 6.1 A missing, skipped or failing composition step cannot leave the aggregate green

Commit Y extends `scripts/ci/f017_measurement_scope_tests_v1.py` with a block
for the new step name that mirrors the existing Slice 2B block. Each workflow
mutation below must be rejected by the doctor (expected refusal
`WORKFLOW_CHECK_INVENTORY_OR_CONTEXT`, as for Slice 2B):

| Control | Mutation of the composition step |
|---|---|
| rename | `name:` with a suffix appended |
| removal | the step block deleted |
| masking | `|| true` appended to the `cargo test … --test composition_qualification …` command |
| summary assertion deleted | the `assert summary["result"] == "PASS"` line removed |
| build-only | the test invocation replaced by `--no-run` |
| non-fatal | `continue-on-error: true` added to the step |
| disabled | `if: false` added to the step |
| moved job | the step moved into a new job outside `apple-mlx-small-fixtures` |

Four further requirements:

- The existing job-level controls apply unchanged: a job `continue-on-error`,
  a job `if:`, workflow `defaults` and a changed aggregate job are all
  rejected.
- The existing Slice 2B controls must still pass.
- The doctor `--check` runs in the required measurement-scope step. The
  aggregate job (`CI aggregate status`, `scripts/ci/aggregate_status_v1.py`)
  is green only when the native job succeeds.
- A failing composition step (summary `FAIL`, child timeout, missing report or
  a skipped suite) fails its job and therefore the aggregate. The step's shell
  runs under `set -euo pipefail`, as the Slice 2B step does.

Evidence for Y records the doctor test output with every control listed and
rejected.

### 6.2 Slice 2B invocation unchanged: required regression proof (planner decision, draft 3)

Draft 2 required the candidate's 363-case Slice 2B child report to be
byte-identical to the attempt-3 report. That cannot hold by construction: the
report embeds the running `qualify` binary's own sha256. The requirement is
replaced by a primary same-run differential (b) and a secondary cross-run
comparison (a).

#### (b) PRIMARY: same-run base vs candidate differential

This runs in the same CI run and the same job (`apple-mlx-small-fixtures`, on
the GitHub `macos-15` runner), inside the required Slice 2C step. Both runs
use the same runner-built native prefix, meaning the same `MLX_C_PREFIX` and
`MLX_PREFIX` produced once by `scripts/ci/install_native_mlx.sh` in that job,
and the same toolchain.

- **BASE.** A detached worktree of `12b063675c2227c59d2157458e051d73647b7045`
  runs its unchanged Slice 2B qualification:
  `cargo test -p mlx-native-affine --release --no-fail-fast --
  --test-threads=1 --nocapture`, with its own `CARGO_TARGET_DIR` and
  `PULSAR_F020_QUALIFICATION_OUT`.
- **CANDIDATE.** The candidate checkout runs the same command, invoking the
  existing Slice 2B mode (`--mode qualify`) unchanged, with its own target and
  output directories.
- **Compare.** A new stdlib-only script,
  `scripts/ci/f020_slice2b_regression_compare_v1.py`, compares the two
  `qualification/child/report.json` files.
  - Canonical form: for each report, parse the JSON, delete exactly the
    volatile fields below, and serialize with Python
    `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`,
    encoded as UTF-8.
  - Deleting a field means removing the key from its object. Arrays keep their
    order, and `cases` stays in manifest order.
  - The two canonical byte strings must be equal. Everything not listed is
    therefore compared byte for byte, including:
    - every case's `outcome`, `refusal_id`, `expected_refusal_id`,
      `geometry`, `kernel`, `metadata_cast`, `structural` and `output`
      (`file`, `sha256`, `nbytes`, `dtype`, `shape`);
    - each case's `stats.numerical_calls_before_decision`,
      `stats.imports_before_decision`, `stats.device_facts_gpu` and
      `stats.e5_peak_memory.output_nbytes`;
    - `canary_start` and `canary_end`, including `output_sha256`;
    - `cleanup` (errors, `array_free_calls`, `result_handles`), `handles`,
      `call_counts` and `error_handler`;
    - `abi_values`, all of `provenance` except the listed field (the native
      library, metallib and prefix identity, the environment, the device,
      `build.rustc`, `build.crate_version` and `build.profile`);
    - `schema`, the three echoed hashes, `completed`, `test_fault` and
      `thread`.
- **Also required in the same run:**
  - the two runs' parent `summary.json` `gate_counts` are identical, and
    equal the attempt-3 counts in the table below;
  - both have `result` PASS and an empty `failures` list;
  - the Slice 2B step's test-name list is identical at base and candidate:
    `cargo test -p mlx-native-affine --release -- --list` and
    `cargo test -p mlx-native-affine --release --doc -- --list`, compared line
    for line;
  - `composition_qualification` appears in neither list (it is
    `test = false`), and
    `cargo test -p mlx-native-affine --release --test composition_qualification -- --list`
    does list it.

**Volatile fields, prospectively enumerated and exhaustive.** These are the
only fields removed. The paths are relative to the child report root, and
`cases[*]` means every element of `cases`.

| # | JSON path | Why it is volatile |
|---|---|---|
| V1 | `provenance.build.qualify_executable_sha256` | the sha256 of the running `qualify` binary (`std::env::current_exe()`, `src/bin/qualify/provenance.rs:188-190`, reported at line 230). Base and candidate are different binaries by construction: the candidate adds `--mode compose` and links `mlx-affine` and `safetensors-catalog`. The report carries no path or size of the executable, so nothing else about it is removed. |
| V2 | `cases[*].stats.e5_peak_memory.active_before` | the allocator's active-memory reading before the operation (`mlx_get_active_memory`, `src/bin/qualify/run.rs:53-66`, `bridge.rs` `memory_before`). It depends on allocator and buffer-cache state, not only on the case's inputs. It is `null` on refused cases in both runs. |
| V3 | `cases[*].stats.e5_peak_memory.peak_after` | the allocator's peak reading after the operation (`mlx_get_peak_memory`, same sites). Volatile for the same reason. |
| V4 | `cases[*].stats.e5_peak_memory.peak_delta_ge_output_nbytes` | derived only from V2 and V3 (`peak_after - active_before >= output_nbytes`, `run.rs:53-56`). It is E5, which is "supporting only" and gates nothing in the Slice 2B contract (`execution_evidence` E5). |

Deliberately NOT listed, and therefore compared:

- `provenance.build.rustc`, `build.crate_version` and `build.profile`: one job
  builds both children with the same toolchain, crate version `0.1.0` and the
  `release` profile, so a difference is a finding. The candidate must not
  change the crate version.
- Every native-library, metallib and prefix-identity field: both children
  load the same runner-built prefix.
- `provenance.os_product_version` and `device_info`: same runner.
- `provenance.environment`: the same fixed child environment, with paths
  already redacted to `<native-prefix>`.

The child report has no timestamp or duration field. The parent's `elapsed_ms`
lives in the parent summary, not in the child report. If an integration
change would add one to the Slice 2B child report, that would itself change
the Slice 2B invocation, which is not allowed.

**Stop rule.** Any difference outside V1–V4, including a field present in one
report and absent from the other, is a STOP condition reported to the planner.
Adding a field to the volatile list after any observation is a contract
change: it needs a new contract version and re-review (correction_policy
rule_2). The comparison script prints the list of differing JSON paths and
exits non-zero. It never prints or accepts a tolerance.

#### (a) SECONDARY: cross-run comparison against attempt 3

The reference is the attempt-3 child report, which the planner has preserved:

- CI run `36006063937`, artifact
  `f020-slice2b-qualification/qualification/child/report.json`;
- sha256 `e3b596bc6d3c3af3eca33d8084c1a9cb3b0c6bbd2b8910d3bbe7c4e32cac5640`,
  519,872 bytes;
- also recorded in
  `docs/architecture/reviews/evidence/f020-slice2b-ci-qualification-attempt-3-v1.json`.

The comparison needs a checked-in or retrievable copy whose sha256 is verified
first. Where it is stored is for the integration owner to propose. It must not
be a private host path in a committed file.

For every one of the 363 case ids, the candidate report's per-case outputs
must equal attempt 3's:

- `outcome`, `refusal_id`;
- `output.sha256`, `output.nbytes`, `output.dtype`, `output.shape`;
- `structural`.

In addition, `canary_start.output_sha256` and `canary_end.output_sha256` must
be equal. The report carries no per-case numerical values beyond these
digests, because the outputs are separate files.

This cross-run comparison relies on the runner's native build (libmlx,
libmlxc, metallib), toolchain and device being identical across runs. The
comparison records both runs' `provenance.native_prefix.identity_sha256`,
`libmlx`/`libmlxc`/`metallib` sha256, `build.rustc`, `os_product_version` and
`device_info`.

A mismatch in (a) while (b) passes is recorded in the evidence together with
those provenance differences, and reported to the planner. It is not silently
accepted, and it is not converted into a pass.

**Attempt-3 gate counts.** All passed; these are the values (b) must also
match.

| Gate | Cases |
|---|---|
| B6-REFUSAL | 37 |
| E1-DEVICE | 362 |
| E6-CPU-REFUSED | 1 |
| G-IMPORT | 8 |
| G-CAST | 2 |
| G-DQ-CODES | 18 |
| G-DQ-RUST | 59 |
| G-DQ-EXACT | 59 |
| G-R1-SELF-DQ | 59 |
| G-QMM-RUST | 239 |
| G-QMM-EXACT | 237 |
| G-R1-SELF-QMM | 237 |
| N-QMM-ZERO | 1 |
| SHAPE-DTYPE | 326 |

## 7. Evidence records (append-only)

For every attempt, the owner adds `docs/architecture/reviews/evidence/f020-slice2c-*.json`
with:

- the candidate commit;
- the contract, manifest, generator and listing sha256;
- the CI run id and job;
- the host architecture;
- the summary and report sha256;
- the gate counts;
- the failures.

A failed attempt gets a record too. A rerun after a targeted fix is a new
record that names the one it follows.

## 8. Fixture population (31 cases, generated, stdlib only)

**Checkpoints:**

- `ck-a-single`: one shard. Default 4-bit. `block.0.stack_a` and
  `block.0.stack_b`, both `[4, 64, 256]`, placed after a dense tensor.
- `ck-a-sibling`: a byte-identical header with a different payload. It has
  the same catalog digest as `ck-a-single`.
- `ck-b-sharded`: three shards plus an index, with a 4-bit default:
  - `block.1.stack_d`: 8-bit by override, `[4, 64, 256]`;
  - `block.1.stack_c`: 4-bit default, `[2, 64, 512]`; its scales start at data offset 0;
  - `block.2.stack_q`: 8-bit by override, `[3, 128, 128]`, with weight, scales and biases in three different shards; its biases are the last tensor of a shard;
  - `block.2.stack_r`: `[3, 64, 128]`; expert 1 has one scale of 2^-33;
  - `block.2.narrow`: `[2, 32, 128]`.

| Family | n | Failure mode each case isolates |
|---|---|---|
| FX-COMP-ACCEPT | 11 | first, middle and last expert; vector and matrix x; default vs override resolution; multi-shard companions; offset-0 and nonzero offsets; K 128/256/512 (qmv_quad, qmv, qmv_fast; split-K 2/4/8); per-plane admission |
| FX-COMP-SEQUENCE | 3 | stale state across selections: A-B-A across bit widths in one child |
| FX-COMP-REFUSE | 8 | index = E; index = 2^64−1 (no wrap or narrowing); rank 0; rank 2; `u64` overflow at E-RANGE; a backing window one byte short; an identical-header sibling payload; a mixed-module triple built through `AffineTriple::new` |
| FX-COMP-INHERITED-REFUSE | 3 | Slice 2B guards applied to the selected plane: R-GEOMETRY (N 32), R-DOMAIN-META-RANGE (one expert only), R-XSHAPE (x vs logical K) |
| FX-COMP-MUTATION | 6 | wrong index; wrong stride; swapped scales; swapped biases; override ignored at resolution; override ignored in the plane |

The generator asserts all of the following on every run, including `--check`:

- the oracle's ranges equal a separate parse of the written headers;
- the file slices equal the expected plane bytes;
- every component differs between every pair of experts;
- each accepted plane passes every Slice 2B guard;
- each refusal probe violates exactly its expected guard;
- each mutation changes exactly the ranges it claims, while staying inside its tensor;
- no model-specific name appears.

The test re-derives the ranges with its own header reader. It also checks
that the Slice 2B exact-R1 reader accepts every standalone file.

## 9. What this plan does not do

- It adds no numerical bound, domain or tolerance.
- It adds no production geometry, real payload, `gather_qmm`, routing, full
  MLP, streaming, residency or performance work.
- It makes no change to the meaning of the Slice 2B invocation.

## 10. Planner resolutions (2026-09-24) and remaining owner GO items

The draft-1 open questions are resolved as follows. Each resolution is folded
into the sections cited.

1. **`.gitignore`.** A single-line path exception,
   `!fixtures/native-composition/**`, is added directly after the existing
   `!fixtures/safetensors/**/*.safetensors`. After it:
   - `git check-ignore --no-index` matches none of the 28 tracked fixture files;
   - a new file under `fixtures/native-composition/` shows as untracked;
   - `*.safetensors` and `checkpoints/` stay ignored everywhere else.
2. **Linking Slice 1 into the child.** Approved. Independence is required at
   two levels, the static source test and the `nm` symbol check with positive
   and negative controls (§2.1).
3. **Slice 2B invocation unchanged.** Replaced by the planner's decision in
   draft 3 (§6.2). The primary requirement is (b): a same-run base vs
   candidate differential of the two child reports as canonical JSON, with
   only V1–V4 removed, plus identical gate counts and an identical test-name
   list. The secondary requirement is (a): per-case output digests against
   the preserved attempt-3 report, recorded and reported on mismatch. Any
   difference outside V1–V4 is a stop condition.
4. **Harness extraction.** Authorized as the behaviour-preserving move listed
   in §2.3. The regression proof is §6.2.
5. **Mutation injection at the selection-record level.** Accepted. The
   required sealed-plane interface test is added in §2.2.
6. **Overflow probe through direct range arithmetic.** Accepted as disclosed
   (contract `composition_refusals.order`, C-R-OVERFLOW).
7. **Required CI step.** The composition step is required through doctor X/Y,
   and the doctor mutation controls are listed in §6.1.

Remaining owner GO items:

1. **Freeze the contract.** Freeze `native-composition-v1.json` draft.3. It is
   normatively draft.1 plus the requirements of resolutions 2, 3 (as decided
   in draft 3), 5 and 7,
   and includes:
   - the composition refusal order;
   - the selection checks;
   - N-COMP-AB as exact bitwise equality under A-DET, with its failure policy.
2. **Freeze the population.** Generator `e4214ffb…`, manifest `bae476dd…`,
   listing `2d314e23…`, 31 cases and 28 files, all unchanged since draft 1.
   The manifest's `contract_schema` field names draft.1, the draft under
   which the population was generated. This follows Slice 2B, whose manifest
   names contract draft.4 under the frozen draft.6.
