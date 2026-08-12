# F017 Prepared M1-B Checkpoint-Identity Handoff

## Status

**PREPARED / NOT AUTHORIZED**

M1-A is accepted at post-evidence commit
`91359dd59265de71fd25848142af23823e41e160` and public evidence SHA-256
`aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`.
This packet does not authorize M1-B. A separate prompt must resolve the local
checkpoint-manifest path, authorize exactly one execution, and require a stop
after evidence review.

## Frozen execution boundary

M1-B is exactly one `--checkpoint-identity-only` execution from a worktree
pinned to commit `91359dd59265de71fd25848142af23823e41e160`. It may perform only:

- reviewed production-environment and measured-host admission;
- actual loaded MLX native/C identity verification;
- six-shard filename, size, and SHA-256 verification;
- checkpoint-set and catalog identity;
- GGUF header and metadata parsing;
- architecture and tokenizer identity;
- production `Glm52TensorMap` validation;
- exactly 79 layers and all 1,809 tensor contracts, including names, shapes,
  quantizations, and required metadata;
- atomic progress/evidence writes and final evidence validation.

It must not:

- decode a tensor or read a tensor range for execution;
- construct an inference layer/model state;
- create an `MlxContext` for compute;
- execute a projection, expert, layer, logits boundary, or token;
- invoke a scaffold/reference path;
- run M1-C or P1.

## Required local bindings

The future authorization must resolve and record these machine-local values:

- `F017_REVIEWED_ENVIRONMENT_MANIFEST`: the production-reviewed manifest whose
  SHA-256 is
  `33f57e945762e1b805ede4663e6ae19ee94240936c5e87940aba5e6e5face251`;
- `F017_REVIEWED_CHECKPOINT_MANIFEST`: a pre-reviewed production checkpoint
  manifest stored adjacent to the canonical six shards;
- `F017_M1_B_FRESH_EVIDENCE`: a nonexistent path on the evidence volume.

The current reviewed local environment package does not contain a production
checkpoint manifest. Therefore the checkpoint-manifest variable must remain
unresolved until the separate M1-B authorization verifies its provenance.
This packet does not search for shards or manufacture a runnable path.

## Canonical command

After the separate authorization resolves those variables, the literal command
is:

```sh
test "$(git rev-parse HEAD)" = \
  91359dd59265de71fd25848142af23823e41e160
test ! -e "$F017_M1_B_FRESH_EVIDENCE"

cargo run --locked -p f017-runner --bin f017-glm52-runner -- \
  --checkpoint-identity-only \
  --checkpoint-manifest "$F017_REVIEWED_CHECKPOINT_MANIFEST" \
  --out "$F017_M1_B_FRESH_EVIDENCE" \
  --validation-mode golden-strict \
  --stream-mode owned-device \
  --memory-floor-bytes 17179869184 \
  --environment-manifest "$F017_REVIEWED_ENVIRONMENT_MANIFEST"
```

The separate authorization must retain this full commit binding without
advancing the execution worktree.

## Mandatory stop

Stop immediately after the single M1-B result is preserved. Do not execute a
tensor, M1-C, or P1. Review the evidence against
[`f017-m1-b-evidence-review-checklist.md`](f017-m1-b-evidence-review-checklist.md)
before considering any further authorization.
