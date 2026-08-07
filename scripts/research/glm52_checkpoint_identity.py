#!/usr/bin/env python3
"""Validate complete UD-IQ2_XXS shard set and write public-safe identity JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

EXPECTED = [
    ("GLM-5.2-UD-IQ2_XXS-00001-of-00006.gguf", 9423744),
    ("GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf", 49105028960),
    ("GLM-5.2-UD-IQ2_XXS-00003-of-00006.gguf", 49143176640),
    ("GLM-5.2-UD-IQ2_XXS-00004-of-00006.gguf", 49143176640),
    ("GLM-5.2-UD-IQ2_XXS-00005-of-00006.gguf", 49143176640),
    ("GLM-5.2-UD-IQ2_XXS-00006-of-00006.gguf", 41914650304),
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(8 * 1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--source-commit", type=str, default="")
    args = p.parse_args(argv)

    if args.out.exists():
        print("refuse overwrite", file=sys.stderr)
        return 1

    files = []
    errors = []
    for name, exp in EXPECTED:
        path = args.model_dir / name
        if not path.exists():
            errors.append(f"missing {name}")
            continue
        size = path.stat().st_size
        if size != exp:
            errors.append(f"size mismatch {name}: {size} != {exp}")
            continue
        print(f"hashing {name} ...", flush=True)
        digest = sha256_file(path)
        files.append({"filename": name, "size_bytes": size, "sha256": digest})

    free = shutil.disk_usage("/").free
    total = sum(f["size_bytes"] for f in files)
    set_hasher = hashlib.sha256()
    for f in files:
        set_hasher.update(f["sha256"].encode())
        set_hasher.update(str(f["size_bytes"]).encode())

    doc = {
        "schema": "pulsarmlx.validation.glm52-checkpoint",
        "schema_version": "1.0.0",
        "feature_id": "016-glm52-full-execution",
        "utc_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_commit": args.source_commit,
        "repo": "unsloth/GLM-5.2-GGUF",
        "quant": "UD-IQ2_XXS",
        "env_var": "PULSARMLX_GLM_GGUF",
        "files": files,
        "file_count": len(files),
        "total_bytes": total,
        "expected_total_bytes": sum(e for _, e in EXPECTED),
        "checkpoint_set_sha256": set_hasher.hexdigest(),
        "free_bytes_after": free,
        "free_gib_after": round(free / 1024**3, 3),
        "min_free_after_required_gib": 250,
        "actual_status": "passed" if not errors and len(files) == 6 and free >= 250 * 1024**3 else "failed",
        "errors": errors,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": doc["actual_status"], "errors": errors, "total_bytes": total}, sort_keys=True))
    return 0 if doc["actual_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
