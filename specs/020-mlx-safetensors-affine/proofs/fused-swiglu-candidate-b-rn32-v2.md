# Candidate B RN32 gradual-underflow certificate v2

This prospective certificate supersedes the activation-only subnormal-intermediate rejection in Candidate B v1 for the v2.4 package. It preserves every Slice 1/2B/2C predicate, especially refusal of zero/subnormal h before down-QMM. No Candidate N/B output defines this proof, table, domain or bound. Exact-source independent acceptance is still required before observations.

## Target and arithmetic hypotheses

Let f(x)=x/(1+exp(-x)), g=min(gate,10), c=clip(up,-10,10), with finite F32 gate/up in [-16,16]. The target is f(g)c. Include all signed-zero, subnormal and normal gate bit patterns in the frozen ranges, total 2,197,815,298. Candidate B is host CPU binary32; this proof asserts no Metal rounding or denormal guarantee.

Require binary32 RN ties-to-even, gradual underflow, no excess precision, no contracted FMA, and finite intermediates. Write u=2^-24, eta=2^-150, h=1/32 and eps=10u. For any finite non-overflowing RN32 operation, absolute error is at most u|z|+eta (a conservative combination of normal rounding and the half-ulp subnormal term). The sharper half-ulp binade bound is used for the final product.

The read-only guard requires ARM64 IEEE binary32, FPCR RMode[23:22]=0, FZ[24]=0, AH/FIZ[1:0]=0, and exception-enable bits[12:8]/[15]=0, and C FE_TONEAREST. Opaque primitive canaries check least-subnormal scaling, both even ties, separate underflow multiply/add, and negative-tiny floor. The guard reads the control word again; it never writes FPCR or changes rounding mode. Check before GPU initialization and before/after every CPU Candidate B batch and before host delta reduction in the same thread. No FP-control-changing support function may run within a batch. The shipped binary is inspected for FMA and separate multiply/add; command-line flags alone are insufficient.

Arm's ABI identifies these mutable control fields: https://github.com/ARM-software/abi-aa/blob/main/aapcs64/aapcs64.rst#simd-and-floating-point-registers . CPU guards do not establish GPU behavior. Unknown native Metal underflow stays inside Candidate N's independent pinned-runtime empirical qualification.

## Continuum derivative and value bounds

Put s=1/(1+exp(-x)), p=s(1-s), and t=|x|. Then 0<=s<=1, p<=1/4 and p<=exp(-t).
f'(x)=s+xp, hence |f'|<=1+16/4=5 on [-16,10].
f''(x)=p(2+x(1-2s)), hence |f''|<=2p+tp.
exp(t)>=1+t+t^2/2>2t because 1-t+t^2/2=((t-1)^2+1)/2>0. Thus t exp(-t)<1/2, and |f''|<1 over the entire interval, including every segment interior.
For x>=0, |f(x)|<=x<=10. For x<0, |f(x)|<=t exp(-t)<1/2. Therefore |f|<=10.
The standard linear-interpolation remainder is <=M h^2/8 with M<=1, hence <=1/8192. No node-only curvature sampling is used.

## Independent table certificate

833 coordinates x_i=(i-512)/32 are exact. The static checker encloses f(x_i) through the unchanged independent exact-rational R1 module. It independently verifies R1's ln2 constants using ln2=2 atanh(1/3) with 128 positive series terms and the geometric tail bound. R1's range-reduced degree64 Taylor interval checks |r|<=1/2 and bounds its remaining series; exact interval operations preserve enclosure. No host libm exp result is trusted. The additive R1 v2 contract corrects v1's five-squaring description to this actual unchanged ln2 implementation, preserving every numerical target, domain, acceptance and down-admission field.

At every node the checker requires width<=2^-160, both interval endpoints round to the same declared F32 bits in a pure integer RN-even model, absolute node error<=eps and |table_i|<=10. It checks all 832 adjacent gaps <=5h+2eps, derived also by the mean-value theorem. Any structural, coefficient, rounding or gap mismatch fails closed. The existing fixture bytes and node count are unchanged.

## Index and exact operations

g*32 is an exact exponent shift under gradual underflow for every F32 g in [-16,10], including subnormals; scaling upward introduces neither discarded bits nor overflow. floor(scaled) is an integer in [-512,320]. Its conversion and addition512 are exact. Clamping i to[0,831] only maps the right endpoint i832 to the final segment. x0=(i-512)/32 is exactly representable; g-x0 lies in[0,h]. Thus each input is assigned to its mathematical segment. In particular gate=2^-149 gives scaled=2^-144; a normal gate can also produce a subnormal product. These values are supported, not removed from coverage.

The checker uses a pure rational RN32 model to test each grid endpoint and neighboring F32 bit patterns plus signed zeros and least/largest-subnormal and least-normal boundaries. These probes corroborate the analytic index theorem; they do not replace a sweep or claim that candidates have executed.

## Operation-by-operation error ledger

Let a,b be adjacent rounded nodes; d=b-a. |d|<=5h+2eps. The explicit RN32 subtraction has error ed<=u(5h+2eps)+eta. Scaling that difference by32 is exact; slope error es=32ed. Its magnitude is <=5+64eps+es<6.
The explicit delta subtraction has error et<=uh+eta. Rounded delta stays in[0,h] because both endpoints are exactly representable; the looser h+et bound below remains sound.
The explicit slope/delta multiplication has error em<=u*6*(h+et)+eta.
Against the exact rounded-node chord, before-add error is <=es*h+6et+em. The chord is a convex combination of a,b and has magnitude<=10; the perturbed pre-add magnitude is <11. Addition error ea<=11u+eta.
Total interpolation evaluation error es*h+6et+em+ea <2^-20. The checker verifies this strict inequality using exact Fraction arithmetic, retaining eta in every relevant operation.

The interpolated output magnitude is <10+2^-20. With |c|<=10, the exact pre-round product is <10(10+2^-20)<128. Every binary32 binade below128 has half-ulp<=2^-18; subnormal half-ulp eta is much smaller. Hence the final product's absolute rounding error<=2^-18. The loose relative-error formula at magnitude100 is not used to infer this bound.

Therefore |B-f(g)c| <=10*(1/8192+10*2^-24+2^-20)+2^-18 =5201/4194304 =beta_B <1/128. The frozen beta_B, E_N and delta_max remain unchanged. Nonfinite results still fail closed. Zero/subnormal activation outputs remain in activation diagnostics and are refused by the unchanged downstream admission.

## Limits and qualification gates

This is a uniform mathematical certificate conditional on the guarded arithmetic and certified table, not a Candidate N certificate or an N-vs-B qualification result. Actual runtime checks, full gate enumeration, exact R1 corroboration, regression evidence and complete independent exact-commit reviews remain mandatory. No public-ref parity or publication is implied by this prospective local package.
