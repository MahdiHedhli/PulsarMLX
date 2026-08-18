#!/usr/bin/env python3
"""Validate the checkpoint-free F017 complete-layer v2 evaluation release."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import stat
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research.evaluate_f017_complete_layer_aggregate_v2 import (
    LEDGER, LEDGER_SHA, RESIDUAL_SHA, ROUTED_INTERSECTION_SHA, ROUTED_NOMINAL_SHA,
    SHARED_SHA, SHARED_REUSE_SHA, STARTING_HEAD, V2_CONTRACT_SHA,
    V2_IMPLEMENTATION_SHA, load_json, require, sha256_path,
)


EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-complete-layer-aggregate-v2-evaluation-v1.json"
DESCRIPTOR = ROOT / "docs/architecture/reviews/evidence/f017-complete-layer3-canonical-authority-v1.json"
SCHEMA = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-complete-layer-aggregate-v2-evaluation-v1.schema.json"
EXPECTED_CANONICAL = "e9427e22ef86f161786cfcf22a74b92c1cca50e3d601c6c119633d1458904594"
EXPECTED_INTERVAL = "8e21fd16c1b0d1c449d395d7368c1d317966c272a5b704f29ca0d5f0d0e3223a"


def _no_private_path(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            require("absolute_path" not in key.lower(), "private path field")
            _no_private_path(item)
    elif isinstance(value, list):
        for item in value:
            _no_private_path(item)
    elif isinstance(value, str):
        require(not value.startswith("/Users/") and ".pulsarmlx-local" not in value, "private path leak")


def validate(private_root: Path | None = None) -> str:
    evidence = load_json(EVIDENCE)
    descriptor = load_json(DESCRIPTOR)
    schema = load_json(SCHEMA)
    require(schema.get("additionalProperties") is False, "schema not fail-closed")
    require(evidence.get("starting_authoritative_head") == STARTING_HEAD, "starting head")
    authority = evidence.get("authority", {})
    require(authority.get("complete_layer_v2_contract_sha256") == V2_CONTRACT_SHA, "contract identity")
    require(authority.get("complete_layer_v2_implementation_sha256") == V2_IMPLEMENTATION_SHA, "theorem identity")
    require(authority.get("shared_reuse_authorization_file_sha256") == SHARED_REUSE_SHA, "shared reuse identity")
    require(sha256_path(LEDGER) == LEDGER_SHA and load_json(LEDGER).get("cumulative_tensor_payloads") == 166,
            "ledger identity/value")
    routed = evidence.get("routed_reuse", {})
    require(routed.get("nominal_canonical_le_f64_sha256") == ROUTED_NOMINAL_SHA, "routed nominal")
    require(routed.get("sound_intersection_canonical_le_f64_interval_sha256") == ROUTED_INTERSECTION_SHA,
            "routed enclosure")
    require(routed.get("routing_propagation_recomputed") is False, "route recomputation")
    complete = evidence.get("canonical_complete_layer", {})
    require(complete.get("canonical_le_f32_sha256") == EXPECTED_CANONICAL and complete.get("shape") == [6144]
            and complete.get("dtype") == "f32" and complete.get("finite_count") == 6144, "canonical layer")
    perturbation = evidence.get("perturbation", {})
    require(perturbation.get("final_f32_componentwise_interval_sha256") == EXPECTED_INTERVAL, "interval identity")
    require(perturbation.get("shared_uncertainty_mode") == "EXACT_CLASS_POINT_DELTA_S_ZERO", "shared point rule")
    acceptance = evidence.get("acceptance", {})
    require(acceptance.get("mathematical_qualification") == "PASS", "mathematical qualification")
    require(acceptance.get("engineering_h2") == "PASS", "engineering H2")
    for field in ("max_absolute", "rmse", "cosine"):
        require(acceptance.get(field, {}).get("status") == "PASS", f"{field} status")
    require(float(acceptance.get("global_safety_factor")) >= 2.0, "global safety factor")
    require(evidence.get("disposition", {}).get("route_ambiguity") == "ROUTE AMBIGUITY QUALIFIED AT COMPLETE-LAYER OUTPUT",
            "route disposition")
    replay = evidence.get("deterministic_replay", {})
    require(replay.get("fresh_process_count") == 3 and replay.get("byte_identical_public_result") is True,
            "deterministic replay")
    require(set(replay.get("canonical_sha256_by_run", [])) == {EXPECTED_CANONICAL}, "canonical replay")
    require(set(replay.get("perturbation_sha256_by_run", [])) == {EXPECTED_INTERVAL}, "interval replay")
    isolation = evidence.get("isolation", {})
    require((isolation.get("checkpoint_reads"), isolation.get("shard_opens"), isolation.get("payload_reads")) == (0, 0, 0),
            "access isolation")
    require(isolation.get("real_payload_ledger_before") == isolation.get("real_payload_ledger_after") == 166,
            "ledger isolation")
    history = evidence.get("historical_immutability", {})
    require(history.get("REAL_1") == history.get("REAL_2") == history.get("REAL_3") == "REJECTED_UNCHANGED",
            "historical REAL dispositions")
    require(history.get("coefficient_qualification") == "0_OF_8_FAIL_UNCHANGED"
            and history.get("routed_aggregate_v1") == "FAIL_UNCHANGED", "historical numerical failures")
    require(descriptor.get("artifact", {}).get("sha256") == EXPECTED_CANONICAL, "descriptor identity")
    require(descriptor.get("source", {}).get("evaluation_file_sha256") == sha256_path(EVIDENCE), "descriptor source")
    require(descriptor.get("classification", {}).get("reproducibility_class") == "PERSISTED_AUTHORITY",
            "descriptor class")
    require(descriptor.get("classification", {}).get("production_mechanism") == "EXACT_CLASS_FIXED_ORDER_ANALYTICAL_COMPOSITION",
            "descriptor mechanism")
    _no_private_path(evidence)
    _no_private_path(descriptor)
    if private_root is not None:
        manifest = private_root / "manifest.json"
        canonical = private_root / "outputs/complete_layer3_canonical.f32le"
        intervals = private_root / "bounds/final_f32_perturbation_intervals.f64le"
        for path, size, identity in ((canonical, 24576, EXPECTED_CANONICAL), (intervals, 98304, EXPECTED_INTERVAL)):
            metadata = path.lstat()
            require(stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode), "private authority type")
            require(metadata.st_size == size and metadata.st_nlink == 1 and not metadata.st_mode & 0o222,
                    "private authority immutability")
            require(sha256_path(path) == identity, "private authority identity")
        require(sha256_path(manifest) == evidence.get("canonical_layer3_authority", {}).get("private_manifest_canonical_sha256"),
                "private manifest identity")
    return "F017_COMPLETE_LAYER_AGGREGATE_V2_EVALUATION_VALID"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-root", type=Path)
    args = parser.parse_args()
    print(validate(args.private_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
