# Feature 002 Reviewer Index

**Status**: Real Apple MLX layer-0 router evidence is published as two append-only
raw experiment records plus regenerated tables and figures. Claims remain
provisional pending clean-checkout reproduction. Expert execution, aggregation,
generation, serving, and tokens-per-second remain unsupported.

The governing package is the [Feature 002 specification](../../specs/002-qwen-router-parity/spec.md),
[plan](../../specs/002-qwen-router-parity/plan.md), [quickstart](../../specs/002-qwen-router-parity/quickstart.md),
[research-evidence contract](../../specs/002-qwen-router-parity/contracts/research-evidence-v1.md),
[router contract](../../specs/002-qwen-router-parity/contracts/router-parity-v1.md),
and [experiment protocol](EXPERIMENT_PROTOCOL.md).

## Raw evidence

The exact independent CPU reference remains the byte-identical
[raw support record](raw/002-router-parity/oracle/f002-router-oracle-freeze-0001.json)
and [review fixture](../../fixtures/research/router-v1/real/f002-router-oracle-freeze-0001.json),
bound by the [manifest](../../fixtures/research/router-v1/real/manifest.json).
Support-record SHA-256:
`3f570ce97f45902a1717d3770c6665d1023d8ccfc18266e25229bc1e86725133`.

Admitted real Apple experiment records (measured source commit
`04b3502aa5cfbe48cda66d1a5b0b07a45902f762`):

- [primary batch-a](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-a.json)
  SHA-256 `b5925db8ba68d90a42507e00be6d3159457a2b97d9fc827f0200245cb20851fa`
- [later batch-b](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-b.json)
  SHA-256 `99346e8be81b4975cb355759be20872aefdea05baa9960f28aa272d970116801`

Both records report `actual_status: passed`, exact top-8 parity, zero ID/order
mismatches, evaluated synchronized `apple-mlx`/`gpu`, no fallback, and the
frozen unsupported-interpretation boundary for everything deeper than the
layer-0 router. Source candidate SHA-256
`b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4`.

Accepted model-free methodology fixtures remain the synthetic
[passed fixture](../../fixtures/research/router-v1/evidence/f002-router-fixture-0001.json),
[failed fixture](../../fixtures/research/router-v1/evidence/f002-router-fixture-failed-0001.json),
and [aborted fixture](../../fixtures/research/router-v1/evidence/f002-router-fixture-aborted-0001.json).

Two earlier external producer candidates failed independent post-processing and
are intentionally not indexed as public evidence.

## Generated tables

Committed generated tables from the real raw records:

- [Markdown summary](tables/002-router-parity-summary.md)
  SHA-256 `eabf9ff1c13a401be9be30648d6c933b078f323472fbe3f43322e0d0ff22f8fb`
- [Markdown sidecar](tables/002-router-parity-summary.md.sources.json)
  SHA-256 `7cf8b4cb6731078e0aa2bfc24620a959cdcc09f893f1d6b5e1b97f2e9a2f0e01`
- [CSV summary](tables/002-router-parity-summary.csv)
  SHA-256 `1476c2a39217365fe93ea84f5851308e2201c179198cf1179309d0d7333eb4f4`
- [CSV sidecar](tables/002-router-parity-summary.csv.sources.json)
  SHA-256 `2e882fb2da4bbbefa2fc3641cc7a6c2e78304a4a4ddb09b163cf0f18bfd1ab71`

Fixture-only baselines remain under
`fixtures/research/router-v1/expected/tables/` for methodology regression.

## Generated figures

Committed generated figures from the real raw records:

- [Median/status figure](figures/002-router-parity-median.svg)
  SHA-256 `616f4342bf5aec35120f27f6e1cbf5185ab31bd3236730eada52e529c1f73870`
- [Figure sidecar](figures/002-router-parity-median.svg.sources.json)
  SHA-256 `6e2f890d346734395092850906ce032ede17361e2991ee9602f949d7b561a0e9`

Fixture-only baselines remain under
`fixtures/research/router-v1/expected/figures/`.

## Claims and reproduction links

The [claims ledger](CLAIMS_LEDGER.md) currently lists three provisional claims
(F002-C01 through F002-C03) bound to the two real raw records and the frozen
oracle. Reproduction guidance is in [REPRODUCIBILITY.md](REPRODUCIBILITY.md).
Observed results and limits are in [RESULTS.md](RESULTS.md) and
[LIMITATIONS.md](LIMITATIONS.md). Model identity is in
[MODEL_MANIFEST.json](MODEL_MANIFEST.json).

Clean-checkout reproduction of the real Apple command is still required before
any claim may be promoted from provisional to verified.
