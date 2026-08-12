# F017 M1-D attempt 3 command-assembly forensics

## Attempt 2 failure chain

Attempt 2 was assembled manually from the reviewed handoff. The handoff named
the activation fixture as
`specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json`,
but the launched preparer command supplied
`specs/017-real-checkpoint-runner/fixtures/f017-m1d-projection-oracle-v1.json`.
That second path does not exist.

The wrong value came from manual/prompt command assembly. It did not come from
the handoff parser, authorization parser, shell wrapper, environment, a CLI
default, or a hard-coded test constant. `prepare_f017_m1d_real_reference.py`
accepted the loose `--activation-oracle` argument and attempted to open it
before opening the checkpoint. The attempt therefore stopped with
`m1d_activation_fixture_read`, zero checkpoint reads, zero projections, and
zero native dispatches.

The attempt-2 authorization validator passed because it validated the packet,
handoff hash, provenance hashes, and frozen contracts. It did not render the
actual launch config or compare launch arguments back to the authorization.
The reviewed value and launched value could consequently diverge after review.

## Authoritative command contract

Attempt 3 uses exactly one data flow:

`machine-readable authorization -> validated typed execution config -> config-only preparer/runner invocation`

The validated config is serialized once with exclusive-create semantics and
content-addressed by SHA-256. Human-readable commands contain only its path and
expected hash. Loose activation, contract, repository-root, checkpoint, and
output overrides are forbidden in the config-only invocation.

The activation symbolic path is an identity field, not merely a way to find
bytes. Identical bytes at another symbolic path are rejected. Repository
artifacts resolve only below the explicitly trusted repository root; private
artifacts resolve only below the private package root. Neither cwd nor an
environment variable participates in resolution.

## Attempt consumption

Rendering and validating the immutable execution config is a non-consuming
preflight. Attempt 3 becomes consumed only when the separately authorized
production invocation transitions to execution and creates its attempt
evidence state. This remediation performs only preflight and synthetic work.
Attempts 1 and 2 remain immutable rejected attempts; attempt 3 remains
unconsumed.
