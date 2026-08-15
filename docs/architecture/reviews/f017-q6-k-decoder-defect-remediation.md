# F017 Q6_K Decoder-Defect Remediation

Status: `CLOSED_CHECKPOINT_FREE_REAL_BYTE_TRUTH_PENDING`

The defect `F017-Q6K-LANE-ORDER-001` was reproduced with a single 210-byte Q6_K block. The old research decoder used `ql[l]` high nibble for the second 32-value group and `ql[l+32]` low nibble for the third. The corrected decoder uses the upstream order: second group from `ql[l+32]` low nibble, third group from `ql[l]` high nibble. The high-bit fields remain `qh` bits 2..3 and 4..5 respectively.

The minimized fixture SHA-256 is `c152e5235619c39ef4ec69a2fc26fb718aebf14416bb2ba25ee8262aa5980cc9`. At element 32/lane 0 the old source is `ql[0]` high nibble `0xa`, producing `-22.0` (`0000b0c1` LE-f32); the corrected source is `ql[32]` low nibble `0x2`, producing `-30.0` (`0000f0c1`). Element 64 demonstrates the reciprocal error.

The correction is independently bound to llama.cpp commit `a94d563ed801d1da1b8c2432946de07d0231bb3d`, tree `df5ef3120316710a104d702115d446ac30d385f2`, `ggml/src/ggml-quants.c` SHA-256 `07143d7068936ae46b3c528b2f3d4bbb666e74d88992165716174d243573965d`, function `dequantize_row_q6_K`. No upstream source was copied.

Three implementations support the corrected result:

- A: grouped scalar Python transcription, implementation SHA-256 `39a153b958b398964966c1041606497eaa23f9e7bee6e15cc406474cc2b20039`.
- B: index-driven scalar Python derivation, implementation SHA-256 `999f228465cc2c805da456413872f327d1437e8651f772a555b94f06363f1b76`.
- C: Rust matrix reference, source SHA-256 `a4d308ef1aa874865e668002a8911d8247247dd490e301018f730aeb06ab35fd`.

All three are classified `INDEPENDENT`: they share neither decoder calls nor generated expected output; C is in a different language and source path. The fail-closed audit rejects decoder imports or missing pairwise independence.

Regression coverage explicitly exercises corrected second-group lane, corrected third-group lane, multiple groups, high/sign bits, signed scales, block boundaries, and canonical LE-f32 serialization. Exact bytes are required.

The F017 evidence sweep found no accepted real gate that decoded Q6_K. Therefore the verdict is `F017_ACCEPTED_EVIDENCE_UNAFFECTED`. F016 Q6_K-dependent baseline/reproduction claims remain historical self-consistency evidence where both sides used the same decoder; they do not establish absolute Q6_K truth or independent token-level attribution. No historical artifact or PASS field was rewritten. Real-byte Q6_K truth remains pending its separately reviewed one-payload gate.

Machine-readable evidence: [f017-q6-k-decoder-defect-v1.json](evidence/f017-q6-k-decoder-defect-v1.json) and [f017-q6-k-historical-impact-v1.json](evidence/f017-q6-k-historical-impact-v1.json).

Real checkpoint access: `0`. Ledger: `57`.
