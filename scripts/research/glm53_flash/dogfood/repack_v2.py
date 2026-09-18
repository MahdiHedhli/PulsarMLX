#!/usr/bin/env python3
"""Repack v2: rewrite a repack directory's expert files in an EXPERT-CONTIGUOUS layout (graph 29).

Upstream repack writes each layer file through mx.save_safetensors, whose data order follows an unordered map: an
expert's nine tensors are scattered across the 4 GB file, so a cold miss is nine reads and a cold prefill is tens of
thousands of scattered requests. This writer emits the safetensors container itself (8-byte header length, JSON
header, raw data) with tensors in the order e0.gate_proj.{weight,scales,biases}, e0.up_proj.*, e0.down_proj.*, e1...,
so every expert occupies one contiguous byte range and experts are in numeric order. Data is copied by byte range
from the source file (no MLX round trip; dtype/shape/offsets come from the source header). offload_index.json gains
layout='expert-contiguous/1' after every layer's file has been read back and checked for contiguity. mx.load reads
the result as any safetensors file. The resident shards and config are copied unchanged.
"""
import argparse
import json
import os
import shutil
import struct
import sys
import time

LAYOUT = "expert-contiguous/1"
_PROJS = ("gate_proj", "up_proj", "down_proj")
_PARTS = ("weight", "scales", "biases")


def read_header(path):
    with open(path, "rb") as fh:
        n = struct.unpack("<Q", fh.read(8))[0]
        header = json.loads(fh.read(n))
    return header, 8 + n


def expert_order(entries):
    """Tensor names in expert-contiguous order; every expert must have the same parts."""
    experts = sorted({int(k.split(".")[0][1:]) for k in entries if k.startswith("e")})
    names = []
    for j in experts:
        for p in _PROJS:
            for k in _PARTS:
                n = f"e{j}.{p}.{k}"
                if n in entries:
                    names.append(n)
    missing = set(k for k in entries if k != "__metadata__") - set(names)
    if missing:
        raise ValueError(f"UNEXPECTED_TENSORS {sorted(missing)[:5]}")
    return experts, names


def write_contiguous(src, dst, chunk=64 << 20):
    header, data_start = read_header(src)
    entries = {k: v for k, v in header.items() if k != "__metadata__"}
    experts, names = expert_order(entries)
    new = {}
    off = 0
    for n in names:
        size = entries[n]["data_offsets"][1] - entries[n]["data_offsets"][0]
        new[n] = {"dtype": entries[n]["dtype"], "shape": entries[n]["shape"], "data_offsets": [off, off + size]}
        off += size
    meta = dict(header.get("__metadata__") or {})
    meta["layout"] = LAYOUT
    hdr = json.dumps({"__metadata__": meta, **new}, separators=(",", ":")).encode()
    hdr += b" " * ((8 - len(hdr) % 8) % 8)   # 8-byte aligned header like the reference writer
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        fout.write(struct.pack("<Q", len(hdr))); fout.write(hdr)
        for n in names:
            a, b = entries[n]["data_offsets"]
            fin.seek(data_start + a); remaining = b - a
            while remaining:
                buf = fin.read(min(chunk, remaining)); fout.write(buf); remaining -= len(buf)
    return experts, off


def check_contiguous(path):
    """True when every expert's tensors form one contiguous range and experts are in numeric order."""
    header, _ = read_header(path)
    entries = {k: v for k, v in header.items() if k != "__metadata__"}
    experts, names = expert_order(entries)
    prev_end = 0
    for j in experts:
        parts = [entries[f"e{j}.{p}.{k}"]["data_offsets"] for p in _PROJS for k in _PARTS if f"e{j}.{p}.{k}" in entries]
        lo, hi = min(a for a, _ in parts), max(b for _, b in parts)
        if hi - lo != sum(b - a for a, b in parts) or lo != prev_end:
            return False
        prev_end = hi
    return (header.get("__metadata__") or {}).get("layout") == LAYOUT


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="existing repack directory (hash-ordered)")
    ap.add_argument("--dst", required=True, help="output directory (expert-contiguous)")
    args = ap.parse_args()
    t0 = time.time()
    os.makedirs(os.path.join(args.dst, "experts"), exist_ok=True)
    idx = json.load(open(os.path.join(args.src, "offload_index.json")))
    for name in sorted(os.listdir(args.src)):
        p = os.path.join(args.src, name)
        if os.path.isfile(p) and name != "offload_index.json" and not name.startswith("pulsar-"):
            shutil.copy2(p, os.path.join(args.dst, name))
    for lid in idx["layers"]:
        src = os.path.join(args.src, "experts", f"layer_{lid:04d}.safetensors"); dst = os.path.join(args.dst, "experts", f"layer_{lid:04d}.safetensors")
        t = time.time(); experts, nbytes = write_contiguous(src, dst)
        if not check_contiguous(dst):
            raise SystemExit(f"CONTIGUITY_CHECK_FAILED layer {lid}")
        print(f"layer {lid}: {len(experts)} experts, {nbytes / 1e9:.2f} GB, {time.time() - t:.1f}s", flush=True)
    json.dump({**idx, "layout": LAYOUT}, open(os.path.join(args.dst, "offload_index.json"), "w"), indent=2)
    print(f"REPACK_V2 DONE {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
