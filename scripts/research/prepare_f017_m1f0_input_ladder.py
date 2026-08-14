#!/usr/bin/env python3
"""Freeze the checkpoint-independent M1-F0 input ladder and selection semantics."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import argparse
from pathlib import Path

SEEDS = tuple(range(17_017_007, 17_017_015))


def select_fixture(outcomes: list[bool]) -> int | None:
    if len(outcomes) != len(SEEDS):
        raise ValueError("complete ladder outcomes are required")
    return next((ordinal for ordinal, passed in enumerate(outcomes) if passed), None)


def build_ladder(root: Path, fixtures: list[dict[str, object]]) -> dict[str, object]:
    if len(fixtures) != len(SEEDS):
        raise ValueError("complete ladder fixtures are required")
    entries = []
    for ordinal, (seed, fixture) in enumerate(zip(SEEDS, fixtures, strict=True)):
        if fixture["generator"]["seed"] != seed:  # type: ignore[index]
            raise ValueError("fixture seed/order mismatch")
        state = fixture["state"]
        assert isinstance(state, dict)
        canonical = (json.dumps(fixture, sort_keys=True, separators=(",", ":")) + "\n").encode()
        entries.append({
            "ordinal": ordinal, "seed": seed, "fixture_sha256": hashlib.sha256(canonical).hexdigest(),
            "package_sha256": fixture["package_sha256"],
            "hidden_sha256": state["hidden"]["sha256"],  # type: ignore[index]
            "component_sha256": {name: component["sha256"] for name, component in state.items()},  # type: ignore[union-attr]
        })
    return {
        "schema": "pulsarmlx.f017.m1f0-input-ladder", "schema_version": "1.0.0",
        "layer": 3, "position": 0, "dsa": "range_fill([0])",
        "family": "normal_f32_with_layer_stress_prefix_v1",
        "family_selection_basis": "checkpoint-independent continuation of accepted fixture semantics",
        "generator": {"path": "scripts/research/generate_f017_m1f0_ladder_input.py",
                      "sha256": hashlib.sha256((root / "scripts/research/generate_f017_m1f0_ladder_input.py").read_bytes()).hexdigest(),
                      "python": "3.13.13", "numpy": "2.4.5", "prng": "PCG64"},
        "fixtures": entries,
        "selection_rule": "first_qualifying_fixture_in_ordinal_order",
        "execution_stopping_rule": "evaluate_and_bank_all_precommitted_fixtures",
        "stability_contract_sha256": "da05364470f7fc5fbdc930441be1ea269af01b6a87173df34e467bcc0b0df9d7",
        "minimum_safety_factor": 4.0, "checkpoint_access": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generator_path = args.root / "scripts/research/generate_f017_m1f0_ladder_input.py"
    spec = importlib.util.spec_from_file_location("f017_input_generator", generator_path)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load input generator")
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    fixtures = [generator.document(seed=seed) for seed in SEEDS]
    value = build_ladder(args.root, fixtures)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(hashlib.sha256(payload).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
