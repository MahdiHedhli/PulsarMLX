# F020 Slice 2A — real-artifact metadata census

**Recorded 2026-09-23.** A header-only metadata census of the two PipeNetwork MLX
checkpoints that F020 targets, run with the Slice 1 libraries. **Header
compatibility is not Q0 payload identity and not numerical qualification.** No
payload byte was read, nothing was downloaded, no shard was hashed, and no model
code was imported or executed.

Evidence (machine-readable, append-only):

* [`f020-slice2a-metadata-census-glm53-v1.json`](reviews/evidence/f020-slice2a-metadata-census-glm53-v1.json)
  — `pipenetwork/GLM-5.3-MLX-mixed-4_8bit` at `e1034d395c26b9bcd3631df783e65737701ff2d6`
* [`f020-slice2a-metadata-census-glm53-flash-v1.json`](reviews/evidence/f020-slice2a-metadata-census-glm53-flash-v1.json)
  — `pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit` at `d43ea8b407ce4e9c25e6ac9baec3feab70d9f5f3`

Each record keeps **observations** (the census and extractor output) apart from
**inferences** (a hand-written, labelled section), and binds every tool file by
path, sha256 and commit.

## How the metadata was obtained, and why no payload byte was read

1. `scripts/research/extract_safetensors_headers_v1.py` ran on the host that holds
   the checkpoints. Per shard it read the 8-byte prefix at offset 0, checked the
   declared header length `N` (at most 100 MiB, and `8 + N` within the file), and
   read exactly `N` bytes at offset 8. Every read is bounded before the system
   call; the per-shard log shows a maximum read end of exactly `8 + N` and an
   unchanged file position for all 79 + 18 shards. It also copied `config.json`,
   `generation_config.json`, `model.safetensors.index.json`,
   `download-record.json` and `tokenizer_config.json`, and recorded directory
   entries by `lstat`. The committed extractor's sha256 equals the one that ran.
2. Only the header files, sidecars and those small JSON files left that host.
3. `crates/mlx-affine/examples/header_census.rs` built each catalog with
   `Checkpoint::from_headers` from those bytes alone (no file descriptor; every
   read returns `NoBackingFile`). `crates/mlx-affine/tests/census_metadata_only.rs`
   proves on a committed header-only fixture that the census asks only for
   metadata names and cannot reach a payload read.
4. Categories come from rules files outside `crates/`:
   `scripts/research/glm53/header_census_rules.json` and
   `scripts/research/glm53_flash/header_census_rules.json`.

## Headline results (observations)

| | GLM-5.3 | GLM-5.3-Flash |
|---|---|---|
| shards / tensors | 79 / 3,355 | 18 / 2,998 |
| header bytes (8 + N, all shards) | 411,576 | 395,485 |
| tensor bytes | 427,746,467,328 | 181,923,504,376 |
| strict tiling, `tensor bytes + 8 + N == file size` | 79/79 | 18/18 |
| index ↔ shards, both directions | agree | agree |
| `metadata.total_size` | equals file bytes, **not** tensor bytes (differs by the header bytes) | same |
| stored dtypes | BF16 2,351; U32 929; F32 75 | BF16 2,040; U32 668; F32 290 |
| default quantization | 4-bit, group 64, affine | 4-bit, group 64, affine |
| explicit overrides | 704, all 8-bit group 64, all resolve | 542, all 8-bit group 64, all resolve |
| modules: quantized / unquantized / refused | 929 / 472 / 0 | 668 / 458 / 0 |
| combinations | 4/64/BF16 × 225; 8/64/BF16 × 704 | 4/64/BF16 × 126; 8/64/BF16 × 542 |
| stacked leading shapes | [256] × 225, [64] × 156 | [288] × 126, [64] × 22 |
| tensors outside any weight/scales/biases module | 96 | 536 |
| MTP tensors (config: `num_nextn_predict_layers` 1) | none | none |

Routed experts (`switch_mlp.{gate,up,down}_proj`, stacked over E) are the only
default-resolved 4-bit modules and hold 95.3% (GLM-5.3) and 94.1% (Flash) of
tensor bytes. Every other quantized module, including `embed_tokens` and
`lm_head`, is an explicit 8-bit override. The GLM-5.3 indexer is unquantized BF16
and present only in the 21 `full` indexer layers; the Flash indexer is 8-bit and
present only in its 11 MLA layers. The Flash census reproduces the Slice 1
metadata compatibility record v2 exactly, including its catalog digest.

## Provenance

* GLM-5.3: the download record states every one of 90 files was verified at
  download time (2026-09-22), with a sha256 for each of the 79 shards; recorded
  shard sizes equal today's `stat` sizes. **This census did not re-verify any of
  it.**
* Flash: the download record holds only the repository, the revision and a
  duration — no per-file sizes, hashes or verification flags.
* The GLM-5.3 repository ships `glm_moe_dsa.py` and a stray upstream
  `__pycache__/glm_moe_dsa.cpython-314.pyc`. Both were listed and never read,
  imported or executed.

## Not covered by Slice 1 (inferences; detail in each record)

* Q0 payload identity for either checkpoint, and any numerical result on real bytes.
* `quantized_matmul` / `gather_qmm`: routed-expert gather over E = 256 or 288,
  per-head `embed_q` / `unembed_out`, quantized embedding lookup and `lm_head`.
* Unquantized BF16 matrices used as matrices (router gates, GLM-5.3 indexer,
  Flash kpool gate and hyper-connection `fn`, the Flash vision tower), and
  non-matrix tensors such as the Flash `conv1d` [24576, 4, 1].
* Tensors with no role in the affine module model: F32
  `e_score_correction_bias`, `.bias` tensors, Flash hyper-connection `base`/`scale`,
  `forget_gate.A_log`/`dt_bias`, indexer kpool tensors.
* Model graphs (MLA/DSA with indexer, Flash linear attention and hyper-connections,
  vision), residency for the stacked experts, and MTP, which neither artifact
  contains.

Header compatibility with the Slice 1 libraries is complete for both revisions.
It is not Q0 payload identity and not numerical qualification.
