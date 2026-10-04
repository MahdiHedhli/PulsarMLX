"""Header-only page catalog for the pinned converted Qwen3.8 checkpoint.

This module never imports checkpoint Python, MLX, or weight payloads. It does not
map pages into memory or claim numerical/runtime compatibility.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

from admit_qwen38_static import DTYPE_BYTES, MANIFEST, inspect_shard


class CatalogError(ValueError):
    pass


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
        if min(layers, experts, ple_shards, ple_rows_per_page) <= 0 or not 0 <= ple_layer < layers:
            raise CatalogError("invalid catalog geometry")
        self.tensors = tensors
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
            rows = refs[0].shape[0]
            if any(len(ref.shape) < 2 or ref.shape[0] != rows for ref in refs):
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
        return refs

    def page(self, key: PageKey) -> PageSpec:
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
        if global_row < 0:
            raise CatalogError("negative PLE global row")
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


def admit_checkpoint(root: Path, *, manifest_path: Path = MANIFEST,
                     ple_rows_per_page: int = 8192) -> PageCatalog:
    manifest = json.loads(manifest_path.read_text())
    receipt = json.loads((root / "acquisition-receipt.json").read_text())
    if not receipt.get("complete") or receipt.get("revision") != manifest["revision"]:
        raise CatalogError("unverified checkpoint revision")
    expected_files = {item["path"]: item["size_bytes"] for item in manifest["files"]}
    if set(receipt.get("verified_files", [])) != set(expected_files):
        raise CatalogError("incomplete checkpoint receipt")
    for filename, size in expected_files.items():
        if Path(filename).name != filename or (root / filename).stat().st_size != size:
            raise CatalogError(f"unsafe or changed file: {filename}")
    config = json.loads((root / "config.json").read_text())
    index = json.loads((root / "model.safetensors.index.json").read_text())["weight_map"]
    if config.get("model_type") != "qwen4_exp" or config.get("model_file") != "qwen4_exp.py":
        raise CatalogError("unexpected checkpoint architecture")
    text = config["text_config"]
    if (text["num_hidden_layers"], text["num_experts"], text["split_ngram_parts"]) != (48, 512, 128):
        raise CatalogError("unexpected checkpoint geometry")
    tensors = {}
    for filename in sorted(set(index.values())):
        if filename not in expected_files or not filename.endswith(".safetensors"):
            raise CatalogError("index names an unadmitted shard")
        names = {name for name, listed in index.items() if listed == filename}
        header, data_start = inspect_shard(root / filename, names)
        for name, item in header.items():
            tensors[name] = TensorRef(filename, data_start, item["dtype"], tuple(item["shape"]),
                                      *item["data_offsets"])
    ple_layers = {int(name.split(".layers.", 1)[1].split(".", 1)[0]) for name in tensors
                  if ".ple.ple_embedding.ngram_embedding.shard_" in name}
    if len(ple_layers) != 1:
        raise CatalogError("expected one pageable PLE layer")
    return PageCatalog(tensors, layers=48, experts=512, ple_layer=ple_layers.pop(),
                       ple_shards=128, ple_rows_per_page=ple_rows_per_page)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(admit_checkpoint(args.dest).summary(), indent=2))


if __name__ == "__main__":
    main()
