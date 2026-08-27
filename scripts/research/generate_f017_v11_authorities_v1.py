#!/usr/bin/env python3
"""Generate/check the V11 scientific-access authority from exact bindings."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEASUREMENT = ROOT / "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v7.json"
OUTPUT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v11-v7.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding(relative: str) -> dict:
    path = ROOT / relative
    return {"path":relative,"sha256":_sha(path)}


def generate() -> dict:
    measurement = json.loads(MEASUREMENT.read_text())
    implementation = {
        Path(record["path"]).stem: {"path":record["path"],"sha256":record["sha256"]}
        for record in measurement["measured_paths"]
    }
    if len(implementation) != measurement["measured_path_count"]:
        raise ValueError("V11 scientific implementation role collision")
    return {
        "schema":"pulsarmlx.f017.corrected-full-checkpoint-oracle-scientific-access/11.3.0",
        "supersedes":"specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v11-v6.json",
        "status":"V11_READINESS_SCOPE_SEPARATED_AND_INSTALL_REDERIVED_NO_EVENT05_AUTHORITY",
        "active_generation":_binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-active-generation-v11.json"),
        "implementation_measurement":_binding("docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v7.json"),
        "implementation_head":measurement["implementation_head"],
        "implementation_tree":measurement["implementation_tree"],
        "implementation":implementation,
        "numerical_contract":_binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json"),
        "numerical_output_interface":_binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-numerical-output-interface-v1.json"),
        "binary_result_envelope":_binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-binary-result-envelope-v11-v2.json"),
        "result_authority":_binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-authority-v11-v2.json"),
        "result_artifact_dag":_binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-artifact-dag-v11.json"),
        "readiness_consumer_interface":_binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-readiness-consumer-interface-v2.json"),
        "approval_interface":_binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-approval-interface-v1.json"),
        "production_tensor_plan":_binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-production-tensor-plan-v9.json"),
        "checkpoint_metadata":_binding("docs/validation/glm52-checkpoint.json"),
        "checkpoint_catalog":_binding("docs/research/glm52/raw/f016-c01-catalog-0001.json"),
        "diagnostic_reuse_grant":_binding("specs/017-rust-native-inference-runtime/contracts/f017-event04-result-envelope-diagnostic-reuse-grant-v11.json"),
        "diagnostic_qualification":_binding("docs/architecture/reviews/evidence/f017-event04-diagnostic-fixture-qualification-v11-v1.json"),
        "full_geometry_qualification":_binding("docs/architecture/reviews/evidence/f017-v11-full-geometry-qualification-v2.json"),
        "failure_qualification":_binding("docs/architecture/reviews/evidence/f017-v11-result-failure-qualification-v2.json"),
        "production_shaped_rehearsal":_binding("docs/architecture/reviews/evidence/f017-event05-production-shaped-no-access-rehearsal-v11-v2.json"),
        "event05_go_template":_binding("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event05-execution-go-template-v11-v2.json"),
        "limits":{"attempts":1,"retries":0,"resume":False,"event_04_retry":False,
                  "event_05_authorization_created":False,"event_05_executed":False,
                  "p1_attempt_2_executed":False},
        "historical_master_ledger":175,
        "original_checkpoint_access":0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(); raw = json.dumps(generate(), sort_keys=True, separators=(",", ":")) + "\n"
    if arguments.check:
        if not OUTPUT.is_file() or OUTPUT.read_text() != raw:
            raise ValueError("V11 scientific-access authority drift")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True); OUTPUT.write_text(raw)
    return 0


if __name__ == "__main__": raise SystemExit(main())
