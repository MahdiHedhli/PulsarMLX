# F017 M1-E Native Loader Remediation

## Preserved failure

The first attempt-3 preflight under config
`ce451e77215b3d3f99e69e96e50af1a2f0d9b3d9b7bbe3435fcd64cbec53d9d5`
failed before attempt consumption or checkpoint access. The attested release
runner linked `@rpath/libmlxc.dylib` and `@rpath/libmlx.dylib`, had no
`LC_RPATH`, and the canonical launcher did not construct a loader environment.
Dyld therefore rejected the process before the runner could emit
`READY_TO_EXECUTE_M1_E`.

Primary class: `INFRASTRUCTURE`. First failure: `m1e_native_library_load`.
Attempt 3 remained `AUTHORIZED_NOT_EXECUTED`; no state marker, oracle, tensor
read, or MLX dispatch was created.

## Minimal remediation

Runtime/tooling commit: `1da693665e5635ad404d472f395a4a407dd348fc`.
Launcher SHA-256:
`c7be6fe622c94b05ee73c10b525f0ad891c0c286da53d184f1eb954760c5b158`.

The canonical launcher now derives the native library directory solely from
the already hash-bound production environment manifest. It verifies the
reviewed `libmlx.dylib` and `libmlxc.dylib` hashes, removes inherited dyld
overrides, and supplies the resulting environment to both preflight and the
candidate runner. No path is accepted from the CLI, current working directory,
or ambient environment.

The arm64 release executable remains intentionally valid without an embedded
`LC_RPATH`, proving that the repaired config-driven launcher closes the exact
failure. Its SHA-256 is
`720a4c61bdc61b5f5fdd1ba479b0a3543a5bcded1d7d10d2e146b9c7eea08919`.

## Regression evidence

- unreviewed `DYLD_LIBRARY_PATH` is replaced by the manifest-bound directory;
- wrong native-library content hashes fail closed;
- canonical synthetic M1-E passes with one expert, ten deterministic repeats,
  thirty native matvec dispatches, oracle ordering, and reconciled lifecycle;
- the full Python suite, workspace check/test, M1-D regressions, decoder-v2,
  repeat divergence, and oracle-order failures remain green.

Frozen expert, decoder, activation, scaffold, Tier-B, and oracle numerical
semantics are unchanged.
