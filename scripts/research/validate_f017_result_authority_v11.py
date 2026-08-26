#!/usr/bin/env python3
"""Mechanical gates for repaired F017 V11 result authority."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-authority-v11.json"
AUTHORITY = ROOT / "scripts/research/f017_binary_comparison_authority_v11.py"
ARTIFACTS = ROOT / "scripts/research/f017_result_artifacts_v11.py"
BUNDLE = ROOT / "scripts/research/f017_result_bundle_authority_v11.py"


def main() -> int:
    contract = json.loads(CONTRACT.read_text())
    if contract["schema"] != "pulsarmlx.f017.corrected-oracle-result-authority/11.0.1": raise ValueError("contract schema")
    source = AUTHORITY.read_text(); tree = ast.parse(source)
    imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imports |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    if "f017_binary_comparator_v11" in imports or "compare_logits" in source:
        raise ValueError("comparison builder import separation")
    fields = contract["comparison_authority"]["rederived_fields"]
    return_keys = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "derive_summary":
            for child in ast.walk(node):
                if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
                    keys = [key.value for key in child.value.keys if isinstance(key, ast.Constant) and isinstance(key.value, str)]
                    if "classification" in keys: return_keys = set(keys)
    if return_keys is None or set(fields) != return_keys or len(fields) != len(set(fields)):
        raise ValueError("rederived field census")
    artifact_source = ARTIFACTS.read_text(); bundle_source = BUNDLE.read_text()
    gates = {
        "F5-01":"independent comparison summary mismatch" in source,
        "F5-02":"_bundle_identity" in {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)} and "validate_receipt" in source,
        "F5-03":"expected_package_attempt_id" in artifact_source and "expected_consumer_event_id" in artifact_source,
        "F5-04":"summary[\"package_attempt_id\"]" in artifact_source and "summary[\"consumer_event_id\"]" in artifact_source,
        "F5-05":"manifest payload inode alias" in artifact_source and "manifest payload leaf alias" in artifact_source,
        "BUNDLE":"compose_comparison_closure" in bundle_source and "validate_receipt" in bundle_source,
    }
    if not all(gates.values()): raise ValueError(f"authority gates: {gates}")
    result = {"schema":"pulsarmlx.f017.event05-result-authority-design-qualification/1.0.0",
        "contract_sha256":hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),
        "independent_validator_sha256":hashlib.sha256(AUTHORITY.read_bytes()).hexdigest(),
        "bundle_validator_sha256":hashlib.sha256(BUNDLE.read_bytes()).hexdigest(),
        "builder_import_separation":"PASS","rederived_field_count":len(fields),
        "findings_repaired":gates,"original_checkpoint_access":0,"result":"PASS"}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__": raise SystemExit(main())
