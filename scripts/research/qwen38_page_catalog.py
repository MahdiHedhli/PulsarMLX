"""Header-only page catalog for the pinned converted Qwen3.8 checkpoint.

This module never imports checkpoint Python, MLX, or weight payloads. It does not
map pages into memory or claim numerical/runtime compatibility.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

from admit_qwen38_static import DTYPE_BYTES, MANIFEST, inspect_shard, inspect_shard_data
from qwen38_verified_files import (MAX_METADATA_BYTES, PINNED_REPO,
                                   PINNED_REVISION, VerifiedFiles, open_pinned_files)


class CatalogError(ValueError):
    pass


_BOUND_TOKEN = object()


@dataclass(frozen=True, order=True)
class PageKey:
    kind: str  # expert or ple
    layer: int
    index: int  # expert ID or PLE shard ID
    block: int = 0  # PLE row block; always zero for experts


@dataclass(frozen=True)
class ByteSpan:
    filename: str
    offset: int  # absolute file byte offset, including the Safetensors header
    length: int
    tensor: str


@dataclass(frozen=True)
class PageSpec:
    key: PageKey
    spans: tuple[ByteSpan, ...]

    @property
    def size_bytes(self) -> int:
        return sum(span.length for span in self.spans)


@dataclass(frozen=True)
class TensorRef:
    filename: str
    data_start: int
    dtype: str
    shape: tuple[int, ...]
    start: int
    end: int

    @property
    def row_bytes(self) -> int:
        return math.prod(self.shape[1:]) * DTYPE_BYTES[self.dtype]

    def rows(self, start: int, count: int, name: str) -> ByteSpan:
        if len(self.shape) < 2 or start < 0 or count <= 0 or start + count > self.shape[0]:
            raise CatalogError(f"invalid row slice: {name}")
        if self.end - self.start != self.shape[0] * self.row_bytes:
            raise CatalogError(f"non-contiguous row layout: {name}")
        return ByteSpan(self.filename, self.data_start + self.start + start * self.row_bytes,
                        count * self.row_bytes, name)


class PageCatalog:
    """Maps exact expert IDs and PLE shard/row blocks to affine tensor spans."""

    def __init__(self, tensors: dict[str, TensorRef], *, layers: int, experts: int,
                 ple_layer: int, ple_shards: int, ple_rows_per_page: int = 8192):
        if (any(type(value) is not int for value in
                (layers, experts, ple_layer, ple_shards, ple_rows_per_page)) or
                min(layers, experts, ple_shards, ple_rows_per_page) <= 0 or
                not 0 <= ple_layer < layers):
            raise CatalogError("invalid catalog geometry")
        self.tensors = tensors
        self._verified_files: VerifiedFiles | None = None
        self.layers = layers
        self.experts = experts
        self.ple_layer = ple_layer
        self.ple_shards = ple_shards
        self.ple_rows_per_page = ple_rows_per_page
        self.ple_rows: dict[int, int] = {}
        for layer in range(layers):
            for projection in ("gate_proj", "up_proj", "down_proj"):
                prefix = f"language_model.model.layers.{layer}.mlp.switch_mlp.{projection}"
                refs = self._triple(prefix)
                if any(len(ref.shape) < 2 or ref.shape[0] != experts for ref in refs):
                    raise CatalogError(f"expert row geometry differs: {prefix}")
        for shard in range(ple_shards):
            prefix = (f"language_model.model.layers.{ple_layer}.ple.ple_embedding."
                      f"ngram_embedding.shard_{shard}")
            refs = self._triple(prefix)
            if any(len(ref.shape) < 2 for ref in refs):
                raise CatalogError(f"PLE row geometry differs: {prefix}")
            rows = refs[0].shape[0]
            if rows <= 0 or any(ref.shape[0] != rows for ref in refs):
                raise CatalogError(f"PLE row geometry differs: {prefix}")
            self.ple_rows[shard] = rows
        discovered = {name for name in tensors if ".mlp.switch_mlp." in name or
                      ".ple.ple_embedding.ngram_embedding.shard_" in name}
        expected = set()
        for layer in range(layers):
            for projection in ("gate_proj", "up_proj", "down_proj"):
                prefix = f"language_model.model.layers.{layer}.mlp.switch_mlp.{projection}"
                expected.update(f"{prefix}.{suffix}" for suffix in ("weight", "scales", "biases"))
        for shard in range(ple_shards):
            prefix = (f"language_model.model.layers.{ple_layer}.ple.ple_embedding."
                      f"ngram_embedding.shard_{shard}")
            expected.update(f"{prefix}.{suffix}" for suffix in ("weight", "scales", "biases"))
        if discovered != expected:
            raise CatalogError("unrecognized or missing pageable tensor")

    def _triple(self, prefix: str) -> tuple[TensorRef, TensorRef, TensorRef]:
        try:
            refs = tuple(self.tensors[f"{prefix}.{suffix}"] for suffix in
                         ("weight", "scales", "biases"))
        except KeyError as exc:
            raise CatalogError(f"incomplete affine triple: {prefix}") from exc
        if refs[0].dtype != "U32" or any(ref.dtype != "BF16" for ref in refs[1:]):
            raise CatalogError(f"unsupported affine dtypes: {prefix}")
        if any(len(ref.shape) < 2 or ref.row_bytes <= 0 for ref in refs):
            raise CatalogError(f"empty or scalar affine tensor: {prefix}")
        return refs

    def page(self, key: PageKey) -> PageSpec:
        if (type(key) is not PageKey or type(key.kind) is not str or
                any(type(value) is not int for value in (key.layer, key.index, key.block))):
            raise CatalogError("invalid page key fields")
        if key.kind == "expert":
            if not 0 <= key.layer < self.layers or not 0 <= key.index < self.experts or key.block != 0:
                raise CatalogError("expert page key out of range")
            spans = []
            for projection in ("gate_proj", "up_proj", "down_proj"):
                prefix = f"language_model.model.layers.{key.layer}.mlp.switch_mlp.{projection}"
                for suffix, ref in zip(("weight", "scales", "biases"), self._triple(prefix)):
                    spans.append(ref.rows(key.index, 1, f"{prefix}.{suffix}"))
            return PageSpec(key, tuple(spans))
        if key.kind == "ple":
            if key.layer != self.ple_layer or not 0 <= key.index < self.ple_shards or key.block < 0:
                raise CatalogError("PLE page key out of range")
            start = key.block * self.ple_rows_per_page
            rows = self.ple_rows[key.index]
            if start >= rows:
                raise CatalogError("PLE row block out of range")
            count = min(self.ple_rows_per_page, rows - start)
            prefix = (f"language_model.model.layers.{key.layer}.ple.ple_embedding."
                      f"ngram_embedding.shard_{key.index}")
            spans = tuple(ref.rows(start, count, f"{prefix}.{suffix}") for suffix, ref in
                          zip(("weight", "scales", "biases"), self._triple(prefix)))
            return PageSpec(key, spans)
        raise CatalogError("unknown page kind")

    def ple_key_for_global_row(self, global_row: int) -> PageKey:
        if type(global_row) is not int or global_row < 0:
            raise CatalogError("invalid PLE global row")
        # The pinned conversion uses equal rows per shard, including tail padding.
        rows_per_shard = self.ple_rows[0]
        if any(rows != rows_per_shard for rows in self.ple_rows.values()):
            raise CatalogError("unequal PLE shard rows")
        shard, row = divmod(global_row, rows_per_shard)
        if shard >= self.ple_shards:
            raise CatalogError("PLE global row out of range")
        return PageKey("ple", self.ple_layer, shard, row // self.ple_rows_per_page)

    def summary(self) -> dict:
        example_expert = self.page(PageKey("expert", 0, 0))
        example_ple = self.page(PageKey("ple", self.ple_layer, 0, 0))
        fixed_text_bytes = 0
        excluded_vision_bytes = 0
        for name, ref in self.tensors.items():
            size = ref.end - ref.start
            if name.startswith("vision_tower.") or name.startswith("model.visual."):
                excluded_vision_bytes += size
            elif not (".mlp.switch_mlp." in name or
                      ".ple.ple_embedding.ngram_embedding.shard_" in name):
                fixed_text_bytes += size
        return {"layers": self.layers, "experts_per_layer": self.experts,
                "expert_page_count": self.layers * self.experts,
                "ple_layer": self.ple_layer, "ple_shards": self.ple_shards,
                "ple_rows_per_page": self.ple_rows_per_page,
                "ple_page_count": sum(math.ceil(rows / self.ple_rows_per_page)
                                      for rows in self.ple_rows.values()),
                "example_expert_page_bytes": example_expert.size_bytes,
                "example_ple_page_bytes": example_ple.size_bytes,
                "fixed_text_tensor_bytes": fixed_text_bytes,
                "excluded_vision_tensor_bytes": excluded_vision_bytes,
                "scope": "header-only affine spans; no payload or execution"}


@dataclass(frozen=True)
class BoundCheckpoint:
    """Catalog and authenticated file handles that must travel together."""

    catalog: PageCatalog
    files: VerifiedFiles
    _token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _BOUND_TOKEN or self.catalog._verified_files is not self.files:
            raise CatalogError("catalog was not parsed from these verified files")

    def read_page_into(self, key: PageKey, target: memoryview) -> None:
        if self.catalog._verified_files is not self.files:
            raise CatalogError("catalog lost verified file binding")
        spec = self.catalog.page(key)
        if (target.readonly or not target.c_contiguous or target.ndim != 1 or
                target.itemsize != 1 or target.nbytes != spec.size_bytes):
            raise CatalogError("page target size or layout differs from catalog")
        cursor = 0
        for span in spec.spans:
            segment = target[cursor:cursor + span.length]
            self.files.readinto(span.filename, segment, span.offset)
            cursor += span.length

    def close(self) -> None:
        self.files.close()

    def __enter__(self) -> BoundCheckpoint:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _verified_shard(files: VerifiedFiles, filename: str,
                    names: set[str]) -> tuple[dict, int]:
    prefix = files.read_metadata(filename, 0, 8)
    if len(prefix) != 8:
        raise CatalogError("short verified Safetensors prefix")
    length = struct.unpack("<Q", prefix)[0]
    if not 0 < length <= MAX_METADATA_BYTES - 8:
        raise CatalogError("unreasonable verified Safetensors header")
    header = json.loads(files.read_metadata(filename, 8, length))
    if type(header) is not dict:
        raise CatalogError("invalid verified Safetensors header")
    return inspect_shard_data(8 + length, header, files.file_sizes[filename], names)


def admit_checkpoint(root: Path, *, manifest_path: Path = MANIFEST,
                     ple_rows_per_page: int = 8192,
                     verified_files: VerifiedFiles | None = None) -> PageCatalog:
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("repo") != PINNED_REPO:
        raise CatalogError("unverified checkpoint revision")
    expected_files = {item["path"]: item["size_bytes"] for item in manifest["files"]}
    if verified_files is None:
        receipt = json.loads((root / "acquisition-receipt.json").read_text())
        if (receipt.get("complete") is not True or
                receipt.get("revision") != manifest["revision"] or
                receipt.get("repo") != manifest["repo"]):
            raise CatalogError("unverified checkpoint revision")
        if set(receipt.get("verified_files", [])) != set(expected_files):
            raise CatalogError("incomplete checkpoint receipt")
    if verified_files is not None:
        if (manifest.get("schema") != "pulsarmlx.qwen38.pinned-checkpoint/1" or
                manifest.get("revision") != PINNED_REVISION or
                root.is_symlink() or root.resolve(strict=True) != verified_files.root or
                verified_files.entries != {entry["path"]: entry for entry in manifest["files"]} or
                verified_files.file_sizes != expected_files):
            raise CatalogError("verified files do not match manifest and root")
    for filename, size in expected_files.items():
        if Path(filename).name != filename:
            raise CatalogError(f"unsafe or changed file: {filename}")
        if verified_files is not None:
            verified_files.check(filename)
        elif (root / filename).is_symlink() or (root / filename).stat().st_size != size:
            raise CatalogError(f"unsafe or changed file: {filename}")
    config = json.loads(verified_files.read_metadata("config.json") if verified_files else
                        (root / "config.json").read_text())
    index = json.loads(verified_files.read_metadata("model.safetensors.index.json") if verified_files else
                       (root / "model.safetensors.index.json").read_text())["weight_map"]
    expected_shards = {name for name in expected_files if name.endswith(".safetensors")}
    if set(index.values()) != expected_shards:
        raise CatalogError("index shard set disagrees with manifest")
    if config.get("model_type") != "qwen4_exp" or config.get("model_file") != "qwen4_exp.py":
        raise CatalogError("unexpected checkpoint architecture")
    text = config["text_config"]
    if (text["num_hidden_layers"], text["num_experts"],
            text["num_experts_per_tok"], text["split_ngram_parts"]) != (48, 512, 10, 128):
        raise CatalogError("unexpected checkpoint geometry")
    quant = config["quantization"]
    if (quant["bits"], quant["group_size"]) != (4, 64):
        raise CatalogError("unexpected checkpoint quantization")
    overrides = collections.Counter((item["bits"], item["group_size"])
                                    for item in quant.values() if isinstance(item, dict))
    if overrides != {(8, 64): 498, (4, 32): 128}:
        raise CatalogError("unexpected quantization overrides")
    tensors = {}
    for filename in sorted(set(index.values())):
        if filename not in expected_files or not filename.endswith(".safetensors"):
            raise CatalogError("index names an unadmitted shard")
        names = {name for name, listed in index.items() if listed == filename}
        header, data_start = (_verified_shard(verified_files, filename, names)
                              if verified_files else inspect_shard(root / filename, names))
        for name, item in header.items():
            tensors[name] = TensorRef(filename, data_start, item["dtype"], tuple(item["shape"]),
                                      *item["data_offsets"])
    ple_layers = {int(name.split(".layers.", 1)[1].split(".", 1)[0]) for name in tensors
                  if ".ple.ple_embedding.ngram_embedding.shard_" in name}
    if ple_layers != {1}:
        raise CatalogError("expected pinned PLE layer 1")
    catalog = PageCatalog(tensors, layers=48, experts=512, ple_layer=ple_layers.pop(),
                          ple_shards=128, ple_rows_per_page=ple_rows_per_page)
    if verified_files is not None:
        catalog._verified_files = verified_files
    return catalog


def _admit_checkpoint_bound_from_manifest(root: Path, *, manifest_path: Path,
                                          ple_rows_per_page: int = 8192) -> BoundCheckpoint:
    """Rehash all pinned files, then parse metadata through the retained handles."""
    files = open_pinned_files(root, manifest_path=manifest_path)
    try:
        catalog = admit_checkpoint(root, manifest_path=manifest_path,
                                   ple_rows_per_page=ple_rows_per_page,
                                   verified_files=files)
        return BoundCheckpoint(catalog, files, _BOUND_TOKEN)
    except BaseException as exc:
        try:
            files.close()
        except OSError as cleanup_error:
            if hasattr(exc, "add_note"):
                exc.add_note(f"bound admission cleanup also failed: {cleanup_error}")
        raise


def admit_checkpoint_bound(root: Path, *, ple_rows_per_page: int = 8192) -> BoundCheckpoint:
    """Production entry point fixed to the project-owned pinned manifest."""
    return _admit_checkpoint_bound_from_manifest(
        root, manifest_path=MANIFEST, ple_rows_per_page=ple_rows_per_page)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(admit_checkpoint(args.dest).summary(), indent=2))


if __name__ == "__main__":
    main()
