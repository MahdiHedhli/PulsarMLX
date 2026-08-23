#!/usr/bin/env python3
"""Generate exact F017 numerical capability contracts and derived manifests."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts/research"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def policy() -> dict:
    return {
        "schema": "pulsarmlx.f017.numerical-capability-policy/1.0.0",
        "status": "FROZEN",
        "semantic_identity_basis": "IMPORT_RESOLUTION_NOT_LOCAL_SPELLING",
        "module_identities": {"numpy": "PYTHON_MODULE_NUMPY", "mlx.core": "PYTHON_MODULE_MLX_CORE"},
        "exact_capability_imports": {
            "primary": [],
            "secondary": [
                {"module": "numpy", "local": "np", "scope": "<module>"},
                {"module": "mlx.core", "local": "mx", "scope": "mv"},
                {"module": "mlx.core", "local": "mx", "scope": "mv"},
                {"module": "mlx.core", "local": "mx", "scope": "transpose_mv"},
            ],
        },
        "semantic_modules": {
            "PYTHON_MODULE_NUMPY": {
                "direct_callable_members": ["asarray", "dot", "exp", "isfinite", "mean", "sqrt", "stack", "zeros"],
                "type_dtype_members": ["float32", "float64", "ndarray"],
                "dtype_consumers": ["asarray", "astype", "exp", "zeros"],
            },
            "PYTHON_MODULE_MLX_CORE": {
                "direct_callable_members": ["array", "eval", "transpose"],
                "type_dtype_members": [],
                "dtype_consumers": [],
            },
        },
        "member_return_provenance": {
            "NUMPY_MEMBER:asarray": "ARRAY_VALUE", "NUMPY_MEMBER:dot": "SAFE_SCALAR",
            "NUMPY_MEMBER:exp": "ARRAY_VALUE", "NUMPY_MEMBER:float32": "SAFE_SCALAR",
            "NUMPY_MEMBER:float64": "SAFE_SCALAR", "NUMPY_MEMBER:isfinite": "ARRAY_VALUE",
            "NUMPY_MEMBER:mean": "SAFE_SCALAR", "NUMPY_MEMBER:ndarray": "UNKNOWN",
            "NUMPY_MEMBER:sqrt": "ARRAY_VALUE", "NUMPY_MEMBER:stack": "ARRAY_VALUE",
            "NUMPY_MEMBER:zeros": "ARRAY_VALUE", "MLX_MEMBER:array": "ARRAY_VALUE",
            "MLX_MEMBER:eval": "SAFE_SCALAR", "MLX_MEMBER:transpose": "ARRAY_VALUE",
        },
        "non_escape_rule": "MODULE_AND_MEMBER_CAPABILITIES_MAY_ONLY_APPEAR_AS_APPROVED_DIRECT_USES",
        "unknown_behavior": "REJECT",
        "prohibited_dynamic_names": [
            "__builtins__", "__import__", "__loader__", "__spec__", "compile", "eval", "exec",
            "getattr", "globals", "hasattr", "locals", "open", "setattr", "vars",
        ],
        "prohibited_meta_attributes": [
            "__class__", "__dict__", "__getattribute__", "__globals__", "__loader__", "__spec__",
            "exec_module", "find_module", "find_spec", "load_module",
        ],
        "prohibited_capability_member_names": [
            "dump", "export", "export_function", "fromfile", "load", "memmap", "open_memmap", "save", "tofile",
        ],
        "parameter_roles": {
            "primary": {
                "_projection.source": "PROTOCOL_OBJECT:SOURCE", "_swiglu.source": "PROTOCOL_OBJECT:SOURCE",
                "execute.source": "PROTOCOL_OBJECT:SOURCE", "_matvec.matrix": "PROTOCOL_OBJECT:ROW_MATRIX_OR_ARRAY",
                "_transpose_matvec.matrix": "PROTOCOL_OBJECT:ROW_MATRIX_OR_ARRAY",
                "JsonSource.__init__.self": "PROTOCOL_OBJECT:STORE", "JsonSource._get.self": "PROTOCOL_OBJECT:STORE",
                "JsonSource.vector.self": "PROTOCOL_OBJECT:STORE", "JsonSource.matrix.self": "PROTOCOL_OBJECT:STORE",
                "JsonSource.expert.self": "PROTOCOL_OBJECT:STORE",
            },
            "secondary": {
                "digest.values": "ARRAY_VALUE", "rms.x": "ARRAY_VALUE", "rms.weight": "ARRAY_VALUE",
                "mv.matrix": "PROTOCOL_OBJECT:ROW_MATRIX_OR_ARRAY", "mv.vector": "ARRAY_VALUE",
                "transpose_mv.matrix": "PROTOCOL_OBJECT:ROW_MATRIX_OR_ARRAY", "transpose_mv.vector": "ARRAY_VALUE",
                "swiglu.store": "PROTOCOL_OBJECT:STORE", "swiglu.x": "ARRAY_VALUE",
                "execute.document": "SAFE_DICT", "execute.store": "PROTOCOL_OBJECT:STORE",
                "Store.get.self": "PROTOCOL_OBJECT:STORE", "Store.vector.self": "PROTOCOL_OBJECT:STORE",
                "Store.matrix.self": "PROTOCOL_OBJECT:STORE", "Store.expert.self": "PROTOCOL_OBJECT:STORE",
            },
        },
        "function_return_provenance": {
            "_hash_f64": "SAFE_STRING", "_hash_json": "SAFE_STRING", "_matvec": "ARRAY_VALUE",
            "_projection": "PROTOCOL_OBJECT:ROW_MATRIX_OR_ARRAY", "_residual": "ARRAY_VALUE", "_rms": "ARRAY_VALUE",
            "_route": "UNKNOWN", "_swiglu": "ARRAY_VALUE", "digest": "SAFE_STRING", "mv": "ARRAY_VALUE",
            "rms": "ARRAY_VALUE", "Store": "PROTOCOL_OBJECT:STORE", "swiglu": "ARRAY_VALUE", "transpose_mv": "ARRAY_VALUE",
        },
        "receiver_roles": {
            "PROTOCOL_OBJECT:SOURCE": {"methods": {"expert": "PROTOCOL_OBJECT:ROW_MATRIX_OR_ARRAY", "matrix": "PROTOCOL_OBJECT:ROW_MATRIX_OR_ARRAY", "vector": "ARRAY_VALUE"}, "attribute_returns": {}, "readable_attributes": [], "writable_attributes": []},
            "PROTOCOL_OBJECT:STORE": {"methods": {"_get": "ARRAY_VALUE", "expert": "PROTOCOL_OBJECT:ROW_MATRIX_OR_ARRAY", "get": "ARRAY_VALUE", "matrix": "PROTOCOL_OBJECT:ROW_MATRIX_OR_ARRAY", "vector": "ARRAY_VALUE"}, "attribute_returns": {"tensors": "SAFE_DICT"}, "readable_attributes": ["tensors"], "writable_attributes": ["tensors"]},
            "PROTOCOL_OBJECT:ROW_MATRIX": {"methods": {"row": "ARRAY_VALUE"}, "readable_attributes": ["rows", "cols", "columns"], "writable_attributes": []},
            "PROTOCOL_OBJECT:ROW_MATRIX_OR_ARRAY": {"methods": {"astype": "ARRAY_VALUE", "row": "ARRAY_VALUE"}, "readable_attributes": ["T", "rows", "cols", "columns"], "writable_attributes": []},
            "ARRAY_VALUE": {"methods": {"all": "SAFE_SCALAR", "astype": "ARRAY_VALUE", "copy": "ARRAY_VALUE", "reshape": "ARRAY_VALUE", "tobytes": "SAFE_BYTES"}, "readable_attributes": ["T", "size"], "writable_attributes": []},
            "HASH_OBJECT": {"methods": {"hexdigest": "SAFE_STRING", "update": "SAFE_SCALAR"}, "readable_attributes": [], "writable_attributes": []},
            "SAFE_LIST": {"methods": {"append": "SAFE_SCALAR", "extend": "SAFE_SCALAR"}, "readable_attributes": [], "writable_attributes": []},
            "SAFE_DICT": {"methods": {"get": "UNKNOWN"}, "readable_attributes": [], "writable_attributes": []},
            "SAFE_SET": {"methods": {"issubset": "SAFE_SCALAR"}, "readable_attributes": [], "writable_attributes": []},
            "SAFE_BYTES": {"methods": {"hex": "SAFE_STRING"}, "readable_attributes": [], "writable_attributes": []},
            "SAFE_STRING": {"methods": {"encode": "SAFE_BYTES"}, "readable_attributes": [], "writable_attributes": []},
        },
        "standard_module_roots": ["hashlib", "json", "math", "struct"],
        "standard_member_return_provenance": {
            "hashlib.sha256": "HASH_OBJECT", "json.dumps": "SAFE_STRING", "struct.pack": "SAFE_BYTES",
            "math.cos": "SAFE_SCALAR", "math.exp": "SAFE_SCALAR", "math.isfinite": "SAFE_SCALAR",
            "math.prod": "SAFE_SCALAR", "math.sin": "SAFE_SCALAR", "math.sqrt": "SAFE_SCALAR",
        },
        "non_method_attributes": [],
        "binding_forms": [
            "Assign", "AnnAssign", "NamedExpr", "Tuple", "List", "Starred", "For", "AsyncFor",
            "comprehension", "With", "AsyncWith", "ExceptHandler", "arguments", "defaults", "kw_defaults",
            "decorators", "class_attributes", "Match", "Import", "ImportFrom",
        ],
        "fixed_point": True,
        "interprocedural_rule": "REJECT_CAPABILITY_ARGUMENT_TRANSPORT",
    }


def main() -> int:
    policy_path = CONTRACTS / "f017-corrected-oracle-numerical-capability-policy-v1.json"
    receiver_path = CONTRACTS / "f017-corrected-oracle-receiver-provenance-v1.json"
    write(policy_path, policy())
    write(receiver_path, {
        "schema": "pulsarmlx.f017.numerical-receiver-provenance/1.0.0",
        "unknown_receiver_behavior": "REJECT",
        "roles": policy()["receiver_roles"],
        "alias_propagation": "FIXED_POINT",
    })
    analyzer_path = RESEARCH / "f017_numerical_capability_analysis_v1.py"
    spec = importlib.util.spec_from_file_location("f017_capability_analysis", analyzer_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    analyses = []
    for role, filename in (
        ("primary", "f017_corrected_oracle_primary_numerics_v2.py"),
        ("secondary", "f017_corrected_oracle_secondary_numerics_v2.py"),
    ):
        analyses.append(module.analyze_path(RESEARCH / filename, policy_path, role).as_json())
    approved_member_names = {
        member
        for module_policy in policy()["semantic_modules"].values()
        for member in (*module_policy["direct_callable_members"], *module_policy["type_dtype_members"])
    }
    prohibited = (set(policy()["prohibited_dynamic_names"]) - approved_member_names) | set(
        policy()["prohibited_capability_member_names"]
    )
    for analysis in analyses:
        overlap = prohibited & set(analysis["bytecode_names"])
        if overlap:
            raise ValueError(f"bytecode dynamic capability names: {sorted(overlap)}")
    write(CONTRACTS / "f017-corrected-oracle-numerical-capability-use-manifest-v1.json", {
        "schema": "pulsarmlx.f017.numerical-capability-use-manifest/1.0.0",
        "derived_review_aid": True,
        "policy_sha256": sha(policy_path),
        "analyzer_sha256": sha(analyzer_path),
        "sources": analyses,
    })
    write(EVIDENCE / "f017-corrected-oracle-numerical-capability-bytecode-audit-v1.json", {
        "schema": "pulsarmlx.f017.numerical-capability-bytecode-audit/1.0.0",
        "result": "PASS",
        "sources": [{"path": value["path"], "names": value["bytecode_names"]} for value in analyses],
        "prohibited_dynamic_names": policy()["prohibited_dynamic_names"],
    })
    print(json.dumps({"result": "PASS", "sources": len(analyses), "policy_sha256": sha(policy_path)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
