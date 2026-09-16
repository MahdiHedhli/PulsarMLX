# Dense/linear decoder-layer composition (Flash AN, Graph 8, slice 1)

`Glm5NextDecoderLayer` for layer type `linear_attention` with a dense
`ClampedMLP` is qualified as one composed forward pass under the supervised
successor harness (`successor.py layer`), against an independent stdlib oracle
composed from the accepted linear-attention reference, the accepted dense-FFN
reference and a reimplemented HyperConnection stage
(`scripts/research/glm53_flash/decoder_layer/oracle.py`). The capsule is the
upstream class with only its name changed (canonical-AST equality enforced);
the attention class is the linear-attention admitted namespace with its
counters and kernel admission, and `ClampedMLP`/`HyperConnection`/`hc_expand`
come from the dense-FFN admitted namespace. Sparse attention and MoE
constructors are refused; this graph qualifies the (linear, dense) layer type
only.

Observed boundaries: the post-norm attention input, the attention output and
the layer output, each within the 1e-4 allowance on CPU and Metal (measured
errors around 1e-8 to 2e-7); the compiled decode-step gate
(`mx.compile(self._ffn_block)`, B=1 L=1) is taken and agrees within 1.2e-7.
The linear-attention counters show one module call and one kernel submission
per token on Metal, and the ops recurrence on CPU. Five capsule mutants are
asserted cell by cell against a frozen matrix with a factor-10 margin: four
kill on both fixtures, the compile-gate control is inactive on both. The
matrix's first version predicted the attention-side comb transposition would
be structurally weak at hc_mult 2, as it was on the dense-FFN fixtures; the
frozen oracle boundary shows that comb is not converged after three rounds
here (asymmetry 2e-2), the mutant kills at 9.9e-3, and the misprediction is
preserved in the fixture record.

Two fixtures (hc_mult 2 and 3, hidden 4, one linear head of dim 32, kernel 2,
S=2, cache `None`). Input design is constrained by the accepted
linear-attention reference, which admits inputs only with |v| <= 1: an
RMS-normalised vector always has an element >= 1 unless magnitudes are equal,
so the layer inputs use a rank-1 sign pattern whose normalised attention input
has uniform magnitude just below 1. The norm stage is therefore exercised only
at that point. Widening the reference's input domain is a separate,
consequential change to an accepted reference and is not made here.

Not covered: cache lifecycle across calls (slice 2), sparse attention and
indexer, MoE experts and combine, the model stack, real weights, quantized or
native-BF16 parity, and any real-model claim. The supervised operation runs
under the admitted `env-g1` identity (mlx 0.32.2); the light-harness CI
qualification of the dense-FFN caller runs at the lockfile's mlx 0.32.0.
