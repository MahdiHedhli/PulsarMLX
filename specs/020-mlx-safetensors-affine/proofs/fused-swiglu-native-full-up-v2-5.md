# Native full-up propagation certificate v2.5

This additive certificate closes the up=1/full-up gap at predecessor 540f317eabd5f92015b283e3522b4febcae1fb77. It changes no domain, coefficient, E_N, beta_B, inherited delta_max, R1 target, Bh rule or down admission. No numerical observations are used to choose this certificate.

## Scalar reference and continuum lemma

The Candidate B v2 proof remains governing for its guarded CPU arithmetic. With s=sigmoid(x), p=s(1-s), t=|x|, p=1/4-(s-1/2)^2<=1/4 and p<=exp(-t). Thus |f''|<=2p+tp<=1/2+t exp(-t)<1: exp(t)>=1+t+t^2/2 and 1-t+t^2/2=((t-1)^2+1)/2>0 prove exp(t)>2t. This explicitly combines the two bounds, including at t=0. Chord error on h=1/32 is <=h^2/8=1/8192. The previous node/rounding/index certificate is preserved and statically rerun.

Let S_B be the guarded CPU interpolated SiLU value. Multiplication by exactly1 is exact, including subnormals under the CPU gradual-underflow guard. Therefore the pre-product certificate gives

    |S_B-f(g)| <= beta_silu = 1/8192 + 10*2^-24 + 2^-20 = 1037/8388608.

The product-specific 2^-18 term in beta_B is not included in beta_silu.

## Materialized native graph and source identity

The prospective bridge explicitly evaluates and synchronizes its native F32 SiLU array before constructing any up-dependent graph. It validates dtype, element count and readable data. The exhaustive path measures those exact materialized SiLU bits directly against CPU B at up=1; it does not use a potentially flushed multiply-by1 output. It retains input up bits0x3f800000, the scalar N/B witness, count and measurement identity. Structured paths apply clip/final multiply to that materialized buffer and retain its bits.

The new source pins include MLX array/evaluation, ops, binary dispatch/instantiation/operators and compile options. ops.cpp creates a Multiply primitive for F32 operands; Clip is Maximum then Minimum. transforms.cpp evaluates pointwise primitives, sets evaluated status and detaches their graph; array.cpp makes a synchronized buffer available. The bridge never calls compile, tracing, vmap or another graph transform. SiLU is independent of up and final multiplication consumes its stored F32 buffer; it cannot be reassociated into sigmoid. unary/binary kernels have pointwise expressions without reductions or other-element dependence. This qualifies the frozen contiguous 1D F32 synthetic graph/runtime, not production geometry or a fused replacement graph. A future changed graph, kernel/source/runtime or geometry needs its own qualification. Materialization count must equal2098 for sweep,1 for each control path.

The frozen source hash checks cover both compiled and JIT selection. Offline CMake uses -fno-fast-math; runtime Metal CompileOptions has fastMathEnabled false. Artifact, OS and toolchain pins remain unchanged and are checked before any capability.

## Native product and optional flushing

Authority: [Apple Metal Shading Language Specification](https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf), edition2026-06-04, sections1.6.3,8.1,8.2,8.4/Table8.1 and8.5, downloaded SHA25641538b30d2f1140a5b2a0c84ce0a9f7b67bf0c707e224cfea0bfe5a44aa26cf5.

The specification makes F32 multiplication correctly rounded, permits RTNE or RTZ and permits subnormal input/output flushing to either signed zero. This certificate covers all those choices. It does not assume GPU RN or gradual underflow, and it assumes no universal native sigmoid accuracy. CPU guard/disassembly are not used to prove Metal arithmetic.

Let tau=2^-126. The exhaustive upward delta certifies |S_N-S_B|<=delta for every gate. Thus e_s=delta+beta_silu bounds |S_N-f(g)|. The preserved inherited guard delta+beta_B<=E_N implies delta<=delta_max; then |S_N|<=10+e_s<11. Both operands of the final product are finite F32. Let c=clip(up,-10,10); |c|<=10. In the pinned finite clip comparisons, a normal up is selected exactly or clamped to an exactly representable boundary. A subnormal up may be selected or flushed to zero; either has distance<tau from c. Flushing before its subsequent multiplication has the same alternative, so the aggregate effective up c' satisfies |c'-c|<=tau and |c'|<=10. Effective S_N' differs from S_N by at most tau and has magnitude<11.

    |S_N' c' - S_N c|
      <= |c'| |S_N'-S_N| + |S_N| |c'-c|
      <= 10 tau + 11 tau.

The exact product has magnitude<110<128. For RTNE or RTZ, its nonflushed F32 rounding error is bounded by a whole representable gap2^-17 throughout that magnitude interval; this bound also covers the subnormal gap. An exact subnormal result can instead be flushed, with absolute error<=tau. Conservatively sum both errors. All permitted native paths therefore satisfy

    |N(g,up)-f(g)c| <= 10*(delta+beta_silu) + 2^-17 + 22*tau.

Signed-zero differences are irrelevant to this absolute-error bound and remain present in the exact bit controls. No nonfinite result is admitted.

## Operational acceptance and corroboration

The driver retains the inherited delta+beta_B<=1/128 comparison and additionally requires the full-up bound above<=1/128, using exact Fractions. The derived scalar ceiling is merely the algebraic consequence of this theorem; the frozen delta_max field is unchanged. A scalar delta passing the old check can fail the new check. There is no limit relaxation, observed threshold tuning or rerun to obtain acceptance. The report records beta_silu, scalar/error envelopes, both comparisons and uses unchanged E_act=E_N=1/128 in Bh=20 Bg+10 Bu+E_act.

The original ordered42 gate/up controls remain required. An additional frozen bit-policy crosses20 small/subnormal/normal/clamp gates, plus the retained worst gate's two neighboring numeric keys on each side (deduplicated and clipped to the original domain), with20 declared up bits. Both zero signs, least/largest subnormal, least normal and adjacent normal, +/-2^-32, clamp neighbors and extreme inputs are present. The policy fixes exact ordering and accepts no replacement/missing/reordered pair. Structured controls corroborate the propagation; they do not replace it or exhaust the Cartesian product. Counts are derived from the frozen policy and worst bits, never guessed.

For any corroborating R1 interval [lo,hi], use max(|candidate-lo|,|candidate-hi|), not distance-to-interval plus half-width. Retain width<=2^-160; reject nonfinite evidence and budget excess exactly. Native regressions retain all363 primitive and32 composition IDs and their original summary gates.

## Gates

Prospective freeze and both exact-source reviews are required before candidate observations. Publication needs separate authorization and exact remote-ref parity. Default/absent-capability modes remain static or fail before GPU creation. No checkpoint payload, full model inference, production geometry, benchmark, merge or next-slice authorization is provided.
