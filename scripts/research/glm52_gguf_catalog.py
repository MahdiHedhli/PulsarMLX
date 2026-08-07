#!/usr/bin/env python3
"""GLM-C01: multi-shard GGUF metadata + tensor catalog (read-only).

Opens a directory of sharded GGUF files (or a single .gguf) and emits a
public-safe JSON catalog: architecture KV, tensor names/types/shapes/sizes,
and per-file offset ranges. Does not load weight payloads into memory.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any

GGUF_MAGIC = b"GGUF"
# gguf value types
GGUF_TYPE = {
    0: "uint8",
    1: "int8",
    2: "uint16",
    3: "int16",
    4: "uint32",
    5: "int32",
    6: "float32",
    7: "bool",
    8: "string",
    9: "array",
    10: "uint64",
    11: "int64",
    12: "float64",
}
# subset of tensor types we care about for reporting
TENSOR_TYPE = {
    0: "F32",
    1: "F16",
    2: "Q4_0",
    3: "Q4_1",
    6: "Q5_0",
    7: "Q5_1",
    8: "Q8_0",
    10: "Q2_K",
    11: "Q3_K",
    12: "Q4_K",
    13: "Q5_K",
    14: "Q6_K",
    15: "Q8_K",
    16: "IQ2_XXS",
    17: "IQ2_XS",
    18: "IQ3_XXS",
    19: "IQ1_S",
    20: "IQ4_NL",
    21: "IQ3_S",
    22: "IQ2_S",
    23: "IQ4_XS",
}


class Reader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.f = path.open("rb")

    def close(self) -> None:
        self.f.close()

    def read(self, n: int) -> bytes:
        b = self.f.read(n)
        if len(b) != n:
            raise EOFError(f"{self.path}: short read {len(b)}/{n} at {self.f.tell()}")
        return b

    def u8(self) -> int:
        return self.read(1)[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.read(8))[0]

    def f32(self) -> float:
        return struct.unpack("<f", self.read(4))[0]

    def f64(self) -> float:
        return struct.unpack("<d", self.read(8))[0]

    def string(self) -> str:
        n = self.u64()
        return self.read(n).decode("utf-8", errors="replace")

    def value(self, vtype: int) -> Any:
        if vtype == 0:
            return self.u8()
        if vtype == 1:
            return struct.unpack("<b", self.read(1))[0]
        if vtype == 2:
            return struct.unpack("<H", self.read(2))[0]
        if vtype == 3:
            return struct.unpack("<h", self.read(2))[0]
        if vtype == 4:
            return self.u32()
        if vtype == 5:
            return self.i32()
        if vtype == 6:
            return self.f32()
        if vtype == 7:
            return bool(self.u8())
        if vtype == 8:
            return self.string()
        if vtype == 9:
            at = self.u32()
            n = self.u64()
            # Cap huge arrays in catalog
            if n > 64:
                # skip payload
                self._skip_array(at, n)
                return {"type": GGUF_TYPE.get(at, str(at)), "len": n, "truncated": True}
            return [self.value(at) for _ in range(n)]
        if vtype == 10:
            return self.u64()
        if vtype == 11:
            return self.i64()
        if vtype == 12:
            return self.f64()
        raise ValueError(f"unknown gguf value type {vtype}")

    def _skip_array(self, at: int, n: int) -> None:
        # element sizes for fixed types
        sizes = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
        if at in sizes:
            self.f.seek(sizes[at] * n, 1)
            return
        if at == 8:
            for _ in range(n):
                ln = self.u64()
                self.f.seek(ln, 1)
            return
        # nested arrays / unknown: fall back to reading values (slow but rare)
        for _ in range(n):
            self.value(at)


def parse_header(path: Path) -> dict[str, Any]:
    r = Reader(path)
    try:
        magic = r.read(4)
        if magic != GGUF_MAGIC:
            raise ValueError(f"{path.name}: bad magic {magic!r}")
        version = r.u32()
        n_tensors = r.u64()
        n_kv = r.u64()
        kv: dict[str, Any] = {}
        for _ in range(n_kv):
            key = r.string()
            vtype = r.u32()
            val = r.value(vtype)
            kv[key] = val
        tensors = []
        for _ in range(n_tensors):
            name = r.string()
            n_dims = r.u32()
            dims = [r.u64() for _ in range(n_dims)]
            ttype = r.u32()
            offset = r.u64()  # relative to data section
            tensors.append(
                {
                    "name": name,
                    "dims": dims,
                    "type_id": ttype,
                    "type": TENSOR_TYPE.get(ttype, f"type_{ttype}"),
                    "data_offset_rel": offset,
                }
            )
        # align to 32 for data section start
        pos = r.f.tell()
        align = 32
        data_start = (pos + align - 1) // align * align
        file_size = path.stat().st_size
        for t in tensors:
            t["data_offset_abs"] = data_start + t["data_offset_rel"]
            if t["data_offset_abs"] >= file_size:
                t["offset_in_range"] = False
            else:
                t["offset_in_range"] = True
        return {
            "file": path.name,
            "file_size_bytes": file_size,
            "gguf_version": version,
            "n_tensors": n_tensors,
            "n_kv": n_kv,
            "data_section_start": data_start,
            "kv": kv,
            "tensors": tensors,
        }
    finally:
        r.close()


def discover_ggufs(root: Path) -> list[Path]:
    if root.is_file() and root.suffix == ".gguf":
        return [root]
    files = sorted(root.glob("*.gguf"))
    nested = sorted((root / "UD-IQ2_XXS").glob("*.gguf")) if (root / "UD-IQ2_XXS").is_dir() else []
    # prefer flat dest root names
    by_name = {p.name: p for p in nested + files}
    return [by_name[k] for k in sorted(by_name)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True, help="GGUF file or shard directory")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--source-commit", type=str, default="")
    args = p.parse_args(argv)

    if args.out.exists():
        print("glm52_gguf_catalog: refuse overwrite", file=sys.stderr)
        return 1

    paths = discover_ggufs(args.model)
    if not paths:
        print("glm52_gguf_catalog: no gguf files", file=sys.stderr)
        return 2

    shards = []
    all_tensors = []
    merged_kv: dict[str, Any] = {}
    type_counts: dict[str, int] = {}
    bad_offsets = 0

    for path in paths:
        print(f"parsing {path.name} ...", flush=True)
        h = parse_header(path)
        shards.append(
            {
                "file": h["file"],
                "file_size_bytes": h["file_size_bytes"],
                "n_tensors": h["n_tensors"],
                "n_kv": h["n_kv"],
                "data_section_start": h["data_section_start"],
                "gguf_version": h["gguf_version"],
            }
        )
        # first non-empty kv wins for arch meta (usually shard 00001)
        for k, v in h["kv"].items():
            if k not in merged_kv:
                merged_kv[k] = v
        for t in h["tensors"]:
            t = dict(t)
            t["file"] = h["file"]
            all_tensors.append(t)
            type_counts[t["type"]] = type_counts.get(t["type"], 0) + 1
            if not t["offset_in_range"]:
                bad_offsets += 1

    arch = merged_kv.get("general.architecture")
    # pull common keys with arch prefix
    def ak(suffix: str) -> Any:
        if not arch:
            return None
        return merged_kv.get(f"{arch}.{suffix}")

    summary = {
        "schema": "pulsarmlx.research.glm52-gguf-catalog",
        "schema_version": "1.0.0",
        "feature_id": "016-glm52-full-execution",
        "boundary": "GLM-C01",
        "source_commit": args.source_commit,
        "model_path_env": "PULSARMLX_GLM_GGUF",
        "shard_count": len(shards),
        "shards": shards,
        "total_file_bytes": sum(s["file_size_bytes"] for s in shards),
        "architecture": arch,
        "kv_selected": {
            "general.architecture": arch,
            "general.name": merged_kv.get("general.name"),
            "general.file_type": merged_kv.get("general.file_type"),
            "block_count": ak("block_count"),
            "context_length": ak("context_length"),
            "embedding_length": ak("embedding_length"),
            "feed_forward_length": ak("feed_forward_length"),
            "expert_count": ak("expert_count"),
            "expert_used_count": ak("expert_used_count"),
            "expert_shared_count": ak("expert_shared_count"),
            "expert_feed_forward_length": ak("expert_feed_forward_length"),
            "attention.head_count": ak("attention.head_count"),
            "attention.head_count_kv": ak("attention.head_count_kv"),
            "attention.q_lora_rank": ak("attention.q_lora_rank"),
            "attention.kv_lora_rank": ak("attention.kv_lora_rank"),
            "attention.key_length_mla": ak("attention.key_length_mla"),
            "attention.value_length_mla": ak("attention.value_length_mla"),
            "attention.indexer.head_count": ak("attention.indexer.head_count"),
            "attention.indexer.key_length": ak("attention.indexer.key_length"),
            "attention.indexer.top_k": ak("attention.indexer.top_k"),
            "rope.dimension_count": ak("rope.dimension_count"),
            "rope.freq_base": ak("rope.freq_base"),
            "vocab_size": merged_kv.get("tokenizer.ggml.tokens")
            if False
            else ak("vocab_size") or merged_kv.get("tokenizer.ggml.model"),
        },
        "tensor_type_counts": type_counts,
        "tensor_count": len(all_tensors),
        "bad_offset_count": bad_offsets,
        "tensors": all_tensors,
        "kv_key_count": len(merged_kv),
        "kv_keys": sorted(merged_kv.keys()),
        "actual_status": "passed" if bad_offsets == 0 and arch else "failed",
        "unsupported_interpretations": [
            "full_model_execution",
            "generation",
            "tokens_per_second",
        ],
    }
    # Don't dump huge tokenizer arrays into selected kv if present as full list
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n")
    print(
        json.dumps(
            {
                "status": summary["actual_status"],
                "architecture": arch,
                "shards": len(shards),
                "tensors": len(all_tensors),
                "types": type_counts,
                "block_count": summary["kv_selected"]["block_count"],
                "expert_count": summary["kv_selected"]["expert_count"],
                "out": str(args.out),
            },
            sort_keys=True,
        )
    )
    return 0 if summary["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
