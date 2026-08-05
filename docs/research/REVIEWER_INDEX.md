# Feature 002 Reviewer Index

**Status**: Methodology index initialized. No real evidence, generated result,
or reviewer-verifiable checkpoint capability is indexed.

The governing package is the [Feature 002 specification](../../specs/002-qwen-router-parity/spec.md),
[plan](../../specs/002-qwen-router-parity/plan.md), [quickstart](../../specs/002-qwen-router-parity/quickstart.md),
[research-evidence contract](../../specs/002-qwen-router-parity/contracts/research-evidence-v1.md),
[router contract](../../specs/002-qwen-router-parity/contracts/router-parity-v1.md),
and [experiment protocol](EXPERIMENT_PROTOCOL.md).

## Raw evidence

No published Feature 002 raw record exists under
`docs/research/raw/002-router-parity/`. The model-free positive methodology
fixture is
[`f002-router-fixture-0001.json`](../../fixtures/research/router-v1/evidence/f002-router-fixture-0001.json)
and is explicitly synthetic.

## Generated tables

No committed generated result tables exist. Deterministic table generation is
implemented by [`generate_tables.py`](../../scripts/research/generate_tables.py).

## Generated figures

No committed generated result figures exist. Bounded static SVG generation is
implemented by [`generate_figures.py`](../../scripts/research/generate_figures.py).

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

## Validation entrypoints

- [`validate_evidence.py`](../../scripts/research/validate_evidence.py): closed
  schema and semantic/privacy validation.
- [`statistics.py`](../../scripts/research/statistics.py): frozen Type-7 and
  sample-statistics implementation.
- [`verify_package.py`](../../scripts/research/verify_package.py): read-only
  candidate and fixture-only regeneration verification.
- [`publish_evidence.py`](../../scripts/research/publish_evidence.py): atomic,
  append-only installation after validation.

The current model-free package entrypoint is:

```sh
PULSARMLX_MODEL_GGUF='' python3 scripts/research/verify_package.py \
  --feature 002-qwen-router-parity \
  --fixture-only
```

A passing fixture-only verification establishes the methodology package only;
it does not create a claim row or model result.
