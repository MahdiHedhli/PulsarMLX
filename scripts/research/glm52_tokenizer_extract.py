#!/usr/bin/env python3
"""Extract GPT-2 style tokenizer tables from a GGUF (shard with KV).

Writes public-safe files under an output directory for harness use.
Does not embed private paths in the files.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

# Reuse low-level reader pieces
from glm52_gguf_catalog import Reader, GGUF_MAGIC


def load_all_kv(path: Path) -> dict:
    r = Reader(path)
    try:
        if r.read(4) != GGUF_MAGIC:
            raise ValueError("bad magic")
        _version = r.u32()
        n_tensors = r.u64()
        n_kv = r.u64()
        kv = {}
        for _ in range(n_kv):
            key = r.string()
            vtype = r.u32()
            # full value without truncation
            kv[key] = _value_full(r, vtype)
        # skip tensor infos (not needed)
        return kv
    finally:
        r.close()


def _value_full(r: Reader, vtype: int):
    if vtype == 4:
        return r.u32()
    if vtype == 5:
        return r.i32()
    if vtype == 6:
        return r.f32()
    if vtype == 7:
        return bool(r.u8())
    if vtype == 8:
        return r.string()
    if vtype == 9:
        at = r.u32()
        n = r.u64()
        return [_value_full(r, at) for _ in range(n)]
    if vtype == 10:
        return r.u64()
    if vtype == 11:
        return r.i64()
    if vtype == 12:
        return r.f64()
    if vtype == 0:
        return r.u8()
    if vtype == 1:
        return struct.unpack("<b", r.read(1))[0]
    if vtype == 2:
        return struct.unpack("<H", r.read(2))[0]
    if vtype == 3:
        return struct.unpack("<h", r.read(2))[0]
    raise ValueError(vtype)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gguf", type=Path, required=True, help="shard containing tokenizer KV")
    p.add_argument("--out-dir", type=Path, required=True)
    args = p.parse_args(argv)
    kv = load_all_kv(args.gguf)
    tokens = kv.get("tokenizer.ggml.tokens")
    merges = kv.get("tokenizer.ggml.merges")
    if not isinstance(tokens, list) or not isinstance(merges, list):
        print("tokenizer tables missing", file=sys.stderr)
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "tokens.json").write_text(
        json.dumps(tokens, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.out_dir / "merges.txt").write_text("\n".join(merges) + "\n", encoding="utf-8")
    meta = {
        "vocab_size": len(tokens),
        "merges": len(merges),
        "model": kv.get("tokenizer.ggml.model"),
        "pre": kv.get("tokenizer.ggml.pre"),
        "bos_token_id": kv.get("tokenizer.ggml.bos_token_id"),
        "eos_token_id": kv.get("tokenizer.ggml.eos_token_id"),
        "pad_token_id": kv.get("tokenizer.ggml.padding_token_id"),
    }
    (args.out_dir / "tokenizer_meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"status": "ok", **meta}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
