# F017 Q4_K Real-Byte Qualification Handoff

Status: `PREPARED_NOT_AUTHORIZED_NOT_EXECUTED`

The future gate qualifies decoder-format truth only. It performs no embedding lookup, MLX candidate execution, dense-prefix execution, or other model compute.

The sole Q4_K dense-prefix tensor is `token_embd.weight`, shard 2, offset `535316320`, packed length `535265280`, logical shape `[6144,154880]`. The mechanically reconciled access budget is one shard open, one positional read, and one tensor payload. A successful separately authorized event changes the real-payload ledger from `57` to `58`.

Decoder A is the scalar Python implementation in `scripts/research/ggml_kquants.py`; decoder B is the separate specification transcription in `scripts/research/f017_m1f_minus1_dense_prefix_prep.py`; decoder C is the Rust matrix decoder in `crates/f017-runner/src/final_output_qualification.rs`. Pairwise independence is fail-closed. PASS requires exact canonical little-endian f32 equality `A == B == C`; no tolerance and no majority vote are permitted. Disagreement is `DECODER_TRUTH_UNRESOLVED`.

The package remains non-executable until the narrow adversarial verdict is `GO FOR ONE Q4_K REAL-BYTE QUALIFICATION` and a separate operator execution instruction binds a reviewed authorization head. Attempt consumption begins immediately before the first positional checkpoint payload read. There is no automatic retry and no automatic Q6_K or dense-prefix continuation.

Prospective M1-G lineage is format-level only: the exact format contract, block layout, decoder implementations, serialization, and relevant tail behavior must match. Any later output-head tensor still needs its own packed identity, shape, and tensor-map binding.

Artifacts: [handoff](evidence/f017-q4-k-real-byte-qualification-handoff-v1.json), [execution config](evidence/f017-q4-k-execution-config-v1.json), [authorization binding](evidence/f017-q4-k-authorization-binding-v1.json), and [attempt ledger](evidence/f017-q4-k-attempt-ledger-v1.json).

Real checkpoint access: `0`. Ledger: `57`.
