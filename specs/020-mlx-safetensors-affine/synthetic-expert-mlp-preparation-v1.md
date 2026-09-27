# Complete synthetic expert MLP — preparation v1

Date: 2026-09-25. **BLOCKED-NONLINEAR-SOURCE-AND-ERROR-CONTRACT**.
Prospective design only; not a frozen contract, fixture package, review verdict,
or implementation authorization. No candidate numerical computation occurred.

## Verified baseline and scope

Successful local inspection found a clean `feat/020-synthetic-expert-mlp-20260925`
at `e91a36b7b997a672834d08b6bfb5e6f88c05a337`. The project-specific owner GO
and account approval were read. This work has one primary implementation owner;
no worker or reviewer was launched. No authentication material was accessed.

Read `CONTRIBUTING.md`, `.specify/memory/constitution.md`, the F020 specification,
Slice 2C plan, inherited contracts and source records. No applicable AGENTS.md
was found. Preserve accepted Slice 1/2B/2C implementations and evidence. This
additive preparation does not invoke the plan setup script, which would risk
replacing existing feature artifacts. No runtime or dependency changes.

## Precise stop and review boundary

The retained Flash caller specifies `nn.silu`, but the inspected repository has
no tracked native `activations.py`, `unary.h`, `unary_ops.h`, or sigmoid source
snapshot. The inherited `source-pins-slice2.json` contains no SiLU/sigmoid
nonlinear error contract. Its native revision pin alone does not establish the
operation graph, lowering, exponential accuracy, general division accuracy,
fusion, or underflow behavior of a new native activation. The old tiny MLP
oracle uses `math.exp` without a certified error bound.

These are essential prerequisites, not permission to invent an exp ULP bound
or extend A-OPS(e) from power-of-two division to sigmoid division. Stop here.
No generator is authored or fixture bytes frozen because numerical admission
and nonlinear acceptance rules cannot yet be completed. No inherited contract
change is proposed or made. The remainder records useful prospective design,
not a claim that these prerequisites are resolved.

To unblock: supply/review immutable native MLX 0.31.2 activation, sigmoid/exp,
division, compilation/fusion source evidence and its justified error model.
Then finish the additive contract, deterministic generator, independently
checked fixture manifest and hashes. Independent read-only review must accept
that exact package within the GO before any candidate observation or runtime
change. Acceptance of this blocker report alone cannot open that gate. No
additional broad project/account GO is requested. An inherited rule change,
if needed, remains a separate stop requiring explicit authorization.

## Source-derived semantics and pins

All following repository paths are bound to the baseline commit above; hashes
are SHA-256 of the inspected committed files, not model payloads.

| Source | SHA-256 |
|---|---|
| `scripts/research/glm53_flash/recurrent_dispatch/upstream-language.txt` | `6de479b6eafc0731e5e965f01f28797a58eecb606e7d5d5657db13642c230196` |
| `scripts/research/glm53_flash/decoder_moe/upstream-switch-layers.txt` | `914b40c985d96ffc8e3025ea6e3bef1fafcd588fa4dd99cf27d5e5f09c26ab35` |
| `scripts/research/glm53_flash/decoder_topology/upstream-config.json` | `3ed164a8f60c96dc81d5742b952b7823335fa7656fe0bbcf69c7ea05a4179d1d` |
| `specs/020-mlx-safetensors-affine/contracts/native-primitives-v1.json` | `76959ccb13046c664db67469fd8186b7fb668910072060400b38b682e92fec72` |
| `specs/020-mlx-safetensors-affine/contracts/native-composition-v1.json` | `e3fc848cea14222e0ed9f1c3c9c3c52faa044ed024d665d8767f7148e0e15c93` |
| `specs/020-mlx-safetensors-affine/source-pins-slice2.json` | `02e963a02cf1d63168c57cff316c1d3471313498396b2abd7b3e5ec432267bb4` |
| `crates/mlx-native-affine/src/compose.rs` | `3550ec6ad6d6b370b074e80c4777c8728c9219ab9170892b7d5d6c04ba2d4ce0` |
| `crates/mlx-native-affine/src/bin/qualify/bridge.rs` | `94cefa71f63db727529831ecbf0bf0663dfc584fa58735c3c7e92a55628b3827` |
| `scripts/research/mlx_affine_qmm_reference_v1.py` | `b9ef145e2bdce533aa733b70866d39364e2e61ee4642746b650e705f8a40ef15` |
| `crates/mlx-affine/src/reference_qmm.rs` | `6a5c8e82f224c79e33f418fdba83a76846df015d62eab8eb7f09258860150fa8` |
| `scripts/research/glm53_flash/decoder_moe/oracle.py` | `838bf9dbe36b4fb22101d5b5e01c0064764e10583737e67a888261bae3057e5e` |

Flash `upstream-language.txt:24-52` defines activation **(up, gate)**:
`gc = min(gate, 10)`, `uc = clip(up, -10, 10)`,
`h = silu(gc) * uc`, then `down(h)`. Gate has no lower clamp.
The config snapshot at lines 253 and 278 records limit 10.0. Caller provenance
in `recurrent_dispatch/provenance.json` binds the language snapshot to
PipeNetwork/glm53-flash-mlx `a61a7c7d2fbdf3d218a9909365a24bd794f3a247`,
`glm53_flash_mlx/glm5_next/language.py`.

Switch snapshot lines 281-298 binds all three projections to the same expert
and applies projection-specific recipes; lines 207-213 warn that an inline
activation replacement previously diverged. This is semantic evidence, not
authorization to execute its routing/offload code or claim compiled parity.

Native QMM remains MLX `68cf2fddd8de5edd8ab3d926391772b2e2cedad8` and MLX-C
`0726ca922fc902c4c61ef9c27d94132be418e945` with the four unchanged patch pins
in the inherited source record. `bridge.rs:185-217` admits before importing,
imports U32 weights unchanged, widens only metadata to F32 and calls QMM with
transpose=true. Inherited MLX `ops.cpp:4509-4512` preserves packed `w`;
`quantized.h:571-690` describes transient decoded tiles, not full dense weights.
These upstream locations are inherited source evidence, not freshly fetched
or requalified native source. `compose.rs:17-34` seals one plane/index and
stages exact bytes. Preserve copy-on-import; no zero-copy claim.

## Proposed numerical contract (incomplete, not executable acceptance)

One independently declared expert index `expert_id` selects gate/up `[H,D]`
and down `[D,H]` from three stacks with the same E. A manifest must bind each
projection's module, recipe, shape, ranges, independent logical codes/metadata,
standalone bytes and hashes before selection. Cross-projection identity is a
new assertion: three separately valid SelectedPlanes are not sufficient.

| Stage | Domain, dtype and rounding obligation |
|---|---|
| Load/select/stage | Slice 1/2C guards unchanged; exact U32 packed bytes; BF16 metadata copied then widened exactly to F32; affine bias is quantization metadata, not an added MLP bias. |
| Gate and up | F32 x `[M,D]`, transpose=true; full inherited D-GEOM and D-NUM; F32 outputs `[M,H]`; inherited family/reduction/FMA assumptions and family-specific `gamma_n * Phi` unchanged. |
| Clamp | Finite F32 gate/up; propose new activation admission `-16 <= gate <= 16`, `-16 <= up <= 16`, checked before nonlinear execution. Constants +/-10 exactly representable; min/clip select represented values. This is a new activation-only restriction, not a changed QMM domain. |
| SiLU/product | Target real `silu(gc)=gc/(1+exp(-gc))`, then multiply by uc. Proposed F32 intermediates/output; exact native operation order, materialization/fusion and nonlinear error `E_act` remain BLOCKED. Do not substitute a stable algebraic form on the candidate path without source review. |
| Down admission | Check actual h bytes, F32 `[M,H]`, through all unchanged Slice 2B predicates before down imports/QMM. Reject NaN/Inf, subnormals, nonzero magnitudes outside `[2^-32,2^32]`, row absolute sum above `2^40`, and all metadata/geometry violations. No clipping, rescaling, rounding-to-zero rescue or reclassification as success. |
| Down result | F32 `[M,D]`; local inherited QMM bound on the actual admitted h, plus a distinct end-to-end bound against the independent expert. |

The ideal clamp implies `|silu(gc)| <= 10`, hence `|h*| <= 100` and for
H<=128 the ideal row sum is <=12800. This explains the comfortable upper
margin, but proves neither the computed upper bound nor the nonzero lower
bound. Cancellation in gate/up can make normal outputs smaller than 2^-32;
SiLU/product can shrink further. Even admitted gate/up inputs do not ensure
down admission. Full inherited metadata guards include nonzero `[2^-32,2^32]`,
no subnormals and `255*|scale|+|bias| <= 2^36` for either bit width.

For independent exact gate/up results G*, U*, use inherited local budgets
Bg, Bu. Clamp is 1-Lipschitz and a conservative global `|silu'|<=2` gives
componentwise `Bh = 20*Bg + 10*Bu + E_act`. `E_act` must bound the local
native activation error on its actual inputs, including every rounding,
approximation and any underflow; no numeric value is asserted here.
With exact independently decoded Wd and actual admitted candidate h3:

`By = Bqmm_down(h3) + sum_hidden abs(Wd) * Bh`.

This counts local down rounding once; it does not replace h* with h3 in the
end-to-end reference. Independently check local gate, up and down QMM gates,
clamped operands, SiLU, product, and final end-to-end result. Acceptance must
place reference uncertainty on the distance side: `distance + E_R1 <= B`,
using exact rationals or outward intervals (never an enlarged tolerance).
Reference diagnostic values derived from candidate inputs may support local
gates only, never define the independent expert or end-to-end target.

## Independent R1 design and nonlinear reference qualification

Reuse the unchanged independent binary64 Rust QMM reference and separately
written exact Python integer/Fraction QMM reader. R1 must not call production
decoding, candidate kernels, or candidate selection. Standalone expected
planes come from independently specified logical expert data, with a separate
header/packing reader verifying written bytes. Retain static and symbol-level
independence controls. R2 (MLX wheel 0.32.0) is compatibility only.

Proposed nonlinear extension: exact rational interval arithmetic, not a claim
that binary64 math.exp is exact. For a rational argument with absolute value
<=16, set a=abs(argument)/32 <=1/2. Enclose exp(a) using the degree-64 Taylor
sum and tail bound `(a^65/65!)/(1-a/66)`. Every operation is rational and the
tail is bounded by a geometric series of successive term ratios. Square the
positive interval five times; take reciprocal endpoints for negative arguments.
Then interval-evaluate sigmoid, SiLU and product. For exact G*, U* this gives
an independent enclosure of h*; multiplication by exact Wd and interval sums
gives y*. For rounded native gate/up it supplies a separate local reference.

Proposed reference admission: every h* interval width <=2^-160; fail closed
if not met (no observed-candidate-based precision or tolerance adjustment).
Down reference width must be propagated as `sum abs(Wd)*width(h*)`, not
discarded. Use rational midpoint with half-width error, or maximum distance
to either endpoint. No reference arithmetic was run this turn. A separately
implemented binary64 nonlinear reference can be checked against those
enclosures, but needs its own proved accumulated rounding/exp-error budget
before becoming a gating R1. The old `decoder_moe/oracle.py:15-40` is useful
semantic guidance only, not such a proof. The new interval implementation,
tail proof, sign/zero handling and self-check mutations require review/tests.

## Proposed small fixture population and generator rules

Propose 48 intended-positive composed cases: Cartesian product
`(D,H) in {(64,64),(64,128),(128,64),(128,128)}` x `M in {1,32}` x
`expert_id in {0,1,2}` x two recipe profiles, with E=3, group=64, BF16 metadata.
Profiles: all projections 4-bit default; and gate/down 8-bit explicit overrides
with up 4-bit default. All dimensions satisfy inherited small geometry;
M avoids the architecture-ambiguous band; rectangular shapes detect transpose
and down-shape errors. Largest per-projection exact work is 32*128*128,
below inherited exact-reference work cap 2^21.

Generate from integer formulas with no RNG, native import, candidate output,
or model data. Independently specify logical codes, exact BF16 bit patterns,
expert and projection markers; pack U32 separately. Every component must
distinguish experts and projections (including when shapes coincide). Bind
the three roles to one expert tuple. Use both single-shard and split-companion
layouts without duplicating historical parser populations.

Within intended-positive cases, reserve channels/rows for exact zero,
positive/negative nonsaturated activation, gate below -10 (not clamped), upper
gate clamp and both up clamps, cancellation, mixed signs, and below/at/above
clamp neighborhoods. Derive these by exact logical projections, not by tuning
observed outputs. Exact clamp-neighbor scalar probes may supplement composed
cases if BF16 projection recipes cannot realize immediate F32 neighbors;
do not label them end-to-end coverage. Required nonlinear budgets must prove
all possible accepted outputs stay in the down domain, or classify the case
prospectively as refusal/uncertain before generating the final manifest.

Propose six additional refusal cases: initial x outside range; selected metadata
outside range; gate below new activation floor; up above new activation cap;
activation product normal but below 2^-32; cross-expert tuple mismatch. The
small-product case needs an interval proof of nonzero and strict threshold
separation, including native error. Each refusal must violate exactly one
evaluable guard, preserve other predicates, and record stage-local zero-call
counters (down refusal does not erase earlier gate/up calls).

Propose ten mutation controls: activation argument swap, gate/up projection
swap, down expert swap, illicit lower gate clamp, missing upper gate clamp,
missing lower up clamp, missing upper up clamp, ignored quantization override,
skipped down admission, and end-to-end reference replaced by actual h3.
Expected detection sets must be established prospectively; a surviving mutant
blocks package acceptance, not justify tolerance tuning. Proposed total: 64
case IDs, not generated/frozen/qualified. Final exact file count, byte-size cap,
formula coefficients, admission margins and hashes await prerequisite closure.

Generator acceptance must include independent header/range/packing checks,
exact case-ID counts, byte-identical regeneration, guard-evaluability tables,
all expected distinctions and full reference error certificates. Until these
are specified and checked, do not claim deterministic fixture acceptance.

## Subsequent bounded sequence (not launched)

1. Resolve nonlinear source/error prerequisite and review the additive package.
2. Freeze reviewed contract, generator, manifests, listing and source hashes
   before candidate computation; retain original failures under original bounds.
3. Implement same-expert composition using accepted selection/staging/QMM;
   full candidate weights stay packed. Preserve child failures, CPU refusal,
   cleanup and source-byte evidence; report additional activation copies/handles
   separately rather than changing the old Slice 2C census.
4. Retain all 363 primitive and 32 composition regression cases, including
   required base/candidate differential and failure/mutation coverage.
5. Studio-only local heavy work; required GitHub runner acceptance remains
   mandatory. Required CI integration uses established doctor X/Y procedure;
   preserve failed attempts and append-only mixed-range integrity evidence.
6. Independent final implementation review of pinned candidate/report; stop.

No real payload/header/rehash/download, production geometry, routing, top-k,
aggregation, full graph, residency, streaming, benchmark or serving work.
No pushes, merges, global configuration changes or unrelated cleanup.
Parent owns this turn's notification publication and receipt verification.

Constitution check: additive source-backed preparation, independent reference
before optimization, no secrets/weights, inherited interfaces unchanged. Native
correctness is unclaimed; the unresolved numerical prerequisite is an explicit
blocking gate rather than an undocumented exception.
