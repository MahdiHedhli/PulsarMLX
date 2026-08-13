# F017 M1-E IQ3_XXS Decoder Remediation

## Result

Root cause: `PYTHON_DECODER_DEFECT`.

M1-E attempt 1 remains immutable and rejected at `m1e_down_decoded`. The
remediation did not execute MLX or a real expert. It reused only the three
private packed payloads already captured by attempt 1 for decode-only
qualification.

## Reproduction

The authorized down payload remained exactly
`442acf3cf5210ade4faa0b38ef0f94aaca7b15571a180804ace52b94cccdf59d`.
The missing candidate identity was reproduced explicitly as
`f91987106198943c8a225b52dcf0099ba8f8b89d1ecad92c4a7c5c4964e20eae`.
The attempt-1 Python identity was
`c252537660deb00330ec289338daaf89d550ce8a3553d7e34ac59353156f756d`.

The first mismatch was logical element 1, row 0, column 1, in compressed
block 0 at payload offset 0. Python emitted bits `bd182e48`
(-0.03715351223945618); Rust and the specification decoder emitted
`3c445cc0` (0.01198500394821167). The absolute difference was
0.04913851618766785. In total, 8,269,400 of 12,582,912 values differed,
covering all 6,144 rows and all 49,152 compressed blocks. This is a systematic
logical-order defect, not a float-serialization or one-ULP discrepancy.

## Format audit and third decoder

The pinned authority is llama.cpp commit
`8e7f22b67ef4667b4ddd50230771287f328cfb3f`,
`ggml/src/ggml-quants.c` SHA-256
`07143d7068936ae46b3c528b2f3d4bbb666e74d88992165716174d243573965d`,
function `dequantize_row_iq3_xxs`.

For each eight-value subgroup, the format emits grid 1 lanes 0–3, followed by
grid 2 lanes 0–3. The pre-fix scalar Python loop appended a grid-1 lane and a
grid-2 lane together; the NumPy transpose encoded the same interleaving. The
Rust implementation already used the authoritative ordering.

The third decoder in `scripts/research/iq3_xxs_spec_decoder.py` is scalar,
does not import either decoder implementation, uses no Rust/FFI/MLX, and was
transcribed directly from the pinned format source. It matched Rust on the
minimized block, sampled real blocks, and the full bounded real matrix.

## Fix and contract

Only the independent Python ordering was corrected. No Rust IQ3 arithmetic,
codebook, sign, scale, shape, serialization, or numerical tolerance changed.
The permanent one-block fixture is
`f017-iq3-xxs-order-regression-v1.json`, SHA-256
`8d60b88d44d812036131beba384d886131f1234f852f95c67f9821283fd4fa48`.
Its packed and decoded identities are respectively
`412e7b8e5b0100e0ddee63aba7859fa140b7d3d9fa906475b9345e37a2534574`
and `f247b81ca959124092a6eca58e177e8b179894ee804569d1f98840682f4a4c3e`.

The replacement contract is `f017-m1e-iq2-iq3-decoder-v2`, SHA-256
`9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84`.
It requires exact row-major little-endian f32 identity and records the v1
ordering defect. After the fix, Python, Rust, and the third decoder all produce
the full real-down hash `f9198710…20eae` with zero bit mismatches.

## Corrected oracle and evidence impact

Decode-only oracle regeneration retained gate, up, and activated-hidden stage
identities. The corrected down ordering changed the final expert reference
from `4b6029ef…fac97` to
`ae1fa8e468418c8f0103a772ba4cf1380ed587435ace37d527642f8f0cda5213`.
The new final bound-vector hash is
`05273dc57a7c8822f0cbf988d465debf1f4010004cd10299ff6e607f9ac6a3d4`.
The frozen expert Tier-B formula and policies remain mathematically valid;
matrix-derived bounds were regenerated without fitting candidate output or
changing tolerances.

Attempt 1 caught a real independent-oracle decoder bug before candidate
compute, so it made no numerical claim and needs no relabeling. M1-D is IQ2
and remains valid. Claims and benchmark rows that directly or transitively
used the old Python IQ3 ordering are marked superseded in the claims ledger;
their raw evidence remains preserved and must be rebanked before reuse.
Feature 018 integration remains outside this F017 sprint.

## Attempt-2 readiness

The exact v2 config at runtime/tooling SHA
`942f23505e5829e55bc9b6611bd08d3c93481672` has SHA-256
`4778a2694fd4a80feb5789ee3641dcd13fea3b2ba1d144dc150dde8af7d14cd7`.
Its non-consuming production preflight returned exactly
`READY_TO_EXECUTE_M1_E`; no attempt-state marker or real oracle was created.
M1-E attempt 2 remains unconsumed and M1-F remains blocked.
