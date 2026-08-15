# F017 Q4_K REAL-1 Evidence Review

## Authority

This review is derived from `docs/architecture/reviews/evidence/f017-q4-k-real-byte-qualification-attempt-1-v1.json` (SHA-256 `035ad4351406c24c65667a5322f1ffae71589f046a5ba3f591b8a4e3f6140994`). The raw artifact, not this prose, is authoritative.

## Result

`Q4K-REAL-1` terminated as `EXACT_REAL_BYTE_QUALIFIED` after exactly one shard open, one positional read, one tensor payload, and 535,265,280 packed bytes. The first-observation packed SHA-256 is `3e4c34141f918333883442b8ff44c78c9927295ae16378047a8a36edeb7ed5ef`.

All three independently bound decoders produced 951,582,720 canonical little-endian f32 elements with SHA-256 `e2cff562131674156704ca21b2b6e850337c2e5d8948b4dcc9f14676ecf8f2c1`. The equality verdict is derived from the three raw hashes. Each output had zero non-finite values and zero negative-zero values; the signed-zero policy preserved and counted exact f32 bits.

The event performed zero model computation, zero MLX candidate dispatches, zero fallback, zero Q6_K access, and zero dense-prefix execution. The attempt is consumed with no retry and no automatic continuation. The append-only real-payload ledger advances from 57 to 58.

## Disposition

`Q4_K REAL-BYTE QUALIFICATION ACCEPTED`

The exact next action is independent adversarial review of the committed Q4_K evidence. Q6_K remains prepared, unauthorized, and unexecuted; the dense-prefix boundary remains blocked.
