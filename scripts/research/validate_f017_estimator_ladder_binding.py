#!/usr/bin/env python3
"""Fail-closed validation for the planning estimator's exact fixture family."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

BINDING = "docs/architecture/reviews/evidence/f017-m1-f0-estimator-ladder-binding-v2.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(root: Path, document: dict[str, object] | None = None) -> None:
    doc = document or json.loads((root / BINDING).read_text())
    if doc.get("schema_version") != "2.0.0" or doc.get("planning_only") is not True:
        raise ValueError("estimator binding version/status")
    bindings = doc.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) != {
        "estimator_implementation", "estimator_contract", "fixture_generator",
        "fixture_family_contract", "ladder_artifact",
    }:
        raise ValueError("estimator binding set")
    for name, binding in bindings.items():
        if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
            raise ValueError(f"invalid estimator binding: {name}")
        path = root / str(binding["path"])
        if not path.is_file() or sha256(path) != binding["sha256"]:
            raise ValueError(f"stale estimator binding: {name}")
    ladder = json.loads((root / str(bindings["ladder_artifact"]["path"])).read_text())
    generator = ladder.get("generator", {})
    environment = doc.get("environment", {})
    if generator.get("sha256") != bindings["fixture_generator"]["sha256"]:
        raise ValueError("ladder generator identity")
    if any(generator.get(key) != environment.get(key) for key in ("python", "numpy", "prng")):
        raise ValueError("mixed ladder environment")
    seeds = [fixture.get("seed") for fixture in ladder.get("fixtures", [])]
    if seeds != environment.get("seeds"):
        raise ValueError("mixed ladder version")


if __name__ == "__main__":
    validate(Path(__file__).resolve().parents[2])
    print("F017_ESTIMATOR_LADDER_BINDING_VALID")
