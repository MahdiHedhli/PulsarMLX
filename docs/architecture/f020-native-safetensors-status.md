# F020 native Safetensors status — current pointer

**Last updated 2026-09-25. Slices 1, 2B and 2C are accepted and merged.
Slice 2B (native primitive qualification on synthetic fixtures) was merged into
`main` by merge commit `274da684a4b3081dde61c772d98c7814198b5752`; see
[Slice 2B](#slice-2b--native-primitives-merged). Slice 2C (synthetic
expert-plane composition) was merged by merge commit
`bd5b83bf0475b1341e209ba7c883e9f609fdd97a`; see
[Slice 2C](#slice-2c--synthetic-expert-plane-composition-merged).** This is a current-pointer document: it says what is qualified
today, what is not, and where to read the detail. It deliberately claims nothing
about a real checkpoint's payload.

## Current state (accepted)

F020 Slice 1 is merged. Native Safetensors catalog/admission and MLX affine
representation/decoder support are qualified on synthetic fixtures. F020 Slice 2B provides native MLX affine primitives, including packed-weight quantized matmul, qualified on frozen synthetic fixtures on the recorded GitHub runner.
Real checkpoint execution and production geometry remain unqualified.
F020 Slice 2C composes synthetic stacked-affine expert-plane selection with native packed-weight quantized matmul. It is qualified on its frozen small-fixture population on the recorded GitHub runner. Real checkpoint payloads, production geometry, full expert MLPs, model execution, streaming and performance remain outside that qualification.
Model execution and residency integration remain unimplemented.

* **Merged** into `main` by merge commit
  [`030d70810c5e01ed91870bb05b1ec05ff5dba079`](https://github.com/MahdiHedhli/PulsarMLX/commit/030d70810c5e01ed91870bb05b1ec05ff5dba079)
  of branch head
  [`faaec8ce794177f2d878ced12d1701093c665a7c`](https://github.com/MahdiHedhli/PulsarMLX/commit/faaec8ce794177f2d878ced12d1701093c665a7c).
  The merge commit's tree is identical to the branch head's tree. Development
  history is preserved un-squashed.
* **Final scope.** Two model-neutral library crates, `crates/safetensors-catalog`
  and `crates/mlx-affine`; the synthetic fixture corpus under
  [`fixtures/safetensors/`](../../fixtures/safetensors/README.md);
  [spec 020](../../specs/020-mlx-safetensors-affine/spec.md) and its two
  contracts; [ADR 0007](decisions/0007-safetensors-affine-format-scope.md); two
  required CI steps; and append-only evidence records. No other crate depends on
  either library crate. No model weights, no downloads, no checkpoint payload
  reads, no model execution, no residency or performance work.
* **Review.** An independent adversarial review accepted Slice 1 after four
  rounds (verdict `SLICE1_ACCEPTABLE`, recorded in the merge commit message).
  The round-by-round account is kept below under
  [Historical — review rounds](#historical--review-rounds); none of its numbers
  is current unless restated in this section.

### Final test results

All from CI run
[`35771542477`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/35771542477)
on the branch head `faaec8ce`, job `Apple MLX small-fixture validation`, GitHub
macOS runner reporting macOS 15.7.9 arm64. Each count belongs to its own suite
and is not added to any other.

| Suite | Command | Result |
|---|---|---|
| Rust, required step `Test MLX affine representation` | `cargo test -p mlx-affine -p safetensors-catalog --no-fail-fast` | 132 passed, 0 failed (ten test binaries; the two doc-test suites are empty) |
| Python CI tooling tests | `python3 -m unittest discover -s scripts/ci/tests -v` | 99 tests, `OK`. The F020 modules in it: `test_mlx_affine_compat_v1` 17, `test_mlx_affine_reference_v1` 14, `test_safetensors_fixtures_v1` 11 |
| R2 compatibility, required step `Qualify MLX affine compatibility (synthetic, pinned MLX wheel)` | `scripts/ci/mlx_affine_compat_v1.py` under `PULSAR_REQUIRE_NATIVE_MLX=1` | `PASS`, 17 quantized modules observed, 0 failures, maximum absolute difference 0.0; MLX 0.32.0, mlx-metal 0.32.0, `Device(gpu, 0)` selected explicitly |

The Rust count was also reproduced locally at `030d7081` (132 passed, 0 failed,
same command, on a local Apple Silicon host). That is a separate environment and
a separate observation, not a second half of one total.

## What Slice 1 qualified

Two model-neutral library crates, on synthetic fixtures, with no model weights, no
downloads and no model execution.

* **`crates/safetensors-catalog`** — Safetensors header and index parsing, a
  deterministic tensor catalog with a stable, length-framed sha256 digest,
  checked byte-range arithmetic with strict tiling of each data section,
  admission of every file by descriptor under an opened root, bounded `pread`
  reads, explicit shard hashing, and a header-only mode that builds the same
  catalog with no payload readable at all. Rules:
  [`specs/020-mlx-safetensors-affine/contracts/catalog-contract.md`](../../specs/020-mlx-safetensors-affine/contracts/catalog-contract.md).
* **`crates/mlx-affine`** — the MLX affine packed-weight representation:
  weight/scales/biases association, bit width and group size, global and
  per-module override resolution, fail-closed refusal of anything unsupported
  or ambiguous, checked slicing arithmetic for one expert or one row, the
  production decoder (R3) and the independent binary64 reference (R1). Rules:
  [`specs/020-mlx-safetensors-affine/spec.md`](../../specs/020-mlx-safetensors-affine/spec.md).

The decoder dequantizes. It does not multiply: no `quantized_matmul` or
`gather_qmm` path exists in either crate. Where a test needs a matrix product —
comparing against the frozen Flash research fixture's stored outputs — the test
computes it itself; the crate supplies only the dequantization.

## Synthetic numerical qualification versus R2 compatibility observation

These are two different kinds of result and are never merged into one claim.

| Arm | What it is | What it establishes | What it never establishes |
|---|---|---|---|
| **R1** | independent binary64 references, written from the format specification alone: `crates/mlx-affine/src/reference.rs` and `scripts/research/mlx_affine_reference_v1.py` | the correct interpretation of the format and of the affine quantization | performance; compatibility with any upstream build |
| **R2** | the pinned upstream Python/MLX wheel, driven by `scripts/ci/mlx_affine_compat_v1.py` | compatibility with the selected upstream execution | **correctness** — a defect shared by MLX and by a native path that calls MLX is invisible to it |
| **R3** | the native candidate, `crates/mlx-affine/src/decode.rs` | correct integration, when compared against R1 under the contract | anything by itself |

* **Synthetic numerical qualification** is R3 against the independent R1, on the
  committed synthetic fixtures, the committed golden case
  `golden-affine-dequant-v1`, seeded randomized rows, and the frozen research
  fixture `glm53-flash-decoder-quantized-v1` under that fixture's own
  tolerances. This is what "qualified" means in this document.
* **R2 compatibility** is an observation against one pinned Python/MLX wheel
  (MLX 0.32.0 on Metal). It records agreement or disagreement with that
  upstream build. It is not a correctness oracle and is never counted as one.

The Rust R1 has no `use` statements, names neither `crate::` nor `super::`,
shares no function name with the decoder, and admits bit widths the decoder
refuses so it can check a case the candidate declines.
`crates/mlx-affine/tests/independence.rs` reads both sources and asserts this.

## The contract and its results

[`contracts/numerics-v1.json`](../../specs/020-mlx-safetensors-affine/contracts/numerics-v1.json)
states the relations between R1, R2 and R3. Its checks, and the last per-check
record ([numerics results v2](reviews/evidence/f020-slice1-numerics-results-v2.json),
Round 2, head `7635158e`):

| Check | Kind | Last per-check record |
|---|---|---|
| `C-CODES` | exact invariant | PASS |
| `C-DEQUANT-HALF` — `R3 == round_to_f32(R1)` for BF16 and F16 metadata | exact invariant | PASS, bit for bit, within the qualified domain |
| `C-DEQUANT-SINGLE` — the two-rounding bound for F32 metadata | derived bound, **corrected after observation** (below) | PASS against the corrected exact form |
| `C-SHAPE` | exact invariant | PASS |
| `C-SLICE` | exact invariant | PASS |
| `C-DETERMINISM` | exact invariant | PASS |
| `C-R2-COMPAT` | compatibility observation | agreement |

The suites that assert these checks passed again at the accepted head in CI run
`35771542477`.

### The F32 decoder error bound was corrected after observation

`C-DEQUANT-SINGLE` first bounded the F32-metadata difference by one ulp of the
*result*. That is wrong under cancellation: the first rounding happens at the
magnitude of the product. It was found by observation — on the golden case
`experts`, R1 gives 8.94e-8, R3 gives exactly 0, and one ulp of the result is
7.1e-15 — and the bound was then replaced by one derived from the dtypes and the
rounding model. The replacement is a derivation, not a fitted multiplier, but it
was adopted **after** an R3 observation, and this document does not describe it
as prospective.

Where it is recorded, in the contract (linked, not restated):

* the `correction` block of check `C-DEQUANT-SINGLE`, which names the superseded
  form `|R3 - R1| <= 1 ulp_f32(R1)` and the observation that refuted it;
* appended correction **`R2-C1`** in `appended_corrections`, which gives the
  exact form of the bound, states the qualified numerical domain, and records
  under `prospective_timing` that the original timing claim cannot be verified
  from Git;
* appended correction **`R3-C2`**, which records that some contract text was
  edited in place despite an earlier statement that it had not been.

### Prospective timing could not be established from Git

The contract's `prospective_statement` says every bound was written before any
R3 or R2 number was produced. Git history does not establish that, and in one
respect it points the other way:

* `git log --follow` on `numerics-v1.json` shows exactly three commits:
  `8c0ec31c` (first appearance), `c7182dc0` and `f7519ab8`. No other ref in the
  repository contains the file.
* Its first committed version, in `8c0ec31c`, **already** contains the corrected
  F32 bound and the `correction` block quoting the `experts` observation. The
  superseded one-ulp-of-the-result form never appears in Git as live contract
  text, only as the quoted superseded statement.
* The decoder `crates/mlx-affine/src/decode.rs` (R3) was committed earlier, in
  `f818d701`. The Python R1, the Rust R1 and the contract first appear together
  in `8c0ec31c`.
* Every F020 evidence file under `docs/architecture/reviews/evidence/` was first
  committed later still (`ef306c5c` onward), so none of them can date the
  contract earlier.

So Git can establish neither that the original F32 bound was frozen before any
observation, nor when the other thresholds were fixed relative to the first R3
run. The contract records the same conclusion itself in `R2-C1`. What can be
checked is the content: each bound is written out as a derivation from the dtypes
and the rounding model.

### Acceptance criteria

`acceptance_criteria_slice_1` in the contract, as amended by `R2-C1`
(`A5`, `A6`, `A10`, `A11`) and `R3-C1`. The contract is the authority for their
text.

## What is not claimed

* **No real-checkpoint qualification.** No shard payload of any released
  checkpoint has been read or hashed by this work. The one real-checkpoint
  result is a header-only metadata *compatibility observation* over the
  retained headers of `pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit`, run by hand
  with the catalog's header-only mode, in which payload reads are refused; see
  [metadata compatibility v2](reviews/evidence/f020-slice1-metadata-compatibility-v2.json).
  It is not a qualification and not a CI gate.
* **No model execution.** Neither GLM-5.3 nor GLM-5.3-Flash was run natively,
  and neither `pipenetwork/GLM-5.3-MLX-mixed-4_8bit` nor
  `pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit` is native-qualified. No model
  graph consumes either crate.
* **No native quantized matmul.** `quantized_matmul` and `gather_qmm` have no
  contract and no native integration in this slice, and `gather_qmm`'s
  `sorted_indices` kernel-selection hazard is untouched.
* **No residency integration.** The slicing arithmetic gives a residency layer
  the provenance it will need; no residency layer uses it.
* **No performance claim.** Nothing here was timed and nothing should be.
* **No quality claim.** What a 4-bit or 8-bit checkpoint retains against the
  original BF16 or FP8 model is a separate evaluation track.

## Admitted quantization

Bits 4 and 8. Group sizes 32, 64 and 128. Mode `affine`. Everything else is
refused, including MLX's own 2, 3, 5 and 6 bits, which use a different
bit-serial layout across the 32-bit word; a decoder that admitted a layout it
does not implement would mis-decode silently. See
[ADR 0007](decisions/0007-safetensors-affine-format-scope.md).

## Fixtures

[`fixtures/safetensors/`](../../fixtures/safetensors/README.md), regenerated byte
for byte by `scripts/research/generate_safetensors_fixtures_v1.py`, plus
`golden-affine-dequant-v1` with its own provenance. At the accepted head,
`fixtures/safetensors/manifest.json` lists four positive checkpoints and 49
negative cases, 142 files totalling 214,309 bytes. Every negative case names
the error variant it expects on the first line of its README, and the tests
read that line. Current corpus evidence:
[fixture manifest v3](reviews/evidence/f020-slice1-fixture-manifest-v3.json).

## CI

Two required steps in `apple-mlx-small-fixtures`, added deliberately and made
mandatory by advancing the measurement-scope doctor's frozen resolution:
`Qualify MLX affine compatibility (synthetic, pinned MLX wheel)` and `Test MLX
affine representation`. The required-step census moved from 10 to 12. The
mechanism and both constants are recorded in
[`docs/research/f017/historical-measurement-current-ci.md`](../research/f017/historical-measurement-current-ci.md).

The compatibility step fails closed: an unusable MLX or an unavailable Metal
with `PULSAR_REQUIRE_NATIVE_MLX=1` is a failure, not a skip. The step asserts,
before and after it runs, that `PULSARMLX_MODEL_GGUF` is empty.

Evidence under `docs/architecture/reviews/evidence/` is **append-only**: an
added file may not later be edited, and a newer record is a new file that names
what it supersedes.

## Slice 2B — native primitives (merged)

Merged into `main` by merge commit
`274da684a4b3081dde61c772d98c7814198b5752` of branch head
`528e6cf9e7365fd8a9056f87e31e1be269346969` (qualified candidate `e6f502ff`).

**Scope.** Under the frozen contract
[`native-primitives-v1.json`](../../specs/020-mlx-safetensors-affine/contracts/native-primitives-v1.json)
(sha256 `76959ccb…`, plan `24a06db0…`, owner GO
[record](reviews/evidence/f020-slice2b-owner-go-v1.json)), the new crate
`crates/mlx-native-affine` qualifies five native MLX 0.31.2 operations through
MLX-C on small synthetic fixtures: exact packed-U32 import, exact F16/BF16/F32
metadata import, the bridge's own metadata widening (`mlx_astype` on the
explicit GPU stream), `mlx_dequantize`, and `mlx_quantized_matmul` with
`transpose=true`, float32 x and the imported U32 weight passed unchanged. Every
request outside D-GEOM, D-NUM or D-DQ is refused, in the contract's frozen
order, before any MLX-C call. All MLX work runs in one child process with a
fixed environment (`MLX_ENABLE_TF32=0`), an 1800 s watchdog and no retry.

**What passed.** The qualified candidate is `e6f502ff`: CI run
[`36006063937`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/36006063937),
attempt 3 ([record](reviews/evidence/f020-slice2b-ci-qualification-attempt-3-v1.json)),
after an implementation review asked that cleanup (teardown) MLX-C failures be
preserved and fail qualification and that error-path frees be counted
directly; both injected cleanup-error controls fail as required, and the
numbers below are unchanged. Attempt 2, CI run
[`35953592030`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/35953592030)
on candidate `844a8f63`, required step `Qualify F020 Slice 2B native primitives
(frozen synthetic population, runner GPU)`: all 363 frozen cases. Imports 8/8
byte-identical; the cast exact on every zero/normal F16 and BF16 pattern (2/2);
dequantize 18/18 exact codes and 59/59 inside N-DQ-BOUND under both the exact
and the binary64 R1 decision; quantized matmul 239/239 inside N-QMM-BOUND under
the binary64 decision and 237/237 under the exact one; N-QMM-ZERO; 37/37
refusals with exactly the expected id and zero MLX-C calls before the decision;
E1 on all 362 GPU records and E6 on the CPU negative control; both R1
self-checks (237 and 59 cases). Worst distance/bound: dequantize 0.988 (BF16),
0.970 (F32), 0.934 (F16); quantized matmul at most 0.127 (split-K). Evidence:
[CI qualification](reviews/evidence/f020-slice2b-ci-qualification-v1.json);
the first attempt on `acc94f40`
([record](reviews/evidence/f020-slice2b-ci-qualification-attempt-1-v1.json))
passed every numerical gate but failed its workflow post-check, which wrongly
expected an `applegpu_*` architecture string; that failure stays recorded.
The R2 cross-version observation (wheel 0.32.0, gates nothing) is
[recorded separately](reviews/evidence/f020-slice2b-r2-cross-version-observation-v1.json),
and so are the [labelled local runs](reviews/evidence/f020-slice2b-local-observations-v1.json).

**The gate host.** The GitHub runner's Metal device is a paravirtual device
(architecture `air64_v27`, parsed generation 2, not NAX-capable, no NAX kernels
in its metallib). Kernel families that depend on the architecture were covered
by the contract's union bound; the family that actually ran is derived, not
observed (no kernel-reporting API exists).

**CI.** The Slice 2B step is required (census 12 → 13), frozen through two
deliberate advances of the doctor's resolution (`99677210`, then `7f28bc5c`);
see [`historical-measurement-current-ci.md`](../research/f017/historical-measurement-current-ci.md).
The R2 step is not required and carries `continue-on-error`.

**Unresolved assumptions.** The bounds and invariants rest on assumptions that
this slice records but cannot verify from source: A-OPS (a)–(e), in particular
U19 (how Metal lowers the power-of-two divisions), U1 (FMA contraction), U2/U3/U16
(denormal and half/bfloat arithmetic semantics), U4/U5 (simd_sum and MMA
accumulation order), U9 (a GPU command-buffer fault is expected to terminate the
child, not be recovered), and U10/U14 (the R2 wheel's build provenance). If an
assumption fails, the derived bounds are void.

**Production-coverage limits.** Small-fixture qualification is not
production-geometry qualification: the largest fixture K is 4096, and no
production module shape is covered by evidence. Vocabulary projection and
embedding, the Flash `indexer.weights_proj` and every stacked rank-3 tensor are
outside v1 geometry and refused; expert and per-head plane extraction is future
work. Metadata admission is not numerical admission: whether real payloads fall
inside D-NUM or D-DQ needs payload reads, which are not authorized. No
transpose=false, half kernel types, NAX, CPU backend, gather_qmm, model graph,
residency or performance claim is made.

## Slice 2C — synthetic expert-plane composition (merged)

Merged into `main` by merge commit
`bd5b83bf0475b1341e209ba7c883e9f609fdd97a` of branch head
`472d98691951baa9ca2aec1f15cdbf25455d1f3f` (qualified candidate `4d39dc3e`).
The account below was written before the merge and is kept as it was, except
for the corrected evidence-control count.

Developed on branch `feat/020-synthetic-expert-plane-composition-20260924`.
Qualified candidate `4d39dc3e` (attempt 2,
CI run [`36053452198`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/36053452198),
[record](reviews/evidence/f020-slice2c-ci-qualification-attempt-2-v1.json)): the
independent implementation review of attempt 1 asked that S-SOURCE-UNCHANGED
require exact, unique and exhaustive shard evidence per phase (with rejection
controls) and that E6, the CPU-context negative control, run in the compose
child; both are implementation fixes under the frozen contract, and attempt 2
passes with them (E6 refused R-DEVICE; 388 source-evidence checks = 371 injected invalid-record rejections + 17 valid-record acceptances — the attempt-2 record's "388 rejected" label is inaccurate, see the [reporting erratum](reviews/evidence/f020-slice2c-attempt-2-reporting-erratum-v1.json)).
Attempt 1 (`110efa72`, below) stays on record.

**Scope.** Under the composition contract
[`native-composition-v1.json`](../../specs/020-mlx-safetensors-affine/contracts/native-composition-v1.json)
(draft.5, sha256 `e3fc848c…`, plan `b4e23bf4…`, frozen before any observation
in [this record](reviews/evidence/f020-slice2c-contract-acceptance-v1.json)),
ONE projection of ONE selected expert plane of a synthetic stacked affine
tensor goes through the Slice 1 catalog, module resolution and checked
selection into the unchanged Slice 2B bridge (`qualify --mode compose`). Two
combinations: 4-bit g64 BF16 (default) and 8-bit g64 BF16 (override), float32
x, `transpose=true`, vector and matrix x. Selection adds only exact checks; no
bound, domain or tolerance changed.

**What passed.** CI run
[`36043386953`](https://github.com/MahdiHedhli/PulsarMLX/actions/runs/36043386953)
([record](reviews/evidence/f020-slice2c-ci-qualification-v1.json)), required
step `Qualify F020 Slice 2C synthetic expert-plane composition (frozen
synthetic population, runner GPU)`: all 32 frozen cases. Selection identity,
ranges, bytes, staged inputs and unchanged sources on 17/17 planes, decided by
the parent from input evidence; A (composed) and B (standalone) outputs
bitwise equal on 14/14 executed cases, A-B-A equal; the inherited R1 gates on
A and on B (exact and binary64) and R1 self-check on 14/14; per-side counters
4/3/3/0/7 with 5 numerical calls; 9/9 composition refusals and 3/3 inherited
refusals with zero MLX-C calls before the decision; 6/6 mutation controls
detected by exactly their listed checks; the child is independent of R1 and
the decoder (static scan and `nm`, both controls). The Slice 2B invocation is
proven unchanged in the same job: base `12b06367` and candidate child reports
are equal as canonical JSON minus V1–V4, with identical gate counts and
test-name lists, and the candidate matches attempt 3 on all 363 cases.
[Labelled local runs](reviews/evidence/f020-slice2c-local-observations-v1.json)
are not acceptance evidence.

**CI.** The Slice 2C step is required (census 13 → 14), through doctor X
`6d76adc6` / Y `110efa72`; all 88 doctor mutation controls reject.

**Not claimed.** No real checkpoint payload, production geometry,
`gather_qmm`, routing, full MLP, model graph, residency or performance. A-DET
is supported by the recorded comparisons on the tested runner, build and
process only; it is not a universal determinism guarantee.

## Next

Slice 2B awaits implementation review and a separate merge GO; nothing beyond it
is authorized.

Slice 2C is qualified on its branch and awaits review and a separate merge GO.

Slice 2A, the header-only metadata census of both PipeNetwork targets (not Q0, not numerical qualification): [f020-slice2a-metadata-census.md](f020-slice2a-metadata-census.md).

## Historical — review rounds

Everything below records how Slice 1 got to the accepted state. Counts and
results here belong to the round and head named, and are **not** current; the
current results are in [Current state (accepted)](#current-state-accepted).

### Round 1 (reviewed at `e1d7c95d`)

Round 1's own record,
[numerics results v1](reviews/evidence/f020-slice1-numerics-results-v1.json)
(head `785ad53a`), reports 90 Rust and 34 Python tests passing. Its fixture
corpus had 33 negative cases. Its first CI observation,
[CI numerics results v1](reviews/evidence/f020-slice1-ci-numerics-results-v1.json)
(run `35739240691` on `2d63b46e`), saw the required compatibility step observe
13 quantized modules on macOS 15.7.9 with MLX 0.32.0 and mlx-metal 0.32.0 on
`Device(gpu, 0)`, with exact codes and bit-identical values after rounding.
Round 1 also recorded
[fixture manifest v1](reviews/evidence/f020-slice1-fixture-manifest-v1.json) and
[metadata compatibility v1](reviews/evidence/f020-slice1-metadata-compatibility-v1.json).

The CI observation is a separate file on purpose. The first attempt to record it
appended it to `f020-slice1-numerics-results-v1.json` instead, and
`scripts/ci/validate_evidence_change.py` correctly refused the push. That file
was restored to its as-added bytes and the CI observation lives in its own file.

### Round 2 (after the independent review of `e1d7c95d`)

The review returned `SLICE1_NEEDS_FOLLOWUP`. Ten findings, all closed. What
changed, and what it meant for the claims above.

| Finding | Change |
|---|---|
| 1 | Containment is decided about the object a descriptor holds. The root is opened once with `O_DIRECTORY\|O_NOFOLLOW`, every shard and the index are resolved with `openat` under it with `O_NOFOLLOW`, and the opened descriptor is bound to the name by `(device, inode)`. |
| 2 | Duplicate JSON members are refused at **any** depth, before anything becomes a map, in headers, the index and the configuration. |
| 3 | Unknown override members, overrides that match no module, a non-regular index, unchecked aggregate totals, caller-supplied read metadata, publicly mutable triples and unchecked reference indexing are all closed. |
| 4 | `hash_shards()` reads by explicit offset, so repeated calls agree; a shard that shrank is `PrematureEof`. |
| 5 | The **qualified numerical domain** is stated and enforced: a non-finite product or result is refused by both arms. A finite BF16 triple whose binary32 product overflows is now a refusal, not an infinity. |
| 6 | Real slicing-overflow coverage, and R1/R3 qualified against the frozen `glm53-flash-decoder-quantized-v1` under its own tolerances. |
| 7 | R2 compares codes as finite floats, compares bit patterns for bit identity, selects the GPU explicitly, and covers all three metadata dtypes and all three group sizes. |
| 8 | Census categorization is caller-supplied; the neutrality claim is narrowed to the library crates. |
| 9 | Strict upstream coverage, the initial `{`, a length-framed digest, and "admitted dtype set". |
| 10 | Round 1 evidence is untouched; Round 2 adds new files that name what they supersede. |

**Two Round 1 conclusions were wrong and are corrected in the open.** "All
acceptance criteria hold" overlooked the domain gap and the missing coverage;
both are recorded in
[the qualification correction](reviews/evidence/f020-slice1-qualification-correction-v1.json)
with what was claimed and why it overreached. And the contract's prospective
timing cannot be established from Git, so it is recorded as unproven rather
than repeated.

Round 2 counts, recorded in the qualification correction's Round 2 block: 123
Rust tests and 97 Python tests; R2 observed 17 quantized modules across seven
bit-width, group-size and metadata-dtype combinations.

Round 2 evidence: [fixture manifest v2](reviews/evidence/f020-slice1-fixture-manifest-v2.json),
[numerics v2](reviews/evidence/f020-slice1-numerics-results-v2.json),
[metadata compatibility v2](reviews/evidence/f020-slice1-metadata-compatibility-v2.json),
[Flash fixture qualification v1](reviews/evidence/f020-slice1-flash-fixture-qualification-v1.json).
The v1 files record Round 1 and are left exactly as they were added.

### Round 3 (after the review of `485d760f`)

Round 3 made the reference's domain check equal to the candidate's (contract
entry `R3-C1`), recorded the in-place contract edits (entry `R3-C2`), validated
complete tensor geometry in the affine constructor, compared the candidate's
weights with the Flash fixture's expectations, and added twelve fixture files:
three escaped-key negatives, the cross-shard duplicate and the reversed range.
Round 3 evidence:
[fixture manifest v3](reviews/evidence/f020-slice1-fixture-manifest-v3.json) and
[Flash fixture qualification v2](reviews/evidence/f020-slice1-flash-fixture-qualification-v2.json).

### Round 4 (after the review's third-round findings)

Round 4 restored files outside the slice scope that a Round 3 commit had
reformatted to their pre-Round-3 bytes, and made the digest-collision test
collide on the offsets the catalogs actually report. The fourth review round
accepted branch head `faaec8ce`, which was then merged as `030d7081`.
