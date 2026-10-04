"""Acquire one pinned Qwen checkpoint copy without importing model code.

Uses curl's HTTP resume support; `.part` files occupy the final directory and
are renamed after size and digest verification, so no second full copy is made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote


DEFAULT_MANIFEST = Path(__file__).resolve().parents[2] / "specs/021-qwen38-io-prefetch-spike/checkpoint-manifest.json"
MIN_FREE_AFTER = 100 * 2**30


def digest(path: Path, size: int, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    if algorithm == "sha1":
        hasher.update(f"blob {size}\0".encode())
    with path.open("rb") as stream:
        while chunk := stream.read(8 * 2**20):
            hasher.update(chunk)
    return hasher.hexdigest()


def verified(path: Path, entry: dict) -> bool:
    if not path.is_file() or path.stat().st_size != entry["size_bytes"]:
        return False
    field, algorithm = ("sha256", "sha256") if "sha256" in entry else ("git_blob_sha1", "sha1")
    return digest(path, entry["size_bytes"], algorithm) == entry[field]


def write_receipt(path: Path, manifest: dict, done: list[str]) -> None:
    result = {
        "schema": "pulsarmlx.qwen38.acquisition-receipt/1",
        "repo": manifest["repo"],
        "revision": manifest["revision"],
        "verified_files": done,
        "verified_bytes": sum(f["size_bytes"] for f in manifest["files"] if f["path"] in done),
        "complete": len(done) == len(manifest["files"]),
    }
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    os.replace(temporary, path)


def remaining_bytes(manifest: dict, root: Path, done: list[str]) -> int:
    remaining = 0
    for entry in manifest["files"]:
        if entry["path"] in done:
            continue
        partial = root / (entry["path"] + ".part")
        current = partial.stat().st_size if partial.exists() else 0
        if current > entry["size_bytes"]:
            raise RuntimeError(f"partial file exceeds pinned size: {partial}")
        remaining += entry["size_bytes"] - current
    return remaining


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if manifest["schema"] != "pulsarmlx.qwen38.pinned-checkpoint/1" or \
       manifest["revision"] != "b2c422f3c643e36f04227a64d61796b44a4b1029" or \
       manifest["total_size_bytes"] != sum(f["size_bytes"] for f in manifest["files"]):
        raise RuntimeError("manifest identity or total size is invalid")
    names = [f["path"] for f in manifest["files"]]
    if len(names) != len(set(names)) or not all(Path(n).name == n for n in names):
        raise RuntimeError("manifest filenames are invalid")
    args.dest.mkdir(parents=True, exist_ok=True)
    receipt = args.dest / "acquisition-receipt.json"

    done: list[str] = []
    for entry in manifest["files"]:
        path = args.dest / entry["path"]
        partial = path.with_name(path.name + ".part")
        if path.exists():
            if not verified(path, entry):
                raise RuntimeError(f"existing file failed pinned digest: {path}")
            done.append(entry["path"])
        else:
            partial_size = partial.stat().st_size if partial.exists() else 0
            if partial_size > entry["size_bytes"]:
                raise RuntimeError(f"partial file exceeds pinned size: {partial}")
            if partial_size == entry["size_bytes"]:
                if not verified(partial, entry):
                    raise RuntimeError(f"complete partial file failed pinned digest: {partial}")
                os.replace(partial, path)
                done.append(entry["path"])

    remaining = remaining_bytes(manifest, args.dest, done)
    free = shutil.disk_usage(args.dest).free
    projected = free - remaining
    print(f"free={free} remaining={remaining} projected_free={projected} "
          f"minimum_free={MIN_FREE_AFTER}", flush=True)
    if projected < MIN_FREE_AFTER:
        raise RuntimeError("insufficient internal-disk headroom for one pinned copy")
    if args.preflight_only:
        return 0

    write_receipt(receipt, manifest, done)
    for entry in manifest["files"]:
        name = entry["path"]
        if name in done:
            continue
        path = args.dest / name
        partial = path.with_name(path.name + ".part")
        free = shutil.disk_usage(args.dest).free
        if free - remaining_bytes(manifest, args.dest, done) < MIN_FREE_AFTER:
            raise RuntimeError("internal-disk headroom fell below stop floor")
        url = f"https://huggingface.co/{manifest['repo']}/resolve/{manifest['revision']}/{quote(name)}"
        print(f"START {name} size={entry['size_bytes']} resume={partial.stat().st_size if partial.exists() else 0}", flush=True)
        started = time.monotonic()
        subprocess.run(
            ["curl", "--fail", "--location", "--silent", "--show-error",
             "--retry", "5", "--retry-all-errors", "--retry-delay", "3",
             "--connect-timeout", "30", "--speed-time", "120", "--speed-limit", "10000",
             "--continue-at", "-", "--output", str(partial), url],
            check=True,
        )
        if not verified(partial, entry):
            raise RuntimeError(f"download failed pinned size or digest: {partial}")
        os.replace(partial, path)
        done.append(name)
        write_receipt(receipt, manifest, done)
        print(f"VERIFIED {name} elapsed_s={time.monotonic() - started:.1f}", flush=True)
    print(f"COMPLETE files={len(done)} bytes={manifest['total_size_bytes']}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ACQUISITION STOPPED: {exc}", file=sys.stderr)
        sys.exit(1)
