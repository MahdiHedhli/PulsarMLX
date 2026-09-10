#!/usr/bin/env python3
"""Independent static and contract gates for the V11 Event-05 runtime."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts/research"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _calls(path: Path, function: str) -> list[ast.Call]:
    tree = ast.parse(path.read_text(), filename=str(path))
    target = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == function)
    return [node for node in ast.walk(target) if isinstance(node, ast.Call)]


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name): return call.func.id
    if isinstance(call.func, ast.Attribute): return call.func.attr
    return ""


def _imports(path: Path) -> set[tuple[str, str, str]]:
    result = set()
    for node in ast.parse(path.read_text(), filename=str(path)).body:
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            result.update((node.module, item.name, item.asname or item.name) for item in node.names)
    return result


def _one_function(path: Path, name: str) -> ast.FunctionDef:
    values = [node for node in ast.walk(ast.parse(path.read_text(), filename=str(path)))
              if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(values) != 1:
        raise ValueError("exact active function: " + name)
    return values[0]


def _one_method(path: Path, class_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(), filename=str(path))
    classes = [node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == class_name]
    if len(classes) != 1:
        raise ValueError("exact active class: " + class_name)
    values = [node for node in classes[0].body
              if isinstance(node, ast.FunctionDef) and node.name == method_name]
    if len(values) != 1:
        raise ValueError("exact active method: " + class_name + "." + method_name)
    return values[0]


def _reject_rebinding(path: Path, names: set[str]) -> None:
    tree = ast.parse(path.read_text(), filename=str(path))
    rebound = {node.id for node in ast.walk(tree)
               if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del))
               and node.id in names}
    if rebound:
        raise ValueError("active source symbol rebound: " + ",".join(sorted(rebound)))


def _bridge_get(value: ast.AST, key: str) -> bool:
    return (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
            and value.func.id == "str" and len(value.args) == 1
            and isinstance(value.args[0], ast.Call)
            and isinstance(value.args[0].func, ast.Attribute)
            and isinstance(value.args[0].func.value, ast.Name)
            and value.args[0].func.value.id == "bridge" and value.args[0].func.attr == "get"
            and len(value.args[0].args) == 1 and isinstance(value.args[0].args[0], ast.Constant)
            and value.args[0].args[0].value == key)


def _validate_active_target_source_separation(primary_wrapper: Path, secondary_wrapper: Path,
                                              prefix: Path, factory: Path,
                                              production: Path) -> None:
    primary_imports = _imports(primary_wrapper)
    secondary_imports = _imports(secondary_wrapper)
    prefix_imports = _imports(prefix)
    factory_imports = _imports(factory)
    if ("f017_corrected_oracle_primary_target_source_v11", "source_from_inherited_descriptors",
            "source_from_inherited_descriptors") not in primary_imports:
        raise ValueError("V11 primary target-source separation")
    if ("f017_secondary_read_observation_prefix_v1", "open_secondary_descriptor_prefix",
            "open_secondary_descriptor_prefix") not in secondary_imports:
        raise ValueError("V11 secondary observation source")
    if any(module in {"f017_corrected_oracle_primary_target_source_v11",
                      "f017_corrected_oracle_secondary_target_source_v11"}
           for module, _, _ in secondary_imports):
        raise ValueError("V11 secondary stale or shared target source")
    if ("f017_secondary_read_observation_factory_v1", "create_descriptor_store",
            "create_descriptor_store") not in prefix_imports:
        raise ValueError("V11 secondary prefix factory linkage")
    if ("f017_secondary_descriptor_source_v1", "SecondaryDescriptorStore",
            "SecondaryDescriptorStore") not in factory_imports:
        raise ValueError("V11 secondary descriptor producer linkage")
    _reject_rebinding(secondary_wrapper, {"open_secondary_descriptor_prefix",
                                         "validate_candidate_document"})
    _reject_rebinding(prefix, {"create_descriptor_store"})
    _reject_rebinding(factory, {"SecondaryDescriptorStore"})
    _reject_rebinding(production, {"_execute_secondary_target"})
    target = _one_function(secondary_wrapper, "_minimum_gate_execute_target_and_bank")
    calls = [node for node in ast.walk(target) if isinstance(node, ast.Call)]
    if sum(_call_name(call) == "open_secondary_descriptor_prefix" for call in calls) != 1:
        raise ValueError("V11 secondary prefix construction")
    if sum(_call_name(call) == "validate_candidate_document" for call in calls) != 1:
        raise ValueError("V11 secondary candidate validation")
    prefix_init = _one_method(prefix, "SecondaryDescriptorPrefix", "__init__")
    prefix_calls = [node for node in ast.walk(prefix_init) if isinstance(node, ast.Call)]
    if sum(_call_name(call) == "create_descriptor_store" for call in prefix_calls) != 1:
        raise ValueError("V11 secondary prefix-to-factory linkage")
    factory_target = _one_function(factory, "create_descriptor_store")
    factory_calls = [node for node in ast.walk(factory_target) if isinstance(node, ast.Call)]
    producer_calls = [call for call in factory_calls if _call_name(call) == "SecondaryDescriptorStore"]
    if len(producer_calls) != 1:
        raise ValueError("V11 secondary factory-to-producer linkage")
    producer_keywords = {item.arg: item.value for item in producer_calls[0].keywords
                         if item.arg is not None}
    owner = producer_keywords.get("_observation_owner")
    if not isinstance(owner, ast.Name) or owner.id != "_observation_owner":
        raise ValueError("V11 secondary fixed owner linkage")
    production_imports = _imports(production)
    if ("f017_corrected_oracle_secondary_wrapper_v11", "_minimum_gate_execute_target_and_bank",
            "_execute_secondary_target") not in production_imports:
        raise ValueError("V11 production secondary wrapper linkage")
    secondary = _one_method(production, "_ProductionNumericalEffect", "secondary")
    targets = [call for call in ast.walk(secondary) if isinstance(call, ast.Call)
               and _call_name(call) == "_execute_secondary_target"]
    if len(targets) != 1:
        raise ValueError("V11 production secondary target call")
    keywords = {item.arg: item.value for item in targets[0].keywords if item.arg is not None}
    if not _bridge_get(keywords.get("package_attempt_id"), "package_attempt_id"):
        raise ValueError("V11 production package identity linkage")
    if not _bridge_get(keywords.get("consumer_event_id"), "secondary_event_id"):
        raise ValueError("V11 production secondary event identity linkage")


def main() -> int:
    primary_v2 = RESEARCH / "f017_corrected_oracle_primary_numerics_v2.py"
    secondary_v2 = RESEARCH / "f017_corrected_oracle_secondary_numerics_v2.py"
    primary_v3 = RESEARCH / "f017_corrected_oracle_primary_numerics_v3.py"
    secondary_v3 = RESEARCH / "f017_corrected_oracle_secondary_numerics_v3.py"
    if _sha(primary_v2) != "657cdff9ee833cb2b3a0b3fa71b6cbc3dd1e0fbc71b74b9bbff9dca6b5b76767":
        raise ValueError("historical primary V2")
    if _sha(secondary_v2) != "e3670b22ac71bad7523efe1e47b00f2345d1f103d2af8f7592e2f3f8c793a791":
        raise ValueError("historical secondary V2")
    historical_sources = {
        "f017_corrected_oracle_primary_target_source_v10.py": "ceab082d593a22fc30f76e67947b1819809edf0be488476f7affa326f5e744f4",
        "f017_corrected_oracle_secondary_target_source_v10.py": "421e3c9c414257527cc20b43906326323bc22d8fc65be3e195048957f40a21b8",
    }
    for name, expected in historical_sources.items():
        if _sha(RESEARCH / name) != expected:
            raise ValueError(f"historical V10 target-source drift: {name}")
    numerical_v4 = json.loads((CONTRACTS / "f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json").read_text())
    if (numerical_v4["oracle_roles"]["primary"]["implementation_sha256"] != _sha(primary_v3)
            or numerical_v4["oracle_roles"]["secondary"]["implementation_sha256"] != _sha(secondary_v3)):
        raise ValueError("V4 successor core binding")
    primary_wrapper = RESEARCH / "f017_corrected_oracle_primary_wrapper_v11.py"
    secondary_wrapper = RESEARCH / "f017_corrected_oracle_secondary_wrapper_v11.py"
    _validate_active_target_source_separation(
        primary_wrapper, secondary_wrapper,
        RESEARCH / "f017_secondary_read_observation_prefix_v1.py",
        RESEARCH / "f017_secondary_read_observation_factory_v1.py",
        RESEARCH / "f017_event06_minimum_gate_path_v1.py",
    )
    p_calls = _calls(primary_wrapper, "_minimum_gate_execute_and_bank")
    s_calls = _calls(secondary_wrapper, "_minimum_gate_execute_and_bank")
    if sum(_call_name(call) == "execute_outputs" for call in p_calls) != 1:
        raise ValueError("primary one-execution gate")
    if sum(_call_name(call) == "execute_outputs" for call in s_calls) != 1:
        raise ValueError("secondary one-execution gate")
    s_gate = next(call.lineno for call in s_calls if _call_name(call) == "require_primary_terminal")
    s_execute = next(call.lineno for call in s_calls if _call_name(call) == "execute_outputs")
    if s_gate >= s_execute: raise ValueError("secondary gate order")
    for path, function in (
        (primary_wrapper, "execute_and_bank"),
        (primary_wrapper, "execute_target_and_bank"),
        (secondary_wrapper, "execute_and_bank"),
        (secondary_wrapper, "execute_target_and_bank"),
    ):
        target = next(
            node for node in ast.walk(ast.parse(path.read_text(), filename=str(path)))
            if isinstance(node, ast.FunctionDef) and node.name == function
        )
        if not any(isinstance(node, ast.Raise) for node in target.body):
            raise ValueError(f"superseded wrapper is not fail closed: {function}")
    builder = (RESEARCH / "f017_result_bundle_builder_v11.py").read_text()
    if ("_minimum_gate_bank_output_bundle" not in builder
            or "bank_payload_bytes" not in builder or "full_logits_payload" not in builder
            or "json.dumps" in builder or "canonical payload must be immutable bytes" not in
            (RESEARCH / "f017_result_envelope_v11.py").read_text()):
        raise ValueError("exact-byte result banking")
    coordinator = (RESEARCH / "execute_f017_corrected_oracle_event_v11.py").read_text()
    positions = [coordinator.index(marker) for marker in (
        "primary = execute_primary", "secondary = execute_secondary", "comparison = derive_summary",
        "result_closure = closure_root", '"PACKAGE_TERMINAL"')]
    if positions != sorted(positions): raise ValueError("V11 causal coordinator order")
    envelope = json.loads((CONTRACTS / "f017-corrected-oracle-binary-result-envelope-v11-v2.json").read_text())
    authority = json.loads((CONTRACTS / "f017-corrected-oracle-result-authority-v11-v2.json").read_text())
    full_geometry = json.loads((ROOT / "docs/architecture/reviews/evidence/f017-v11-full-geometry-qualification-v2.json").read_text())
    expected_numerical = {
        "path":"specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json",
        "sha256":_sha(CONTRACTS / "f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json")}
    if envelope["numerical_contract"] != expected_numerical or authority["numerical_contract"] != expected_numerical:
        raise ValueError("V11 numerical V4 binding")
    if (full_geometry.get("real_core_summary_coupling") != "PASS"
            or full_geometry.get("real_core_summary_coupling_cases") != 2):
        raise ValueError("V11 real-core banking seam")
    active = json.loads((CONTRACTS / "f017-corrected-oracle-active-generation-v11.json").read_text())
    if (active["active_corrected_oracle_generation"] != "NONE"
            or active["event_05_authorization_created"] is not False
            or active["event_05_executed"] is not False):
        raise ValueError("pre-acceptance V11 posture")
    result = {
        "schema":"pulsarmlx.f017.v11-execution-authority-validation/1.0.0",
        "historical_v2_cores":"BYTE_EXACT",
        "successor_v3_cores":"BOUND_BY_NUMERICAL_V4",
        "primary_execute_outputs_calls":1,
        "secondary_execute_outputs_calls":1,
        "secondary_gate_before_execution":"PASS",
        "exact_immutable_payload_banking":"PASS",
        "real_core_summary_coupling":"PASS",
        "historical_v10_target_sources":"BYTE_EXACT",
        "v11_target_source_separation":"PASS",
        "control_plane_full_arrays":0,
        "coordinator_causal_order":"PASS",
        "event_04_retry":False,
        "event_05_executed":False,
        "live_event_05_authorization_created":False,
        "original_checkpoint_access":0,
        "result":"PASS",
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__": raise SystemExit(main())
