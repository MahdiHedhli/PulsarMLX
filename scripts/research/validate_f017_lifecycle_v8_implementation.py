#!/usr/bin/env python3
"""Independent exact-binding validation of the non-live V8 implementation."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


def load(relative: str) -> dict:
    path = ROOT / relative
    raw = path.read_bytes()
    value = json.loads(raw)
    if raw != canonical(value):
        raise ValueError(f"noncanonical authority: {relative}")
    return value


def binding(value: object) -> Path:
    if type(value) is not dict or set(value) != {"path", "sha256"}:
        raise ValueError("authority binding census")
    if type(value["path"]) is not str or type(value["sha256"]) is not str:
        raise ValueError("authority binding types")
    path = ROOT / value["path"]
    if not path.is_file() or sha(path) != value["sha256"]:
        raise ValueError(f"authority binding drift: {value['path']}")
    return path


def validate() -> dict:
    manifest_path = "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-v8-implementation-authority-manifest.json"
    manifest = load(manifest_path)
    if (manifest["status"] != "ACTIVE_IMPLEMENTATION_NO_EVENT_AUTHORITY"
            or manifest["event_04_authorization_created"] is not False
            or manifest["event_04_executed"] is not False
            or manifest["original_checkpoint_access"] != 0):
        raise ValueError("implementation manifest posture")
    binding(manifest["active_generation"])
    scientific_path = binding(manifest["scientific_access"])
    inert_path = binding(manifest["inert_authorization"])
    binding(manifest["design_authority"])
    binding(manifest["synthetic_qualifier"])
    binding(manifest["synthetic_qualification"])
    binding(manifest["production_shaped_rehearsal"])
    binding(manifest["production_shaped_rehearsal_evidence"])
    binding(manifest["implementation_validator"])
    binding(manifest["operator_go_template"])
    for item in manifest["implementation"].values():
        binding(item)
    scientific = load(str(scientific_path.relative_to(ROOT)))
    if scientific["status"] != "ACTIVE_IMPLEMENTATION_NO_EVENT_AUTHORITY" or scientific["active_generation"] != "V8":
        raise ValueError("scientific authority posture")
    if scientific["implementation"] != manifest["implementation"]:
        raise ValueError("scientific implementation mismatch")
    for name in (
        "primary_capability", "secondary_capability", "causal_artifact_dag",
        "descriptor_scalar_contract", "checkpoint_identity_contract",
        "descriptor_continuity_contract", "event_accounting_contract",
        "serialization_contract", "numerical_contract", "checkpoint_metadata",
    ):
        binding(scientific[name])
    active = load(manifest["active_generation"]["path"])
    if (active["active_corrected_oracle_generation"] != "V8"
            or active["implemented_generation"] != "V8"
            or active["event_04_operator_go_present"] is not False
            or active["live_authority_without_fresh_operator_go"] is not False):
        raise ValueError("active generation posture")
    inert = load(str(inert_path.relative_to(ROOT)))
    if (inert["live"] is not False or inert["authority"] is not False
            or inert["scientific_access_contract"] != manifest["scientific_access"]):
        raise ValueError("inert authority binding")
    with tempfile.TemporaryDirectory(prefix="f017-v8-independent-check-") as raw:
        package_root = Path(raw) / "packages"
        subprocess.run([
            sys.executable, str(ROOT / "scripts/research/construct_f017_lifecycle_v8_symbolically.py"),
            "--output-root", str(package_root),
        ], cwd=ROOT, check=True, capture_output=True)
        subprocess.run([
            sys.executable, str(ROOT / "scripts/research/check_f017_descriptor_type_safety_v8.py"),
            "--package-root", str(package_root / "complete_success"),
        ], cwd=ROOT, check=True, capture_output=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/research/validate_f017_lifecycle_causal_design_v8.py")], cwd=ROOT, check=True, capture_output=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/research/validate_f017_corrected_oracle_numerical_authority_v3.py")], cwd=ROOT, check=True, capture_output=True)
    return {
        "result": "PASS", "active_generation": "V8",
        "implementation_binding_count": len(manifest["implementation"]),
        "scientific_access_sha256": sha(scientific_path),
        "event_04_authorization_created": False, "event_04_executed": False,
        "original_checkpoint_access": 0,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), sort_keys=True, separators=(",", ":")))
