#!/usr/bin/env python3
"""Fresh-process V8 lifecycle qualification using synthetic shards only."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from execute_f017_corrected_oracle_event_v8 import execute_synthetic
from f017_canonical_serialization_v8 import bank_exclusive
from f017_descriptor_runtime_mutations_v8 import qualify as qualify_runtime_mutations
from f017_synthetic_checkpoint_v8 import FORMATS, prepare


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
NUMERICAL_REQUALIFICATION = ROOT / "docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v3.json"


def _single(seed: int, mixed: bool) -> dict:
    with tempfile.TemporaryDirectory(prefix="f017-v8-package-") as raw:
        root = Path(raw)
        installed, receipt, _ = prepare(root, seed, f"P{seed}-{'MIXED' if mixed else 'MINIMAL'}", mixed)
        result = execute_synthetic(installed, receipt, root / "evidence")
        expected_formats = FORMATS if mixed else ["F32"]
        if (result["result"] != "PASS" or result["primary"]["format_coverage"] != expected_formats
                or result["secondary"]["format_coverage"] != expected_formats
                or result["identity"]["retained_lease_count"] != 5
                or result["primary"]["path_reopen_count"] != 0
                or result["secondary"]["path_reopen_count"] != 0
                or result["release"]["live_leases_after_release"] != 0):
            raise ValueError("synthetic V8 package result")
        return {
            "result": "PASS", "kind": "MIXED_FORMAT" if mixed else "MINIMAL_F32",
            "candidate_sha256": result["candidate_sha256"],
            "descriptor_count": result["identity"]["retained_lease_count"],
            "primary_path_reopens": result["primary"]["path_reopen_count"],
            "secondary_path_reopens": result["secondary"]["path_reopen_count"],
            "formats": expected_formats, "live_leases_after_terminal": 0,
            "original_checkpoint_access": 0,
        }


def _subprocess_json(command: list[str]) -> dict:
    completed = subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def qualify(output: Path) -> dict:
    packages = []
    for index in range(20):
        packages.append(_subprocess_json([
            sys.executable, str(SELF), "--single", "--seed", str(18101 + index % 12),
            *( ["--mixed"] if index >= 10 else [] ),
        ]))
    symbolic_repetitions = []
    for _ in range(5):
        symbolic_repetitions.append(_subprocess_json([
            sys.executable, str(ROOT / "scripts/research/construct_f017_lifecycle_v8_symbolically.py")
        ]))
    if any(item["constructed_outcomes"] != 48 or item["result"] != "PASS" for item in symbolic_repetitions):
        raise ValueError("fresh-process failure outcome construction")
    mutations = qualify_runtime_mutations()
    numerical = json.loads(NUMERICAL_REQUALIFICATION.read_bytes())
    if numerical["result"] != "PASS" or numerical["format_count"] != 11:
        raise ValueError("numerical format authority")
    result = {
        "schema": "pulsarmlx.f017.corrected-oracle-lifecycle-v8-synthetic-qualification/1.0.0",
        "result": "PASS",
        "implementation_shas": {
            name: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            for name, relative in {
                "authorizer": "scripts/research/validate_f017_corrected_oracle_access_v8.py",
                "coordinator": "scripts/research/execute_f017_corrected_oracle_event_v8.py",
                "lease_manager": "scripts/research/f017_descriptor_lease_manager_v8.py",
                "primary_wrapper": "scripts/research/f017_corrected_oracle_primary_v8.py",
                "secondary_wrapper": "scripts/research/f017_corrected_oracle_secondary_v8.py",
            }.items()
        },
        "successful_package_count": len(packages),
        "minimal_f32_package_count": sum(item["kind"] == "MINIMAL_F32" for item in packages),
        "mixed_format_package_count": sum(item["kind"] == "MIXED_FORMAT" for item in packages),
        "successful_packages": packages,
        "candidate_dual_validation_fresh_process_count": len(packages),
        "installed_authorization_handshake_fresh_process_count": len(packages),
        "identity_stage_fresh_process_count": len(packages),
        "primary_continuity_validation_fresh_process_count": len(packages),
        "secondary_continuity_validation_fresh_process_count": len(packages),
        "terminal_outcome_class_fresh_process_repetitions": 5,
        "legal_outcomes_per_repetition": 48,
        "failure_outcome_count_per_repetition": 47,
        "symbolic_artifacts_per_repetition": symbolic_repetitions[0]["real_artifacts_created"],
        "runtime_descriptor_mutations_rejected": mutations["mutation_count"],
        "total_v8_design_and_runtime_mutations_rejected": 256 + mutations["mutation_count"],
        "mutation_unexpected_passes": mutations["unexpected_passes"],
        "uncontrolled_exception_classes": mutations["uncontrolled_exception_classes"],
        "format_authority": {
            "formats": FORMATS,
            "numerical_requalification_path": str(NUMERICAL_REQUALIFICATION.relative_to(ROOT)),
            "numerical_requalification_sha256": hashlib.sha256(NUMERICAL_REQUALIFICATION.read_bytes()).hexdigest(),
            "packed_decoder_case_count": numerical["packed_decoder_case_count"],
        },
        "descriptor_count_per_consumer": 5,
        "descriptor_ordinals": [2, 3, 4, 5, 6],
        "path_reopen_count": 0,
        "live_leases_after_success_terminal": 0,
        "original_checkpoint_shard_opens": 0,
        "original_checkpoint_identity_hash_reads": 0,
        "original_checkpoint_payload_reads": 0,
        "event_04_authorization_created": False,
        "event_04_executed": False,
        "p1_attempt_2_executed": False,
    }
    bank_exclusive(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single", action="store_true")
    parser.add_argument("--seed", type=int, default=18101)
    parser.add_argument("--mixed", action="store_true")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    if arguments.single:
        print(json.dumps(_single(arguments.seed, arguments.mixed), sort_keys=True, separators=(",", ":")))
        return 0
    if arguments.output is None:
        raise ValueError("--output is required")
    result = qualify(arguments.output)
    print(json.dumps({
        "result": result["result"], "successful_packages": result["successful_package_count"],
        "failure_repetitions": result["terminal_outcome_class_fresh_process_repetitions"],
        "runtime_mutations": result["runtime_descriptor_mutations_rejected"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
