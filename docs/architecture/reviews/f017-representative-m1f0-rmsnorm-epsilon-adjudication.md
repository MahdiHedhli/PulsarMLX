# F017 representative M1-F0 RMSNorm epsilon adjudication

The authoritative representative layer-3 RMSNorm epsilon is `f32(1e-5)`: exact
decimal `9.999999747378752e-6`, binary32 bits `0x3727c5ac`, and little-endian
bytes `ac c5 27 37`.

The production runtime loads `glm-dsa.attention.layer_norm_rms_epsilon` into one
`f32` configuration field and passes it to layer attention and FFN RMSNorm
sites. The accepted representative M1-F0 oracle uses the exact binary32 value
at the attention-input, query-rank, compressed-KV, and post-attention FFN
normalizations. Its attempt-2 result was accepted with ten identical repeats.
Independent R9 attention and dense-prefix oracle lineages use the same value.

The `1e-6` values in the layer-3 semantic graph v1 and representative boundary
v2 are unsupported declarative transcriptions. Their freeze attested artifact
identity and structural semantics but did not compare the epsilon to model
configuration, production plumbing, or the already-bound executable oracle.
Other `1e-6` research helpers are synthetic or legacy surfaces and are not
production GLM-5.2 numerical authority.

The correction is append-only. Semantic graph v2 and representative boundary
v3 supersede only the RMSNorm epsilon declarations; v1, v2, their freeze, and
all accepted historical execution evidence remain byte-identical. The new
boundary grants no checkpoint access or execution authority.
