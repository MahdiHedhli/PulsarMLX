# Feature 020, Slice 2B: native MLX primitive qualification (plan)

**Status: plan draft 7 (2026-09-23); contract draft.6.** This plan answers the
independent reviews below, all under the planner's decisions:

| Review | Answered in |
|---|---|
| `astra-f020-s2b-contract-20260923T184644Z-19626` | draft 3 |
| `astra-f020-s2b-contract-r2-20260923T192954Z-13486` (R2-1 to R2-5) | draft 4 |
| `astra-f020-s2b-contract-r3b-20260923T204009Z-31395` (R3-1, R3-2) | draft 5 |
| `astra-f020-s2b-contract-r5-20260923T212604Z-15423` (R5-1 to R5-3, plan wording only) | plan draft 7 |

Draft 5 was reviewed as `CONTRACT_READY_FOR_OWNER_GO`
(`astra-f020-s2b-contract-r4-20260923T211104Z-10633`).

**Draft 6 changes wording and reporting only, at the owner's request.** It
touches four things:

- the o_proj boundary wording;
- a statement that metadata admission is not numerical admission;
- how stacked expert planes are reported;
- a statement of the packed-weight path.

**It changes nothing normative.** No bound, domain value, refusal predicate,
acceptance rule or assumption changed. The generator, manifest and fixtures
are byte-identical.

Nothing in the plan is authorized until the owner gives the GO in §10.

Related files:

| Role | Path |
|---|---|
| Contract | `contracts/native-primitives-v1.json` (`1.0.0-draft.6`) |
| Pins and unknowns | `source-pins-slice2.json` |
| Frozen population | `scripts/research/f020_native_primitives_fixtures_v1.py` (generator) and `fixtures/native-primitives/` (manifest and 361 case files) |

This plan leaves the following untouched: `contracts/numerics-v1.json`,
`contracts/catalog-contract.md`, every `specs/017-*` file, the five frozen F017
files, and `crates/stream`.

Qualifying on small fixtures is **not** qualifying at production geometry.

## 1. What is qualified

### 1.1 Imports

- **Packed U32 import:** the weight is read back bit for bit.
- **Metadata import:** F16, BF16 and F32 values are read back bit for bit. For
  F16 and BF16 this is checked exhaustively over all 65536 bit patterns.

### 1.2 Bridge-side cast (OP-CAST)

The bridge widens F16 and BF16 scales and biases to float32 itself, using
`mlx_astype` on the explicit GPU stream. It does this for review F6: inside
`quantized_matmul`, MLX calls `astype(scales, dtype)` and `astype(biases, dtype)`
without a stream argument (ops.cpp:4509-4512). Those calls would resolve through
`default_stream(default_device())` (utils.cpp:15-17).

Once the bridge has cast, those internal `astype` calls are same-dtype no-ops.
They return their argument without creating a primitive (ops.cpp:258-261).

As a second safeguard, the child process does two things:

- it sets the default device to GPU at startup;
- it asserts that the default device is GPU before every operation.

N-CAST-WIDEN then qualifies the bridge's own cast.

### 1.3 `mlx_dequantize`

- Metadata may be F16, BF16 or F32. The output is in the metadata dtype.
- Accepted only inside domain **D-DQ**.
- Gated by the derived bound N-DQ-BOUND and the exact code checks. There is no
  exact-value invariant, because FMA contraction is unknown (U1).

### 1.4 `mlx_quantized_matmul`

- `transpose=true` only, which is y = x·Wᵀ with W in `[N, K·bits/32]`
  (Safetensors `[out, in]`).
- x must be float32.
- Accepted only inside domains **D-GEOM** and **D-NUM**.

**Packed-weight path.** Quantized matmul consumes the packed U32 weight tensor
directly, and the weight is **never expanded to an f32 tensor** on this path.

- **What the bridge passes.** The imported U32 array is passed to
  `mlx_quantized_matmul` unchanged, as argument `w`.
- **What is widened.** Only the scales and biases are widened to f32, by the
  exact bridge cast (§1.2). They hold 1/group_size of the weight's logical
  element count, so 1/64 for the target checkpoints.
- **MLX does not cast the weight either.** It builds the primitive's inputs as
  `{astype(x), w, astype(scales), astype(biases)}`, leaving `w` alone
  (MLX312 ops.cpp:4509-4512). The kernels decode codes transiently: in
  registers for the qmv family, and in 32-wide tiles in threadgroup memory for
  the matrix family (quantized.h:571-690).
- **Dequantize is separate.** It is its own qualified operation, not a
  preprocessing step of quantized matmul.

This matches the bridge design already stated:

- §1.2 casts only scales and biases;
- the contract's `operations.OP-QMM.mlx_c_call` passes `w` next to
  `scales_f32` and `biases_f32`;
- `operations.OP-CAST` applies only to metadata.

### 1.5 Production relevance

The census facts come from the planner. Both target checkpoints use only
bits {4,8} × group 64 × BF16 metadata. The frozen population therefore
includes group-64/BF16 cases for both bit widths, marked
`production_relevant`. Groups 32 and 128 are kept as well.

### 1.6 Deferred or out of scope

These are refused before MLX is called:

- `transpose=false`: qvm, qvm_split_k and qmm_n. Reasons: the 0.31.2
  split-K defect (fixed upstream in 241f1bf7) and U12.
- Half kernel types (U3, U16).

Also out of scope: NAX, the CPU backend, `gather_qmm`, and batched weights.

**None of the following is in this slice:** `gather_qmm`, streaming, padding,
an alternate kernel, or a model graph.

## 2. Admitted domains

Every guard below is a named bridge refusal. The bridge checks them in the
frozen order and before any MLX-C numerical call. This covers review findings
F1–F4.

### 2.1 D-GEOM

**Lower bounds (R2-2).**

- Every dimension of every tensor (x, w, scales, biases) must be ≥ 1. The
  refusal is **R-EMPTY-DIM**. It sits in the refusal order before R-META,
  R-XSHAPE and R-GEOMETRY, and so before any check that uses a dimension as a
  divisor.
- That gives M_eff ≥ 1, N ≥ 1 and K ≥ 1 for quantized matmul, and rows ≥ 1
  and K ≥ 1 for dequantize.
- N ≥ 1 together with N % 64 == 0 gives **N ≥ 64**.
- K ≥ group follows from R-META (packed·32 == groups·group·bits, with
  groups ≥ 1).
- This means MLX never reaches its upstream division `out.size()/M/N`
  (quantized.cpp:191, 249, 714) with a zero dimension.

**Upper bounds and alignment.**

- K ≤ 16384, N ≤ 16384, M_eff ≤ 4096.
- N % 64 == 0.
- K % group == 0.
- Weight rank is 2.
- x rank is 1–3.

**Why N % 64.** It removes the qmv_quad tail (review F5). That kernel launches
⌈N/64⌉ threadgroups (quantized.cpp:193-199), and it loads `sl[0]`/`bl[0]`
before its row test (quantized.h:729-738). With N % 64 == 0, every load is in
bounds. The hazard stays recorded as U18.

**γ validity.** Under D-GEOM, every γ exponent has n·u ≤ 1/8. The largest is
qmm_t at K+3 ≤ 16387, which gives n·u ≈ 9.8e-4.

**int32 safety.** The contract lists every int32 index expression on the
qualified paths and shows each is at most 2^28. For example, `packed_cols*32`
at ops.cpp:107 is at most 2^17.

**U17 (resolved).** The Slice 2A metadata census settled the target
checkpoints' K and N values. See "Production geometry vs the v1 domain" below.
Any module outside D-GEOM is refused.

### 2.2 D-NUM (quantized matmul)

Admitted inputs:

- finite (**R-NONFINITE**);
- no subnormal x, scale or bias (**R-SUBNORMAL**);
- every nonzero |x|, |s| and |b| in [2⁻³², 2³²] (**R-DOMAIN-X-RANGE**,
  **R-DOMAIN-META-RANGE**);
- for each row, Σ|x| ≤ 2⁴⁰ (**R-DOMAIN-ROWSUM**);
- for each group, |s|·255 + |b| ≤ 2³⁶ (**R-DOMAIN-WMAX**).

**Why these exponents.** Lemma L in the contract is a lattice argument: if all
operands lie on the lattice 2^-L with L ≤ 126, every intermediate is either
exactly zero or a normal number. Tracing the kernels' actual operation graph
under D-NUM:

| Path | Largest lattice exponent |
|---|---|
| qmv family (x/4096 prescale, then s·A) | 2⁻¹²² |
| matrix families (s/16, then x·w) | 2⁻¹¹⁴ |

Both are within the limit, so no intermediate underflows (answers F1). The
largest intermediate is ≤ 2⁷⁸, so none overflows either, and that includes the
unweighted Σx and Σx·q (answers F2).

**Lemma premise (R2-1).** Lemma L assumes each exact result lies within the
finite float32 range. The ≤ 2⁷⁸ envelope guarantees that, so round-to-nearest
cannot overflow.

**Prescaling (R2-1).** The divisions by powers of two are not covered by lemma
L. They rely on the new assumption A-OPS(e), described in §3.

The reviewer's counterexamples are frozen as single-guard refusal fixtures.

### 2.3 D-DQ (dequantize)

The same finite, no-subnormal and magnitude rules apply. Two per-element
checks are then computed exactly on the host:

- **R-DQ-RANGE:** |s|·q + |b| ≤ ½·max_T. This covers the contracted path; the
  reviewer's F3 example 144·229 + 32544 is refused.
- **R-DQ-NORMAL:** the exact values P+b and RN_T(P)+b are each either zero or
  ≥ λ_T.

## 3. Assumptions (review F7)

A-RN is replaced by A-OPS, which states five things separately:

- **(a)** A conversion whose result is representable returns it exactly,
  including the sign of zero.
- **(b)** Basic operations on normal or zero operands with a normal result are
  correctly rounded. For half types, the operation may instead round to f32 and
  then to T.
- **(c)** Exact-zero results follow the IEEE 754 sign rules.
- **(d)** Subnormal operands are refused, and subnormal results are excluded by
  the domains. Flush-to-zero behaviour (U2) therefore cannot affect a
  qualified result.
- **(e)** *(R2-1)* Dividing a normal f32 by an exact power of two returns the
  exact quotient whenever that quotient is normal. Under D-NUM it always is.
  - Call sites: `x/16.0f`, `x/256.0f` and `x/4096.0f` in `load_vector` and
    `load_vector_safe` (quantized.h:62-71, 142-151), and `scale/16` in the
    matrix dequantize helper (quantized.h:521-525).
  - This is an **assumption** about Metal arithmetic. Pinned lowering evidence
    was not obtained; this is recorded as **U19**.
  - No runtime probe is added, because it would be a numerical observation.

A-SIMD, A-MMA and A-NONAX are kept. The contract's derivation map shows which
assumption each exact invariant depends on:

| Invariant | Depends on |
|---|---|
| N-CAST-WIDEN | (a) |
| N-DQ-CODES | (a), (b), (c) |
| N-QMM-ZERO | (c) |

## 4. Bounds (prospective, T = float32)

u = 2⁻²⁴, γ_n = nu/(1−nu), and Φ = Σ(|s|q + |b|)|x|. No underflow term is
needed, because lemma L excludes underflow.

| Family | Bound |
|---|---|
| qmv_quad (K ∈ {64,128}) | γ_{K/4+5}·Φ |
| qmv_fast, 4-bit | γ_{K/16+17}·Φ |
| qmv_fast, 8-bit | γ_{K/8+9}·Φ |
| qmv, 4-bit | γ_{K/8+9}·Φ |
| qmv, 8-bit | γ_{K/4+5}·Φ |
| qmm_t | γ_{K+3}·Φ |
| qmm_t_splitk | γ_{Kp+sk+3}·Φ (includes the float32 reduction) |

**Kernel selection.** L is 6–32 depending on architecture. Which family runs:

- M_eff ≤ 5: the vector family.
- M_eff ≥ 32: the matrix family.
- 6 ≤ M_eff ≤ 31: either one, depending on architecture. The bound used is the
  larger of the two family bounds.

**Dequantize:**

|out − w| ≤ u*_T(1+u*_T)|P| + u*_T|w|

where u*_T = u for F32, and u_T + u + u_T·u for F16 and BF16.

**How acceptance is decided (R2-3).** The contract's `acceptance_implementation`
freezes exactly one algorithm for each gate and each reference kind, written out
in full with no "analogously".

- **G-QMM-EXACT:** pass iff |y3 − y*| ≤ (n/(2²⁴−n))·Φ, computed exactly in
  `Fraction`.
- **G-QMM-RUST:** pass iff d_hi ≤ B_lo. The quantities are:
  - Φ_lo and Φ_hi come from Φ̂ widened by γ64_{2K+4};
  - B_lo = g·Φ_lo, with M48 padding;
  - e_R1_hi = γ64_{K+1}·Φ_hi;
  - d_hi = |fl(y3 − y1)| + e_R1_hi, with P48 padding.
- **G-DQ-EXACT:** pass iff |out − w| ≤ u*(1+u*)|P| + u*|w|, computed exactly.
- **G-DQ-RUST:**
  - **R1 error.** s·q is exact in binary64, and one addition follows, so
    |ŵ − w| ≤ 2⁻⁵³|w|.
  - **Bound, lower estimate:**
    B_lo = [c1_lo·|P| + c2·|ŵ|·(1 − 2⁻⁵²)]·M48.
  - **Distance, upper estimate:**
    d_hi = [|fl(out − ŵ)|·P48 + |ŵ|·2⁻⁵²]·P48.
  - Pass iff d_hi ≤ B_lo for every element.
- **G-DQ-CODES:** 18 code and canary cases. They pass only on exact bit equality
  with the code. No R1-bound decision applies to them; this exception is
  explicit.

**Padding rule.** P48 = 1 + 2⁻⁴⁸ and M48 = 1 − 2⁻⁴⁸. Each padded expression
contains at most 8 binary64 round-to-nearest operations after the bounded
quantity, for a combined relative deviation below 2⁻⁴⁹·⁹. A single P48 or M48
factor dominates that deviation. Individual roundings go either way; the
conservatism comes only from this combined padding.

**When both references exist, both decisions must pass.**

**R1 self-checks (B5, R3-1).** Each op has its own predicate, and both are
decided by exact rational comparison:

- **Quantized matmul (237 dual-reference cases):** N-R1-SELF,
  |y_R1 − y*| ≤ γ64_{K+1}·Φ.
- **Dequantize (59 dual-reference cases):** N-R1-SELF-DQ,
  |ŵ_R1 − w_exact| ≤ 2⁻⁵³·|w_exact| for every element. It holds because s·q
  is exact in binary64 and is followed by a single addition. No padding is
  needed.

The 18 `codes_exact` cases are excluded from B5, because no R1-bound decision
applies to them.

**Coverage, matching the manifest exactly:**

| Reference | Cases |
|---|---|
| Rust binary64 R1 | 298 (239 quantized matmul + 59 dequantize) |
| Exact Python R1 | 296 (59 dequantize + 237 quantized matmul with M·N·K ≤ 2²¹), all of them also Rust |
| `codes_exact` only | 18 |
| `byte_identity` | 8 |
| `exact_host_widening` | 2 |

Since draft 3, R1's own error is added to the distance, not to the bound.

## 5. Correction policy (review F10)

1. A result that exceeds a bound is a FAIL, recorded against the original
   criteria, and kept permanently.
2. Any change to a bound, domain, refusal or assumption makes a new contract
   version. That version must be independently reviewed and authorized by the
   owner before qualification is run again.
3. No appended entry can turn a recorded failure into a pass.
4. Reports bind the sha256 values of the contract, the manifest and the
   generator.

## 6. New crate `crates/mlx-native-affine`

The new code lives here, not in the existing bridge. The existing bridge in
`crates/stream` is left untouched.

### 6.1 Layout

| Area | Plan |
|---|---|
| Build | Modelled on `crates/f017-native/build.rs`, with `src/abi_check.c` for layout assertions. |
| FFI | Hand-written FFI for the MLX-C surface in §6.2, with `#[repr(C)]` structs checked against the C side. |
| Error handler (review F8) | `mlx_set_error_handler` is called exactly once per process, through `std::sync::Once`, before any context is created. It passes null data and a null dtor, because MLX-C stores both in unsynchronized globals (error.cpp:17-34). The handler writes into a thread-local slot and returns. Contexts never reinstall it. Coexistence rule: no other component may install a handler in the child. A static test checks that the crate has a single call site and that no other linked crate calls it. |
| Empty-handle checks | Every constructor that returns a handle rather than a status is checked for an empty handle and for the error slot: `mlx_device_new_type`, `mlx_stream_new_device`, `mlx_array_new_data` and `mlx_device_info_new`. Accessors without a status (`dtype`, `ndim`, `size`, `shape`) are called only on handles already proven non-empty, and the error slot is checked after each. `data_*` and `shape` must return non-null. |
| Refusals | All ids R-* are checked in the frozen order. The public quantized matmul has no transpose parameter. |
| Ownership | `NativeContext` and `NativeArray<'ctx>`. Imports copy; each handle is freed exactly once; error paths free what they created; nothing is `Send` or `Sync`. |
| Evaluation (review F13) | An `Evaluated` typestate enforces eval, then synchronize, then host copy. MLX-C does **not** stop reads of unevaluated data (array.cpp:517-524, array.h:373-381), so the typestate is what enforces the order. |
| Kernel family | `family.rs` transcribes the 0.31.2 kernel-selection rules, used only to pick the bound. It records the effective geometry, L, split_k and the derived family. |

### 6.2 MLX-C surface

- `mlx_set_error_handler`
- `mlx_device_new_type`, `mlx_device_free`, `mlx_device_get_type`
- `mlx_get_default_device`, `mlx_set_default_device`
- `mlx_device_info_*`
- `mlx_metal_is_available`
- `mlx_stream_new_device`, `mlx_stream_free`, `mlx_stream_get_device`,
  `mlx_synchronize`
- `mlx_array_new`, `mlx_array_new_data`, `mlx_array_free`, `mlx_array_eval`
- the array accessors
- `mlx_astype`, `mlx_dequantize`, `mlx_quantized_matmul`
- `mlx_version`, and the peak-memory calls

## 7. R1 extension

- `crates/mlx-affine/src/reference_qmm.rs`: binary64, with no `use`
  statements and no reference to `decode`.
- `scripts/research/mlx_affine_qmm_reference_v1.py`: stdlib only, computes the
  exact rational result.
- Neither calls MLX or the production decode.

## 8. Child process, watchdog, R2, CI

### 8.1 The qualification child

The parent test launches the `qualify` child with a fixed environment:

- `MLX_ENABLE_TF32=0` is set;
- `MLX_METAL_GPU_ARCH`, `MLX_MAX_OPS_PER_BUFFER` and `MLX_MAX_MB_PER_BUFFER`
  are removed;
- `DYLD_LIBRARY_PATH` points only at the native prefix.

The child then runs these steps in order:

1. Assert the environment. On failure it refuses with R-NAX.
2. Install the error handler (the Once).
3. Set the default device to GPU.
4. Record provenance:
   - the paths of the loaded libmlx and libmlxc (found with `dladdr`) and
     their sha256;
   - the colocated metallib's sha256, and whether it contains `_nax_` names;
   - the architecture string and generation.
5. Run the E4 canary.
6. Run every manifest case.
7. Run the E4 canary again.
8. Write the report.

### 8.2 The parent

**Before running**, the parent checks the frozen population:

- the manifest's sha256 must match the value frozen in the contract;
- every case file's sha256 must match the manifest;
- the generator's `--check` must pass.

**After running**, the parent requires:

- the report's set of case ids equals the manifest's exactly;
- the report echoes the manifest, generator and contract hashes.

**Watchdog (review F12).** The timeout is frozen at `CHILD_TIMEOUT_SECONDS = 1800`.
When it expires, the parent sends SIGKILL, reaps the child with `waitpid`, and
records **TIMEOUT**. It does not retry.

**Failure conditions.** Each of these fails the run, and the parent reports it
with the signal, exit status or reason:

- the child dies from a signal;
- the child exits with a nonzero status;
- the timeout expires;
- the report is missing or can't be parsed;
- manifest validation fails;
- any case fails.

### 8.3 R2 (observation only)

`scripts/ci/mlx_native_primitives_compat_v1.py` runs on the same manifest.

- **Labels:** every record is marked `CROSS_VERSION_0.32.0_vs_0.31.2`.
  `different_kernel_family` applies when all of these hold: transpose,
  M_eff < L, K ∉ {64,128}, M_eff ≥ 2, and generation ≥ 15. The 0.32.0 quad
  branch is checked first (review F11).
- **Isolation:** it runs with `env -u DYLD_LIBRARY_PATH`.
- **Gating:** it gates nothing.

### 8.4 Hosts

- **Required gate host:** the GitHub macOS runner (`macos-15`). Its
  architecture is recorded.
- **Other hosts:** the Studio and the MacBook produce labelled observations
  only.

### 8.5 Workflow change

Adding the step as non-required changes nothing gated. Making it required uses
the two-commit X/Y pattern with `REQUIRED_EXTRA_STEP_NAMES` and a
`RESOLUTION_BASE` advance. The MLX-C patch hashes are verified at build time by
`install_native_mlx.sh:45`.

## 9. Fixture coverage (frozen, 363 cases)

| Family | Count |
|---|---|
| Imports | 8 |
| Cast (exhaustive F16/BF16 → f32) | 2 |
| Dequantize | 77 |
| Quantized matmul | 239 |
| Refusal probes | 37 |
| **Total** | **363** |

**Dequantize (77):**

- 54 grid cases (bits × group × dtype × 3 shapes);
- 18 unit-scale code and canary cases;
- 2 production cases (group 64, BF16, 64×4096);
- 3 edge-magnitude cases.

**Quantized matmul (239):**

- 13 shapes × 18 (bits, group, dtype) combinations, dropping the unsupported
  group-128/K=64 combination.
- The shapes cover qmv_quad K = 64 and 128, qmv, qmv_fast, M = 2 and 5, the
  ambiguous band M = 8, 16 and 31, matrix M = 32 and 33, rank-3 x (M_eff = 34),
  and rank-1 x.
- Plus 2 matrix cases without split-K (M = 512, N = 1024).
- Plus 6 production cases (group 64, BF16).
- Plus 3 edge cases:
  - x at 2⁻³² and 2³²;
  - metadata at the WMAX boundary;
  - a signed-zero row, and a row exactly at the row-sum boundary 2⁴⁰.

**Refusal probes (37).** There is at least one probe for every refusal id that
data can reach.

**Every probe violates exactly one evaluable guard, its expected id (R2-5).**
The generator enforces this on every run, including `--check`:

- **How it checks.** `guard_results` evaluates *all* guards, not just the first
  to fail. Value classes are disjoint:
  - a non-finite value is judged only by R-NONFINITE;
  - a subnormal value is judged only by R-SUBNORMAL;
  - the range, row-sum, envelope and element guards read only zero or normal
    values.
- **Guards it cannot evaluate.** A guard whose input is structurally invalid is
  recorded in the manifest as `not_evaluable_guards`. Examples: the metadata
  guards when R-META fails, and the x guards when x is not F32.
- **Admitted cases.** Every guard is evaluated and every guard is satisfied.
- **Contract wording (R3-2).** R-XSHAPE no longer includes a zero-dimension
  clause, since R-EMPTY-DIM owns zero dimensions. With that change, the
  contract's own predicates agree with the generator on all 37 probes (0
  mismatches). Each probe now violates exactly one contract guard, its expected
  id.

**Probes derived from the reviews:**

- The reviewer's F1 vector example (x = 2⁻¹²⁰ → R-DOMAIN-X-RANGE) and F1
  matrix example (s = 2⁻¹²⁶ → R-DOMAIN-META-RANGE).
- **F2.** The literal F2 values (x = 2¹²⁶) necessarily violate two guards, so
  they are split into two single-guard probes:
  - ref-astra-f2-rowsum-in-range: every |x| = 2³², Σ = 2⁴¹ → R-DOMAIN-ROWSUM;
  - ref-x-above-range: |x| = 2³³ → R-DOMAIN-X-RANGE.
- **F3:** the reviewer's example is refused by R-DQ-RANGE.
- **Qmv_quad tail:** N = 8.
- **R-EMPTY-DIM:** five probes:
  - the reviewer's exact R2-2 example (x [1,64] zero, w [0,8], scales and
    biases [0,1]);
  - M = 0;
  - K = 0;
  - dequantize with empty metadata rows;
  - dequantize with K = 0.

**R-NAX** is tested by the parent, not by a data fixture.

**Size and storage (decided 2026-09-23).** The population is 10.8 MB (10,844,998
bytes, including the manifest), of which
about 1.6 MB is zero-filled refusal probes that compress well in Git.

- **Committed:** all 361 `.bin` case files, together with the manifest and the
  generator. The frozen population therefore lives in Git. `.gitignore` does not
  exclude `*.bin` (it excludes only `*.bin.tmp`).
- **Checked in CI:** CI also runs
  `f020_native_primitives_fixtures_v1.py --out fixtures/native-primitives --check`.
  This check requires the regenerated bytes to equal the committed files
  exactly, and it fails on any missing or extra file.
- **Checked by the parent:** the parent test separately checks the committed
  manifest and case hashes against the contract.

## Production geometry vs the v1 domain

This is a data addendum dated 2026-09-23. It resolves U17 and changes no bound,
domain value or refusal. The machine-readable form is
`source-pins-slice2.json#production_geometry`.

**Source.** The Slice 2A metadata census of both target checkpoints (sanitized,
not yet committed):

| Census file | sha256 |
|---|---|
| `f020-slice2a-metadata-census-glm53-v1.json` | `b418e787…` |
| `f020-slice2a-metadata-census-glm53-flash-v1.json` | `712aaaa7…` |

**Configuration.** Both checkpoints default to 4 bits with group 64. Some
families carry explicit 8-bit overrides, also group 64. All metadata is BF16.

**How the table was computed.** For each quantized module family, the U32
weight shape is matched to its layer-index set. Then:

- N = `shape[-2]`;
- K = `shape[-1]·32/bits`, using the family's resolved bits;
- the leading dimensions are `shape[:-2]`.

Each value was checked exactly against the census's `in_features`,
`out_features` and `leading`, and against `scales` × group.

**Geometry tested.**

- quantized_matmul v1: rank-2 weight, K ≤ 16384, N ≤ 16384, N % 64 == 0, and
  K % 64 == 0.
- dequantize v1: rank-2 weight, K ≤ 16384, rows ≤ 16384, and K % group == 0.

**What IN and OUT mean.**

- **IN** means the shape would pass the v1 geometry refusals. It does **not**
  mean the shape is qualified. v1 qualifies the primitives on small fixtures,
  where the largest K is 4096. **None of these production shapes is covered by
  v1 evidence.**
- **The caps are inclusive: K ≤ 16384 and N ≤ 16384.** A shape exactly at a cap
  is marked `IN — boundary`.
- **OUT** shapes are refused by the bridge.

**Metadata admission is not numerical admission.** The census establishes
metadata compatibility only: bits, group size, dtypes and shapes. It does
**not** establish that real payload values (scales, biases, activations) fall
inside the numerical domain of the operation that would use them. The contract
keeps two separate numerical domains:

- **D-NUM (OP-QMM):** the [2⁻³², 2³²] magnitude ranges, the refusal of
  subnormals, the row-sum guard (Σ|x| ≤ 2⁴⁰) and the envelope guard
  (|s|·255 + |b| ≤ 2³⁶).
- **D-DQ (OP-DQ):** the dequantize element checks (R-DQ-RANGE, R-DQ-NORMAL)
  and the subnormal refusal for metadata.

Any later numerical admission of real payloads must establish the applicable
operation's domain; that requires payload reads, which are not authorized.

Whether real payloads fall inside D-NUM is a question for a later qualification.
Answering it needs payload reads, and those are not authorized.

| Checkpoint | Module family | Layers (count) | Bits | Weight shape (U32) | N | K | quantized_matmul v1 | dequantize v1 |
|---|---|---|---|---|---|---|---|---|
| glm53 | `lm_head` | - (1) | 8 | [154880, 1536] | 154880 | 6144 | OUT: N>16384 | OUT: rows>16384 |
| glm53 | `model.embed_tokens` | - (1) | 8 | [154880, 1536] | 154880 | 6144 | OUT: N>16384 | OUT: rows>16384 |
| glm53 | `layers.*.mlp.down_proj` | 0-2 (3) | 8 | [6144, 3072] | 6144 | 12288 | IN | IN |
| glm53 | `layers.*.mlp.gate_proj` | 0-2 (3) | 8 | [12288, 1536] | 12288 | 6144 | IN | IN |
| glm53 | `layers.*.mlp.shared_experts.down_proj` | 3-77 (75) | 8 | [6144, 512] | 6144 | 2048 | IN | IN |
| glm53 | `layers.*.mlp.shared_experts.gate_proj` | 3-77 (75) | 8 | [2048, 1536] | 2048 | 6144 | IN | IN |
| glm53 | `layers.*.mlp.shared_experts.up_proj` | 3-77 (75) | 8 | [2048, 1536] | 2048 | 6144 | IN | IN |
| glm53 | `layers.*.mlp.switch_mlp.down_proj` | 3-77 (75) | 4 | [256, 6144, 256] | 6144 | 2048 | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [6144, 2048] fits D-GEOM — see stacked-family table | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [6144, 2048] fits D-GEOM — see stacked-family table |
| glm53 | `layers.*.mlp.switch_mlp.gate_proj` | 3-77 (75) | 4 | [256, 2048, 768] | 2048 | 6144 | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [2048, 6144] fits D-GEOM — see stacked-family table | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [2048, 6144] fits D-GEOM — see stacked-family table |
| glm53 | `layers.*.mlp.switch_mlp.up_proj` | 3-77 (75) | 4 | [256, 2048, 768] | 2048 | 6144 | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [2048, 6144] fits D-GEOM — see stacked-family table | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [2048, 6144] fits D-GEOM — see stacked-family table |
| glm53 | `layers.*.mlp.up_proj` | 0-2 (3) | 8 | [12288, 1536] | 12288 | 6144 | IN | IN |
| glm53 | `layers.*.self_attn.embed_q` | 0-77 (78) | 8 | [64, 512, 48] | 512 | 192 | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [512, 192] fits D-GEOM — see stacked-family table | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [512, 192] fits D-GEOM — see stacked-family table |
| glm53 | `layers.*.self_attn.kv_a_proj_with_mqa` | 0-77 (78) | 8 | [576, 1536] | 576 | 6144 | IN | IN |
| glm53 | `layers.*.self_attn.o_proj` | 0-77 (78) | 8 | [6144, 4096] | 6144 | 16384 | IN — boundary (K = 16384, inclusive cap) | IN — boundary (K = 16384, inclusive cap) |
| glm53 | `layers.*.self_attn.q_a_proj` | 0-77 (78) | 8 | [2048, 1536] | 2048 | 6144 | IN | IN |
| glm53 | `layers.*.self_attn.q_b_proj` | 0-77 (78) | 8 | [16384, 512] | 16384 | 2048 | IN — boundary (N = 16384, inclusive cap) | IN — boundary (N = 16384, inclusive cap) |
| glm53 | `layers.*.self_attn.unembed_out` | 0-77 (78) | 8 | [64, 256, 128] | 256 | 512 | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [256, 512] fits D-GEOM — see stacked-family table | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [256, 512] fits D-GEOM — see stacked-family table |
| glm53-flash | `lm_head` | - (1) | 8 | [154880, 1024] | 154880 | 4096 | OUT: N>16384 | OUT: rows>16384 |
| glm53-flash | `model.embed_tokens` | - (1) | 8 | [154880, 1024] | 154880 | 4096 | OUT: N>16384 | OUT: rows>16384 |
| glm53-flash | `layers.*.mlp.down_proj` | 0-2 (3) | 8 | [4096, 3072] | 4096 | 12288 | IN | IN |
| glm53-flash | `layers.*.mlp.gate_proj` | 0-2 (3) | 8 | [12288, 1024] | 12288 | 4096 | IN | IN |
| glm53-flash | `layers.*.mlp.shared_experts.down_proj` | 3-44 (42) | 8 | [4096, 512] | 4096 | 2048 | IN | IN |
| glm53-flash | `layers.*.mlp.shared_experts.gate_proj` | 3-44 (42) | 8 | [2048, 1024] | 2048 | 4096 | IN | IN |
| glm53-flash | `layers.*.mlp.shared_experts.up_proj` | 3-44 (42) | 8 | [2048, 1024] | 2048 | 4096 | IN | IN |
| glm53-flash | `layers.*.mlp.switch_mlp.down_proj` | 3-44 (42) | 4 | [288, 4096, 256] | 4096 | 2048 | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [4096, 2048] fits D-GEOM — see stacked-family table | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [4096, 2048] fits D-GEOM — see stacked-family table |
| glm53-flash | `layers.*.mlp.switch_mlp.gate_proj` | 3-44 (42) | 4 | [288, 2048, 512] | 2048 | 4096 | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [2048, 4096] fits D-GEOM — see stacked-family table | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [2048, 4096] fits D-GEOM — see stacked-family table |
| glm53-flash | `layers.*.mlp.switch_mlp.up_proj` | 3-44 (42) | 4 | [288, 2048, 512] | 2048 | 4096 | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [2048, 4096] fits D-GEOM — see stacked-family table | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [2048, 4096] fits D-GEOM — see stacked-family table |
| glm53-flash | `layers.*.mlp.up_proj` | 0-2 (3) | 8 | [12288, 1024] | 12288 | 4096 | IN | IN |
| glm53-flash | `layers.*.self_attn.b_proj` | every layer not in 3,7,…,43 (34) | 8 | [64, 1024] | 64 | 4096 | IN | IN |
| glm53-flash | `layers.*.self_attn.embed_q` | 3,7,11,15,19,23,27,31,35,39,43 (11) | 8 | [64, 512, 64] | 512 | 256 | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [512, 256] fits D-GEOM — see stacked-family table | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [512, 256] fits D-GEOM — see stacked-family table |
| glm53-flash | `layers.*.self_attn.forget_gate.f_a_proj` | every layer not in 3,7,…,43 (34) | 8 | [128, 1024] | 128 | 4096 | IN | IN |
| glm53-flash | `layers.*.self_attn.forget_gate.f_b_proj` | every layer not in 3,7,…,43 (34) | 8 | [8192, 32] | 8192 | 128 | IN | IN |
| glm53-flash | `layers.*.self_attn.g_a_proj` | every layer not in 3,7,…,43 (34) | 8 | [128, 1024] | 128 | 4096 | IN | IN |
| glm53-flash | `layers.*.self_attn.g_b_proj` | every layer not in 3,7,…,43 (34) | 8 | [8192, 32] | 8192 | 128 | IN | IN |
| glm53-flash | `layers.*.self_attn.indexer.weights_proj` | 3,7,11,15,19,23,27,31,35,39,43 (11) | 8 | [32, 1024] | 32 | 4096 | OUT: N%64!=0 | IN |
| glm53-flash | `layers.*.self_attn.indexer.wk` | 3,7,11,15,19,23,27,31,35,39,43 (11) | 8 | [128, 1024] | 128 | 4096 | IN | IN |
| glm53-flash | `layers.*.self_attn.indexer.wq_b` | 3,7,11,15,19,23,27,31,35,39,43 (11) | 8 | [4096, 384] | 4096 | 1536 | IN | IN |
| glm53-flash | `layers.*.self_attn.k_proj` | every layer not in 3,7,…,43 (34) | 8 | [8192, 1024] | 8192 | 4096 | IN | IN |
| glm53-flash | `layers.*.self_attn.kv_a_proj_with_mqa` | 3,7,11,15,19,23,27,31,35,39,43 (11) | 8 | [512, 1024] | 512 | 4096 | IN | IN |
| glm53-flash | `layers.*.self_attn.o_proj` | 3,7,11,15,19,23,27,31,35,39,43 (11) | 8 | [4096, 4096] | 4096 | 16384 | IN — boundary (K = 16384, inclusive cap) | IN — boundary (K = 16384, inclusive cap) |
| glm53-flash | `layers.*.self_attn.o_proj` | every layer not in 3,7,…,43 (34) | 8 | [4096, 2048] | 4096 | 8192 | IN | IN |
| glm53-flash | `layers.*.self_attn.q_a_proj` | 3,7,11,15,19,23,27,31,35,39,43 (11) | 8 | [1536, 1024] | 1536 | 4096 | IN | IN |
| glm53-flash | `layers.*.self_attn.q_b_proj` | 3,7,11,15,19,23,27,31,35,39,43 (11) | 8 | [16384, 384] | 16384 | 1536 | IN — boundary (N = 16384, inclusive cap) | IN — boundary (N = 16384, inclusive cap) |
| glm53-flash | `layers.*.self_attn.q_proj` | every layer not in 3,7,…,43 (34) | 8 | [8192, 1024] | 8192 | 4096 | IN | IN |
| glm53-flash | `layers.*.self_attn.unembed_out` | 3,7,11,15,19,23,27,31,35,39,43 (11) | 8 | [64, 256, 128] | 256 | 512 | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [256, 512] fits D-GEOM — see stacked-family table | (a) OUT: whole stacked tensor (R-WDTYPE) · (b) plane [256, 512] fits D-GEOM — see stacked-family table |
| glm53-flash | `layers.*.self_attn.v_proj` | every layer not in 3,7,…,43 (34) | 8 | [8192, 1024] | 8192 | 4096 | IN | IN |

**Stacked families.** Each stacked family has two distinct execution questions:

- **(a)** direct execution of the whole stacked rank-3 tensor;
- **(b)** execution of one individually selected rank-2 plane: an expert plane
  for `switch_mlp`, or a per-head plane for `embed_q` and `unembed_out`.

The plane's logical shape is [N, K], with N = `shape[-2]` and
K = `shape[-1]·32/bits`.

Every plane fits D-GEOM. Even so, **extracting a plane and qualifying its
execution are future work, not part of this slice.**

| Checkpoint | Stacked family | Layers (count) | Bits | Stacked weight shape (U32) | Leading dim | (a) direct execution of the whole stacked rank-3 tensor | (b) one selected rank-2 plane: logical [N, K] | (b) plane vs D-GEOM (N ≤ 16384, K ≤ 16384, N % 64, K % 64) | Plane extraction + execution qualification |
|---|---|---|---|---|---|---|---|---|---|
| glm53 | `layers.*.mlp.switch_mlp.down_proj` | 3-77 (75) | 4 | [256, 6144, 256] | 256 (experts) | OUT — R-WDTYPE; gather/stacked dispatch deferred | [6144, 2048] (expert plane) | fits (N % 64 = 0, K % 64 = 0) | future work (not in this slice) |
| glm53 | `layers.*.mlp.switch_mlp.gate_proj` | 3-77 (75) | 4 | [256, 2048, 768] | 256 (experts) | OUT — R-WDTYPE; gather/stacked dispatch deferred | [2048, 6144] (expert plane) | fits (N % 64 = 0, K % 64 = 0) | future work (not in this slice) |
| glm53 | `layers.*.mlp.switch_mlp.up_proj` | 3-77 (75) | 4 | [256, 2048, 768] | 256 (experts) | OUT — R-WDTYPE; gather/stacked dispatch deferred | [2048, 6144] (expert plane) | fits (N % 64 = 0, K % 64 = 0) | future work (not in this slice) |
| glm53 | `layers.*.self_attn.embed_q` | 0-77 (78) | 8 | [64, 512, 48] | 64 (heads) | OUT — R-WDTYPE; gather/stacked dispatch deferred | [512, 192] (per-head plane) | fits (N % 64 = 0, K % 64 = 0) | future work (not in this slice) |
| glm53 | `layers.*.self_attn.unembed_out` | 0-77 (78) | 8 | [64, 256, 128] | 64 (heads) | OUT — R-WDTYPE; gather/stacked dispatch deferred | [256, 512] (per-head plane) | fits (N % 64 = 0, K % 64 = 0) | future work (not in this slice) |
| glm53-flash | `layers.*.mlp.switch_mlp.down_proj` | 3-44 (42) | 4 | [288, 4096, 256] | 288 (experts) | OUT — R-WDTYPE; gather/stacked dispatch deferred | [4096, 2048] (expert plane) | fits (N % 64 = 0, K % 64 = 0) | future work (not in this slice) |
| glm53-flash | `layers.*.mlp.switch_mlp.gate_proj` | 3-44 (42) | 4 | [288, 2048, 512] | 288 (experts) | OUT — R-WDTYPE; gather/stacked dispatch deferred | [2048, 4096] (expert plane) | fits (N % 64 = 0, K % 64 = 0) | future work (not in this slice) |
| glm53-flash | `layers.*.mlp.switch_mlp.up_proj` | 3-44 (42) | 4 | [288, 2048, 512] | 288 (experts) | OUT — R-WDTYPE; gather/stacked dispatch deferred | [2048, 4096] (expert plane) | fits (N % 64 = 0, K % 64 = 0) | future work (not in this slice) |
| glm53-flash | `layers.*.self_attn.embed_q` | 3,7,11,15,19,23,27,31,35,39,43 (11) | 8 | [64, 512, 64] | 64 (heads) | OUT — R-WDTYPE; gather/stacked dispatch deferred | [512, 256] (per-head plane) | fits (N % 64 = 0, K % 64 = 0) | future work (not in this slice) |
| glm53-flash | `layers.*.self_attn.unembed_out` | 3,7,11,15,19,23,27,31,35,39,43 (11) | 8 | [64, 256, 128] | 64 (heads) | OUT — R-WDTYPE; gather/stacked dispatch deferred | [256, 512] (per-head plane) | fits (N % 64 = 0, K % 64 = 0) | future work (not in this slice) |

**Summary (R2-4, recomputed from the JSON).** There are 46 (checkpoint, family)
entries in all:

- **quantized_matmul:** 31 are IN v1 geometry and 15 are OUT.
- **dequantize:** 32 are IN and 14 are OUT.

These counts treat each stacked family as a whole tensor.

The OUT entries are:

- **N > 16384:** `lm_head` and `embed_tokens`, both with N = 154880, in both
  checkpoints. `embed_tokens` is an embedding table, not a matmul operand.
- **N % 64 ≠ 0:** the Flash `indexer.weights_proj`, with N = 32. Dequantize
  geometry does not require N % 64, so it passes there.
- **Stacked rank-3 tensors:** ten entries —
  - the MoE `switch_mlp` gate, up and down weights (256 or 288 experts);
  - `embed_q` and `unembed_out` (64 heads);
  - in both checkpoints.

  Executed whole, `R-WDTYPE` refuses them, and stacked or gather dispatch is
  deferred. Each rank-2 plane fits D-GEOM (see the stacked-family table), but
  plane extraction and qualification are future work.

**Shapes exactly at the inclusive caps.**

- GLM-5.3 `self_attn.o_proj`: bits 8, packed [6144, 4096], scales [6144, 256].
  Its logical shape is [6144, 16384], so **K = 16384 exactly**.
- Flash `self_attn.o_proj` in layers 3,7,…,43: logical shape [4096, 16384].
  Its other layers have K = 8192.
- `q_b_proj` in both checkpoints: N = 16384 exactly.

These boundary shapes (GLM-5.3 `o_proj`, Flash `o_proj` in layers 3,7,…,43, and
`q_b_proj` in both checkpoints) are `IN — boundary`. The remaining Flash
`o_proj` layers (K = 8192) are plain `IN`.

**Correction note.** An earlier planner expectation said some `o_proj` might
exceed K = 16384 (at 4 bits). That was a reporting error. The census shows
every `o_proj` is 8-bit. GLM-5.3 `o_proj` and Flash `o_proj` in layers
3,7,…,43 reach K = 16384 exactly, at the inclusive cap; the other 34 Flash
`o_proj` layers have K = 8192 (packed [4096, 2048] at 8 bits). No bound,
domain value or refusal was changed to reconcile it.

## 10. Owner GO items

1. Freeze contract draft.6 (normatively identical to draft 5), including:
   - domains D-GEOM (with its lower bounds), D-NUM and D-DQ, and the refusal
     order (with R-EMPTY-DIM);
   - assumptions A-OPS(a)–(e) (with (e) resting on U19), A-SIMD, A-MMA and
     A-NONAX;
   - the union-bound rule for the ambiguous band;
   - the acceptance implementation;
   - the correction policy.
2. Freeze the fixture population: the generator's sha256 `28078a6d…`, the
   manifest's sha256 `472b5b64…`, the cases listing's sha256 `ed0c2e73…`, and
   363 cases. As decided, the 361 `.bin` files are committed, and CI also runs
   the generator with `--check`.
3. Authorize the new crate `crates/mlx-native-affine`, including its child
   binary, with the resulting changes to the root `Cargo.toml` and
   `Cargo.lock`.
4. Authorize the R1 additions.
5. Authorize the R2 script.
6. Decide whether the new CI step is required. If it is, authorize the X/Y
   change.
7. Acknowledge the production-geometry gap, which comes from the census (U17
   is resolved):
   - v1 covers no production shape;
   - the vocabulary projection, the embedding, the Flash `indexer.weights_proj`
     and every stacked MoE/attention family fall outside v1 geometry
     altogether.
