# F020 bounded selected expert content: Studio capture

Host capture source `cd98e0465a0c91338c212cef7b73c2a645dbeb60` follows
reviewed range source `5973a176` and published evidence `8932939e`, whose
required CI passed. Exact source review attempt 2 accepted with zero blockers
using `claude-opus-5-5`. Attempt 1 ended in a provider tool-call parsing error
without a valid verdict; its capsule and raw response are retained privately.

The admitted Studio run bound the prior metadata identity, loaded layer 3 /
expert 0's nine original packed ranges, and wrote a private selected snapshot:

| Measure | Result |
| --- | --- |
| Geometry | E=288, D=4096, H=2048 |
| Recipe | 4/4/4-bit, group 64, BF16 metadata |
| Original selected payload requested/read | 14,155,776 bytes, nine range attempts |
| Snapshot payload written | 14,155,776 bytes |
| Snapshot including bounded manifest | 14,159,388 bytes |
| Real native calls | 0 |
| Whole-checkpoint loads / original shard hashes / downloads | 0 / 0 / 0 |
| Independent snapshot framing and nine hashes | PASS |
| Host tests | 21 PASS; no sparse skips |
| Portable workspace tests | 658 PASS, zero failures, three ignored; f017-native excluded |
| Scoped format / Clippy / workspace check | PASS / PASS / PASS |
| Independent verifier synthetic mutation/refusal tests | 6 PASS |

Snapshot SHA-256 is
`43e251a64d1d475900214d3c51b9b21ca988e7b6634d3891fbc6c3a0d5733305`.
It identifies the captured selected content, not the whole checkpoint. Raw bytes
and raw capture receipts remain in the private Studio audit. Sanitized custody
and source/review bindings are in
[`selected-payload-studio-evidence-v1.json`](../../specs/020-mlx-safetensors-affine/qualification/selected-payload-studio-evidence-v1.json).
The exporter never opens model or snapshot payloads. The independent verifier
reads only the small selected snapshot, and performs byte/hash checks, not R1
or numerical evaluation.

Source stamp checks retain their timestamp-granularity limits. Mode 0400
reduces accidental mutation; future consumers must reverify hashes. File flush
does not guarantee crash durability of its parent-directory entry. Counter
deltas are used with the example's single-threaded source; they do not establish
physical SSD traffic or a global concurrent memory bound. Host results do not
qualify Linux/CUDA execution or native real-expert numerics. Publication and CI
results must be checked separately from these capture receipts.

Each full real projection requires 8,388,608 MACs; the accepted synthetic
composition caps each QMM at 2^21 and covers D/H=64 or 128. The next numerical
gate needs independent original-byte R1, a prospectively frozen original F32
input, an exact reviewed bounded native adapter and a separately qualified
geometry/MAC extension (or a correctly labeled bounded block). E_act=1/128,
beta_B=5201/4194304 and the declared down admission floor remain unchanged.
This capture grants no full-shape numerical capability, routing/aggregation,
model generation or performance claim.
