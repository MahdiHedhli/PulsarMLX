# Feature 002 Reviewer Index

**Status**: The independent CPU-oracle support package is frozen and indexed.
Two external Apple MLX producer attempts failed closed before evidence
admission, so no Apple experiment record, generated real result, or promoted
router capability is indexed.

The governing package is the [Feature 002 specification](../../specs/002-qwen-router-parity/spec.md),
[plan](../../specs/002-qwen-router-parity/plan.md), [quickstart](../../specs/002-qwen-router-parity/quickstart.md),
[research-evidence contract](../../specs/002-qwen-router-parity/contracts/research-evidence-v1.md),
[router contract](../../specs/002-qwen-router-parity/contracts/router-parity-v1.md),
and [experiment protocol](EXPERIMENT_PROTOCOL.md).

## Raw evidence

The exact independent CPU reference is available as a byte-identical
[raw support record](raw/002-router-parity/oracle/f002-router-oracle-freeze-0001.json)
and [review fixture](../../fixtures/research/router-v1/real/f002-router-oracle-freeze-0001.json),
bound by the [manifest](../../fixtures/research/router-v1/real/manifest.json).
The support record freezes the complete two-row hidden-state input, all router
outputs, exact top-8 IDs, hashes, tolerances, source/checkpoint/tensor identity,
and bounded public provenance. Its record SHA-256 is
`3f570ce97f45902a1717d3770c6665d1023d8ccfc18266e25229bc1e86725133`;
the manifest SHA-256 is
`ba2165b985195ca34df1813189228c0763bef414f0e1040833c069b999e66816`.
It contains no model or router-tensor bytes and is not an Apple experiment.

No top-level `pulsarmlx.research.experiment` record exists yet under
`docs/research/raw/002-router-parity/`. The accepted model-free inputs are the
synthetic [passed fixture](../../fixtures/research/router-v1/evidence/f002-router-fixture-0001.json),
[failed fixture](../../fixtures/research/router-v1/evidence/f002-router-fixture-failed-0001.json),
and [aborted fixture](../../fixtures/research/router-v1/evidence/f002-router-fixture-aborted-0001.json).
The separate excluded record is an expected-rejection mutation and is not
accepted evidence or a frozen-output input.

## Generated tables

No committed generated result tables exist. Deterministic table generation is
implemented by [`generate_tables.py`](../../scripts/research/generate_tables.py).
The frozen fixture baselines are the [Markdown
summary](../../fixtures/research/router-v1/expected/tables/002-router-parity-summary.md)
and [Markdown
sidecar](../../fixtures/research/router-v1/expected/tables/002-router-parity-summary.md.sources.json),
plus the [CSV
summary](../../fixtures/research/router-v1/expected/tables/002-router-parity-summary.csv)
and [CSV
sidecar](../../fixtures/research/router-v1/expected/tables/002-router-parity-summary.csv.sources.json).

## Generated figures

No committed generated result figures exist. Bounded static SVG generation is
implemented by [`generate_figures.py`](../../scripts/research/generate_figures.py).
The frozen fixture baseline is the [median/status
figure](../../fixtures/research/router-v1/expected/figures/002-router-parity-median.svg)
and its [figure
sidecar](../../fixtures/research/router-v1/expected/figures/002-router-parity-median.svg.sources.json).

## Claims and reproduction links

The [claims ledger](CLAIMS_LEDGER.md) contains zero claims. The
[reproducibility guide](REPRODUCIBILITY.md), [results structure](RESULTS.md),
[limitations](LIMITATIONS.md), [model manifest](MODEL_MANIFEST.json), and
[artifact manifest](ARTIFACT_MANIFEST.json) are initialized for later
append-only evidence.

The model manifest contains only the inherited Feature 001 checkpoint identity
and pre-access expectations. Its Feature 002 router observation is unset. The
artifact manifest contains unsealed placeholders, not evidence hashes or a
measured source commit.

The six fixture outputs were reproduced byte-for-byte and hash-for-hash from a
detached clean worktree at
`d6f5820050cdc59944a7b2af26b7b0c2c15767c6`. The exact procedure is in the
reproducibility guide. That attestation covers three synthetic records, six
generated artifacts, and zero claims.

Every sidecar binds all three fixture paths and SHA-256 values, the exact
generator and hash, normalized generation command, fixture-record source
commit, and output hash. This is test provenance, not a measured model commit.

Raw evidence publication is exclusive, atomic, and append-only. Existing or
duplicate experiment IDs cannot be overwritten; failed and aborted history is
retained; and every rerun, correction, or reproduction receives a new ID. Raw
evidence must be committed and pushed before result generation.

The ledger allows `verified`, `provisional`, `rejected`, and `unsupported`.
Only an exact-scope claim with complete committed evidence and matching
clean-checkout reproduction can be `verified`. Fixture methodology creates no
capability or performance row.

## Validation entrypoints

- [`validate_evidence.py`](../../scripts/research/validate_evidence.py): closed
  schema and semantic/privacy validation.
- [`statistics.py`](../../scripts/research/statistics.py): frozen Type-7 and
  sample-statistics implementation.
- [`verify_package.py`](../../scripts/research/verify_package.py): read-only
  candidate and fixture-only regeneration verification.
- [`publish_evidence.py`](../../scripts/research/publish_evidence.py): atomic,
  append-only installation after validation.
- [`oracle_publication.py`](../../scripts/research/oracle_publication.py):
  exact-value validation and manifest-last publication of the bounded CPU
  reference package.

The current model-free package entrypoint is:

```sh
PULSARMLX_MODEL_GGUF='' python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity \
  --fixture-only
```

A passing fixture-only verification now also checks the exact three-file
CPU-oracle support inventory. It does not create a claim row or Apple model
result. No MLX tensor operation ran and no Apple GPU memory was used to create
the frozen oracle index.
