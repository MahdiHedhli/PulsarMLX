# Concrete prospective population v2

All positives: selected plane only, M1,D4096,H2048; original F32 input v2;
U32 little-endian codes q[j]=(j+row+role_index) mod16; group64;
BF16 s=1/16, b=t/2-15/32 in gate/up. Thue-Morse has zero correlation
with each low-bit digit and with constants over64, so sum_j x[j]q[j]=15;
therefore xW=t exactly. Signed scales are covered by positive B, which uses
s=-1/16,b=t/2+15/32 (same t). Packing shifts use j mod8, least nibble first.

Positive A targets cycle by row through (G,U)=(1,2),(4,-3),(12,12),(2,-12).
Positive B targets cycle (2,1),(3,-4),(12,-12),(4,12). All 2048 hidden lanes
are nonzero. Down uses q as above, s=1/4096,b=1/8192 (A), and
s=-1/4096,b=-1/8192 (B); every output is a nontrivial full-row contraction.
These are two complete full-shape positives, not clamp/control/zero cases.
Independent proof must show G/U +/- gamma*Phi in [-16,16] and each h interval
+/- (20Bg+10Bu+1/128) outside the 2^-32 floor and within all caps.

Required refusal IDs (one evaluable violation each): input-floor (x[0]=2^-33),
metadata-floor (first gate scale=2^-33), gate-margin (first target=17),
up-margin (first target=17), computed-hidden-margin (first gate target=2^-20,
first up target=1; metadata s=0,b=t/2), source/layer/expert/role/recipe/shape
identity mismatch, each nine range hash mutation, length/trailing/duplicate-key
framing. Injected down 2^-33 is a separately labeled guard-only control.

Required semantic mutation IDs and predicates:
- omit-gate-bias, omit-up-bias: original projection error exceeds Bg/Bu.
- nibble-order: reversed nibble decoder disagrees on an independent sparse
  packed-code witness; main x has linear low-bit cancellation, so that witness
  is required, not claimed detected by the real vector or positive formulas.
- gate-up-swap: at least one ideal hidden discrepancy exceeds frozen Bh.
- lower-gate-clamp: exact clamp witness G=-15,U=1, guard/control only.
- missing-upper-gate-clamp and missing-up-upper/lower-clamp: exact clamp
  witnesses (12,2),(2,12),(2,-12), preserving handle census.
- role-swap/expert-swap: identity refusal before native import.
- reinterpret-8-bit: strict all4-bit recipe refusal; replaces the old ignored
  mixed override control for this scope. Inherited mixed tests still run.
- skip-down-admission: missing admission trace detected; never unsafe dispatch.
- candidate-fed-reference: authority binding rejects candidate hidden input.

No incidental exception counts as mutation detection. All expected IDs must
appear exactly once. Host controls remain distinct from native positive cases.

## Execution counts and control scope

Frozen manifest v2 declares2 positives,24 refusal/guard cases and13 mutation IDs.
Positive native work is6 QMMs total and2 activation calls of2048 lanes. The two
bias-omission controls each execute one safe full-shape projection, with zeroed
bias metadata and no activation/down follow-on. Four clamp controls and the
activation gate/up swap each execute a baseline and a mutant activation of2048
lanes, with no down projection;10 additional activation calls. Thus the scoped
population has8 QMM calls (67,108,864 MACs) and12 activation calls (24,576 lane
instances), before inherited regressions. Numeric bias/swap controls compare
against original reference budgets and separately bounded mutant rounding.
Host custody/refusal/authority controls never dispatch inadmissible kernels.

### Revision after final review 01 (no observations)

The earlier inline nibble witness was rejected as vacuous and is not credited.
`nibble-order` now executes the full native gate projection and original-byte
Plane/affine/code with repeated U32=0x76543210, scales=1, biases=0 and x=e0.
The independent reversed-nibble interpretation of those original words gives7;
the original gives0 with zero local budget. This is a control, never a positive.
Native controls are now eight; host mutations five; total population stays39.
Total selected synthetic QMM work becomes nine projections /75,497,472 MAC.
Activation work remains twelve calls /24,576 lanes. Floor entries explicitly
cover R1 admission; the separate Rust preflight tests cover candidate guards.
