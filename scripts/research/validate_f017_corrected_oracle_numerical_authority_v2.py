#!/usr/bin/env python3
"""Fail-closed validator for numerical authority v2 and legacy retirement."""
from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
HISTORICAL_COMMIT = "84f0d1dc3e60a4151329ed82773880951ee3e618"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_value(path: Path) -> dict:
    return json.loads(path.read_text())


def require_file_binding(binding: dict, path: Path, root: Path = ROOT) -> None:
    expected = {"path": str(path.relative_to(root)), "sha256": sha(path)}
    if binding != expected:
        raise ValueError(f"file authority binding drift: {expected['path']}")


def historical_sha(path: str) -> str:
    data = subprocess.run(["git", "show", f"{HISTORICAL_COMMIT}:{path}"], cwd=ROOT, check=True, capture_output=True).stdout
    return hashlib.sha256(data).hexdigest()


def symbols(text: str) -> set[str]:
    tree = ast.parse(text); found = set()
    def walk(node, prefix=""):
        for child in getattr(node, "body", []):
            if isinstance(child, (ast.FunctionDef, ast.ClassDef)):
                name = prefix + child.name; found.add(name)
                if isinstance(child, ast.ClassDef): walk(child, name + ".")
            elif not prefix and isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                found.update(target.id for target in targets if isinstance(target, ast.Name))
    walk(tree); return found


def function_names(text: str) -> set[str]:
    """Return every function/method name, including methods nested in classes."""
    return {
        node.name
        for node in ast.walk(ast.parse(text))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def import_signature(text: str) -> list[str]:
    return sorted(
        ast.dump(node, include_attributes=False)
        for node in ast.walk(ast.parse(text))
        if isinstance(node, (ast.Import, ast.ImportFrom))
    )


def assigned_surface_names(text: str) -> set[str]:
    result: set[str] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for part in ast.walk(target):
                    if isinstance(part, ast.Name): result.add(part.id)
                    if isinstance(part, ast.Attribute): result.add(part.attr)
        if isinstance(node, ast.Dict):
            result.update(
                key.value for key in node.keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            )
    return result


def validate_pure_core(path: Path, role: str) -> None:
    text = path.read_text(); tree = ast.parse(text)
    expected_imports = {
        "primary": [
            "Import(names=[alias(name='hashlib')])", "Import(names=[alias(name='json')])",
            "Import(names=[alias(name='math')])", "Import(names=[alias(name='struct')])",
            "ImportFrom(module='__future__', names=[alias(name='annotations')], level=0)",
            "ImportFrom(module='dataclasses', names=[alias(name='dataclass')], level=0)",
            "ImportFrom(module='typing', names=[alias(name='Protocol'), alias(name='runtime_checkable')], level=0)",
        ],
        "secondary": [
            "Import(names=[alias(name='hashlib')])", "Import(names=[alias(name='math')])",
            "Import(names=[alias(name='mlx.core', asname='mx')])",
            "Import(names=[alias(name='mlx.core', asname='mx')])",
            "Import(names=[alias(name='mlx.core', asname='mx')])",
            "Import(names=[alias(name='numpy', asname='np')])", "Import(names=[alias(name='struct')])",
            "ImportFrom(module='__future__', names=[alias(name='annotations')], level=0)",
            "ImportFrom(module='typing', names=[alias(name='Protocol'), alias(name='runtime_checkable')], level=0)",
        ],
    }[role]
    if import_signature(text) != sorted(expected_imports):
        raise ValueError(f"{role} pure-core exact import surface")
    dangerous_call_names = {
        "open", "compile", "exec", "eval", "__import__", "getattr",
        "globals", "locals", "vars",
    }
    tainted_aliases = set(dangerous_call_names)
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            tainted = (
                isinstance(value, ast.Name) and value.id in tainted_aliases
            ) or (
                isinstance(value, ast.Attribute) and value.attr in {"open", "dlopen", "__import__"}
            )
            if not tainted:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in tainted_aliases:
                    tainted_aliases.add(target.id)
                    changed = True
    numeric_attribute_allowlist = {
        "np": {"asarray", "dot", "exp", "float32", "float64", "isfinite", "mean", "ndarray", "sqrt", "stack", "zeros"},
        "mx": {"array", "eval", "transpose"},
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in tainted_aliases:
                raise ValueError(f"{role} pure-core call")
            if isinstance(node.func, ast.Attribute) and node.func.attr in {
                "open", "dlopen", "__import__",
            }:
                raise ValueError(f"{role} pure-core attribute call")
        if isinstance(node, ast.Name) and node.id in {
            "open", "compile", "exec", "eval", "__import__", "getattr",
            "globals", "locals", "vars", "__builtins__", "__loader__", "__spec__",
        }:
            raise ValueError(f"{role} pure-core builtin/meta-loader escape")
        if isinstance(node, ast.Attribute) and node.attr in {"__globals__", "load_module", "exec_module"}:
            raise ValueError(f"{role} pure-core meta-loader attribute escape")
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            root = node.value.id
            if root in numeric_attribute_allowlist and node.attr not in numeric_attribute_allowlist[root]:
                raise ValueError(f"{role} pure-core numerical module capability")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Name) and decorator.id in tainted_aliases:
                    raise ValueError(f"{role} pure-core decorator escape")
    forbidden_names = {"AUTH_SCHEMA", "StreamingCatalogSource", "CatalogStore", "main"}
    if symbols(text) & forbidden_names: raise ValueError(f"{role} pure-core target symbol")


def main() -> int:
    primary = ROOT / "scripts/research/f017_corrected_oracle_primary_numerics_v2.py"
    secondary = ROOT / "scripts/research/f017_corrected_oracle_secondary_numerics_v2.py"
    validate_pure_core(primary, "primary"); validate_pure_core(secondary, "secondary")
    target_method_census = {
        "f017_corrected_oracle_primary_target_source_v6.py": {
            "__getitem__", "__init__", "_event", "_hash_path", "_pairs",
            "_raw", "_strict_json", "_tensor", "close", "expert", "matrix",
            "row", "vector",
        },
        "f017_corrected_oracle_secondary_target_source_v6.py": {
            "__getitem__", "__init__", "_event", "_get", "_pairs", "close",
            "expert", "hash_path", "matrix", "row", "strict", "vector",
        },
    }
    for target in (ROOT / "scripts/research/f017_corrected_oracle_primary_target_source_v6.py", ROOT / "scripts/research/f017_corrected_oracle_secondary_target_source_v6.py"):
        target_functions = function_names(target.read_text())
        graph_arithmetic = {
            "execute", "rms", "_rms", "mv", "_matvec", "matvec",
            "transpose_mv", "_transpose_matvec", "route", "_route",
            "swiglu", "_swiglu", "softmax", "rope", "attention",
        }
        if target_functions & graph_arithmetic:
            raise ValueError(f"target source contains graph arithmetic: {sorted(target_functions & graph_arithmetic)}")
        if assigned_surface_names(target.read_text()) & graph_arithmetic:
            raise ValueError("target source contains assigned graph arithmetic surface")
        if target_functions != target_method_census[target.name]:
            raise ValueError(f"target source function census drift: {target.name}")
    inventory = json_value(CONTRACTS / "f017-corrected-oracle-numerical-source-inventory-v1.json")
    for role in ("primary", "secondary"):
        record = inventory[role]; historical_text = subprocess.run(["git", "show", f"{HISTORICAL_COMMIT}:{record['path']}"], cwd=ROOT, check=True, capture_output=True, text=True).stdout
        declared = [name for values in record["symbols"].values() for name in values]
        if len(declared) != len(set(declared)) or set(declared) != symbols(historical_text) or record["symbol_count"] != len(declared): raise ValueError(f"{role} inventory census")
        if record["symbols"]["UNRESOLVED"]: raise ValueError(f"{role} unresolved symbol")
        if historical_sha(record["path"]) != record["sha256"]: raise ValueError(f"{role} historical bytes")
    manifest = json_value(CONTRACTS / "f017-corrected-oracle-historical-numerical-authority-manifest-v1.json")
    for authority in manifest["authorities"]:
        if historical_sha(authority["path"]) != authority["sha256"]: raise ValueError("historical manifest")
    tombstones = [
        "scripts/research/f017_corrected_oracle_primary.py", "scripts/research/f017_corrected_oracle_secondary.py",
        "scripts/research/validate_f017_corrected_oracle_access.py", "scripts/research/execute_f017_corrected_oracle_event.py",
        "scripts/research/validate_f017_corrected_oracle_access_v2.py", "scripts/research/execute_f017_corrected_oracle_event_v2.py",
        "scripts/research/validate_f017_corrected_oracle_access_v3.py", "scripts/research/execute_f017_corrected_oracle_event_v3.py",
        "scripts/research/f017_corrected_oracle_primary_v3.py", "scripts/research/f017_corrected_oracle_secondary_v3.py",
    ]
    for relative in tombstones:
        tree = ast.parse((ROOT / relative).read_text())
        if "HISTORICAL_ONLY" not in (ROOT / relative).read_text() or any(isinstance(node, ast.Import) and any(alias.name in {"os", "mmap"} for alias in node.names) for node in ast.walk(tree)):
            raise ValueError(f"retirement tombstone: {relative}")
    contract = json_value(CONTRACTS / "f017-corrected-full-checkpoint-oracle-numerical-contract-v2.json")
    if contract["numerical_methodology_changed"] is not False or contract["numerical_thresholds_changed"] is not False: raise ValueError("numerical semantic drift")
    expected_thresholds = {"max_absolute_error": 0.0065169706285814755, "rmse": 0.003463567697419031, "cosine_minimum": 0.9999999985448085, "top_n": 32}
    if contract["frozen_thresholds"] != expected_thresholds: raise ValueError("threshold drift")
    for role, path in (("primary", primary), ("secondary", secondary)):
        if contract["oracle_roles"][role]["implementation_sha256"] != sha(path): raise ValueError(f"{role} core binding")
    role_paths = {
        "primary": {
            "implementation": primary,
            "target_source": ROOT / "scripts/research/f017_corrected_oracle_primary_target_source_v6.py",
            "decoder": ROOT / "scripts/research/f017_oracle_primary_decoders.py",
        },
        "secondary": {
            "implementation": secondary,
            "target_source": ROOT / "scripts/research/f017_corrected_oracle_secondary_target_source_v6.py",
            "decoder": ROOT / "scripts/research/qualify_f017_quantization_matrix_v1.py",
        },
    }
    for role, bindings in role_paths.items():
        declared = contract["oracle_roles"][role]
        for field, path in bindings.items():
            if declared[field] != str(path.relative_to(ROOT)):
                raise ValueError(f"{role} {field} path binding")
            if declared[f"{field}_sha256"] != sha(path):
                raise ValueError(f"{role} {field} SHA binding")
    expected_authority_bindings = {
        "historical_authority_manifest": CONTRACTS / "f017-corrected-oracle-historical-numerical-authority-manifest-v1.json",
        "numerical_requalification": EVIDENCE / "f017-corrected-oracle-numerical-requalification-v2.json",
        "numerical_qualifier": ROOT / "scripts/research/qualify_f017_corrected_oracle_numerical_authority_v2.py",
        "numerical_validator": ROOT / "scripts/research/validate_f017_corrected_oracle_numerical_authority_v2.py",
        "separation_architecture": CONTRACTS / "f017-corrected-oracle-numerical-separation-architecture-v1.json",
    }
    if set(contract["authority_bindings"]) != set(expected_authority_bindings):
        raise ValueError("authority binding census")
    for name, path in expected_authority_bindings.items():
        try:
            require_file_binding(contract["authority_bindings"][name], path)
        except ValueError as exc:
            raise ValueError(f"authority binding drift: {name}") from exc
    qualification = json_value(EVIDENCE / "f017-corrected-oracle-numerical-requalification-v2.json")
    if qualification["result"] != "PASS" or qualification["historical_successor_equivalence_case_count"] != 24 or qualification["packed_decoder_case_count"] != 44 or qualification["target_adapter_synthetic_repeat_count"] != 10: raise ValueError("numerical qualification census")
    if qualification["original_checkpoint_shard_opens"] != 0 or qualification["original_checkpoint_payload_reads"] != 0: raise ValueError("checkpoint access")
    qualification_bindings = {
        "primary_pure_core_sha256": primary,
        "secondary_pure_core_sha256": secondary,
        "primary_target_source_sha256": role_paths["primary"]["target_source"],
        "secondary_target_source_sha256": role_paths["secondary"]["target_source"],
    }
    for field, path in qualification_bindings.items():
        if qualification[field] != sha(path):
            raise ValueError(f"qualification source binding drift: {field}")
    print(json.dumps({"result": "PASS", "historical_authorities": 2, "pure_cores": 2, "tombstones": len(tombstones), "equivalence_cases": 24}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
