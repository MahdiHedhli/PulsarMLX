#!/usr/bin/env python3
"""Extract historical target readers into separately reviewable v6 adapters."""
from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HISTORICAL_COMMIT = "84f0d1dc3e60a4151329ed82773880951ee3e618"
SCHEMA = "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/6.0.0"


def historical(path: str) -> str:
    return subprocess.run(
        ["git", "show", f"{HISTORICAL_COMMIT}:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def classes(text: str, names: tuple[str, ...]) -> str:
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    nodes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    if not all(name in nodes for name in names):
        raise ValueError("historical target class census")
    return "\n\n".join("".join(lines[nodes[name].lineno - 1:nodes[name].end_lineno]) for name in names)


def install(relative: str, text: str) -> None:
    path = ROOT / relative
    temporary = path.with_name(path.name + ".extracting")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(text.encode())
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def primary() -> str:
    body = classes(
        historical("scripts/research/f017_corrected_oracle_primary.py"),
        ("StreamingCatalogSource", "StreamingMatrix"),
    )
    body = body.replace("StreamingCatalogSource", "PrimaryTargetSourceV6")
    body = body.replace("StreamingMatrix", "PrimaryTargetMatrixV6")
    body = body.replace('auth.get("primary_sha256")', 'auth.get("primary_target_source_sha256")')
    return f'''#!/usr/bin/env python3
"""Authorization-bound primary checkpoint source; contains no graph arithmetic."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

from f017_oracle_primary_decoders import LAYOUT, decode

AUTH_SCHEMA = {SCHEMA!r}


def _pairs(items):
    result = {{}}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {{key}}")
        result[key] = value
    return result


def _strict_json(path: Path) -> dict:
    return json.loads(path.read_text(), object_pairs_hook=_pairs)


def _hash_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


{body}
'''


def secondary() -> str:
    body = classes(
        historical("scripts/research/f017_corrected_oracle_secondary.py"),
        ("CatalogStore", "CatalogMatrix"),
    )
    body = body.replace("CatalogStore", "SecondaryTargetSourceV6")
    body = body.replace("CatalogMatrix", "SecondaryTargetMatrixV6")
    body = body.replace('auth.get("secondary_sha256")', 'auth.get("secondary_target_source_sha256")')
    return f'''#!/usr/bin/env python3
"""Authorization-bound secondary checkpoint source; contains no graph arithmetic."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import numpy as np

AUTH_SCHEMA = {SCHEMA!r}


def _pairs(items):
    result = {{}}
    for key, value in items:
        if key in result:
            raise ValueError(f"duplicate JSON key: {{key}}")
        result[key] = value
    return result


def strict(path: Path) -> dict:
    return json.loads(path.read_text(), object_pairs_hook=_pairs)


def hash_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


{body}
'''


def main() -> int:
    install("scripts/research/f017_corrected_oracle_primary_target_source_v6.py", primary())
    install("scripts/research/f017_corrected_oracle_secondary_target_source_v6.py", secondary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
