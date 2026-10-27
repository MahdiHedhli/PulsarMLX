# Routed CPU fixture v1 (prospective freeze)

Two layers; four experts/layer; top-2; hidden/intermediate width 4; vocabulary 8.
One seed, at most eight generated tokens. No attention, recurrent/KV state,
quantization, checkpoint, tokenizer, paging or native execution is modeled.

Matrices are row-major `[output,input]`; expert banks are `[expert,output,input]`.
The file concatenates embedding `[8,4]`, then each layer's router `[4,4]`,
gate/up/down `[4,4,4]`, then head `[8,4]`. Scalars are IEEE binary64 LE;
all fixture inputs are exactly representable dyadics. A separate u32 LE input
token selects an embedding. Every dot product starts at +0 and accumulates
columns 0..3 using separate multiply/add operations (no explicit FMA).

For each layer: router projection; descending top-2 with lower expert ID on
exact ties; stable selected-score softmax; gate/up projections for each selected
slot; SiLU(z)=z/(1+exp(-z)); elementwise SiLU(gate)*up; down projection;
slot-order weighted sum; residual addition. Layer 1 consumes layer 0's residual.
Head projection follows layer 1; greedy ties choose the lower token ID.
SiLU is evaluated directly on this bounded domain. Every runtime input and
intermediate must be finite. Arbitrary finite payloads that overflow refuse.

The seed is pushed once before StepCoordinator ownership. Position 1 is the
first generated request; each successful step adds one token and one position.
The committed token selects the next embedding. EOS is included and stops after
its commit/delivery; max-token stops after exactly the requested commits. A pending
delivery blocks advancing, even at EOS/max-token. Matching retries replay the
retained COMMITTED bytes, including with a cancelled token. Failures preserve the
previous committed prefix. There is no second generated-token state owner.

The 80-digit Decimal reference independently implements all scalar math; a
100-digit run checks finite-fixture stability. It shares values, not routing,
activation, projection or aggregation code with Rust. Goldens include input,
scores, selected IDs/weights, gate/up/SiLU/product/down, mix/residual, logits,
tokens and positions. The zero embedding gives exact route and greedy ties.
The max case changes routes and runs eight steps; the EOS case starts at seed 5
and ends at token 7. Expert banks and non-tie weights are asymmetric.

## Frozen comparison policy (before candidate observations)

Integers, identities, route IDs and ties are exact. For every floating scalar:
`abs(candidate-reference) <= 2^-35 + 2^-35*abs(reference) + 2^-180`.
No NaN/infinity is accepted. Goldens use 65 significant decimal digits.
Non-tie selected/unselected and greedy boundaries must exceed 2^-10 in the
reference (exact ties are checked separately). Do not tune this policy to Rust.

Budget rationale: input infinity norm <=1; expert matrix row sums <=1/2;
`|SiLU(z)|<=|z|`; the residual bound is B_next <= B+B^2/8, so two layers
remain below 2. Router scores stay within [-1,1], selected exp arguments [-2,0],
and the softmax denominator is >=1. Head row sums <=2; logits remain below 4.
Using binary64 unit roundoff u=2^-53, an engineering allowance of eight ulps
per libm exp, and <=1024u local rounding/exp allowance per layer, a conservative
error recurrence E_next <=8E+1024u covers the small projections, activation,
softmax and mixing. Two layers plus head/diagnostics fit below 32768u.
The absolute 2^-35 allowance is eight times that envelope; the relative term
covers scaling. Decimal uncertainty/serialization allowance is 2^-180;
80/100-digit stability is checked below 1e-70. This is a finite CPU differential
policy with an explicit libm assumption, not a universal floating-point proof.

Weights are eagerly declared/read by the coordinator (11 inputs, two layers).
Selected expert *computation* is exercised; selected-only I/O is not. New owning
decoded weights, two bounded traces, math temporaries, route allocations, output
serialization and the driver's pending request are covered by the declared
64 KiB logical scratch allowance, in addition to coordinator-loaded inputs,
output, retained output and token history. Fixed geometry and existing 64-input/
64-layer caps remain unchanged. The fixture owner/caller copies, allocator
capacity/metadata and physical RSS are not governed by this logical reservation.
