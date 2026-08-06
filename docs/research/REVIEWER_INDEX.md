# Feature 002 Reviewer Index

**Status**: Real Apple MLX layer-0 router evidence is published as four
append-only raw experiment records (primary plus clean-checkout reproduction)
with regenerated tables/figures and three package-level verified claims.
Expert execution, aggregation, generation, serving, and tokens-per-second
remain unsupported.

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

Primary candidate `b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4`:

- [primary batch-a](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-a.json)
  SHA-256 `b5925db8ba68d90a42507e00be6d3159457a2b97d9fc827f0200245cb20851fa`
- [primary batch-b](raw/002-router-parity/f002-router-real-b4262d84eef41665cf8306c352701a58838f5e5f0180c3342f3a6ab618a751d4-batch-b.json)
  SHA-256 `99346e8be81b4975cb355759be20872aefdea05baa9960f28aa272d970116801`

Clean-checkout reproduction candidate
`3dc290b5a02daf673eb00e7c47e9428cf3aa1b935401db2327c0e59c03a3e3f3`:

- [repro batch-a](raw/002-router-parity/f002-router-real-3dc290b5a02daf673eb00e7c47e9428cf3aa1b935401db2327c0e59c03a3e3f3-batch-a.json)
  SHA-256 `0cc828bb77f2dca62d039c700a575ec123cef1367e1d942956f1a6fe8481c616`
- [repro batch-b](raw/002-router-parity/f002-router-real-3dc290b5a02daf673eb00e7c47e9428cf3aa1b935401db2327c0e59c03a3e3f3-batch-b.json)
  SHA-256 `ce8e6d71d2a8a209d5119b3a6c886f3f1e65e2d75d4b8502a363dd44edc67a44`

All four records report `actual_status: passed`, exact top-8 parity, zero
ID/order mismatches, evaluated synchronized `apple-mlx`/`gpu`, no fallback,
identical promotion identity, and identical case output hashes
`3751004998d2a3d4c0b10fa2a2b517f2cd690b60636b1058263a5683cd1d5b4a` (single-row)
and `7b3d5b522c77074706336c669885d70ff71af17077987e625dd2345dc30b7088` (two-row).

Accepted model-free methodology fixtures remain the synthetic
[passed fixture](../../fixtures/research/router-v1/evidence/f002-router-fixture-0001.json),
[failed fixture](../../fixtures/research/router-v1/evidence/f002-router-fixture-failed-0001.json),
and [aborted fixture](../../fixtures/research/router-v1/evidence/f002-router-fixture-aborted-0001.json).

## Generated tables

- [Markdown summary](tables/002-router-parity-summary.md)
  SHA-256 `db1b86454d0df9f558028af6cc7cfa771aafb64ee30ee020943ee75081316308`
- [Markdown sidecar](tables/002-router-parity-summary.md.sources.json)
  SHA-256 `84de70bed09b27e4fb4767c42b8d266ffda648cad82093c6604c37afd871485a`
- [CSV summary](tables/002-router-parity-summary.csv)
  SHA-256 `64c6bd7cf305be32f54ec78032e748043d9ec3d1da0b61916ccab74e4ff15ff7`
- [CSV sidecar](tables/002-router-parity-summary.csv.sources.json)
  SHA-256 `71be1f2748ebfcedcb3aa9b01005c2291ae4c9233cc2edf5aab2cc1890d40079`

## Generated figures

- [Median/status figure](figures/002-router-parity-median.svg)
  SHA-256 `8084a0876f71a2a9ab839a12b118f75f8a4fb235d021050a25f65d6a58483568`
- [Figure sidecar](figures/002-router-parity-median.svg.sources.json)
  SHA-256 `e05db61d084dff0980f4efa5efd0514329b1dc181c37c22917497fb83571cb43`

## Claims and reproduction links

The [claims ledger](CLAIMS_LEDGER.md) lists three verified claims (F002-C01
through F002-C03) bound to all four real raw records. Reproduction guidance is
in [REPRODUCIBILITY.md](REPRODUCIBILITY.md). Observed results and limits are in
[RESULTS.md](RESULTS.md) and [LIMITATIONS.md](LIMITATIONS.md). Model identity is
in [MODEL_MANIFEST.json](MODEL_MANIFEST.json).
