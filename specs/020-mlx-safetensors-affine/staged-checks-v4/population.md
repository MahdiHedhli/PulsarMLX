# Public CPU/mock control population v4

Freeze these expectations before implementation. All values are authored public
rationals/F32 words; oracle functions must not call the checker under test to
compute expected accept/refuse. Original bytes use inherited public A/B generators
and analytic proof, never real content. Full positives exercise all2048/4096 lanes
through live barriers with CPU/mock outputs rounded from independent literal or
independently authored Decimal high-precision oracle; mocks are NOT MLX results.

A01 original rectangle crossing gate10 and up+/-10; literal endpoints (9,11),
(9,11),(-11,-9); clipped endpoints(9,10),(9,10),(-10,-9); entire rectangle bound
must contain independent corner and interior Decimal oracle; constant gate[11,12]
gives Lg0. Reject rectangle extending past16, even if candidate is inside.
A02 gate=-2/up3 versus gate3/up=-2; literal outputs have the SAME negative sign and distinct magnitudes. Independent
coarse outward rational enclosures are [-716/1000,-715/1000] and
[-5716/1000,-5715/1000], separation>=4999/1000. At the original zero-width unit
rectangle, swapped H violates ideal-hidden EPERR<=E; this is a mathematical unit
witness, not an assertion of zero Phi from nonzero original bytes. Integrated
swap mutations additionally use the inherited full-shape A/B original sources. Clamp asymmetry: gate-15 stays-15, up-15 clamps-10.
A03 exact Phi witness x=(1,1),s=1,b=-1,q=(1,1): signed products zero but Phi4;
gamma273 bound nonzero. Replacing Phi by absolute products must be detected.
A04 mock supplies biased activation +1/1024 inside old Eact but outside a for
original g1/u2: refuse before down despite claimed native-compliant flag.
A05 exact-zero g=Bg=0 yields E0,H0; h=smallest F32 nonzero refuses. Numeric-unit-only tiny
nonzero g=2^-20,u1 with Bg=Bu0 refuses prospective floor under profile, no rescue.
A06 corrupt only final lane2047 and middle lane1023 in independent gate/up/hidden
cases; neither prefix sampling nor omitted E element allowed; reject length2047.
A07 fixed +1/1024 activation error above new local ceiling and below1/128 refuses;
new<=old analytical comparison all lanes. No adaptive profile or observed fit.
A08 replace one E by oldBh, alter profile/rectangle/input/source/build/attempt/digest;
refuse before later stage, consistent E used in floor/magnitude/row-sum/D/hidden.
A09 interval[0,2^-160],candidate0,budget2^-161: endpointQ2^-160 refuses although
interval distance0. Wrong order/width and non-dyadic endpoints refuse.
A10 down weights(1,-1),errors(e,e): D=2e, not0; independently signed ideal Y
contracts endpoints correctly. Explicit mutant signed propagation rejected.
A11 expected successful call prefix gate_up,activation,down,cleanup once each;
GU fault=>no activation/down, H/actual-hidden fault=>no down; callback exception,
reentry, duplicate attempt/receipt, buffer replacement, cleanup failure terminal.
Checked hidden digest and object equal down input; exported receipt cannot advance
or restart owner. Separate all-stage failure counters and receipt chain literals.
A12 precision!=256,width>2^-160,non-lattice E,integer769bits,NaN/Inf,badmetadata,
wrong lengths/hashes/role/recipe/endian,nine independent corruption controls;
resource each cap+1/deadline900s+epsilon/invalid samples refuse before later stage.
Native100ms watchdog/asynchronous cleanup are NOT RUN, never inferred from mocks.

Inherited populations unchanged:41 selected (2positive26refusal13mutation),
363primitive32plane. Run safe original CPU custody/proof/authority controls;
all numerical GPU controls NOT RUN. Preserve complete original population IDs
with an explicit executed/unrun mapping in final evidence, not aggregate pass.

Design-review01 refinements (all mandatory):
A05 source-level exactzero fixture sets every scale/bias group in one gate row to0;
packed codes remain unchanged. Both +0.0 and -0.0 hidden satisfy numerical zero;
semantic clamp words preserve the corresponding zero sign. Nonzero/subnormal
hidden cannot use the exception. Tiny nonzero source-row witness uses inherited
public g bias2^-21/up bias1/2 with its actual positive Phi/Bg/Bu.
A06 down4096 outputs corrupt lanes2048 and4095. Direct unit check witnesses exercise
local and ideal predicates separately; integrated down perturbations must refuse
with(1,1,1,1). A logically inconsistent ideal-only unit witness is never admitted
as original reference. Actual hidden subnormal/below-floor/above-cap at lane2047,
clamp mismatch at2047 =>(1,1,0,1), including independently exercised actual-domain
predicate when prior tighter checks already reject the same bad value. Mutate E
indices0,1023,2047 and D indices0,2048,4095; invalid identity refuses before later
stage. Reject each F32/clamp vector at n-1 and n+1 (hidden2047/2049,output4095/4097).
A08 checker digest covers numeric/source/owner/literals sources; proof digest covers
approved theorem/uniform-certificate/exact-stage inputs. Mutate each independently.
A11 literal counts (gate_up,activation,down,cleanup): pre-admission fault(0,0,0,1),
GU fault(1,0,0,1),activation/H/pre-down fault(1,1,0,1),down fault(1,1,1,1),
success(1,1,1,1) with DOWN_CHECKED before TERMINAL. Reentry uses immediate owner
flag refusal, no blocking lock; test timeout proves no hang and cleanup once.
Mutable bytes/bytearray/memoryview return refuses; clamp bits must be tuple[int].
Mutant replaces retained buffer after later callback; owner rechecks all digests.
CPU mock oracle Decimal precision120, converted to exact rational then exact
rational-to-F32 ties-even (no Python-float double rounding); analytic independently
proved literals validate the conversion, oracle disagreement refuses, never tunes.
A12 periodic row-loop deadline/RSS refusal; cache key includes role+packed row+
metadata bytes+original x or hidden digest; omitted-metadata cache mutant detected
by identical codes/different bias literal rows. Record full-positive CPU elapsed.

A03 add CPU decoder literals: U32 0x76543210,s1,b0,basis e0 yields0, reversed
nibbles yields7. Full asymmetric row repeats that word with x[j]=(j%8)+1,
s1,b=-1: each 8-wide block sums132; 4096-wide row sums67584; reverse yields
48 per block/24576 per row. This is decoder-unit scope with its explicit public
x, not the unchanged full-expert input. Import AST test requires literals/mock
import none of numeric/source/owner, and checker modules import none of literals/mock.
Full-shape positives run each in a fresh CPU child process with independent
ru_maxrss high-water measurement and deadline900s. RSS controls use isolated
children or explicit injected mock samples. No baseline subtraction; exceeding
a cap or deadline fails the positive, never tunes the caps.

Accepted review03 acceptance-side control A07P: public positive A with mock GU
lane0=(0x3f800040,0x40000040), lanes1023/2047=(0x40000040,0xc13fffc0),
other lanes original. These authored F32 perturbations are respectively
(1+2^-17,2+2^-16) and(2+2^-16,-12+2^-14), strictly inside original Bg/Bu.
Independent oracle H at these points must have ideal error>a but<=E; assert this
explicitly, then require full DOWN_CHECKED counts(1,1,1,1). Omit-P E:=a and Lg0
mutants must fail this accept-side witness. No tolerance or input changes.
