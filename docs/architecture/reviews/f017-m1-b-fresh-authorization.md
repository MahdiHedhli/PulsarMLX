# F017 Fresh M1-B Authorization Packet

## Status

**PREPARED / NOT EXECUTED / NOT SELF-AUTHORIZING**

This packet is ready for a fresh explicit authorization. It does not authorize
or execute M1-B, M1-C, tensor decode/execution, projection, MLX compute, or P1.

## Frozen bindings

- required runtime source:
  `b29202171a279cd3bb2ac2cf4dc6b3be7486019e`
- accepted M1-A public evidence SHA-256:
  `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`
- reviewed environment manifest SHA-256:
  `33f57e945762e1b805ede4663e6ae19ee94240936c5e87940aba5e6e5face251`
- reviewed checkpoint manifest SHA-256:
  `208969118007ec0ae6e6b49f45f3d253b3bac7824b7f8f495a1fef1bcea844d4`
- checkpoint-set SHA-256:
  `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`
- catalog SHA-256:
  `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0`

## Required operator-provided local values

Before a future run, set:

- `F017_M1_B_RUNTIME_WORKTREE`: a clean worktree pinned to the required runtime
  source;
- `F017_M1_B_LOCAL_CONFIG`: the reviewed permission-restricted local file that
  exports the environment and checkpoint manifest paths;
- `F017_M1_B_FRESH_EVIDENCE`: one new path that does not exist.

The local configuration must resolve the two reviewed manifests above. Public
documents intentionally do not disclose its absolute path.

## Exact canonical command

```sh
set -euo pipefail
: "${F017_M1_B_RUNTIME_WORKTREE:?}"
: "${F017_M1_B_LOCAL_CONFIG:?}"
: "${F017_M1_B_FRESH_EVIDENCE:?}"

cd "$F017_M1_B_RUNTIME_WORKTREE"
test "$(git rev-parse HEAD)" = \
  b29202171a279cd3bb2ac2cf4dc6b3be7486019e
test -z "$(git status --porcelain)"

. "$F017_M1_B_LOCAL_CONFIG"
test "$(shasum -a 256 "$F017_REVIEWED_ENVIRONMENT_MANIFEST" | awk '{print $1}')" = \
  33f57e945762e1b805ede4663e6ae19ee94240936c5e87940aba5e6e5face251
test "$(shasum -a 256 "$F017_REVIEWED_CHECKPOINT_MANIFEST" | awk '{print $1}')" = \
  208969118007ec0ae6e6b49f45f3d253b3bac7824b7f8f495a1fef1bcea844d4
test ! -e "$F017_M1_B_FRESH_EVIDENCE"

caffeinate -dimsu cargo run --locked -p f017-runner \
  --bin f017-glm52-runner -- \
  --checkpoint-identity-only \
  --checkpoint-manifest "$F017_REVIEWED_CHECKPOINT_MANIFEST" \
  --out "$F017_M1_B_FRESH_EVIDENCE" \
  --validation-mode golden-strict \
  --stream-mode owned-device \
  --memory-floor-bytes 17179869184 \
  --environment-manifest "$F017_REVIEWED_ENVIRONMENT_MANIFEST"
```

## One-attempt and isolation rule

A fresh prompt may authorize this command exactly once. On the first admission,
identity, evidence, or infrastructure failure, preserve the result and stop;
do not patch, replace a shard, or retry.

The run may hash/read headers/catalog and validate tokenizer plus the production
79-layer / 1,809-tensor map. It must record zero tensor execution, zero quant
decode, zero projection/layer execution, zero adapter compute, and zero
reference/scaffold/fallback dispatch. Stop after M1-B evidence. M1-C and P1
remain separately blocked.
