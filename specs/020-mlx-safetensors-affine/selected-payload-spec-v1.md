# F020 selected expert payload freeze

This additive host-only gate follows reviewed range source `5973a176` and
published evidence `8932939e`. Both required CI suites passed. It does not
change the accepted native primitive, activation or synthetic-composition
contracts. Real numerical candidate observations are outside this gate.

The first capture is layer 3, expert 0, E=288, D=4096, H=2048, gate/up/down
default 4-bit, group 64, BF16 metadata. Bind the metadata identity from the
previous private metadata-only plan. Read exactly nine catalog-derived ranges,
14,155,776 bytes, through the reviewed sealed plan. The existing 32 MiB selected
budget applies before payload allocation/read. No full original file hashing,
whole tensor load, mmap, dequantization, MLX or native call is permitted.

The snapshot writer receives the sealed plan and a mandatory lowercase 64-digit
expected metadata SHA-256. It refuses a mismatch, relative/non-snapshot output,
oversized manifest or existing output before reading payload. It exclusively
creates a private output file (mode 0600) before loading, keeps the descriptor
open, and writes the original owned packed buffers without decoding. Success
requires complete writes and flush; the file becomes mode 0400. Partial or empty
failure artifacts remain private for diagnosis and are never successful captures.
The caller supplies an authorized private output parent; this interface is not a
general hostile-parent filesystem confinement mechanism.

Format: 8-byte magic `PLSEX001`, little-endian u64 header length (maximum 128 KiB),
UTF-8 JSON manifest, then nine original ranges in gate/up/down order and
weight/scales/biases component order. The manifest embeds the owned receipt and
nine lengths. The receipt includes metadata identity, declared roles, original
ranges, recipes and nine selected-range hashes. The entire small snapshot also
gets a SHA-256. A future independent reader must bound and validate this framing,
all lengths/hashes and the exact content before consuming it. Snapshot identity
is selected-content identity, not a checksum of the complete checkpoint.

Successful counters distinguish requested source payload bytes/read calls from
snapshot payload bytes written. Physical SSD traffic and kernel copies are
unknown. The application does not clone or expand the nine payload buffers;
small JSON serialization is separately bounded. File permissions reduce accidental
mutation; they are not an atomic snapshot or protection against the owner/root.
Future consumption must revalidate the content hashes. Original source stamp
checks retain the reviewed timestamp-granularity limits.

Tests cover independent framing/hash/byte reconstruction, metadata/output
refusals before any payload read, preservation of existing outputs and symlinks,
descriptor mutation refusal with a retained empty artifact, and real 4096/2048
storage geometry on a synthetic sparse 288-expert shard. A bounded sparse probe
precedes the large logical fixture. Report any sparse skip honestly. These are
host storage tests, not numerical tests or real-model generation.

Exact source and host results must be frozen and independently reviewed before
the first real payload capture. Preserve review/failure attempts. The real
capture is one admitted run on Studio, never ColPanicM2. Raw bytes stay in the
private Studio audit and are never committed or sent to a reviewer. Only source,
synthetic fixtures and sanitized metadata/hash receipts enter review packets.

## Prospective real geometry and MAC boundary

Storage can admit the full selected shape without numerical execution. At M=1,
each real projection has 8,388,608 MACs (4096*2048), exceeding the accepted
synthetic composition's per-QMM 2^21 cap and D/H=64 or 128 population. This
snapshot gate therefore grants no full-shape numerical capability.

A subsequent full-shape extension must freeze the input, independent original-
byte R1, native adapter, prospective population, resource caps and unchanged
bound method before candidate observations. Preserve E_act=1/128 and
beta_B=5201/4194304. Establish finite values and actual gate/up, activation and
down-input domains, then prove the down admission floor or stop on failure.
Candidate hidden state may support local down admission, never replace ideal R1.
No clipping, rescaling or tolerance repair after observing outputs is permitted.

Before a real native case, qualify a separately reviewed bounded synthetic
real-geometry population. Alternatively, define and accurately label a smaller
block experiment within the existing capability; its result cannot qualify the
complete real expert. The current gate intentionally provides original packed
content for that independent work and does not choose either numerical path.
