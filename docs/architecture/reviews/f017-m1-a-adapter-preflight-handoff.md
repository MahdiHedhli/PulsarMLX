# F017 Prepared M1-A Adapter-Preflight Handoff

## Status

Prepared, not authorized. Use only after the internal implementation review
returns GO on the exact final head containing the environment-isolation fix and
that head has green Apple-native CI. A fresh operator prompt must authorize
exactly one execution.

## Exact stage boundary

M1-A is `--adapter-preflight-only` and nothing else. It must use:

- the exact final SHA named by the internal GO disposition;
- the reviewed `production_reviewed` environment manifest;
- the pinned arm64 MLX native 0.31.2 / MLX C 0.6.0 installation;
- `--stream-mode owned-device`;
- `--memory-floor-bytes 17179869184`;
- a fresh, exclusively acquired evidence path;
- measured host telemetry and mandatory loaded-library verification.

The canonical command shape is:

```sh
cargo run --locked -p f017-runner --bin f017-glm52-runner -- \
  --adapter-preflight-only \
  --out "$F017_M1_A_FRESH_EVIDENCE" \
  --validation-mode golden-strict \
  --stream-mode owned-device \
  --memory-floor-bytes 17179869184 \
  --environment-manifest "$F017_REVIEWED_ENVIRONMENT_MANIFEST"
```

The two machine-local variables must be resolved and recorded by the future
authorization. The output must not exist. The environment manifest must match
the reviewed content hash and identify the actually loaded pinned libraries.

## Required behavior

- reject any non-`production_reviewed` environment before adapter creation;
- reject synthetic telemetry;
- verify actual loaded MLX native/C images and hashes;
- accept no checkpoint argument and touch no checkpoint path;
- exercise the production `MlxContext`, ownership, synchronization, and
  teardown lifecycle;
- persist PASS only after full reconciliation;
- stop immediately after evidence validation.

## Still blocked

This handoff does not authorize M1-B. M1-B requires review of M1-A evidence and
a separate prompt. T017-140/M1-C, T017-141/P1 command publication, P1,
Feature 018 integration, and output-head residency remain blocked.

