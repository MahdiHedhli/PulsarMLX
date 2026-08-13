#!/usr/bin/env python3
"""Fail-closed generated-artifact, duplicate-key, and privacy gate for M1-F0."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


ABSOLUTE_PRIVATE = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\)")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def scan_privacy(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            scan_privacy(key)
            scan_privacy(child)
    elif isinstance(value, list):
        for child in value:
            scan_privacy(child)
    elif isinstance(value, str) and ABSOLUTE_PRIVATE.search(value):
        raise ValueError("private absolute path")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument(
        "--execution-config",
        type=Path,
        default=Path("docs/architecture/reviews/evidence/f017-m1-f0-attempt-2-execution-config-v1.json"),
    )
    args = parser.parse_args()
    root = args.repository_root.resolve(strict=True)
    admission = load_module("m1f0_admission", root / "scripts/research/f017_m1f0_admission.py")
    generator = load_module("m1f0_input", root / "scripts/research/generate_f017_m1f0_input.py")

    input_path = root / generator.OUTPUT_PATH
    fixture = load_json(input_path)
    if fixture != generator.document():
        raise ValueError("input generated artifact differs")

    config_path = args.execution_config
    if not config_path.is_absolute():
        config_path = root / config_path
    config_path = config_path.resolve(strict=True)
    if not config_path.is_relative_to(root):
        raise ValueError("execution config escapes repository root")
    config = load_json(config_path)
    admission.validate_config(root, config)

    synthetic_path = root / "docs/architecture/reviews/evidence/f017-m1-f0-synthetic-qualification-v1.json"
    synthetic = load_json(synthetic_path)
    if synthetic != admission.synthetic_qualification(fixture):
        raise ValueError("synthetic generated artifact differs")

    stress_path = root / "docs/architecture/reviews/evidence/f017-m1-f0-stress-qualification-v1.json"
    stress = load_json(stress_path)
    if stress != admission.synthetic_stress(fixture):
        raise ValueError("stress generated artifact differs")

    soak = load_json(root / "docs/architecture/reviews/evidence/f017-m1-f0-synthetic-soak-v1.json")
    expected_soak_identity = hashlib.sha256(
        admission.canonical_json({"stage_hashes": synthetic["stage_hashes"], "selection": synthetic["selection"]})
    ).hexdigest()
    if (
        soak.get("schema") != "pulsarmlx.f017.m1f0-synthetic-soak"
        or soak.get("status") != "passed"
        or soak.get("cycles", 0) < 1
        or soak.get("complete_discoveries") != soak.get("cycles") * 10
        or soak.get("stage_and_route_identity_sha256") != expected_soak_identity
        or soak.get("first_mismatch") is not None
        or soak.get("checkpoint_accessed") is not False
        or soak.get("expert_tensor_accesses") != 0
    ):
        raise ValueError("soak evidence differs")

    for path in [
        input_path,
        config_path,
        synthetic_path,
        stress_path,
        root / "docs/architecture/reviews/evidence/f017-m1-f0-synthetic-soak-v1.json",
        *[root / relative for relative in admission.CONTRACT_PATHS.values()],
    ]:
        scan_privacy(load_json(path))

    print("M1-F0 package validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
