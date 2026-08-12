# F017 Repaired M1-B Checkpoint-Identity Handoff

## Status

**REPAIRED / PREPARED / NOT EXECUTED**

M1-A remains accepted. The required runtime source for a future M1-B execution
is exactly `b29202171a279cd3bb2ac2cf4dc6b3be7486019e`. The earlier handoff pin to
`91359dd59265de71fd25848142af23823e41e160` is invalid because the intervening
delta added compiled runner code (`f017_runner::local_boundary` and its public
module binding). The M1-A commit remains evidence provenance; it is not the
M1-B executable source.

This repaired handoff and its provisioning verifier are a non-runtime
descendant of `b2920217`. Any future M1-B evidence must nevertheless report
the exact required runtime source `b2920217`, not the later documentation or
provisioning commit.

## Accepted prior gate

- M1-A evidence commit:
  `91359dd59265de71fd25848142af23823e41e160`
- M1-A public evidence SHA-256:
  `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`
- Reviewed production environment manifest SHA-256:
  `33f57e945762e1b805ede4663e6ae19ee94240936c5e87940aba5e6e5face251`

## Reviewed checkpoint binding

The canonical six-shard checkpoint was provisioned through the header/hash-only
procedure documented in
[`f017-production-checkpoint-manifest-review.md`](f017-production-checkpoint-manifest-review.md).
The private manifest is stored adjacent to the shards and is selected through
the reviewed machine-local environment file; public artifacts carry only
basenames and hashes.

- private manifest SHA-256:
  `208969118007ec0ae6e6b49f45f3d253b3bac7824b7f8f495a1fef1bcea844d4`
- checkpoint-set SHA-256:
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- catalog SHA-256:
  `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0`
- immutable revision:
  `abc55e72527792c6e77069c99b4cb7de16fa9f23`
- tokenizer identity:
  `glm52-gguf-tokenizer-v1:149e907384517d91d236a819835aa0dc97e6d4a3c512e6d5806d6b162ced1c6d`

## Frozen execution boundary

A separately authorized M1-B is exactly one
`--checkpoint-identity-only` execution from a clean worktree pinned to
`b29202171a279cd3bb2ac2cf4dc6b3be7486019e`. It may perform only:

- production-reviewed environment and measured-host admission;
- actual loaded MLX native/C identity verification;
- six-shard filename, size, and SHA-256 verification;
- checkpoint-set and catalog identity;
- GGUF header and metadata parsing;
- architecture and tokenizer identity;
- production `Glm52TensorMap` validation;
- 79 layers and all 1,809 tensor contracts;
- atomic progress/evidence writes and final evidence validation.

It must not decode a tensor, read a tensor range for numerical execution,
construct inference state, create an `MlxContext` for compute, dispatch a
projection/expert/layer/logits/token path, invoke a scaffold/reference path, or
enter M1-C/P1.

## Required machine-local bindings

The separately authorized operator must source the reviewed local configuration
that resolves:

- `F017_REVIEWED_ENVIRONMENT_MANIFEST`;
- `F017_REVIEWED_CHECKPOINT_MANIFEST`;
- a new `F017_M1_B_FRESH_EVIDENCE` path that does not exist.

Before execution, require exact hashes for both manifests and confirm that the
checkpoint manifest is selected from the unique canonical six-shard directory.
No path in this public handoff discloses the private location.

## Exact command contract

The prepared literal command is published in
[`f017-m1-b-fresh-authorization.md`](f017-m1-b-fresh-authorization.md). That
packet is **PREPARED / NOT EXECUTED** and is not authorization by itself.

## Mandatory stop

Stop after the single future M1-B result. Review it against
[`f017-m1-b-evidence-review-checklist.md`](f017-m1-b-evidence-review-checklist.md).
M1-C, tensor decode/execution, and P1 remain blocked.
