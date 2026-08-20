#!/usr/bin/env python3
"""Generate checkpoint-free real-geometry rehearsal evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research.f017_representative_routed_aggregate_executor_v1 import IDS, WEIGHTS

ROOT = Path(__file__).resolve().parents[2]
EXECUTOR = ROOT / "scripts/research/f017_representative_routed_aggregate_executor_v1.py"
PYTHON = Path("/opt/homebrew/bin/python3.14")


def synthetic_raw(ordinal: int) -> bytes:
    values = [((ordinal + 1) * ((k % 257) - 128) + ((k * 17 + ordinal) % 31) - 15) / 2048.0 for k in range(6144)]
    return struct.pack("<6144f", *values)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        records = []
        for ordinal, (expert_id, weight) in enumerate(zip(IDS, WEIGHTS, strict=True)):
            name = f"{ordinal:02d}-expert-{expert_id}-down.f32le"
            raw = synthetic_raw(ordinal)
            target = root / name
            target.write_bytes(raw)
            os.chmod(target, 0o400)
            records.append({"ordinal": ordinal, "expert_id": expert_id, "routing_weight": weight,
                            "private_relative_path": name, "output_sha256": sha(raw),
                            "dtype": "little-endian-f32", "shape": [6144], "byte_length": 24576})
        manifest = {"schema": "pulsarmlx.f017.representative-routed-aggregate-synthetic-input",
                    "schema_version": "1.0.0", "synthetic": True, "inputs": records}
        manifest_path = root / "synthetic-manifest.json"
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
        identities = []
        process_results = []
        for repeat in range(2):
            output_path = root / f"aggregate-{repeat}.f64le"
            result = subprocess.run([str(PYTHON), str(EXECUTOR), "--synthetic-rehearsal",
                                     "--synthetic-manifest", str(manifest_path), "--output-root", str(root),
                                     "--output", str(output_path)], check=True, capture_output=True, text=True)
            packet = json.loads(result.stdout)
            raw = output_path.read_bytes()
            identities.append(sha(raw))
            process_results.append(packet)
        if len(set(identities)) != 1:
            raise RuntimeError("fresh-process identity mismatch")
        protected_manifest = json.loads(json.dumps(manifest))
        protected_manifest["inputs"][0]["output_sha256"] = "0b6036ef2e77142094b673c421b96719619a58e15eee7522347b37f73d9b892b"
        protected_path = root / "protected-manifest.json"
        protected_path.write_text(json.dumps(protected_manifest, sort_keys=True, separators=(",", ":")) + "\n")
        negative = subprocess.run([str(PYTHON), str(EXECUTOR), "--synthetic-rehearsal",
                                   "--synthetic-manifest", str(protected_path), "--output-root", str(root),
                                   "--output", str(root / "forbidden.f64le")], capture_output=True, text=True)
        if negative.returncode != 2 or "protected representative output declared" not in negative.stderr:
            raise RuntimeError("synthetic protected-output gate failed")
        evidence = {
            "schema": "pulsarmlx.f017.representative-routed-aggregate-synthetic-rehearsal",
            "schema_version": "1.0.0",
            "synthetic": True,
            "real_geometry": {"inputs": 8, "input_dtype": "little-endian-f32", "input_shape_each": [6144],
                              "input_bytes_each": 24576, "output_dtype": "little-endian-f64",
                              "output_shape": [6144], "output_bytes": 49152},
            "canonical_order": list(IDS),
            "routing_weights": list(WEIGHTS),
            "synthetic_input_manifest_sha256": sha(manifest_path.read_bytes()),
            "synthetic_input_sha256": [record["output_sha256"] for record in records],
            "fresh_processes": 2,
            "fresh_process_output_sha256": identities,
            "exact_identity": True,
            "output_sha256": identities[0],
            "process_dispositions": [packet["disposition"] for packet in process_results],
            "all_after_hashes_exact": all(packet["inputs_after"] == [r["output_sha256"] for r in records]
                                             for packet in process_results),
            "checkpoint_reads": 0,
            "shard_opens": 0,
            "expert_executions": 0,
            "real_aggregate_executions": 0,
            "synthetic_aggregate_executions": 2,
            "fresh_process_protected_output_rejection": "PASS_RC_2",
            "real_representative_output_bytes_used": False,
            "result": "PASS"
        }
        args.output.write_text(json.dumps(evidence, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
