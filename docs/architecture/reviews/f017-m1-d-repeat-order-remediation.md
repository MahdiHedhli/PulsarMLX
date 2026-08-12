# F017 M1-D Repeat/Ordering Remediation

## Disposition

**READY FOR FRESH M1-D AUTHORIZATION**

This checkpoint-free remediation moved the M1-D runtime boundary from
`291295665896c8a489c1f4e5741b199cf5515b2f` to
`d68cb10758693dc61d3af7cf76b8019f6b3b235d`. M1-D attempts remain zero and no
real M1-D matrix payload was accessed.

## Repeat proof

The production loop now synchronizes and reads every repeat, serializes all
576 f32 lanes in canonical little-endian order, and records hashes for exact
ordinals `0..9` before buffer reuse. PASS requires ten observed hashes, exact
equality to repeat 0, a selected hash bound to repeat 9, and ten native
dispatches. A checkpoint-free one-bit injection at repeat 5 fails with
`m1d_repeat_divergence` even though the final repeat remains clean.

## Oracle ordering proof

The independent preparer exclusively creates a read-only finalized oracle.
The runner validates its schema and bound SHA, re-hashes it immediately before
candidate start, records structural sequence markers and strict timestamps,
then re-hashes the package again after execution. Missing/equal/late markers,
stale hashes, boolean-only claims, and post-validation mutation all fail.

## Frozen numerical package

The boundary, activation payload, decoder, exact scaffold, and Tier-B hashes
remain respectively:

- `d4333ab9a6cd8638434f61c4c78f729869c5690305cc6de7ba86add611443613`;
- `dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2`;
- `aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd`;
- `3948039430cf48509a63757d97a21099b6e08ea46fcf6f022df06493a5f8a6b5`;
- `f93e7a90684c93e78c03e054f62be932b3e16a120e63f41ba1d64f6d6e26a28b`.

The checkpoint-free expected output remains
`17dd54b26bcd170128eb9cb80d3ae64188e199c7d00cf1396af150a32276f8c9`.
No threshold or numerical payload changed.

## Validation boundary

Workspace check/tests, deterministic oracle regeneration, oracle finalization
tests, repeat/applicability negative tests, and the Apple-native synthetic M1-D
integration passed locally. The native integration recorded one conceptual
projection, ten identical output hashes, ten native dispatches, zero
scaffold/reference/fallback/errors, valid structural ordering, and reconciled
lifecycle. Final-head CI is required before execution authorization.

M1-E, T017-141, P1/P2/golden-eight, Feature 018, and output-head residency
remain blocked.
