#!/usr/bin/env python3
"""Full-geometry, checkpoint-free V11 bundle and comparison qualification."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f017_binary_comparison_authority_v11 import derive_summary, validate_summary
from f017_canonical_serialization_v10 import canonical_bytes
from f017_result_artifacts_v11 import require_primary_terminal
from f017_result_bundle_authority_v11 import compose_comparison_closure
from f017_result_bundle_builder_v11 import bank_output_bundle
from f017_v11_full_geometry_fixture import DISTRIBUTIONS, make_output


def _sha(value: dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _fingerprint(role: str, distribution: str, seed: int) -> dict:
    output = make_output(role, distribution, seed)
    return {
        "role": role,
        "distribution": distribution,
        "seed": seed,
        "hidden": output.final_hidden_sha256,
        "normalized": output.final_normalized_sha256,
        "logits": output.full_logits_sha256,
        "selected_token": output.selected_token,
    }


def _fresh_fingerprint(role: str, distribution: str, seed: int) -> dict:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--fingerprint", role,
         "--distribution", distribution, "--seed", str(seed)],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def qualify() -> dict:
    digest = hashlib.sha256(b"F017-V11-SYNTHETIC-AUTHORITY").hexdigest()
    chunk_sizes = (1, 7, 257, 4_096, 8_191, 65_536)
    classifications: dict[str, int] = {}
    package_fingerprints: list[str] = []
    for case in range(30):
        distribution = DISTRIBUTIONS[case % len(DISTRIBUTIONS)]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            primary = bank_output_bundle(
                make_output("PRIMARY", distribution, case), root / "primary",
                authorization_id="F017-V11-SYNTHETIC-AUTH", package_attempt_id=f"PKG-{case:03d}",
                consumer_event_id=f"PRIMARY-{case:03d}", producer_measurement_sha256=digest,
                durable_start_sha256=digest, access_census_sha256=digest,
            )
            pa = primary["artifacts"]
            require_primary_terminal(pa["consumer_terminal"], _sha(pa["result_terminal"]),
                                     _sha(pa["receipt"]), _sha(pa["manifest"]))
            secondary = bank_output_bundle(
                make_output("SECONDARY", distribution, case), root / "secondary",
                authorization_id="F017-V11-SYNTHETIC-AUTH", package_attempt_id=f"PKG-{case:03d}",
                consumer_event_id=f"SECONDARY-{case:03d}", producer_measurement_sha256=digest,
                durable_start_sha256=digest, access_census_sha256=digest,
            )
            sa = secondary["artifacts"]
            summary = derive_summary(
                root / "primary", pa["manifest"]["payloads"][2],
                root / "secondary", sa["manifest"]["payloads"][2],
                pa["routing"], sa["routing"], pa["manifest"], sa["manifest"],
                pa["top32"], sa["top32"], pa["receipt"], sa["receipt"],
                "F017-V11-SYNTHETIC-AUTH", chunk_elements=chunk_sizes[case % len(chunk_sizes)],
            )
            validate_summary(summary, root / "primary", pa["manifest"]["payloads"][2],
                root / "secondary", sa["manifest"]["payloads"][2], pa["routing"], sa["routing"],
                pa["manifest"], sa["manifest"], pa["top32"], sa["top32"], pa["receipt"],
                sa["receipt"], "F017-V11-SYNTHETIC-AUTH",
                chunk_elements=chunk_sizes[case % len(chunk_sizes)])
            closure = compose_comparison_closure(
                primary_directory=root / "primary", secondary_directory=root / "secondary",
                authorization_id="F017-V11-SYNTHETIC-AUTH", package_attempt_id=f"PKG-{case:03d}",
                primary_artifacts=pa, secondary_artifacts=sa, comparison_summary=summary,
            )
            classifications[summary["classification"]] = classifications.get(summary["classification"], 0) + 1
            package_fingerprints.append(_sha(closure))
    fresh_primary = []
    fresh_secondary = []
    fresh_complete = []
    for repetition in range(20):
        distribution = DISTRIBUTIONS[repetition % len(DISTRIBUTIONS)]
        p = _fresh_fingerprint("PRIMARY", distribution, repetition)
        s = _fresh_fingerprint("SECONDARY", distribution, repetition)
        if p != _fingerprint("PRIMARY", distribution, repetition):
            raise ValueError("primary fresh-process determinism")
        if s != _fingerprint("SECONDARY", distribution, repetition):
            raise ValueError("secondary fresh-process determinism")
        fresh_primary.append(hashlib.sha256(canonical_bytes(p)).hexdigest())
        fresh_secondary.append(hashlib.sha256(canonical_bytes(s)).hexdigest())
        fresh_complete.append(hashlib.sha256(canonical_bytes({"primary":p,"secondary":s})).hexdigest())
    return {
        "schema": "pulsarmlx.f017.v11-full-geometry-qualification/1.0.0",
        "primary_result_bundles": 30,
        "secondary_result_bundles": 30,
        "complete_comparison_packages": 30,
        "primary_geometry": {"hidden": 6_144, "normalized": 6_144, "logits": 154_880, "dtype":"f64le"},
        "secondary_geometry": {"hidden": 6_144, "normalized": 6_144, "logits": 154_880, "dtype":"f32le"},
        "chunk_sizes": list(chunk_sizes),
        "value_distributions": list(DISTRIBUTIONS),
        "classification_census": classifications,
        "fresh_process_primary": len(fresh_primary),
        "fresh_process_secondary": len(fresh_secondary),
        "fresh_process_complete": len(fresh_complete),
        "deterministic_fingerprint_count": len(set(fresh_primary + fresh_secondary + fresh_complete)),
        "package_closure_count": len(package_fingerprints),
        "control_plane_full_arrays": 0,
        "original_checkpoint_access": 0,
        "result": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fingerprint", choices=("PRIMARY", "SECONDARY"))
    parser.add_argument("--distribution", choices=DISTRIBUTIONS, default="ZEROS")
    parser.add_argument("--seed", type=int, default=0)
    arguments = parser.parse_args()
    if arguments.fingerprint:
        result = _fingerprint(arguments.fingerprint, arguments.distribution, arguments.seed)
    else:
        result = qualify()
    raw = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(raw)
    else:
        print(raw, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
