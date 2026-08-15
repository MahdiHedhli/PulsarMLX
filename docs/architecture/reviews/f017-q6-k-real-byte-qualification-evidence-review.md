# F017 Q6_K REAL-1 Evidence Review

The authoritative raw artifact is
`docs/architecture/reviews/evidence/f017-q6-k-real-byte-qualification-attempt-1-v1.json`,
SHA-256 `375e6b852733e8ac885d53c3814a03deb3a80e639bf61d427f1e49f1aae57086`.
This review derives its claims from that artifact.

`Q6K-REAL-1` consumed exactly one authorized payload read for
`blk.0.ffn_down.weight`: one shard open, one positional read, and 61,931,520
packed bytes. The first-observation packed SHA-256 is
`845b4fd6b5d290506e576ca5099336bae7d28f3ebfcec964ed2136c3ea4a8ede`.

The corrected grouped Python decoder, the independent index-driven Python
decoder, and the independent Rust reference each produced canonical
little-endian f32 SHA-256
`ff26151a7997379c1713b90852fdbfd8301b36d5d89a1c3bb623b9b8f273483a`.
Each output contains 75,497,472 finite elements and 992,625 signed-zero bit
patterns. Exact equality therefore holds without tolerance or majority vote.

The terminal classification is `EXACT_REAL_BYTE_QUALIFIED`. The real-byte side
of `F017-Q6K-LANE-ORDER-001` is closed without modifying its historical defect
artifact. The append-only real-payload ledger moves from 58 to 59. Model
compute and MLX candidate dispatch are both zero. Dense-prefix execution did
not occur and is not automatically authorized.
