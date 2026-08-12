# F017 M1-D attempt 2 handoff

Status: **PREPARED / NOT AUTHORIZED / NOT EXECUTED**

This handoff supersedes no historical artifact. Attempt 1 remains rejected as
`FAIL_INFRASTRUCTURE_EVIDENCE / m1d_contract_read`; its public evidence SHA-256
is `a5aefaaf59583dad87765303e159986c895017c20ea80eb874cd447ad80f9a62`.

## Runtime and path semantics

- Runtime source: `258127d4b5e4d2cca592c8b3ec5403a98e39f29f`
- Prior failed runtime: `d68cb10758693dc61d3af7cf76b8019f6b3b235d`
- Package schema: `pulsarmlx.f017.m1d-projection-package` version `2.0.0`
- Path contract: `f017-m1d-artifact-path-resolution-v1`
- Path contract SHA-256: `40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d`

The runner requires an explicit `--repository-root`. It canonicalizes that
root, rejects a symlink root, and requires its Git HEAD to equal the compiled
runtime SHA. `repository_relative` artifacts resolve only beneath that root.
`package_relative` artifacts resolve only beneath the canonical parent of the
private package. Both namespaces reject non-normal components and symlinks and
verify content SHA-256 before parsing or use. There is no cwd or package-parent
fallback for repository artifacts.

## Frozen numerical boundary

- Tensor: `blk.0.attn_kv_a_mqa.weight`
- Shape/type: `[6144,576]`, Q8_0, logical `576 x 6144`
- Boundary: `d4333ab9a6cd8638434f61c4c78f729869c5690305cc6de7ba86add611443613`
- Activation: `dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2`
- Decoder: `aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd`
- Scaffold: `3948039430cf48509a63757d97a21099b6e08ea46fcf6f022df06493a5f8a6b5`
- Tier B: `f93e7a90684c93e78c03e054f62be932b3e16a120e63f41ba1d64f6d6e26a28b`
- Repeat integrity: `1e8ceff5bca49d8c22c38342c3e938af189b819333c075558e1e242869a6685f`
- Oracle ordering: `f8b2d48d4a3ff4ef502c33c4b29c4f2390f80ff4d03a2964c988a189ea341528`

No numerical byte, decoder behavior, scaffold ordering, or Tier-B threshold was
changed by the path remediation.

## Provenance

- Activation generation source: `29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984`
- Fixture finalization source: `0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92`
- Attempt-2 real-reference preparer: `0d1d70671ab424e0dc9bead70dfba58756126bd6d6669cb08fe5e022ed4761d4`

The preparer change is path-schema-only. It receives the explicit repository
root/runtime identity and emits repository-relative contract references plus a
package-relative oracle reference. It does not change Q8_0 decode, activation,
sequential accumulation, or Tier-B derivation.

## Canonical commands

Oracle/package preparation (only after a separate attempt-2 authorization):

```text
python3 scripts/research/prepare_f017_m1d_real_reference.py \
  --target-shard <reviewed-shard-2> \
  --checkpoint-manifest <reviewed-private-checkpoint-manifest> \
  --activation-oracle specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json \
  --repository-root <absolute-trusted-runtime-worktree> \
  --runtime-source-sha 258127d4b5e4d2cca592c8b3ec5403a98e39f29f \
  --output-oracle <fresh-private-package-root>/f017-m1d-real-oracle-v1.json \
  --output-package <fresh-private-package-root>/f017-m1d-real-package-v2.json
```

Candidate command:

```text
f017-glm52-runner \
  --out <fresh-exclusive-public-evidence.json> \
  --validation-mode golden-strict \
  --stream-mode owned-device \
  --memory-floor-bytes 17179869184 \
  --environment-manifest <reviewed-production-environment.json> \
  --repository-root <absolute-trusted-runtime-worktree> \
  --checkpoint-manifest <reviewed-private-checkpoint-manifest> \
  --real-projection-boundary <fresh-private-package-root>/f017-m1d-real-package-v2.json \
  --numerical-mode production-mlx-tier-b
```

Exactly one conceptual projection and ten native repeats are admitted. Stop
after attempt 2. M1-E, a second projection, layers, logits, P1/P2, and
golden-eight remain unauthorized.
