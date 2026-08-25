#!/usr/bin/env python3
"""Production-shaped V8 rehearsal that never opens a checkpoint shard."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import tempfile
from pathlib import Path

from f017_canonical_serialization_v8 import bank_exclusive
from f017_descriptor_runtime_mutations_v8 import qualify as qualify_runtime_mutations
from f017_macos_memory_observation_v1 import observe_vm_stat
from validate_f017_corrected_oracle_access_v8 import (
    install_rehearsal_candidate,
    render_rehearsal_candidate,
    validate_installed_rehearsal,
)


ROOT = Path(__file__).resolve().parents[2]
CHECKPOINT_METADATA = ROOT / "docs/validation/glm52-checkpoint.json"
PRODUCTION_ROOT = Path("/Users/mhedhli/Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS")
MEMORY_THRESHOLD = 17_179_869_184


def rehearse(output: Path) -> dict:
    metadata_raw = CHECKPOINT_METADATA.read_bytes()
    metadata = json.loads(metadata_raw)
    if (metadata["actual_status"] != "passed" or metadata["file_count"] != 6
            or metadata["total_bytes"] != sum(item["size_bytes"] for item in metadata["files"])):
        raise ValueError("production checkpoint metadata")
    shards = [{
        "filename": item["filename"], "size_bytes": item["size_bytes"],
        "sha256": item["sha256"],
        "role": "IDENTITY_ONLY" if index == 1 else "GRAPH_PAYLOAD",
    } for index, item in enumerate(metadata["files"], start=1)]
    observation = observe_vm_stat()
    mutation_result = qualify_runtime_mutations()
    with tempfile.TemporaryDirectory(prefix="f017-event04-v8-shadow-") as raw:
        work = Path(raw)
        candidate_path = work / "candidate.json"
        rendered = render_rehearsal_candidate(
            PRODUCTION_ROOT, shards, candidate_path, "EVENT04-SHADOW"
        )
        installed_path = work / "noncanonical-install" / "authorization.json"
        receipt_path = work / "installation-receipt.json"
        install = install_rehearsal_candidate(candidate_path, installed_path, receipt_path)
        handshake = validate_installed_rehearsal(installed_path, receipt_path)
        if candidate_path.read_bytes() != installed_path.read_bytes():
            raise ValueError("shadow candidate/install identity")
        result = {
            "schema": "pulsarmlx.f017.corrected-oracle-event04-production-shaped-rehearsal/8.0.0",
            "result": "PASS",
            "authority": False,
            "operator_go": False,
            "active_generation_during_rehearsal": "NONE",
            "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
            "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "architecture": platform.machine(),
            "machine_brand": subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
            "memory_page_size_bytes": observation.page_size_bytes,
            "memory_available_bytes": observation.available_bytes,
            "future_live_memory_threshold_bytes": MEMORY_THRESHOLD,
            "future_live_memory_gate": "PASS" if observation.available_bytes >= MEMORY_THRESHOLD else "FAIL_CLOSED",
            "memory_observed_at_unix_ns": observation.observed_at_unix_ns,
            "checkpoint_metadata_path": str(CHECKPOINT_METADATA.relative_to(ROOT)),
            "checkpoint_metadata_sha256": hashlib.sha256(metadata_raw).hexdigest(),
            "checkpoint_set_sha256": metadata["checkpoint_set_sha256"],
            "checkpoint_shard_count": len(shards),
            "checkpoint_total_bytes": metadata["total_bytes"],
            "checkpoint_root_descriptor": str(PRODUCTION_ROOT),
            "checkpoint_root_opened": False,
            "candidate_sha256": rendered["candidate_sha256"],
            "primary_candidate_validation": rendered["primary"]["result"],
            "secondary_candidate_validation": rendered["secondary"]["result"],
            "candidate_installed_byte_identity": install["candidate_install_bytes_equal"],
            "installation_kind": install["installation_kind"],
            "installed_handshake": handshake["result"],
            "package_attempt_id_represented": True,
            "primary_event_id_represented": True,
            "secondary_event_id_represented": True,
            "descriptor_plan": {
                "identity_only_count": 1, "graph_descriptor_count": 5,
                "ordinals": [2, 3, 4, 5, 6], "mode_domain": "0<=mode<2**16",
                "lease_id_type": "EXACT_STRING", "path_reopen_count": 0,
            },
            "type_safety_probes_rejected": mutation_result["mutation_count"],
            "type_safety_unexpected_passes": mutation_result["unexpected_passes"],
            "state_created": False,
            "checkpoint_shard_opens": 0,
            "checkpoint_identity_hash_reads": 0,
            "checkpoint_payload_reads": 0,
            "numerical_operations": 0,
            "event_04_authorization_created": False,
            "event_04_executed": False,
            "p1_attempt_2_executed": False,
        }
    bank_exclusive(output, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = rehearse(arguments.output)
    print(json.dumps({
        "result": result["result"], "checkpoint_opens": result["checkpoint_shard_opens"],
        "checkpoint_reads": result["checkpoint_payload_reads"],
        "candidate_sha256": result["candidate_sha256"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
