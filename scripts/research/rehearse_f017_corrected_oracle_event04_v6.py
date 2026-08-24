#!/usr/bin/env python3
"""Production-shaped Event-04 rehearsal with zero checkpoint-file access."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path

from execute_f017_corrected_oracle_event_v6 import installed_handshake
from f017_corrected_oracle_authorization_v6 import ROOT, canonical_bytes, sha256_path, strict_bytes
from f017_corrected_oracle_wrapper_support_v6 import bank
from f017_macos_memory_observation_v1 import observe_vm_stat
from generate_f017_corrected_oracle_inert_v6 import generate as inert_document
from validate_f017_corrected_oracle_access_v6 import construct_candidate_from_inert, install_candidate, render_candidate, validate_candidate

INTERFACE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v6.json"
SCIENTIFIC = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v6.json"
MODEL = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v6.json"
ACCOUNTING = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event-accounting-v6.json"
PATHS = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-path-timing-v6.json"
SERIALIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-canonical-json-bytes-v6.json"
CHECKPOINT_ROOT = Path("/Users/mhedhli/Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS")
THRESHOLD = 17_179_869_184


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_nonsymlink_directory(path: Path) -> Path:
    canonical = path.resolve(strict=True)
    cursor = Path(canonical.anchor)
    for part in canonical.parts[1:]:
        cursor /= part
        if cursor.is_symlink() or not cursor.is_dir():
            raise ValueError("checkpoint-root canonical nonsymlink ancestry")
    return canonical


def _replace_inert_ids(value: object, prefix: str = "ROOT") -> None:
    if type(value) is dict:
        for key, nested in value.items():
            if key.endswith("_id") and type(nested) is str and "INERT" in nested:
                value[key] = f"F017-E04-SHADOW-{prefix}-{key[:-3].upper().replace('_', '-')}"
            else:
                _replace_inert_ids(nested, f"{prefix}-{key.upper().replace('_', '-')}")
    elif type(value) is list:
        for index, nested in enumerate(value):
            _replace_inert_ids(nested, f"{prefix}-{index}")


def rehearse(output: Path | None, measurement_manifest: Path | None) -> dict:
    checkpoint_root = CHECKPOINT_ROOT
    checkpoint_root_ancestry_verified = False
    if checkpoint_root.exists():
        checkpoint_root = _canonical_nonsymlink_directory(checkpoint_root)
        checkpoint_root_ancestry_verified = True
    observation = observe_vm_stat()
    if observation.available_bytes < THRESHOLD:
        raise ValueError("rehearsal memory threshold")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    scientific = strict_bytes(SCIENTIFIC.read_bytes())
    with tempfile.TemporaryDirectory(prefix="f017-event04-rehearsal-") as temporary:
        work = Path(temporary)
        interface_path = work / "interface.json"
        interface = strict_bytes(INTERFACE.read_bytes())
        interface["interface_scope"] = "PRODUCTION_SHAPED_REHEARSAL"
        interface["pinned_values"] = {**interface["pinned_values"], "authority_scope": "PRODUCTION_SHAPED_REHEARSAL"}
        bank(interface_path, interface)
        approval_path = work / "rehearsal-approval.json"
        approval = {
            "schema": "pulsarmlx.f017.corrected-oracle-rehearsal-approval/6.0.0",
            "authority": False,
            "operator_go": False,
            "event_04_authorization_permitted": False,
            "purpose": "PRODUCTION_SHAPED_NO_ACCESS_REHEARSAL",
        }
        approval_sha = bank(approval_path, approval)
        memory_path = work / "memory-observation.json"
        memory_sha = bank(memory_path, {"schema": "pulsarmlx.f017.memory-observation/1.0.0", **observation.as_dict()})
        installed = work / "rehearsal-authorization.json"
        candidate = work / "candidate.json"
        doc = inert_document()
        replacements = {key: value for key, value in doc.items() if key not in {"schema", "authority_generation"}}
        replacements.update({
            "state": "AUTHORIZED", "live": True, "authority_scope": "PRODUCTION_SHAPED_REHEARSAL",
            "authorization_id": "F017-EVENT-04-SHADOW-AUTHORIZATION",
            "operator_approval_id": "F017-EVENT-04-SHADOW-APPROVAL",
            "operator_approval_sha256": approval_sha,
            "package_attempt_id": "F017-EVENT-04-SHADOW-PACKAGE",
            "primary_event_id": "F017-EVENT-04-SHADOW-PRIMARY",
            "secondary_event_id": "F017-EVENT-04-SHADOW-SECONDARY",
            "branch": "feat/017-rust-native-inference-runtime",
            "implementation_measurement_head": head,
            "implementation_measurement_manifest_sha256": sha256_path(measurement_manifest) if measurement_manifest else "0" * 64,
            "authorization_interface_sha256": sha256_path(interface_path),
            "scientific_access_contract_sha256": sha256_path(SCIENTIFIC),
            "event_accounting_contract_sha256": sha256_path(ACCOUNTING),
            "path_timing_contract_sha256": sha256_path(PATHS),
            "canonical_serialization_contract_sha256": sha256_path(SERIALIZATION),
            "lifecycle_semantic_model_sha256": sha256_path(MODEL),
            "memory_preflight_sha256": memory_sha,
            "memory_observed_at_unix_ns": observation.observed_at_unix_ns,
            "checkpoint_root": str(checkpoint_root),
            "canonical_install_path": str(installed.resolve()),
        })
        for section, role in (("package", "PACKAGE"), ("primary", "PRIMARY"), ("secondary", "SECONDARY")):
            replacements[section] = dict(replacements[section])
            replacements[section]["state_root"] = str(work / "future-state" / role.lower())
            replacements[section]["output_root"] = str(work / "future-output" / role.lower())
        replacements["primary"]["event_id"] = replacements["primary_event_id"]
        replacements["secondary"]["event_id"] = replacements["secondary_event_id"]
        _replace_inert_ids(replacements)
        document = construct_candidate_from_inert(replacements)
        candidate_sha = render_candidate(document, candidate)
        report_root = work / "candidate-reports"; report_root.mkdir()
        candidate_handshake = validate_candidate(candidate, interface_path, checkpoint_root, report_root)
        receipt_path = work / "installation-receipt.json"
        install_candidate(candidate, installed, receipt_path, candidate_handshake, operator_approval_sha256=approval_sha, allow_rehearsal=True)
        installed_root = work / "installed-handshake"; installed_root.mkdir()
        handshake = installed_handshake(installed, interface_path, checkpoint_root, receipt_path, installed_root)
        roots = [Path(replacements[name][kind]) for name in ("package", "primary", "secondary") for kind in ("state_root", "output_root")]
        if any(path.exists() or path.is_symlink() for path in roots):
            raise ValueError("rehearsal created future state")
        result = {
            "schema": "pulsarmlx.f017.corrected-oracle-event04-production-shaped-rehearsal/6.0.0",
            "result": "PASS", "authority": False, "operator_go": False,
            "branch": replacements["branch"], "implementation_head": head,
            "machine_brand": subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
            "architecture": platform.machine(), "memory_page_size_bytes": observation.page_size_bytes,
            "memory_available_bytes": observation.available_bytes, "memory_threshold_bytes": THRESHOLD,
            "candidate_sha256": candidate_sha, "candidate_installed_byte_identity": candidate.read_bytes() == installed.read_bytes(),
            "primary_candidate_validation_sha256": candidate_handshake["primary"]["sha256"],
            "secondary_candidate_validation_sha256": candidate_handshake["secondary"]["sha256"],
            "installed_handshake_sha256": _sha_bytes(canonical_bytes(handshake)),
            "checkpoint_set_sha256": scientific["production_checkpoint"]["checkpoint_set_sha256"],
            "checkpoint_shard_metadata": scientific["production_checkpoint"]["shards"],
            "checkpoint_root_descriptor": str(checkpoint_root),
            "checkpoint_root_ancestry_verified_on_host": checkpoint_root_ancestry_verified,
            "package_attempt_id_represented": True, "consumer_event_ids_represented": True,
            "candidate_installed_at_canonical_production_path": False,
            "state_created": False, "checkpoint_shard_opens": 0, "checkpoint_payload_reads": 0,
            "numerical_operations": 0, "event_04_authorization_created": False, "event_04_executed": False,
        }
    if output:
        output.write_bytes(canonical_bytes(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--measurement-manifest", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(rehearse(arguments.output, arguments.measurement_manifest), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
