# F017 M1-D Real-Projection Handoff

## Status

**PREPARED / NOT AUTHORIZED / NOT EXECUTED**

M1-D attempts remain `0`. This package authorizes nothing by itself.

## Frozen bindings

- runtime source: `291295665896c8a489c1f4e5741b199cf5515b2f`;
- M1-A: `aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805`;
- M1-B: `9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770`;
- M1-C: `343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e`;
- checkpoint set: `d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee`;
- catalog: `0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0`;
- tensor map: `ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223`.

## One boundary

`blk.0.attn_kv_a_mqa.weight`, layer 0 MLA KV latent projection, is the only
admitted tensor. Its GGUF shape is `[6144, 576]`, its logical matvec shape is
`576 x 6144`, and its output is `[576]`. It is Q8_0 in shard 2 at offset
`1,077,266,272`, with exactly `3,760,128` packed bytes and `6,528` bytes per
row. The versioned identity is
[`m1d-projection-boundary-v1.json`](../../../specs/017-rust-native-inference-runtime/contracts/m1d-projection-boundary-v1.json),
SHA-256 `d4333ab9a6cd8638434f61c4c78f729869c5690305cc6de7ba86add611443613`.

## Frozen activation and oracle

The canonical activation has 6,144 little-endian f32 values and SHA-256
`dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2`.
It was generated independently with Python 3.13.13, NumPy 2.4.5, PCG64 seed
`17017004`, by
[`generate_f017_m1d_projection_oracle.py`](../../../scripts/research/generate_f017_m1d_projection_oracle.py).
The committed real-shaped checkpoint-free oracle is
[`f017-m1d-projection-oracle-v1.json`](../../../specs/017-rust-native-inference-runtime/fixtures/f017-m1d-projection-oracle-v1.json),
SHA-256 `edcc216b046ade881ea7529dd6d39cbbca522fc5891fb628416d6fa17aac5c32`.

For the later real attempt,
[`prepare_f017_m1d_real_reference.py`](../../../scripts/research/prepare_f017_m1d_real_reference.py)
must run first. It exclusively creates the local oracle and package after one
bounded matrix read, then records the real packed, decoded, and expected-output
hashes. The runner consumes those immutable files afterward. This ordering is
validated; candidate output cannot define or alter the oracle or bounds.

## Decoder, scaffold, and Tier B

- Q8_0 decoder: `f017-q8-0-decoder-v1`, SHA-256
  `aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd`;
- exact scaffold: `f017-m1d-q8-0-sequential-f32-v1`, SHA-256
  `3948039430cf48509a63757d97a21099b6e08ea46fcf6f022df06493a5f8a6b5`;
- Tier B: `f017-production-m1d-projection-tier-b-v1`, SHA-256
  `f93e7a90684c93e78c03e054f62be932b3e16a120e63f41ba1d64f6d6e26a28b`.

The scaffold uses separately rounded f32 multiply/add in strict increasing
column order. Ten exact repeats are required. The Tier-B row bound is
`B_i = 2*gamma_(2n)*sum(abs(w_ij*x_j)) + 4*n*2^-149`, with `n=6144`,
`u=2^-24`, and `gamma_(2n)=(2n*u)/(1-2n*u)`. RMSE and cosine bounds derive
deterministically from the row bounds. Candidate output is never an input to
threshold derivation. Signed zero must match exactly; NaN/Inf is forbidden.
Greedy applicability is `not_applicable`; success is
`numerically_qualified_greedy_not_applicable`. The v1 contract is immutable.

## Canonical command

After a separate authorization creates the local-only oracle/package, execute
exactly once from the runtime SHA worktree:

```bash
f017-glm52-runner \
  --out "$PULSAR_F017_M1D_EVIDENCE" \
  --validation-mode golden-strict \
  --stream-mode owned-device \
  --memory-floor-bytes 17179869184 \
  --environment-manifest "$PULSAR_F017_ENV_MANIFEST" \
  --checkpoint-manifest "$PULSAR_F017_CHECKPOINT_MANIFEST" \
  --real-projection-boundary "$PULSAR_F017_M1D_PACKAGE" \
  --numerical-mode production-mlx-tier-b
```

The four variables are reviewed machine-local paths. Output acquisition is
exclusive. Any missing/stale binding, second projection, fallback, backend
error, lifecycle mismatch, numerical failure, or non-greedy classification
mismatch fails closed. M1-E, expert/layer/logits, P1/P2/golden-eight,
Feature 018, and output-head residency remain blocked.
