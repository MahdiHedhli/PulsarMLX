# Research decisions v1
Pinned repository sources are evidence of reference semantics, not verified
selected-checkpoint headers or payload. See source-pins.json.

* Dispatch is explicit from upstream-config.json; never infer all layers from
  a modulo pattern alone. Cross-check linear_attn_config lists and mlp_layer_types.
* Router: sigmoid FP32 projection in retained source, correction only for ranking,
  original sigmoid scores for normalized mixture times 2.5. n_group=1. Tiny
  deterministic ties cannot establish upstream argpartition tie behavior.
* mHC: comb[input_stream][output_stream], so expansion contracts the first
  axis; attention and FFN have separate collapse/norm/branch/expand operations.
* KDA: raw q/k/v projection suffix before SiLU; normalized q/key; per-key decay
  exp(-5 sigmoid(exp(A_log)*(a+dt_bias))); beta=sigmoid(b). Native value/key
  layout differs from mini-candidate key/value. Mask semantics of retained
  module and recurrence differ; padded/masked production batches remain open.
* Sparse: full pools visible only after final member; partial visible tail
  always included; positions are absolute and relative pool origin explicit.
  NoPE MLA does not authorize removing indexer-specific position behavior.
* Retained decoder stack is a tiny two-layer reference, not the real 45 layers.
  Tiny sparse prefill oracle has no cache. This addendum defines a prospective
  append-only, no-padding state contract, not upstream cache equivalence.
* Prefer chronological oracle versus suffix-based candidate so chunk/state
  bugs have different computational paths. No external research needed: task
  pins local source and prohibits expanding access.
