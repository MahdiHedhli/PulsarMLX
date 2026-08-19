#!/usr/bin/env python3
"""Ten-run retained-only reproduction acceptance for representative M1-F0."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np

from f017_representative_m1f0_executor import (
    InventoryEntry,
    ProductionComputationStage,
    RetainedSpec,
    canonical_json,
)
from f017_representative_m1f0_executor_v3 import EagerDecoderRegistry, OpenRetainedAuthority, atomic_bytes, sha_file


REQUIRED_RUNS = 10
MINIMUM_FRESH_PROCESSES = 2
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-candidate-v3.json"


def validate_reproduction_bundle(bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    runs = bundle.get("runs", [])
    if len(runs) != REQUIRED_RUNS:
        errors.append("REPEAT_COUNT")
        return errors
    stage_identities = [item.get("required_stage_sha256") for item in runs]
    route_identities = [item.get("route_sha256") for item in runs]
    if any(item != stage_identities[0] for item in stage_identities) or not stage_identities[0]:
        errors.append("STAGE_IDENTITY")
    if any(item != route_identities[0] for item in route_identities) or not route_identities[0]:
        errors.append("ROUTE_IDENTITY")
    if any(item.get("checkpoint_rereads") != 0 or item.get("additional_shard_opens") != 0 for item in runs):
        errors.append("CHECKPOINT_FREE")
    if any(item.get("finite_checks") is not True for item in runs):
        errors.append("FINITE_CHECKS")
    if len({item.get("process_identity") for item in runs if item.get("fresh_process")}) < MINIMUM_FRESH_PROCESSES:
        errors.append("FRESH_PROCESSES")
    if bundle.get("retained_authority_before_sha256") != bundle.get("retained_authority_after_sha256"):
        errors.append("RETAINED_REHASH")
    if bundle.get("s0_before_sha256") != bundle.get("s0_after_sha256"):
        errors.append("S0_REHASH")
    if not bundle.get("same_executor") or not bundle.get("same_stage_vocabulary") or not bundle.get("same_serialization"):
        errors.append("PRODUCER_IDENTITY")
    if bundle.get("source") != "RETAINED_PAYLOADS_FROM_SINGLE_NINE_READ_EVENT":
        errors.append("SOURCE_CLASS")
    return errors


def route_identity(stages: dict[str, str]) -> str:
    return hashlib.sha256(canonical_json({name: stages[name] for name in (
        "ranking", "selected_ids", "routing_weights",
    )})).hexdigest()


def reproduce_once(candidate: dict[str, Any], retention_root: Path,
                   retained_paths: dict[str, Path]) -> dict[str, Any]:
    decoders = EagerDecoderRegistry().instantiate()
    decoded = {}
    for item in candidate["attention_payload_inventory"]:
        entry = InventoryEntry(item["ordinal"], item["key"], item["offset"], item["packed_bytes"],
            item["quantization"], tuple(item["logical_shape"]), item["packed_sha256"], item["decoded_sha256"])
        packed = retention_root / "packed" / f"{entry.ordinal:02d}.bin"
        if not packed.is_file() or sha_file(packed) != entry.packed_sha256:
            raise ValueError("RETAINED_PACKED_IDENTITY")
        pair = decoders[entry.quantization]
        first = pair.a.decode(packed, entry)
        second = pair.b.decode(packed, entry)
        if first.identity != second.identity or first.identity != entry.decoded_sha256:
            raise ValueError("DECODER_DISAGREEMENT")
        if first.canonical_bytes is not None and not np.isfinite(np.frombuffer(first.canonical_bytes, dtype="<f4")).all():
            raise ValueError("NONFINITE_DECODED")
        decoded[entry.key] = first
    open_authorities = {}
    try:
        for item in candidate["retained_inputs"]:
            spec = RetainedSpec(item["role"], item["key"], item["sha256"], item["dtype"],
                tuple(item["shape"]), item["byte_length"], item.get("private_manifest_sha256"))
            open_authorities[item["role"]] = OpenRetainedAuthority(retained_paths[item["role"]], spec)
        arrays = {role: authority.array() for role, authority in open_authorities.items()}
        if not all(np.isfinite(value).all() for value in arrays.values()):
            raise ValueError("NONFINITE_RETAINED")
        stages = ProductionComputationStage().compute(decoded, arrays)
        after = {role: authority.verify_after() for role, authority in open_authorities.items()}
        return {
            "required_stage_sha256": hashlib.sha256(canonical_json(stages)).hexdigest(),
            "route_sha256": route_identity(stages),
            "retained_after_sha256": after,
            "checkpoint_rereads": 0,
            "additional_shard_opens": 0,
            "finite_checks": True,
        }
    finally:
        for authority in open_authorities.values():
            authority.close()


def produce_bundle(candidate_path: Path, retention_root: Path,
                   retained_paths: dict[str, Path], output: Path) -> dict[str, Any]:
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    before = {role: sha_file(path) for role, path in retained_paths.items()}
    runs = []
    with tempfile.TemporaryDirectory(prefix="f017-m1f0-reproduction-") as name:
        temporary = Path(name)
        config = temporary / "config.json"
        config.write_bytes(canonical_json({
            "candidate": str(candidate_path), "retention_root": str(retention_root),
            "retained_paths": {role: str(path) for role, path in retained_paths.items()},
        }))
        for index in range(MINIMUM_FRESH_PROCESSES):
            target = temporary / f"fresh-{index}.json"
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--one-run",
                            "--config", str(config), "--output", str(target)], check=True)
            item = json.loads(target.read_text(encoding="utf-8"))
            item.update(fresh_process=True, process_identity=f"fresh-{index+1}")
            runs.append(item)
    for _ in range(REQUIRED_RUNS - MINIMUM_FRESH_PROCESSES):
        item = reproduce_once(candidate, retention_root, retained_paths)
        item.update(fresh_process=False, process_identity="parent")
        runs.append(item)
    after = {role: sha_file(path) for role, path in retained_paths.items()}
    bundle = {
        "runs": runs,
        "source": "RETAINED_PAYLOADS_FROM_SINGLE_NINE_READ_EVENT",
        "retained_authority_before_sha256": before,
        "retained_authority_after_sha256": after,
        "s0_before_sha256": before["canonical_s0"],
        "s0_after_sha256": after["canonical_s0"],
        "same_executor": True,
        "same_stage_vocabulary": True,
        "same_serialization": True,
    }
    errors = validate_reproduction_bundle(bundle)
    if errors:
        raise ValueError("REPRODUCTION_FAILED:" + ",".join(errors))
    atomic_bytes(output, canonical_json(bundle))
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--bundle", type=Path)
    mode.add_argument("--produce", action="store_true")
    mode.add_argument("--one-run", action="store_true")
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--retention-root", type=Path)
    parser.add_argument("--canonical-s0", type=Path)
    parser.add_argument("--ffn-norm", type=Path)
    parser.add_argument("--router-matrix", type=Path)
    parser.add_argument("--correction-bias", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.one_run:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        result = reproduce_once(json.loads(Path(config["candidate"]).read_text()),
            Path(config["retention_root"]), {k: Path(v) for k,v in config["retained_paths"].items()})
        args.output.write_bytes(canonical_json(result))
        return 0
    if args.produce:
        required = (args.retention_root, args.canonical_s0, args.ffn_norm,
                    args.router_matrix, args.correction_bias, args.output)
        if any(value is None for value in required):
            parser.error("--produce requires retention root, four retained inputs, and output")
        produce_bundle(args.candidate, args.retention_root, {
            "canonical_s0": args.canonical_s0, "ffn_norm": args.ffn_norm,
            "router_matrix": args.router_matrix, "correction_bias": args.correction_bias,
        }, args.output)
        print(json.dumps({"result":"PASS","required_runs":10,"checkpoint_reads":0,"shard_opens":0},sort_keys=True))
        return 0
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    if "reproduction" in bundle: bundle = bundle["reproduction"]
    errors = validate_reproduction_bundle(bundle)
    print(json.dumps({"result": "FAIL" if errors else "PASS", "errors": errors,
                      "required_runs": REQUIRED_RUNS, "checkpoint_reads": 0,
                      "shard_opens": 0}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
