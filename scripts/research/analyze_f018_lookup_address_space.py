#!/usr/bin/env python3
"""Generate/check the bounded IQ2 lookup-address-space comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEVICE = ROOT / "docs/research/glm52/raw/f018-iq2-xxs-synthetic-strict-device-0002.json"
CONSTANT = ROOT / "docs/research/glm52/raw/f018-iq2-xxs-synthetic-strict-constant-0001.json"
OUTPUT = ROOT / "docs/research/glm52/raw/f018-iq2-lookup-address-space-0001.json"
TABLE = ROOT / "docs/research/glm52/tables/f018-iq2-lookup-address-space-0001.md"


def _load(path: Path) -> tuple[dict[str, Any], str]:
    data = path.read_bytes()
    return json.loads(data), hashlib.sha256(data).hexdigest()


def _summary(record: dict[str, Any]) -> dict[str, Any]:
    samples = [float(value) for value in record["timing"]["measured_samples_seconds"]]
    ordered = sorted(samples)
    mean = sum(samples) / len(samples)
    variance = sum((value - mean) ** 2 for value in samples) / (len(samples) - 1)
    return {
        "source_commit": record["source"]["commit"],
        "sample_count": len(samples),
        "median_seconds": (ordered[(len(ordered) - 1) // 2] + ordered[len(ordered) // 2]) / 2,
        "mean_seconds": mean,
        "sample_standard_deviation_seconds": variance**0.5,
        "minimum_seconds": min(samples),
        "maximum_seconds": max(samples),
        "classification": record["classification"],
        "candidate_output_sha256": record["correctness"]["candidate_output_sha256"],
    }


def build() -> dict[str, Any]:
    device, device_sha = _load(DEVICE)
    constant, constant_sha = _load(CONSTANT)
    device_summary = _summary(device)
    constant_summary = _summary(constant)
    if device_summary["candidate_output_sha256"] != constant_summary["candidate_output_sha256"]:
        raise ValueError("lookup address-space outputs differ")
    if device_summary["sample_count"] != 100 or constant_summary["sample_count"] != 100:
        raise ValueError("lookup address-space populations must retain 100 samples")
    for record in (device, constant):
        compiler = record["setup"]["compiler"]
        if compiler["fast_math_enabled"] or compiler["language_version"] != "3.2":
            raise ValueError("lookup experiment compiler contract changed")
    ratio = constant_summary["median_seconds"] / device_summary["median_seconds"]
    return {
        "schema": "pulsarmlx.research.f018-iq2-lookup-address-space",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "inputs": {
            "device": {"path": str(DEVICE.relative_to(ROOT)), "sha256": device_sha},
            "constant": {"path": str(CONSTANT.relative_to(ROOT)), "sha256": constant_sha},
        },
        "device": device_summary,
        "constant": constant_summary,
        "constant_over_device_median_ratio": ratio,
        "exact_candidate_output_identity": True,
        "decision": {
            "retained_address_space": "device",
            "constant_tables_retained": False,
            "reason": "The bounded constant-table population preserved output identity but had a higher median; it offered no measured benefit.",
        },
        "claim_boundary": "Two sequential 100-sample synthetic populations on one M1 Ultra; not a counterbalanced hardware benchmark or real-matrix result.",
    }


def markdown(record: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Feature 018 IQ2 Lookup Address-Space Experiment",
            "",
            "| Variant | Samples | Median (s) | Mean (s) | Std dev (s) | Min (s) | Max (s) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            *[
                "| {} | {} | {:.9f} | {:.9f} | {:.9f} | {:.9f} | {:.9f} |".format(
                    name,
                    record[name]["sample_count"],
                    record[name]["median_seconds"],
                    record[name]["mean_seconds"],
                    record[name]["sample_standard_deviation_seconds"],
                    record[name]["minimum_seconds"],
                    record[name]["maximum_seconds"],
                )
                for name in ("device", "constant")
            ],
            "",
            f"Constant/device median ratio: `{record['constant_over_device_median_ratio']:.6f}`.",
            "Exact candidate output identity was preserved. The device address space remains in the scaffold because the constant experiment showed no bounded benefit.",
            "",
            record["claim_boundary"],
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = build()
    payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
    table = markdown(record)
    if args.check:
        if OUTPUT.read_text() != payload or TABLE.read_text() != table:
            raise SystemExit("lookup address-space artifacts are stale")
    else:
        OUTPUT.write_text(payload)
        TABLE.write_text(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
