# fixtures/safetensors

Synthetic Safetensors checkpoints for `crates/safetensors-catalog` and
`crates/mlx-affine`. Everything here is generated, deterministic and small:
about 180 KB in total, no model weights, no downloads, no MLX.

Regenerate or verify with

```
python3 scripts/research/generate_safetensors_fixtures_v1.py --check
python3 scripts/research/generate_safetensors_fixtures_v1.py --write
```

`manifest.json` records the sha256 and byte length of every file, plus the
sha256 of the generator and of the R1 reference that produced the expected
values.

## Model neutrality

The module paths are `block.N....`, which belongs to no model. That is
deliberate: the crates under test must not be able to recognise a name, and a
test that used real GLM tensor names would quietly reward a parser that did.
`scripts/ci/tests/test_safetensors_fixtures_v1.py` asserts that no
model-specific token appears anywhere in the positive fixtures.

## Positive checkpoints

| Directory | Shape |
| --- | --- |
| `uniform-affine-v1` | one shard, no index, three modules, all 4-bit group 64, `__metadata__` present, `config.json` with only the default |
| `mixed-4-8-v1` | three shards and an index; default 4-bit group 64; one module overridden to 8-bit group 64 and one to 8-bit group 32; one unquantized BF16 weight; one F32 vector; one stacked three-expert tensor at 4 bits; a deliberate 24-byte gap in the first shard |
| `mixed-4-8-index-total-size-v1` | the same checkpoint with `metadata.total_size` declared |

Each carries `expected.json`: the R1 dequantization of every quantized module,
as binary32 bit patterns, produced by
`scripts/research/mlx_affine_reference_v1.py`. **MLX was not run.** Whether the
pinned MLX agrees is observed separately and labelled by
`scripts/ci/mlx_affine_compat_v1.py`.

The uniform and mixed checkpoints together are the demonstration the owner
required before Slice 1 closes: `crates/mlx-affine/tests/fixtures.rs`'s
`the_same_parser_describes_a_uniform_and_a_mixed_checkpoint` opens both with
the same `Checkpoint::open` and classifies every module with the same
`classify_module`, asserting the per-module kind and spec of each, with no
parser change between them.

## Negative cases

There are 33 negative cases. `negative/<case>/` holds a tiny checkpoint or a
handful of header bytes and a
`README` whose **first line is the error variant the crate must return** and
whose second line says why. The two fixture-driven tests --
`crates/safetensors-catalog/tests/negative_fixtures.rs` and
`crates/mlx-affine/tests/fixtures.rs` -- read that first line and assert the
exact variant, so a fixture cannot drift away from what it claims to test.

Coverage: malformed headers (truncated prefix, declared length beyond the
file, non-object JSON, non-string `__metadata__`), duplicate tensor names,
overlapping ranges, a range beyond the data section, a length mismatch, an
unsupported dtype, a shape product that overflows `u64`, a missing shard, an
unindexed tensor, an indexed tensor absent from its shard, a cross-shard
mismatch, an ambiguous two-shard layout, three path-traversal spellings, four
incomplete-triple shapes, scales/biases dtype and shape mismatches, an
inconsistent override, an override for a module without scales, scales with no
configuration, unsupported bit widths and group sizes, an unsupported mode,
differing `quantization` and `quantization_config`, and a non-object override
value.

## `golden-affine-dequant-v1`

A separate fixture with its own provenance; see its own `README.md`. It is not
produced by this generator and `--check` ignores it.
