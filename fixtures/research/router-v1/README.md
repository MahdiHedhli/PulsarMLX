# Generated Router-v1 Fixture

This directory contains a redistributable, model-free fixture for the bounded
Feature 002 complete-router contract. It has the Qwen3MoE router dimensions
(`2048` hidden values, `128` experts, and top `8`) but contains no checkpoint
tensor bytes and is not evidence about any real Qwen activation or route.

The fixture is synthetic and generated entirely from the exact formulas below.
It may be used in CI and offline development without locating, opening, or
downloading an external model. Its source and generated values are distributed
under the repository's MIT license.

## Contents

- `manifest.json` is the entry point. It records the case IDs, shapes, scope,
  file hashes, generator hash, and canonical binary32 hashes.
- `golden/weight_recipe.json` describes the complete expert-major
  `[128,2048]` F32 matrix without committing its 1,048,576 raw bytes.
- `golden/hidden_states.json` stores two complete, finite, distinct `[2048]`
  one-hot rows. Their canonical combined representation is exactly 16,384
  bytes, which is the frozen fixture bound.
- `golden/expected_results.json` stores complete independently computed logits,
  full 128-way softmax probabilities, ordered top-8 IDs, selected probabilities
  before renormalization, final normalized weights, and hashes for both cases.
- `golden/generate.py` is the standard-library-only generator and byte checker.
  It imports no MLX, PulsarMLX worker code, NumPy, model parser, or checkpoint
  reader.

The two case IDs match the worker contract tests:

| Case | Hidden rows | Purpose |
| --- | ---: | --- |
| `generated-qwen3moe-router-single-row-v1` | row 0 | Complete single-row router output |
| `generated-qwen3moe-router-two-row-v1` | rows 0 and 1 | Complete bounded two-row output |

These generated IDs are deliberately different from the reserved real-case
IDs in the Feature 002 protocol.

## Real oracle support package

`real/` is reserved for the bounded, redistributable projection of the
independent CPU oracle. Once published, it contains the complete two-row
hidden-state input and complete router outputs needed for offline review, but
no GGUF bytes, router weights, capture binaries, private paths, or runtime
device identities. Its record is byte-identical to the support copy under
`docs/research/raw/002-router-parity/oracle/`; `real/manifest.json` binds both
copies and is installed last as the transaction-completion marker.

The support record is not a measured Apple experiment and therefore is kept in
the dedicated `oracle/` subtree rather than being parsed as a top-level
`pulsarmlx.research.experiment` record. Validate an installed package without
checkpoint access with:

```sh
PULSARMLX_MODEL_GGUF='' python3 -B \
  scripts/research/oracle_publication.py --check
```

A passing check establishes only the frozen CPU reference input and output. It
does not establish Apple MLX execution, parity, performance, expert execution,
or any deeper inference boundary.

## Exact weight recipe

For expert ID `e` in `0..128`, the logical expert-major row is generated in
ascending input-column order:

```text
W[e, 0] = f32((((e * 37) % 128) - 64) / 16.0)
W[e, 1] = f32((((e * 53 + 7) % 128) - 64) / 16.0)
W[e, c] = +0.0f32, for c in 2..2048
```

The canonical weight encoding concatenates each value as IEEE-754 binary32
little-endian, first by ascending expert ID and then by ascending input column.
Only this recipe and its canonical hash are committed; the raw 1 MiB weight
buffer is reconstructed in memory by tests or the implementation under test.

The hidden rows are `one_hot(0)` and `one_hot(1)`. Consequently, an independent
review can derive each expected logit from the corresponding first or second
weight coefficient without trusting a matrix library.

## Independent expected-result arithmetic

The generator computes expected values independently with a scalar procedure:

1. multiply and accumulate each expert row in ascending input-column order,
   rounding every multiply and add to binary32;
2. subtract the row maximum in binary32;
3. calculate each exponential at Decimal precision 80, then round to binary32;
4. accumulate the full 128-way denominator in ascending expert-ID order with
   binary32 rounding and divide each exponential in binary32;
5. rank by probability descending and expert ID ascending;
6. retain the first eight full-softmax probabilities; and
7. accumulate their sum in rank order and renormalize in binary32.

Every stored floating-point value is finite. JSON decimal values round-trip to
the encoded binary32 values. Canonical hashes are SHA-256 over the flattened
row-major values encoded as IEEE-754 F32 little-endian. Expert-ID hashes use
unsigned 32-bit little-endian values and are labeled separately so they cannot
be confused with floating-point hashes.

The ordered expected IDs are:

```text
row 0: [83, 38, 121, 76, 31, 114, 69, 24]
row 1: [24, 123, 94, 65, 36, 7, 106, 77]
```

`manifest.json` and `golden/expected_results.json` are authoritative for the
current file and canonical value hashes.

## Validate deterministic regeneration

From the repository root, regenerate all documents in memory and require a
byte-for-byte match with the committed files:

```sh
python3 fixtures/research/router-v1/golden/generate.py --check
```

To reproduce into a separate directory without changing the checkout:

```sh
fixture_tmp="$(mktemp -d)"
python3 fixtures/research/router-v1/golden/generate.py \
  --write \
  --output-root "$fixture_tmp/router-v1"
cmp fixtures/research/router-v1/manifest.json \
  "$fixture_tmp/router-v1/manifest.json"
for fixture_file in hidden_states.json weight_recipe.json expected_results.json; do
  cmp "fixtures/research/router-v1/golden/$fixture_file" \
    "$fixture_tmp/router-v1/golden/$fixture_file"
done
```

`--write` targets only the three generated golden JSON files and the manifest.
The README and generator source are never rewritten by that command.

## Capability boundary

Scalar regeneration and manifest checks establish only synthetic
complete-router values and deterministic bytes. The separate generated
Rust-to-worker integration can additionally establish explicit Apple MLX GPU
execution for these generated fixtures. Neither level establishes external
checkpoint identity, real hidden-state provenance, expert execution, a
complete layer or model, inference, generation, serving, performance, or
Linux/CUDA runtime parity.
