# F017 R13 Local-Boundary Fixture Preparation

## Status

Checkpoint-free validator infrastructure is implemented and the reviewed real
checkpoint identity is now bound in
[`evidence/f017-r13-checkpoint-identity-binding-v1.json`](evidence/f017-r13-checkpoint-identity-binding-v1.json).
T017-140 remains open because no real checkpoint-derived boundary fixture has
been generated or validated.

## Contract

The machine-readable schema is
[`../../specs/017-rust-native-inference-runtime/contracts/local-real-boundary-fixture-v1.schema.json`](../../../specs/017-rust-native-inference-runtime/contracts/local-real-boundary-fixture-v1.schema.json).
The Rust validator is `f017_runner::local_boundary`.

Every future local-only R13 manifest binds:

- checkpoint-set hash and immutable revision;
- exact tensor name, shard identity/hash, byte offset and length;
- quantization and dimensions;
- producing source SHA;
- decoder contract identity/hash;
- local fixture length/path/hash;
- independent generator source and input/output hashes;
- explicit `local_only_private_checkpoint_derived` privacy classification;
- `redistributable: false`.

Validation rejects duplicate JSON keys, unknown fields, malformed hashes,
empty or overflowing tensor ranges, zero dimensions, relative fixture paths,
symlinks, non-files, length/hash mismatch, redistributable private fixtures,
and non-independent provenance.

## Validator proof

Unit tests construct temporary public-safe fake shard bytes and cover:

- valid manifest plus exact local payload hash;
- duplicate-key rejection;
- relative-path rejection;
- payload-hash mismatch;
- offset overflow;
- non-independent reference provenance.

The original validator work was checkpoint-free. A later explicitly authorized
manifest-provisioning pass streamed all six real shard hashes and parsed only
GGUF headers/catalogs. That pass bound the immutable revision, checkpoint-set
hash, shard identities, catalog hash, tensor-map version/hash, and local-only
privacy policy without generating a tensor payload fixture. It recorded zero
tensor execution, quant decode, and model compute.

## Remaining T017-140 gate

T017-140 may close only after a separately authorized local extraction creates
at least one real-boundary manifest and the validator proves its checkpoint,
tensor, decoder, fixture, reference, and privacy identities. That later step is
part of the M1-C admission ladder and is not authorized here.
