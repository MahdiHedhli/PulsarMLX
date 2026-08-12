# F017 M1-D Attempt 2 Evidence Review

**Verdict: M1-D ATTEMPT 2 REJECTED**

Date: 2026-08-12

## Binding and admission

The pre-access reconciliation passed at runtime
`258127d4b5e4d2cca592c8b3ec5403a98e39f29f`, tooling
`dc95783c9e2666989b038f2744f7b12e2756aa18`, and repository head
`53165bb5ac78bca087e82fe769bdb14110a4df4c`. The attempt-2 handoff hash was
`bd3f1d177190306697a32f2fd71fc1aa39be3eb1cede2a4114849e8faa4ca68b`.
All M1-A/B/C, checkpoint, catalog, map, frozen numerical, path-schema, and
provenance bindings matched. In particular, the current preparer hash was
`0d1d70671ab424e0dc9bead70dfba58756126bd6d6669cb08fe5e022ed4761d4`;
the historical preparer was rejected.

Production admission passed with a `production_reviewed` environment,
measured-host telemetry, arm64 identity, exact loaded MLX hashes, 80.76 GiB
available memory, normal memory pressure and thermal state, clear competing
inference, and no port 1234 listener.

## First failure

The attempt stopped in the independent preparer before checkpoint access. The
launch command supplied
`specs/017-real-checkpoint-runner/fixtures/f017-m1d-projection-oracle-v1.json`,
which does not exist. The immutable handoff correctly specifies
`specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json`.
This was command assembly/operator error, not a path-resolver regression and
not a numerical result.

- classification: `FAIL_INFRASTRUCTURE_EVIDENCE`
- failure code: `m1d_activation_fixture_read`
- activation fixture opened: `false`
- checkpoint opened: `false`
- real matrix payload count: `0`
- oracle/package artifacts created: `false`
- candidate started: `false`
- conceptual projections: `0`
- native dispatches/repeats: `0/0`

The no-retry rule was enforced. Attempt 2 is consumed and preserved as a
distinct rejection; attempt 1 remains unchanged. No Tier-B, repeat-integrity,
oracle-order, lifecycle-PASS, or production numerical claim is made.

## Review answers

1. Repository/package path-resolution result? **Not reached by the candidate.**
2. Attempt-2 preparer exact? **Yes; source hash matched before invocation.**
3. Exactly one real matrix payload? **No; zero payloads were accessed.**
4. Oracle independent and finalized? **No; preparation stopped before input load.**
5. Exactly ten repeat hashes? **No; the candidate never started.**
6. Tier-B passed? **No result.**
7. Compute and tensor execution zero? **Yes.**
8. Private paths sanitized? **Yes; only repository-relative symbolic paths are public.**
9. Is M1-E meaningful or authorized? **No.**

Another M1-D execution would require a separately reviewed, explicit attempt-3
authorization. This review does not prepare or authorize M1-E.
