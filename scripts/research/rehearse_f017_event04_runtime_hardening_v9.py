#!/usr/bin/env python3
"""Production-shaped V9 execution rehearsal with zero checkpoint payload access."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import tempfile
from pathlib import Path

from f017_canonical_serialization_v8 import bank_exclusive
from f017_event04_tensor_plan_v9 import build_plan, validate_plan
from f017_memory_gate_v9 import observe, prove_enforced_policy
from validate_f017_corrected_oracle_access_v9 import install_rehearsal_candidate, render_rehearsal_candidate, validate_installed_rehearsal


ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_METADATA = ROOT / "docs/validation/glm52-checkpoint.json"
CATALOG = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"
PRODUCTION_ROOT = Path("/Users/mhedhli/Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS")


def rehearse(output: Path) -> dict:
    metadata_raw = CHECKPOINT_METADATA.read_bytes(); metadata = json.loads(metadata_raw)
    if metadata["actual_status"] != "passed" or metadata["file_count"] != 6: raise ValueError("production metadata")
    shards = [{"filename": item["filename"], "size_bytes": item["size_bytes"], "sha256": item["sha256"],
               "role": "IDENTITY_ONLY" if index == 1 else "GRAPH_PAYLOAD"}
              for index, item in enumerate(metadata["files"], start=1)]
    plan = validate_plan(build_plan()); package_memory = observe(enforce=False); memory_policy = prove_enforced_policy()
    with tempfile.TemporaryDirectory(prefix="f017-event04-v9-shadow-") as raw:
        work = Path(raw); candidate = work / "candidate.json"
        rendered = render_rehearsal_candidate(PRODUCTION_ROOT, shards, CATALOG, candidate, "EVENT04-SHADOW",
                                               scope="PRODUCTION_SHADOW_NO_ACCESS")
        installed = work / "noncanonical-install" / "authorization.json"; receipt = work / "installation-receipt.json"
        install = install_rehearsal_candidate(candidate, installed, receipt); handshake = validate_installed_rehearsal(installed, receipt)
        core = {"schema": "pulsarmlx.f017.event04-production-shadow-deterministic-core/9.0.0", "result": "PASS",
                "checkpoint_metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(), "checkpoint_set_sha256": metadata["checkpoint_set_sha256"],
                "checkpoint_shard_count": 6, "checkpoint_total_bytes": metadata["total_bytes"], "graph_tensor_count": plan["graph_tensor_count"],
                "non_access_tensor_count": plan["non_access_tensor_count"], "graph_shards": plan["graph_shards"], "formats": plan["formats"],
                "candidate_validation": [rendered["primary"]["result"], rendered["secondary"]["result"]],
                "candidate_install_bytes_equal": install["candidate_install_bytes_equal"], "installed_handshake": handshake["result"],
                "production_memory_gate_policy": memory_policy,
                "synthetic_root_path_used": False, "production_identity_stage_invoked": False, "state_created": False,
                "checkpoint_shard_opens": 0, "checkpoint_identity_hash_reads": 0, "checkpoint_payload_reads": 0,
                "numerical_operations": 0, "event_04_authorization_created": False, "event_04_executed": False}
        core_bytes = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"
        envelope = {"schema": "pulsarmlx.f017.event04-production-shadow-volatile-envelope/9.0.0",
                    "deterministic_core_sha256": hashlib.sha256(core_bytes).hexdigest(), "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
                    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "architecture": platform.machine(),
                    "candidate_sha256": rendered["candidate_sha256"], "mint_memory_gate": rendered["candidate"]["mint_memory_gate"],
                    "package_start_memory_gate": package_memory, "temporary_root": str(work)}
    result = {"schema": "pulsarmlx.f017.event04-production-shaped-rehearsal/9.0.0", "result": "PASS",
              "deterministic_core": core, "deterministic_core_sha256": hashlib.sha256(core_bytes).hexdigest(), "volatile_envelope": envelope,
              "original_checkpoint_access": 0, "historical_master_ledger": 175}
    bank_exclusive(output, result); return result


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, required=True); args = parser.parse_args()
    result = rehearse(args.output); print(json.dumps({"result": result["result"], "checkpoint_opens": 0, "checkpoint_reads": 0,
        "graph_tensors": result["deterministic_core"]["graph_tensor_count"]}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
