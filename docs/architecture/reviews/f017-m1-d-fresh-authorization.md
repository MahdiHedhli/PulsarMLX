# F017 Fresh M1-D Authorization Packet

## Status

**PREPARED / NOT AUTHORIZED / NOT EXECUTED**

This packet is ready for a later explicit authorization of exactly one M1-D
projection attempt. It does not authorize execution now.

The remediated runtime source is
`d68cb10758693dc61d3af7cf76b8019f6b3b235d`.
Accepted M1-A/B/C evidence hashes are, respectively,
`aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`,
`9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770`,
and `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e`.

The exact boundary, activation, decoder, scaffold, and Tier-B bindings are in
[`f017-m1-d-real-projection-handoff.md`](f017-m1-d-real-projection-handoff.md).
The checkpoint-free package passed through the canonical binary and production
MLX adapter with one conceptual projection, ten separately captured and
identically hashed native repeats, no scaffold/reference/fallback production
dispatch, structural oracle-before-candidate proof, and reconciled teardown.

A future authorization must perform, in order:

1. revalidate source, environment, M1-A/B/C, checkpoint/catalog/map identities;
2. run the independent local reference preparer once, reading only the reviewed
   Q8_0 range and exclusively freezing its immutable oracle/package before
   candidate work;
3. run the literal `--real-projection-boundary` command from the handoff once;
4. require ten ordinal output hashes, exact equality, ten native dispatches,
   and the finalized-oracle hash/ordering proof;
5. bank evidence and stop.

It must not admit a second projection, M1-E, expert/layer/logits execution,
P1/P2/golden-eight, Feature 018, or threshold retuning.
