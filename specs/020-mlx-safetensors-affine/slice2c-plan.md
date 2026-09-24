# Feature 020, Slice 2C: synthetic expert-plane composition (plan)

**Status: plan draft 1 (2026-09-24), with contract `1.0.0-draft.1`.** Prepared
before any composition code exists. Nothing here is authorized until the owner
gives the GO in §10.

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
| `crates/mlx-native-affine/Cargo.toml` | Add `mlx-affine` and `safetensors-catalog` as normal (path) dependencies; `mlx-affine` is currently a dev-dependency (see §2.1). Add `[[test]] name = "composition_qualification"`, `test = false`, so that the Slice 2B step's `cargo test -p mlx-native-affine` does not run it (to be confirmed, see §10). |
| `crates/mlx-native-affine/src/lib.rs` | Add `pub mod compose;` and `pub mod frozen_compose;`. The crate stays `#![forbid(unsafe_code)]` and MLX-free. |
| `src/compose.rs` (new) | All selection logic. See §2.2. |
| `src/frozen_compose.rs` (new) | The Slice 2C frozen identities: contract, manifest, generator, listing, case count 31, report schemas, and the composition refusal order. `frozen.rs` stays byte-identical. |
| `src/bin/qualify/main.rs` | Accept `--mode compose` and dispatch it to a new module. `qualify` and `selftest` are unchanged. |
| `src/bin/qualify/compose_run.rs` (new) | The compose child. See §3. It reuses `bridge`, `native`, `ffi`, `provenance` and the E4 canary unchanged. |
| `src/harness.rs` | Only if needed, one behaviour-preserving extraction: pull the exit-status, cleanup/handle-census and case-id-set checks out of `accept_report` into helpers that `accept_report` and a new `accept_compose_report` both call. `accept_report`'s decisions stay identical, and its existing tests stay green. |
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
- **Initial status.** It is added as non-required, which changes nothing
  gated.
- **Making it required.** This uses the doctor procedure in
  `scripts/ci/f017_measurement_scope_v1.py`:
  - commit X adds the step;
  - commit Y adds its exact name to `REQUIRED_EXTRA_STEP_NAMES` and advances
    `RESOLUTION_BASE` and `RESOLUTION_WORKFLOW_SHA256` to X;
  - the earlier required blocks stay contained byte for byte.
- **Existing steps.** The Slice 2B required step's body is not changed. The
  new test target has `test = false`, so that step runs the same tests as
  before.

The generator test runs in the existing research-methodology step. That step
discovers `scripts/research/tests/test*.py` and needs no workflow change.

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

## 10. Owner GO items and open questions

1. **Freeze the contract.** Freeze `native-composition-v1.json` draft.1,
   including:
   - the composition refusal order;
   - the selection checks;
   - N-COMP-AB as exact bitwise equality under the new assumption A-DET, with
     its failure policy (STOP, and no tolerance fallback without a new
     version).
2. **Freeze the population.** Generator `e4214ffb…`, manifest `bae476dd…`,
   listing `2d314e23…`, 31 cases and 28 files. CI runs `--check` through the
   generator test.
3. **Authorize the dependencies.** Make `mlx-affine` and `safetensors-catalog`
   normal dependencies of `mlx-native-affine`, so they link into the child
   (§2.1). The alternative is to keep selection in the parent and pass staged
   bytes to the child. That weakens "refusal before native call" to a
   parent-side argument, and is not recommended.
4. **Confirm the test-target setting.** Confirm that `test = false` on the new
   `[[test]]` target keeps the Slice 2B step's inventory unchanged, while
   `--test composition_qualification` still runs it. This must be verified on
   the pinned toolchain before the CI step is written.
5. **Harness extraction.** Authorize the optional behaviour-preserving helper
   extraction in `harness.rs`, or require a separate `accept_compose_report`
   that re-implements the three checks.
6. **CI requirement.** Decide whether the new step is required. If it is,
   authorize the doctor X/Y advance.
7. **Mutation injection point.** Mutation controls are injected at the
   selection-record level through a test-only child path, not inside the
   sealed plane constructor. Confirm that this satisfies the "mutation
   control" requirement for I-PLANE-SINGLE-INDEX. The type requirement itself
   is verified statically.
8. **Ignored fixture files.** `.gitignore` ignores `*.safetensors` outside
   `fixtures/safetensors/`, and ignores every `checkpoints/` directory. The 28
   generated files under `fixtures/native-composition/` were therefore added
   with `git add -f`. Once tracked, they behave like any other file, and
   `--check` reports any missing or changed file. `.gitignore` is outside this
   preparation's file scope. Decide whether to add a path exception there, like
   the existing `!fixtures/safetensors/**/*.safetensors`, in a separately
   authorized change.
