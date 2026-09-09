# Finite full linear-attention module composition

The `linear` research operation composes the complete original
`Glm5NextLinearAttention` constructor and call method under synthetic FP32
parameters. It includes original `Glm5NextForgetGate`, `Glm5NextRMSNormGated`
and `_l2norm` definitions, all seven recurrent functions and their four factory
initializers, and the previously accepted actual `ArraysCache` class.

The language source is PipeNetwork/glm53-flash-mlx at
`a61a7c7d2fbdf3d218a9909365a24bd794f3a247`; the recurrent source is
Blaizzy/mlx-vlm at `8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90`.
The accepted vendored texts and license notices remain in the predecessor
component directories. Whole AST nodes and byte spans are verified before
execution. A minimal global-name census supplies only admitted MLX, typing,
synthetic configuration and the original recurrent dependency. Whole upstream
modules and model loaders are never imported.

Seven fixture/configuration/partition cases plus one interleaving schedule
make eight scientific cases. They use B1–2, S1–5, hidden size4/8, heads1/2,
head dimension32 and convolution kernels2/3. Dk=Dv32 is newly declared
geometry for this module; earlier Dv4/8 contracts remain unchanged. The source
launch grid is `(32,32,B*H)` and threadgroup `(32,4,1)`. Bounds are conditional
on32-lane SIMD/x-major packing. Metadata checks establish sizes and index
bounds under that assumption and do not attest physical driver behavior.

All thirteen consumed parameter leaves are replaced with explicit dyadic FP32
fixtures before the first call. The live parameter census, exact installed
values, native Linear/Conv1d instances and absent quantization attributes are
checked. Random constructor allocations supply no trial values. The source
starts with `fuse_in=True` and `_fused_ready=False`. Counters record first
construction, exact concatenation/split metadata and reuse of the same fused
weight object. Parameters are unchanged after that construction.

The full path covers fused Q/K/V/forget/output-gate/beta projections, causal
depthwise convolution and cache0, SiLU, head reshape, L2 normalization and
query scaling, ordinary/safe forget gates, default recurrent selection and
cache1/advance, gated RMS normalization and output projection. CPU uses the
original ops path; Metal uses the original custom kernel. The module's boolean
mask zeros mixed Q/K/V before convolution. It is not passed into recurrence:
history and independently computed gates remain active at masked times.

The independent reference uses stdlib binary64 loops for every stage. Dense
weights have `[out,in]` orientation, depthwise weights `[channel,kernel,1]`,
and recurrent state `[B,head,value,key]`. The accepted scalar recurrence runs
through its unchanged Dv8 interface in four independent value-row blocks;
there is no cross-value-row dependency. A separate forward-error recurrence
must agree with those values. No candidate outputs or candidate code supply
the reference. The sparse anchor gives projected1/8 and pre-SiLU convolution
1/16 at the declared first channel, independently checked with exact fractions.

The fixed ceiling for returned output and both caches is
`abs(error) <= 1e-4 + 1e-5*abs(expected)`. Before observation, propagated
interval radii include FP32 constant conversion, reductions, convolution,
normalization conditioning, gate error and recurrent accumulation. Working
assumptions are unit roundoff2^-24, exp/rsqrt relative error2e-6 and
sigmoid/softplus absolute error2e-6 on this bounded domain. They are explicit
finite working assumptions, not a universal transcendental guarantee. The
effective driver math mode is NOT_OBSERVED. No tolerance is fitted to results.

Complete returned outputs, both actual cache tensors and length/padding
advance are observed only at each outer call boundary. Actual tensors remain
in the same cache between chunks. Oracle states are comparison-only. The
parameter-admission observation is separately counted before the first call.
Normal module/recurrent source has no inner eval, tolist or item. Entry
wrappers preserve algorithms, selectors and return values. Python boundary,
fused construction, API submission and explicit barrier counts are distinct
from unobserved physical compilation, GPU instructions, faults and disk I/O.

Eight controls use fresh normal/mutant/restored objects and frozen inputs:
valid projection segment swap, wrong history, missing query scaling, wrong
forget parameter, dropped cache1, incorrect advance, omitted output
normalization/gate and an illicit inner barrier. The last is a harness
control; the other seven alter one source semantic site while preserving
safe dimensions. Actual output/cache/advance/barrier predicates decide
detection. Missing/bad identities, unsafe dimensions and malformed archives
are refused before candidate entry with their actual exception classes.

Normal CPU and Metal trials and fresh materialized CPU and Metal confirmations
belong to one pre-observation generation. Source-free doctors, bounded capture,
confinement and archive verification use the existing successor mechanisms.
Only explicit operation, input and archive-layout registration is added.
Quantization, the unused standalone forget-gate call, the unfused diagnostic
branch, masked/scalar recurrent kernels and all other model classes remain
outside the declared active path. This is a finite synthetic module result;
full blocks/models, production geometry, BF16, mixed quantization, weights,
expert routing integration, storage performance and dogfood are excluded.
