# Selected numerical v2 implementation plan

Branch: feat/020-real-expert-numerical-admission-20261004.
Base bff720bd4ddc83fcf6c41ed4c58a938d8c2c33ef. Sequential sole worker.
Python stdlib exact integer/rational R1 and fixtures; additive Rust owned
snapshot adapter and existing pinned C++ activation/MLX-C bridge. No installs.

## Phase 0 decisions

See research.md. Source inspection found dense inherited Fraction matrices and
an M1 reference exponent shortcut; do not reuse those as full-shape authority.
Read accepted contracts without changing their scope. Input v2 has positive DC
and alternating structure, no zero group sums. Real admissibility unknown.

## Phase 1 design

See contracts/selected-numerical-v2.json and population-v2.md. First implement
input/fixture declarations, analytic synthetic domains and host tests. Then
bounded strict snapshot readers in Python and Rust independently; row-streamed
R1 in scripts/research/f020_selected_r1_v2.py and additive Rust adapter in
crates/mlx-expert-mlp/src/selected_snapshot.rs. Keep accepted sources unchanged
except explicit additive integration. No candidate observation during build.

## Phase 2 gates

1. Host tests, resource ledger and negative controls; freeze complete source,
   interpreter/build/executable, input and generated synthetic manifest hashes.
2. Claude CLI tools disabled, source/synthetic-only exact review ACCEPT/0;
   verify raw response and exact bindings. Rejected versions preserved.
3. Bounded synthetic reference/candidate population, owned process watchdog and
   handle census, full geometry plus inherited 363+32 regression qualification.
4. Review binding still exact; selected snapshot only, original R1 pre-admission;
   refusal stops real candidate. Otherwise one real candidate, local+ideal gates.
5. Sanitized evidence review, validated narrow push and required CI to terminal.

## Constitution check before/after design

I/VI: original-byte oracle, fixed prospective tolerances; no performance work.
II/V: additive selected adapter; old portable/Linux/CUDA behavior unchanged,
portable checks mandatory and Linux claims require CI. III/VII/VIII: planning,
synthetic coverage and real qualification separate; exact commands and bounds.
IV: Studio pinned device, memory accounting, refusal and owned cleanup.
IX/X/XI: attribution preserved, focused tested changes, no weights/private
receipts/capsules in Git or external review. XII: linked spec/tasks/contract.
No constitution exception requested. Implementation/measurement gates pending;
this design check does not assert numerical validity.

## Adapter implementation detail (before native source changes)

The owned adapter stages one role at a time from validated snapshot buffers to
HostTensor packed U32/BF16 arrays and applies inherited check_qmm unchanged.
An additional selected-only shape/MAC gate admits exactly M1 with the two
specified N/K shapes. Exponents must equal273/145. Activation will use a
separately named source/symbol restricted to M1/H2048; the accepted 128-lane
shim must not gain an unconditional geometry relaxation. No native entrypoint
is enabled until review/capability/resource verification is implemented.

## Exact authority integration

A source-only package verifier will independently parse strict raw provider JSON,
match actual modelUsage and ACCEPT/0, and compare the assessed descriptor to the
capsule. The descriptor binds commit/tree, complete source file hashes, build
command/toolchain/executable, contract/input/population and native pins. The
current clean tree and each original source file must match before any numerical
capability. A preliminary host verdict cannot satisfy this schema. Parser tests
use explicitly synthetic provider documents and never create execution authority.

Synthetic positive snapshots use the same PLSEX001 framing and exact selected
geometry, with explicitly synthetic checkpoint/metadata identities and fixture
component hashes. Create-only generation records all bytes and full snapshot
hashes before review. Real bindings come only from the fixed contract/public
accepted capture hash; never from the untrusted snapshot's own declarations.

### Exact source package and capability issuer

The freezer includes tracked transitive crate sources, build scripts, lockfile,
selected tests/design/contract, original synthetic definitions and inherited
reference/acceptance methods. It rejects dirty source and never consumes real
snapshot bytes. Its descriptor binds commit/tree, every source hash, executable,
regression executables, interpreter, compiler/build flags and pinned libraries.
The review capsule additionally contains the generated synthetic manifest only.
A separate issuer accepts an actual final raw provider response only through
the independent authority validator. Issuing a synthetic capability does not
execute it. The sole worker records the one real attempt in the preserved audit;
create-only attempt files prevent silent retries in the chosen attempt directory.
Inherited summaries are checked before new synthetic execution, with their
separate primitive/plane schemas and raw-child digests. No missing evidence can
be repaired by treating a partial synthetic run as qualification.
