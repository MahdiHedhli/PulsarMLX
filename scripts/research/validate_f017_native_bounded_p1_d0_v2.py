#!/usr/bin/env python3
"""Resolve and validate the append-only F017 D0 v2 overlay."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.research.validate_f017_native_bounded_p1_d0_v1 import (
    D0Error,
    _git,
    _json,
    _sha,
    validate as validate_v1,
)


def _resolve(document: Any, dotted: str) -> Any:
    value = document
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise D0Error(f"unresolved D0 v2 field: {dotted}")
        value = value[part]
    return value


def validate(contract_path: Path, root: Path) -> dict[str, Any]:
    raw = contract_path.read_bytes()
    overlay = _json(raw, str(contract_path))
    if overlay.get("schema") != "pulsarmlx.f017.native-bounded-p1-numeric-acceptance-contract-overlay" or overlay.get("schema_version") != "2.0.0":
        raise D0Error("D0 v2 schema mismatch")
    base_path = root / overlay["base_contract"]["path"]
    if _sha(base_path.read_bytes()) != overlay["base_contract"]["sha256"]:
        raise D0Error("D0 v2 base SHA mismatch")
    validate_v1(base_path, root)
    base = _json(base_path.read_bytes(), str(base_path))
    base_json_by_role = {row["role"]: row for row in base["bound_oracles"]}
    parsed_by_role: dict[str, dict[str, Any]] = {}
    required_json_fields = {
        "branch", "commit", "path", "sha256", "schema", "schema_version", "semantic_role"
    }
    for binding in overlay["source_identities"]:
        if set(binding) != required_json_fields:
            raise D0Error("D0 v2 JSON source identity census mismatch")
        original = base_json_by_role.get(binding["semantic_role"])
        if original is None or any(binding[key] != original[key] for key in ("branch", "commit", "path", "sha256")):
            raise D0Error(f"D0 v2 source does not resolve base authority: {binding['semantic_role']}")
        data = _git(root, "show", f"{binding['commit']}:{binding['path']}")
        if _sha(data) != binding["sha256"]:
            raise D0Error(f"D0 v2 source SHA mismatch: {binding['semantic_role']}")
        parsed = _json(data, binding["path"])
        if type(parsed.get("schema_version")) is not type(binding["schema_version"]):
            raise D0Error(f"D0 v2 source schema-version type mismatch: {binding['semantic_role']}")
        if parsed.get("schema") != binding["schema"] or parsed.get("schema_version") != binding["schema_version"]:
            raise D0Error(f"D0 v2 source schema mismatch: {binding['semantic_role']}")
        parsed_by_role[binding["semantic_role"]] = parsed
    if set(parsed_by_role) != set(base_json_by_role):
        raise D0Error("D0 v2 source role census mismatch")
    base_code_by_role = {row["role"]: row for row in base["bound_oracle_implementation"]}
    required_code_fields = {"branch", "commit", "path", "sha256", "content_type", "semantic_role"}
    seen_code: set[str] = set()
    for binding in overlay["implementation_source_identities"]:
        if set(binding) != required_code_fields:
            raise D0Error("D0 v2 code identity census mismatch")
        original = base_code_by_role.get(binding["semantic_role"])
        if original is None or any(binding[key] != original[key] for key in ("branch", "commit", "path", "sha256")):
            raise D0Error(f"D0 v2 code source does not resolve base authority: {binding['semantic_role']}")
        if _sha(_git(root, "show", f"{binding['commit']}:{binding['path']}")) != binding["sha256"]:
            raise D0Error(f"D0 v2 code source SHA mismatch: {binding['semantic_role']}")
        seen_code.add(binding["semantic_role"])
    if seen_code != set(base_code_by_role):
        raise D0Error("D0 v2 code identity role census mismatch")
    expected_override = {
        "ordinal": 13,
        "id": "router_normalized",
        "backend": "RUST_SERIAL_F32",
        "class": "NUMERICALLY_BOUNDED_REQUIRED",
        "oracle": "RETAINED_CANONICAL_ROUTER_NORMALIZED",
        "metric": "native_intermediate_tier_b",
        "boundary": "router",
    }
    if overlay["stage_overrides"] != [expected_override]:
        raise D0Error("D0 v2 stage override differs from reviewed repair")
    effective_rows = copy.deepcopy(base["stage_rows"])
    effective_rows[13] = copy.deepcopy(expected_override)
    registry: dict[str, dict[str, Any]] = {}
    comparison = parsed_by_role["ACCEPTED_PROOF_REFERENCE_COMPARISON_VOCABULARY"]
    independent = parsed_by_role["INDEPENDENT_SYNTHETIC_SEVEN_BOUNDARY_ORACLE"]
    for entry in overlay["oracle_registry"]:
        label = entry.get("label")
        if not isinstance(label, str) or label in registry:
            raise D0Error("D0 v2 duplicate or invalid oracle registry label")
        if entry["authority"] == "ACCEPTED_PROOF_REFERENCE_COMPARISON_VOCABULARY":
            if set(entry) != {"label", "authority", "comparison_ordinals", "expected_sha256"}:
                raise D0Error(f"D0 v2 retained registry census mismatch: {label}")
            rows = [comparison["stage_rows"][ordinal] for ordinal in entry["comparison_ordinals"]]
            if [row["ordinal"] for row in rows] != entry["comparison_ordinals"]:
                raise D0Error(f"D0 v2 comparison ordinal mismatch: {label}")
            if [row["expected_sha256"] for row in rows] != entry["expected_sha256"]:
                raise D0Error(f"D0 v2 expected artifact SHA mismatch: {label}")
        elif entry["authority"] == "INDEPENDENT_SYNTHETIC_SEVEN_BOUNDARY_ORACLE":
            if set(entry) != {"label", "authority", "json_paths"}:
                raise D0Error(f"D0 v2 independent registry census mismatch: {label}")
            for path in entry["json_paths"]:
                resolved = _resolve(independent, path)
                if not isinstance(resolved, dict) or resolved.get("classification") != "INDEPENDENT":
                    raise D0Error(f"D0 v2 independent oracle path mismatch: {label}")
        else:
            raise D0Error(f"D0 v2 unknown oracle authority: {label}")
        registry[label] = entry
    effective_labels = {row["oracle"] for row in effective_rows}
    if set(registry) != effective_labels:
        raise D0Error("D0 v2 effective stage oracle registry mismatch")
    lock = overlay["epistemic_lock"]
    if lock != {
        "field": "tolerance_epistemics.misderived_tolerance_repair",
        "exact_value": "APPEND_ONLY_NEW_D0_REVISION_FROM_FRESH_CORPUS_EXCLUDING_TRIGGERING_D3_5_OUTPUT_AND_NEW_FABLE_REVIEW",
    } or _resolve(base, lock["field"]) != lock["exact_value"]:
        raise D0Error("D0 v2 misderived-tolerance repair lock mismatch")
    determinism = overlay["d3_5_determinism_evidence"]
    expected_identities = [
        "native_executable_sha256", "mlx_dylib_sha256", "mlx_c_dylib_sha256",
        "metal_environment", "macos_build", "hardware_class", "stage_backend_and_dispatch_symbol",
    ]
    if determinism["capture_kernel_dispatch_identity"] is not True or determinism["required_identities"] != expected_identities:
        raise D0Error("D0 v2 D3.5 dispatch identity requirement weakened")
    if determinism["numeric_tolerance_may_hide_repeat_failure"] is not False:
        raise D0Error("D0 v2 permits tolerance to hide repeat failure")
    expected_findings = {"F1", "F2", "F3", "F4", "F5"}
    if {row["finding_id"] for row in overlay["finding_repairs"]} != expected_findings:
        raise D0Error("D0 v2 finding repair census mismatch")
    if overlay["retained_qualification_executed"] is not False or overlay["real_p1_executed"] is not False:
        raise D0Error("D0 v2 claims forbidden execution")
    return {
        "result": "PASS",
        "sha256": _sha(raw),
        "base_sha256": overlay["base_contract"]["sha256"],
        "effective_stages": len(effective_rows),
        "router_normalized_grade": "NUMERICALLY_BOUNDED_REQUIRED",
        "resolved_oracle_labels": len(registry),
        "source_schema_bindings": len(parsed_by_role),
        "retained_qualification_executed": False,
        "p1_executed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--contract", type=Path,
        default=Path("specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v2.json"),
    )
    args = parser.parse_args()
    root = args.root.resolve()
    path = args.contract if args.contract.is_absolute() else root / args.contract
    print(json.dumps(validate(path, root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
