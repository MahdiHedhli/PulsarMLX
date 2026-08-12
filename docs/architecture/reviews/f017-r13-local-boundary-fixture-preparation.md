# F017 R13 Local-Boundary Fixture Preparation

## Status

Checkpoint-free validator infrastructure is implemented. T017-140 remains
open because no real checkpoint-derived boundary fixture has been generated or
validated.

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

## Checkpoint-free proof

Unit tests construct temporary public-safe fake shard bytes and cover:

- valid manifest plus exact local payload hash;
- duplicate-key rejection;
- relative-path rejection;
- payload-hash mismatch;
- offset overflow;
- non-independent reference provenance.

No real shard was searched, opened, statted, hashed, or copied while preparing
this infrastructure.

## Remaining T017-140 gate

T017-140 may close only after a separately authorized local extraction creates
at least one real-boundary manifest and the validator proves its checkpoint,
tensor, decoder, fixture, reference, and privacy identities. That later step is
part of the M1-C admission ladder and is not authorized here.
