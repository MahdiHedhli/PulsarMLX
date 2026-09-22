#!/usr/bin/env python3
"""Build the manifest and tensor catalog the F017 native loader admits, from a
directory of split GGUF shards.

`load_plan_only` needs two documents that describe a checkpoint: a manifest
naming every shard with its size and SHA-256, and a catalog naming every
tensor with its absolute data offset, dimensions and quantisation type. For
GLM-5.2 those were produced during Feature 016. This produces them for any
split GGUF of the same family, by reading each shard's header.

Only headers are parsed. The tensor payload is read once, and only to hash
each shard for the manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from read_gguf_metadata_v1 import Reader  # noqa: E402

# GGUF tensor type ids, restricted to the set the native loader accepts.
TYPE_NAMES = {
    0: "F32", 8: "Q8_0", 10: "Q2_K", 11: "Q3_K", 12: "Q4_K", 13: "Q5_K",
    14: "Q6_K", 16: "IQ2_XXS", 18: "IQ3_XXS", 22: "IQ2_S", 23: "IQ4_XS",
}
# Reported for a clearer refusal when a checkpoint uses something else.
OTHER_TYPE_NAMES = {
    1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1", 9: "Q8_1", 15: "Q8_K",
    17: "IQ2_XS", 19: "IQ1_S", 20: "IQ4_NL", 21: "IQ3_S", 29: "IQ1_M", 30: "BF16",
}
SELECTED_SUFFIXES = (
    "block_count", "embedding_length", "vocab_size", "feed_forward_length",
    "expert_count", "expert_used_count", "expert_feed_forward_length",
    "expert_shared_count", "leading_dense_block_count", "context_length",
    "attention.head_count", "attention.head_count_kv", "attention.q_lora_rank",
    "attention.kv_lora_rank", "attention.key_length", "attention.key_length_mla",
    "attention.value_length", "attention.value_length_mla",
    "attention.indexer.head_count", "attention.indexer.key_length",
    "attention.indexer.top_k", "rope.dimension_count", "rope.freq_base",
)


def read_header(path: Path) -> dict:
    """Parse one shard's key/value block and tensor table."""
    with open(path, "rb") as handle:
        head = handle.read(64 << 20)
    if head[:4] != b"GGUF":
        raise ValueError(f"{path.name}: not a GGUF file")
    version, tensor_count, kv_count = struct.unpack("<IQQ", head[4:24])
    reader = Reader(head)
    reader.offset = 24
    metadata = {}
    for _ in range(kv_count):
        key_length = struct.unpack("<Q", reader.take(8))[0]
        key = reader.take(key_length).decode("utf-8", "replace")
        kind = struct.unpack("<I", reader.take(4))[0]
        metadata[key] = reader.value(kind, 4)
    tensors = []
    for _ in range(tensor_count):
        name_length = struct.unpack("<Q", reader.take(8))[0]
        name = reader.take(name_length).decode("utf-8", "replace")
        dimension_count = struct.unpack("<I", reader.take(4))[0]
        dims = [struct.unpack("<Q", reader.take(8))[0] for _ in range(dimension_count)]
        type_id, offset = struct.unpack("<IQ", reader.take(12))
        tensors.append({"name": name, "dims": dims, "type_id": type_id, "relative_offset": offset})
    alignment = metadata.get("general.alignment", 32)
    if not isinstance(alignment, int) or alignment <= 0:
        alignment = 32
    header_end = reader.offset
    data_start = (header_end + alignment - 1) // alignment * alignment
    return {"version": version, "metadata": metadata, "tensors": tensors,
            "data_start": data_start, "alignment": alignment}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 24), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(directory: Path, pattern: str, hash_shards: bool) -> tuple[dict, dict, list]:
    shards = sorted(directory.glob(pattern))
    if not shards:
        raise ValueError(f"no shards matching {pattern} in {directory}")
    architecture = None
    selected: dict = {}
    tensors: list[dict] = []
    files: list[dict] = []
    unsupported: list[str] = []
    for shard in shards:
        header = read_header(shard)
        metadata = header["metadata"]
        if architecture is None:
            architecture = metadata.get("general.architecture")
            for suffix in SELECTED_SUFFIXES:
                key = f"{architecture}.{suffix}"
                if key in metadata:
                    selected[suffix] = metadata[key]
        for tensor in header["tensors"]:
            name = TYPE_NAMES.get(tensor["type_id"])
            if name is None:
                label = OTHER_TYPE_NAMES.get(tensor["type_id"], f"type_id_{tensor['type_id']}")
                unsupported.append(f"{tensor['name']} is {label}")
                continue
            tensors.append({
                "data_offset_abs": header["data_start"] + tensor["relative_offset"],
                "dims": tensor["dims"],
                "file": shard.name,
                "name": tensor["name"],
                "type": name,
                "type_id": tensor["type_id"],
            })
        files.append({
            "filename": shard.name,
            "sha256": sha256_file(shard) if hash_shards else "0" * 64,
            "size_bytes": shard.stat().st_size,
        })
    manifest = {
        "checkpoint_set_sha256": hashlib.sha256(
            "".join(f"{item['filename']}:{item['sha256']}\n" for item in files).encode()
        ).hexdigest(),
        "checkpoint_set_sha256_rule": "sha256 over 'filename:sha256\\n' for each shard in name order",
        "file_count": len(files),
        "total_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
    }
    catalog = {
        "architecture": architecture,
        "kv_selected": selected,
        "shard_count": len(files),
        "tensor_count": len(tensors),
        "tensors": sorted(tensors, key=lambda item: (item["file"], item["data_offset_abs"])),
    }
    return manifest, catalog, unsupported


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--pattern", default="*.gguf")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--skip-hashes", action="store_true",
                        help="leave shard SHA-256 as zeros; the loader will then refuse, so this is for inspection only")
    arguments = parser.parse_args(argv)
    manifest, catalog, unsupported = build(arguments.directory, arguments.pattern, not arguments.skip_hashes)
    if unsupported:
        print(f"REFUSED: {len(unsupported)} tensors use a type the native loader has no decoder for", file=sys.stderr)
        for line in unsupported[:10]:
            print(f"  {line}", file=sys.stderr)
        return 1
    arguments.manifest.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    arguments.catalog.write_text(json.dumps(catalog, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "architecture": catalog["architecture"],
        "shards": manifest["file_count"],
        "total_bytes": manifest["total_bytes"],
        "tensors": catalog["tensor_count"],
        "checkpoint_set_sha256": manifest["checkpoint_set_sha256"],
        "kv_selected": catalog["kv_selected"],
    }, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
