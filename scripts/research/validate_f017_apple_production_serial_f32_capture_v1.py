#!/usr/bin/env python3
"""Fail-closed retained-only validator for the F017 Apple serial-f32 surface."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = Path("specs/017-rust-native-inference-runtime/contracts")
EVIDENCE = Path("docs/architecture/reviews/evidence")


class ValidationError(RuntimeError):
    pass


def unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValidationError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(), object_pairs_hook=unique)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"object required: {path}")
    return value


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def exact_binding(root: Path, value: dict[str, Any]) -> Path:
    require(set(value) >= {"path", "sha256"}, "binding field census")
    path = root / value["path"]
    require(path.is_file(), f"binding path:{path}")
    require(sha(path) == value["sha256"], f"binding hash:{path}")
    return path


def rust_stage_ids(source: str) -> list[str]:
    match = re.search(r"pub const STAGE_IDS: &\[&str\] = &\[(.*?)\];", source, re.S)
    require(match is not None, "Rust stage constant")
    return re.findall(r'"([a-z0-9_]+)"', match.group(1))


def validate_stage_contract(stage: dict[str, Any], source: str) -> None:
    rows = stage.get("stages")
    require(isinstance(rows, list) and len(rows) == 34, "stage count")
    ids = [row.get("id") for row in rows]
    require(len(ids) == len(set(ids)) and ids == rust_stage_ids(source), "stage order/census")
    required = {"id", "symbol", "input", "output", "accumulator", "order", "rounding", "backend", "determinism", "classification"}
    classes = {"AUTHORITATIVE_APPLE_PRODUCTION", "SHARED_PRODUCTION_IMPLEMENTATION", "PRODUCTION_BACKEND_SPECIFIC"}
    for row in rows:
        expected_fields = required | ({"numeric_constants"} if row.get("id") == "query_heads" else set())
        require(set(row) == expected_fields, f"stage fields:{row.get('id')}")
        require(row["classification"] in classes, f"stage class:{row['id']}")
        require("UNRESOLVED" not in json.dumps(row), f"unresolved stage:{row['id']}")
        require("run_r9" not in row["symbol"] and "run_r10" not in row["symbol"] and "reference" not in row["symbol"].lower(), f"reference stage:{row['id']}")
        require("f64" not in row["accumulator"].lower() and "binary64" not in row["rounding"].lower(), f"non-f32 production arithmetic:{row['id']}")
    require(ids[-3:] == ["shared_expert_output", "production_ffn", "production_s2"], "terminal graph")
    require(next(r for r in rows if r["id"] == "routed_aggregate")["order"] == "SELECTED_SLOT_RANK_0_TO_7_SERIAL_LEFT_FOLD", "routed order")
    require(next(r for r in rows if r["id"] == "production_ffn")["rounding"] == "ONE_BINARY32_ADD", "FFN rounding")
    require(next(r for r in rows if r["id"] == "production_s2")["rounding"] == "ONE_BINARY32_ADD", "S2 rounding")
    require(next(r for r in rows if r["id"] == "query_heads")["numeric_constants"] == {"rope_base_f32": 1_000_000.0, "position": 0}, "RoPE constants")


def validate_source_semantics(source: str, binary: str) -> None:
    require("use crate::layer_qualification" not in source and "run_r9" not in source and "run_r10" not in source and "as f64" not in source, "proof helper contamination")
    for exact in [
        "pub const RMS_EPSILON: f32 = 0.00001_f32;",
        "pub const ROUTER_TOP_K: usize = 8;",
        "pub const ROUTER_DENOMINATOR_FLOOR: f32 = 6.103_515_625e-5_f32;",
        "inputs.rope_base.to_bits() != 1_000_000.0_f32.to_bits()",
        "for slot in 0..ROUTER_TOP_K",
        "ranking.sort_by",
        "then_with(|| a.cmp(&b))",
        ".map(|(&a, &b)| add_f32(a, b))",
    ]:
        require(exact in source, f"executable numeric/ordering binding:{exact}")
    require("PULSARMLX_F017_OWNED_ATTEMPT_SHA256" in binary, "owned executor gate")
    require("PINNED_NATIVE_MLX_REQUIRED" in binary, "native-only execution")
    require("PACKAGE_EXTRA_OR_MISSING_TENSOR" in binary, "exact tensor census")
    require("publish_bytes" in binary and "PUBLICATION_READBACK" in binary, "durable readback publication")


def validate_capture_contract(capture: dict[str, Any], ids: list[str]) -> None:
    require(capture.get("stage_ids") == ids, "capture stage IDs")
    require(capture.get("recomputation") is False and capture.get("arithmetic_mutation") is False, "capture purity")
    require(capture.get("serialization") == "CONTIGUOUS_CANONICAL_LITTLE_ENDIAN", "capture serialization")
    require(capture.get("all_required_exactly_once") is True, "capture census policy")


def validate_rn1_contract(rn1: dict[str, Any]) -> None:
    require(rn1.get("lock", {}).get("mechanism") == "EXCLUSIVE_FIXED_ATTEMPT_ROOT_MKDIR", "RN1 lock")
    require(rn1.get("cross_invocation_terminalization") is False, "RN1 cross invocation")
    require(rn1.get("shared_terminal_as_authority") is False, "RN1 terminal authority")
    require(rn1.get("accounting", {}).get("terminal_json_sole_authority") is False, "RN1 receipt authority")
    require(rn1.get("accounting", {}).get("mismatch") == "FAIL_CLOSED", "RN1 mismatch")
    require(rn1.get("artifact_inventory", {}).get("orphan_hash") == "REJECTED", "RN1 orphan")
    require(rn1.get("retry") is False and rn1.get("resume") is False and rn1.get("second_invocation") is False, "RN1 one shot")


def validate_package_contract(package: dict[str, Any]) -> None:
    require(package.get("package_created") is False and package.get("live_package_manifest") is False, "no live package")
    require(len(package.get("tensor_roles", [])) == 19, "package role census")
    require(package.get("checkpoint_paths") == [] and package.get("fallback") is False, "package fallback")
    require(package.get("fixed_graph", {}).get("routed_expert_ids") == [250, 10, 237, 62, 73, 177, 218, 28], "package route")
    require(package.get("fixed_graph", {}).get("rope_base_f32") == 1_000_000.0, "package RoPE base")


def validate_release_shape(release: dict[str, Any]) -> None:
    require(release.get("schema") == "pulsarmlx.f017.apple-production-serial-f32-capture-release", "release schema")
    require(release.get("schema_version") == "2.0.0", "release version")
    require(release.get("real_event_authorized") is False, "release authorization")
    require(release.get("ledger") == {"start": 175, "terminal": 175}, "release ledger")
    budgets = release.get("execution_budgets", {})
    zero = ["checkpoint_reads", "shard_opens", "attention_executions", "expert_executions", "aggregate_executions", "shared_expert_executions", "ffn_compositions", "s1_materializations", "s2_constructions"]
    require(all(type(budgets.get(key)) is int and budgets[key] == 0 for key in zero), "zero budgets")
    require(budgets.get("production_equivalence_executions") == 1, "single future execution")
    require(release.get("retry") is False and release.get("resume") is False and release.get("second_attempt") is False, "single use")
    require(release.get("stop_boundary") == "AFTER_APPLE_PRODUCTION_SERIAL_F32_CAPTURE_AND_COMPARISON_ONLY", "stop boundary")
    require(release.get("live_go_token_created") is False, "live token")


def validate(root: Path, *, machine_runtime: bool = True, release_required: bool = True) -> dict[str, Any]:
    prior = load(root / EVIDENCE / "f017-production-serial-f32-equivalence-specification-closeout-v1.json")
    require(prior.get("specification_phase") == "ACCEPTED", "prior spec")
    require(prior.get("count_reconciliation", {}).get("receipt_chain_terminal") == 175, "receipt terminal")
    ledger = root / EVIDENCE / "f017-real-payload-access-ledger-v2.json"
    require(sha(ledger) == "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e", "master ledger")

    architecture = load(root / CONTRACTS / "f017-apple-production-serial-f32-architecture-v1.json")
    stage = load(root / CONTRACTS / "f017-apple-production-serial-f32-stage-manifest-v1.json")
    capture = load(root / CONTRACTS / "f017-apple-production-serial-f32-capture-manifest-v1.json")
    runtime = load(root / CONTRACTS / "f017-apple-production-serial-f32-runtime-binding-v1.json")
    decoder = load(root / CONTRACTS / "f017-apple-production-serial-f32-decoder-bindings-v1.json")
    package = load(root / CONTRACTS / "f017-apple-production-serial-f32-package-schema-v1.json")
    rn1 = load(root / CONTRACTS / "f017-apple-production-serial-f32-rn1-ownership-v2.json")
    determinism = load(root / CONTRACTS / "f017-apple-production-serial-f32-determinism-v1.json")
    tombstone = load(root / CONTRACTS / "f017-apple-production-serial-f32-wrapper-v1-supersession-v1.json")
    authorization = load(root / CONTRACTS / "f017-apple-production-serial-f32-future-authorization-schema-v1.json")
    code_manifest = load(root / CONTRACTS / "f017-apple-production-serial-f32-code-manifest-v1.json")
    release_path = root / CONTRACTS / "f017-apple-production-serial-f32-capture-single-use-release-v2.json"
    release = load(release_path) if release_required else None

    source_path = root / "crates/f017-runner/src/apple_serial_f32.rs"
    binary_path = root / "crates/f017-runner/src/bin/f017-apple-serial-f32-capture.rs"
    source = source_path.read_text()
    binary = binary_path.read_text()
    validate_source_semantics(source, binary)
    validate_stage_contract(stage, source)
    exact_binding(root, stage["source"])
    for item in architecture["sources"]:
        exact_binding(root, item)
    exact_binding(root, architecture["stage_manifest"])
    exact_binding(root, architecture["runtime_binding"])
    require(architecture.get("unresolved_load_bearing_semantics") == [], "architecture unresolved")
    require(architecture.get("checkpoint_access") == "CHECKPOINT_ACCESS_REQUIRED: NO", "checkpoint decision")
    require(architecture.get("production_equivalence_executed") is False, "premature comparison")
    validate_capture_contract(capture, rust_stage_ids(source))
    exact_binding(root, capture["stage_manifest"])
    exact_binding(root, capture["runner"])
    require(runtime["mlx"]["version"] == "0.32.1" and runtime["mlx_c"]["version"] == "0.6.0_4", "runtime versions")
    if machine_runtime:
        for key in ("library", "version_header"):
            require(sha(Path(runtime["mlx"][key]["path"])) == runtime["mlx"][key]["sha256"], f"machine MLX {key}")
            require(sha(Path(runtime["mlx_c"][key]["path"])) == runtime["mlx_c"][key]["sha256"], f"machine MLX-C {key}")
        require(sha(Path(runtime["mlx_c"]["umbrella_header"]["path"])) == runtime["mlx_c"]["umbrella_header"]["sha256"], "machine MLX-C umbrella")
    require(len(decoder.get("formats", [])) == 6, "decoder format census")
    for row in decoder["formats"]:
        exact_binding(root, row["implementation"])
    validate_package_contract(package)
    for binding in package.get("source_authorities", []):
        exact_binding(root, binding)
    exact_binding(root, rn1["wrapper"]); exact_binding(root, rn1["terminalizer"])
    validate_rn1_contract(rn1)
    require(determinism.get("repetitions") == 10 and determinism.get("executed") is False, "determinism")
    require(tombstone.get("current_execution_authority") is False, "v1 tombstone")
    exact_binding(root, tombstone["wrapper_v1"])
    require(authorization.get("inert") is True and authorization.get("real_event_authorized") is False and authorization.get("issued_approvals") == 0 and authorization.get("issued_tokens") == 0, "inert authorization")
    require(code_manifest.get("schema") == "pulsarmlx.f017.apple-production-serial-f32-code-manifest", "code manifest")
    for binding in code_manifest.get("artifacts", []): exact_binding(root, binding)
    if release is not None:
        validate_release_shape(release)
        exact_binding(root, release["code_manifest"])
        exact_binding(root, release["authorization_schema"])
        exact_binding(root, release["runtime_binding"])
        require(release.get("code_manifest", {}).get("sha256") == sha(root / CONTRACTS / "f017-apple-production-serial-f32-code-manifest-v1.json"), "gate immutable code")
        require(not Path(release["machine_local_paths"]["go_token"]).exists(), "live GO token present")
    return {"result":"PASS","stages":34,"decoder_formats":6,"ledger":175,"checkpoint_reads":0,"shard_opens":0,"production_equivalence_executions":0,"live_go_tokens":0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-machine-runtime", action="store_true")
    parser.add_argument("--pre-release", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(args.root.resolve(), machine_runtime=not args.skip_machine_runtime, release_required=not args.pre_release), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
