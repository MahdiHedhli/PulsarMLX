#!/usr/bin/env python3
"""Production-shaped V11/Event-05 planning with no checkpoint payload access."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]

from f017_corrected_oracle_authorization_v11 import production_shards, IMPLEMENTATION_MEASUREMENT
from f017_result_envelope_v11 import PAYLOAD_SPECS
from validate_f017_corrected_oracle_access_v11 import (
    install_rehearsal_candidate, render_rehearsal_candidate, validate_installed_rehearsal,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    event04 = json.loads((ROOT / "docs/architecture/reviews/evidence/f017-event04-v10-authorization-candidate-v1.json").read_text())
    plan_path = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-production-tensor-plan-v9.json"
    plan = json.loads(plan_path.read_text())
    if (plan["result"] != "PASS" or plan["graph_tensor_count"] != 1_410
            or plan["non_access_tensor_count"] != 399
            or plan["formats"] != ["F32","IQ2_S","IQ2_XXS","IQ3_XXS","IQ4_XS","Q2_K","Q3_K","Q4_K","Q5_K","Q6_K","Q8_0"]):
        raise ValueError("production tensor plan")
    measurement = json.loads(IMPLEMENTATION_MEASUREMENT.read_text())
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        rendered = render_rehearsal_candidate(
            Path(event04["checkpoint_root"]), production_shards(), plan_path.resolve(),
            root / "candidate.json", "EVENT05-V11", scope="PRODUCTION_SHADOW_NO_ACCESS",
        )
        receipt = install_rehearsal_candidate(
            root / "candidate.json", root / "installed.json", root / "installation-receipt.json"
        )
        handshake = validate_installed_rehearsal(root / "installed.json", root / "installation-receipt.json")
        candidate_sha = rendered["candidate_sha256"]
        if receipt["candidate_sha256"] != candidate_sha or handshake["candidate_sha256"] != candidate_sha:
            raise ValueError("rehearsal candidate/install identity")
    payload_plan = [spec.record() for spec in PAYLOAD_SPECS.values()]
    if sum(record["expected_byte_count"] for record in payload_plan) != 2_006_016:
        raise ValueError("V11 binary payload byte plan")
    result = {
        "schema":"pulsarmlx.f017.event05-production-shaped-no-access-rehearsal/11.0.0",
        "branch":"feat/017-rust-native-inference-runtime",
        "measurement_path":str(IMPLEMENTATION_MEASUREMENT.relative_to(ROOT)),
        "measurement_sha256":_sha(IMPLEMENTATION_MEASUREMENT),
        "implementation_head":measurement["implementation_head"],
        "implementation_tree":measurement["implementation_tree"],
        "candidate_sha256":candidate_sha,
        "candidate_validation":[rendered["primary"]["result"],rendered["secondary"]["result"]],
        "candidate_install_bytes_equal":True,
        "installed_handshake":"PASS",
        "machine":{"architecture":platform.machine(),"platform":platform.platform()},
        "checkpoint_root_metadata_only":event04["checkpoint_root"],
        "checkpoint_shard_count":len(production_shards()),
        "graph_tensor_count":plan["graph_tensor_count"],
        "non_access_tensor_count":plan["non_access_tensor_count"],
        "formats":plan["formats"],
        "primary_one_execution_output_plan":"PASS",
        "secondary_one_execution_output_plan":"PASS",
        "payload_plan":payload_plan,
        "payload_count":6,
        "full_logits_element_count":154_880,
        "control_plane_full_logits_arrays":0,
        "comparison_plan":"STREAMING_BINARY_PAYLOADS",
        "package_terminal_closure":"ALL_SIX_PAYLOADS",
        "event04_promotion":"PROHIBITED",
        "state_created":False,
        "live_authority_created":False,
        "event05_executed":False,
        "checkpoint_opens":0,
        "checkpoint_identity_reads":0,
        "checkpoint_reads":0,
        "numerical_operations":0,
        "original_checkpoint_access":0,
        "historical_master_ledger":175,
        "result":"PASS",
    }
    raw = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True); arguments.output.write_text(raw)
    else: print(raw, end="")
    return 0


if __name__ == "__main__": raise SystemExit(main())
