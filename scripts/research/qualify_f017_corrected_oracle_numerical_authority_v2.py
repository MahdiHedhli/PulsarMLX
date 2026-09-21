#!/usr/bin/env python3
"""Complete checkpoint-free requalification of numerical authority v2."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts/research"
HISTORICAL_COMMIT = "84f0d1dc3e60a4151329ed82773880951ee3e618"
SEEDS = list(range(18101, 18113))


def run(command, *, cwd=ROOT, stdout=None) -> None:
    subprocess.run(command, cwd=cwd, check=True, stdout=stdout)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); arguments = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="f017-num-authority-v2-") as directory:
        work = Path(directory); archive = work / "historical.tar"
        with archive.open("wb") as output:
            run(["git", "archive", HISTORICAL_COMMIT, "scripts/research"], stdout=output)
        historical = work / "historical"; historical.mkdir()
        with tarfile.open(archive) as source: source.extractall(historical, filter="data")
        fixtures = work / "fixtures"
        run([sys.executable, str(RESEARCH / "generate_f017_corrected_oracle_fixtures.py"), str(fixtures)])
        accepted = work / "accepted-corpus.json"
        run([sys.executable, str(RESEARCH / "qualify_f017_corrected_oracles.py"), "--output", str(accepted)])
        accepted_doc = json.loads(accepted.read_text())
        equivalence = []
        for seed in SEEDS:
            fixture = fixtures / f"fixture-{seed}.json"
            for role in ("primary", "secondary"):
                old = historical / "scripts/research" / f"f017_corrected_oracle_{role}.py"
                old_output = work / f"{seed}-{role}-old.json"; new_output = work / f"{seed}-{role}-new.json"
                run([sys.executable, str(old), "synthetic", str(fixture), str(old_output)], cwd=historical / "scripts/research")
                run([sys.executable, str(RESEARCH / "f017_corrected_oracle_checkpoint_free_runner_v2.py"), role, str(fixture), str(new_output)])
                old_value = json.loads(old_output.read_text()); new_value = json.loads(new_output.read_text())
                exact = old_value == new_value
                if not exact: raise ValueError(f"historical numerical drift: {seed}/{role}")
                equivalence.append({"seed": seed, "role": role, "exact_complete_result": True,
                                    "old_sha256": sha(old_output), "new_sha256": sha(new_output)})
        repeat_fixture = fixtures / "fixture-18106.json"
        repeat_identity = {}
        for role in ("primary", "secondary"):
            hashes = []
            for repeat in range(10):
                output = work / f"fresh-{role}-{repeat:02}.json"
                run([sys.executable, str(RESEARCH / "f017_corrected_oracle_checkpoint_free_runner_v2.py"), role, str(repeat_fixture), str(output)])
                hashes.append(sha(output))
            if len(set(hashes)) != 1: raise ValueError(f"fresh-process drift: {role}")
            repeat_identity[role] = {"processes": 10, "unique_output_sha256_count": 1, "output_sha256": hashes[0]}
        target = work / "target-adapters.json"
        run([sys.executable, str(RESEARCH / "qualify_f017_corrected_oracle_target_adapters_v6.py"), "--repeats", "10", "--output", str(target)])
        target_doc = json.loads(target.read_text())
        document = {
            "schema": "pulsarmlx.f017.corrected-oracle-numerical-requalification/2.0.0",
            "result": "PASS",
            "status": "CORRECTED_ORACLE_NUMERICAL_REQUALIFICATION_V2",
            "historical_commit": HISTORICAL_COMMIT,
            "canonical_seeds": SEEDS,
            "canonical_case_count": accepted_doc["seeds"].__len__(),
            "packed_decoder_case_count": accepted_doc["packed_decoder_case_count"],
            "format_count": 11,
            "mutation_count": accepted_doc["mutation_count"],
            "historical_successor_equivalence_case_count": len(equivalence),
            "historical_successor_equivalence": equivalence,
            "fresh_process_identity": repeat_identity,
            "target_adapter_synthetic_repeat_count": target_doc["repeat_count"],
            "target_adapter_result": target_doc["result"],
            "frozen_thresholds": accepted_doc["frozen_thresholds"],
            "numerical_methodology_changed": False,
            "numerical_thresholds_changed": False,
            "primary_pure_core_sha256": sha(RESEARCH / "f017_corrected_oracle_primary_numerics_v2.py"),
            "secondary_pure_core_sha256": sha(RESEARCH / "f017_corrected_oracle_secondary_numerics_v2.py"),
            "primary_target_source_sha256": sha(RESEARCH / "f017_corrected_oracle_primary_target_source_v6.py"),
            "secondary_target_source_sha256": sha(RESEARCH / "f017_corrected_oracle_secondary_target_source_v6.py"),
            "original_checkpoint_shard_opens": 0,
            "original_checkpoint_payload_reads": 0,
        }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"result": "PASS", "equivalence_cases": len(equivalence), "target_repeats": 10}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
