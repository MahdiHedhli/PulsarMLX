#!/usr/bin/env python3
"""Repack v2: rewrite a repack directory's expert files in an EXPERT-CONTIGUOUS layout (graph 29; hardened in graph 32).

Upstream repack writes each layer file through mx.save_safetensors, whose data order follows an unordered map: an
expert's nine tensors are scattered across the 4 GB file, so a cold miss is nine reads and a cold prefill is tens of
thousands of scattered requests. This writer emits the safetensors container itself (8-byte header length, JSON
header, raw data) with tensors in the order e0.gate_proj.{weight,scales,biases}, e0.up_proj.*, e0.down_proj.*, e1...,
so every expert occupies one contiguous byte range and experts are in numeric order. Data is copied by byte range
from the source file (no MLX round trip; dtype/shape/offsets come from the source header). offload_index.json gains
layout='expert-contiguous/1' after every layer's file has been read back and checked for contiguity. mx.load reads
the result as any safetensors file. The resident shards and config are copied unchanged.

Graph 32 (fail-safe): the first version's copy loop never terminated on a truncated source (an empty read left
`remaining` unchanged) and check_contiguous validated header relationships only, so a truncated destination passed.
Now:
  * a source header is validated before any copy: the header length fits the file, every entry has a known dtype and
    shape x itemsize == its byte length, the intervals are non-overlapping and tile [0, data_end) exactly, the file
    length equals data_start + data_end (a truncated payload or trailing bytes are rejected), every expert has the
    same parts, and no unexpected tensor is present;
  * the copy rejects an empty read while bytes remain (SHORT_READ_EOF) - a source that shrinks under us terminates;
  * output is written to <dst>.partial, fsync'd, validated with check_contiguous (header relationships AND file
    length), then renamed over <dst> (os.replace) with the directory fsync'd; on any error the .partial is removed;
  * offload_index.json (the layout flag) is written last, the same way, only after every layer verified;
  * source/destination aliases (same file or same directory after resolving links) and an existing destination
    layer file are refused; --resume keeps a destination file that passes the full check and rewrites one that does
    not, and removes stale .partial files.
Crash-durability boundary: after this process returns, a layer file is either absent, a `.partial` (never read: the
store globs layer_*.safetensors), or complete-and-validated; offload_index.json with the layout flag exists only when
every layer is complete. fsync is issued on every published file and its directory; no claim is made about media
write caches beyond what fsync provides on the host filesystem.
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
_ITEMSIZE = {"BOOL": 1, "U8": 1, "I8": 1, "U16": 2, "I16": 2, "F16": 2, "BF16": 2, "U32": 4, "I32": 4, "F32": 4, "U64": 8, "I64": 8, "F64": 8}
PARTIAL = ".partial"


class RepackError(ValueError):
    """A source or destination file that must not be used (the message names the check)."""


def read_header(path):
    """(header dict, data_start): the container framing only; use validate_file for the full check."""
    size = os.path.getsize(path)
    if size < 8:
        raise RepackError(f"HEADER_TRUNCATED {path}: {size} bytes")
    with open(path, "rb") as fh:
        n = struct.unpack("<Q", fh.read(8))[0]
        if n > size - 8:
            raise RepackError(f"HEADER_TRUNCATED {path}: header length {n} exceeds file ({size - 8} bytes after the prefix)")
        raw = fh.read(n)
    try:
        header = json.loads(raw)
    except ValueError as exc:
        raise RepackError(f"HEADER_NOT_JSON {path}: {exc}") from None
    if not isinstance(header, dict):
        raise RepackError(f"HEADER_NOT_OBJECT {path}")
    return header, 8 + n


def validate_file(path):
    """Full container check: every entry well-formed, intervals tile [0, data_end) exactly, file length exact.
    Returns (header, data_start, entries, data_end)."""
    header, data_start = read_header(path)
    entries = {k: v for k, v in header.items() if k != "__metadata__"}
    if not entries:
        raise RepackError(f"NO_TENSORS {path}")
    for name, e in entries.items():
        if not isinstance(e, dict) or not {"dtype", "shape", "data_offsets"} <= set(e):
            raise RepackError(f"ENTRY_MALFORMED {path}: {name}")
        if e["dtype"] not in _ITEMSIZE:
            raise RepackError(f"DTYPE_UNKNOWN {path}: {name} {e['dtype']}")
        shape = e["shape"]
        if not isinstance(shape, list) or any((not isinstance(d, int)) or isinstance(d, bool) or d < 0 for d in shape):
            raise RepackError(f"SHAPE_MALFORMED {path}: {name} {shape}")
        offs = e["data_offsets"]
        if not (isinstance(offs, list) and len(offs) == 2 and all(isinstance(o, int) and not isinstance(o, bool) and o >= 0 for o in offs)) or offs[1] < offs[0]:
            raise RepackError(f"OFFSETS_MALFORMED {path}: {name} {offs}")
        count = 1
        for d in shape:
            count *= d
        if count * _ITEMSIZE[e["dtype"]] != offs[1] - offs[0]:
            raise RepackError(f"LENGTH_MISMATCH {path}: {name} shape {shape} x {e['dtype']} != {offs[1] - offs[0]} bytes")
    ordered = sorted(entries.items(), key=lambda kv: kv[1]["data_offsets"][0])
    expected_start = 0
    for name, e in ordered:
        a, b = e["data_offsets"]
        if a != expected_start:
            raise RepackError(f"INTERVALS_NOT_TILING {path}: {name} starts at {a}, expected {expected_start} (gap or overlap)")
        expected_start = b
    data_end = expected_start
    size = os.path.getsize(path)
    if size != data_start + data_end:
        raise RepackError(f"FILE_LENGTH_MISMATCH {path}: {size} bytes, header describes {data_start + data_end}")
    return header, data_start, entries, data_end


def expert_order(entries):
    """Tensor names in expert-contiguous order; every expert must have the same parts and nothing else may be present."""
    experts = sorted({int(k.split(".")[0][1:]) for k in entries if k.startswith("e") and k.split(".")[0][1:].isdigit()})
    if not experts:
        raise RepackError("NO_EXPERT_TENSORS")
    parts_of = {}
    names = []
    for j in experts:
        parts = tuple((p, k) for p in _PROJS for k in _PARTS if f"e{j}.{p}.{k}" in entries)
        parts_of.setdefault(parts, []).append(j)
        names.extend(f"e{j}.{p}.{k}" for p, k in parts)
    if len(parts_of) != 1:
        described = {" ".join(f"{p}.{k}" for p, k in parts): js[:3] for parts, js in parts_of.items()}
        raise RepackError(f"INVENTORY_MISMATCH experts do not share the same parts: {described}")
    missing = set(k for k in entries if k != "__metadata__") - set(names)
    if missing:
        raise RepackError(f"UNEXPECTED_TENSORS {sorted(missing)[:5]}")
    return experts, names


def _copy_range(fin, fout, start, length, chunk):
    fin.seek(start); remaining = length
    while remaining:
        buf = fin.read(min(chunk, remaining))
        if not buf:
            raise RepackError(f"SHORT_READ_EOF at {start + length - remaining}: {remaining} bytes remain")
        fout.write(buf); remaining -= len(buf)


def _fsync_dir(path):
    fd = os.open(os.path.dirname(os.path.abspath(path)) or ".", os.O_RDONLY)
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def write_contiguous(src, dst, chunk=64 << 20, fault_hook=None):
    """Validated source -> <dst>.partial -> validated -> renamed to dst. Returns (experts, data bytes)."""
    if os.path.exists(dst) and os.path.samefile(src, dst):
        raise RepackError(f"ALIAS src and dst are the same file: {src}")
    if os.path.exists(dst):
        raise RepackError(f"DST_EXISTS {dst} (use --resume to keep a verified file or rewrite a failed one)")
    header, data_start, entries, _ = validate_file(src)
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
    tmp = dst + PARTIAL
    try:
        if fault_hook is not None:
            fault_hook("before-copy")
        with open(src, "rb") as fin, open(tmp, "wb") as fout:
            fout.write(struct.pack("<Q", len(hdr))); fout.write(hdr)
            for i, n in enumerate(names):
                a, b = entries[n]["data_offsets"]
                _copy_range(fin, fout, data_start + a, b - a, chunk)
                if fault_hook is not None:
                    fault_hook("copied", i)
            fout.flush(); os.fsync(fout.fileno())
        if not check_contiguous(tmp):
            raise RepackError(f"CONTIGUITY_CHECK_FAILED {tmp}")
        os.replace(tmp, dst)
        _fsync_dir(dst)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return experts, off


def check_contiguous(path):
    """True when the file is a complete, validated container (exact length, tiling intervals) whose experts each form
    one contiguous range in numeric order with the layout flag set. Never raises: any defect is False."""
    try:
        header, _, entries, _ = validate_file(path)
        experts, names = expert_order(entries)
    except (RepackError, OSError, ValueError):
        return False
    prev_end = 0
    for j in experts:
        parts = [entries[f"e{j}.{p}.{k}"]["data_offsets"] for p in _PROJS for k in _PARTS if f"e{j}.{p}.{k}" in entries]
        lo, hi = min(a for a, _ in parts), max(b for _, b in parts)
        if hi - lo != sum(b - a for a, b in parts) or lo != prev_end:
            return False
        prev_end = hi
    return (header.get("__metadata__") or {}).get("layout") == LAYOUT


def _write_json_atomic(path, obj):
    tmp = path + PARTIAL
    with open(tmp, "w") as fh:
        json.dump(obj, fh, indent=2); fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, path)
    _fsync_dir(path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", required=True, help="existing repack directory (hash-ordered)")
    ap.add_argument("--dst", required=True, help="output directory (expert-contiguous)")
    ap.add_argument("--link-resident", action="store_true", help="symlink the unchanged resident shards/config from --src instead of copying them (same volume)")
    ap.add_argument("--resume", action="store_true", help="keep destination layer files that pass the full check, rewrite the others, drop stale .partial files")
    args = ap.parse_args(argv)
    t0 = time.time()
    if os.path.realpath(args.src) == os.path.realpath(args.dst):
        raise SystemExit(f"ALIAS src and dst are the same directory: {args.dst}")
    os.makedirs(os.path.join(args.dst, "experts"), exist_ok=True)
    idx = json.load(open(os.path.join(args.src, "offload_index.json")))
    present = sorted(os.listdir(os.path.join(args.dst, "experts")))
    if present and not args.resume:
        kind = "PARTIAL_PRESENT" if any(n.endswith(PARTIAL) for n in present) else "DST_EXISTS"
        raise SystemExit(f"{kind} {os.path.join(args.dst, 'experts', present[0])} (an earlier or interrupted run; use --resume)")
    for name in sorted(os.listdir(args.src)):
        p = os.path.join(args.src, name); q = os.path.join(args.dst, name)
        if os.path.isfile(p) and name != "offload_index.json" and not name.startswith("pulsar-"):
            if os.path.lexists(q):
                if not args.resume:
                    raise SystemExit(f"DST_EXISTS {q}")
                os.remove(q)
            if args.link_resident:
                os.symlink(os.path.abspath(p), q)
            else:
                shutil.copy2(p, q)
    kept = 0
    for lid in idx["layers"]:
        src = os.path.join(args.src, "experts", f"layer_{lid:04d}.safetensors"); dst = os.path.join(args.dst, "experts", f"layer_{lid:04d}.safetensors")
        if os.path.exists(dst + PARTIAL):
            if not args.resume:
                raise SystemExit(f"PARTIAL_PRESENT {dst + PARTIAL} (an interrupted run; use --resume)")
            os.remove(dst + PARTIAL)
        if os.path.exists(dst):
            if not args.resume:
                raise SystemExit(f"DST_EXISTS {dst}")
            if check_contiguous(dst):
                kept += 1; print(f"layer {lid}: kept (verified)", flush=True); continue
            os.remove(dst)
        t = time.time()
        try:
            experts, nbytes = write_contiguous(src, dst)
        except RepackError as exc:
            raise SystemExit(f"layer {lid}: {exc}")
        print(f"layer {lid}: {len(experts)} experts, {nbytes / 1e9:.2f} GB, {time.time() - t:.1f}s", flush=True)
    _write_json_atomic(os.path.join(args.dst, "offload_index.json"), {**idx, "layout": LAYOUT})
    print(f"REPACK_V2 DONE {time.time() - t0:.0f}s ({kept} layers kept)", flush=True)


if __name__ == "__main__":
    main()
