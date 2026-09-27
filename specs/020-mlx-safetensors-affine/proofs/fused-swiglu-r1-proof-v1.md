# F020 fused ClampedSwiGLU R1 proof artifact v1

Status: frozen prospective proof plan; no Candidate N or Candidate B output was
computed. This artifact is independent of candidate selection and fixture
outputs.

## R1 reference

For rational x with |x| <= 16, set a = |x|/32 <= 1/2. The exact rational
Taylor sum T64(a) = sum(k=0..64) a^k/k! has positive remainder bounded by
(a^65/65!)/(1-a/66). Square the interval five times to recover exp(|x|),
reverse endpoints for negative exponents, then perform rational interval
reciprocal, SiLU, clamp, and product operations. Every endpoint operation is
outward exact rational arithmetic. Any enclosure wider than 2^-160 fails
closed. Down-reference width is propagated through
sum(abs(Wd))*width(h*).

## Candidate B certificate

Candidate B uses the frozen 833-node table and linear interpolation with
h=1/32. The interval proof subdivides each cell at its endpoints and midpoint
and bounds the exact second derivative
silu''(x)=s(x)(1-s(x))(2+x(1-2s(x))) using the same rational exponential
enclosures over [-16,10]. The resulting frozen global bound is M<=1; hence
the real interpolation error is at most M*h^2/8 = 1/8192.

Each table node is rounded once to binary32, bounded by 10*2^-24. The
interpolation error is multiplied by |up|<=10 before the final product. The
frozen evaluation order contributes at most 2^-20 before that multiplication.
Because |silu|<=10 and |up|<=10, the final product magnitude is at most 100,
so its binary32 round-to-nearest error is at most 2^-18. Thus the composite
bound is 10*(1/8192 + 10*2^-24 + 2^-20) + 2^-18, strictly below 1/128.
E_B=1/128 remains frozen. If an independent checker cannot reproduce these
inequalities, Candidate B is rejected; no coefficient or bound may be changed
after observations.

## Candidate N certificate boundary

The pinned source establishes the graph operation and actual Metal
implementation path, but not a universal transcendental error bound. Candidate
N therefore receives an environment-scoped empirical certificate only after
the exhaustive gate sweep and structured composition controls execute on the
declared runtime. The sweep reduces on device and retains worst input, absolute,
relative, ULP, non-finite, subnormal, monotonicity, sign, and violation counts.
No result exists at freeze.
