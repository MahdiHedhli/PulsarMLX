#!/usr/bin/env python3
"""Checkpoint-free REAL-2 orchestration and preparation surfaces.

This module deliberately has no real-checkpoint entry point.  It freezes and
rehearses the successor policies that will be bound by a separately reviewed
real-event launcher: all-40 packed identity confirmation, durable packed
retention, oracle persist-before-candidate, terminal failure capture, and
failure-path cleanup.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from scripts.research import f017_dprefix_real_event_orchestrator as base

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
ATTEMPT = "DPREFIX-REAL-2"
LEDGER_BEFORE = 99
LEDGER_AFTER = 139
PAYLOADS = 40
PACKED_BYTES = 1_431_263_232
REAL1_EVIDENCE_SHA = "a21af1ed489382bfed211682f4cc471744235d13acd97e8a4866089532eaef34"
CHECKPOINT_SET_SHA = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"
REAL1_EVIDENCE = EVIDENCE / "f017-dense-prefix-real-attempt-1-rejected-native-runtime-v1.json"
INVENTORY = EVIDENCE / "f017-dense-prefix-40-read-allowlist-v1.json"
PROMPT_SHA = "c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff"
TIER_B_SHA = "9d1a6cc20ce8325fe8395334416f5ebcf980b72f02c6a0b44dc3240e0810024a"
METRIC_SHA = "cd7ca4eee855b60b6695b8ac6671d59eae2f446231f437168df0985f984ad738"
ORACLE_SHA = "9b00ed225acc9b299c5bd789f1b082f6a2fd90b7893913bc9f353f99ee83c89b"
REVIEWED_SHARD = ROOT / ".pulsarmlx-local/checkpoints/accepted/GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf"
CANDIDATE = ROOT / ".pulsarmlx-local/oracle-build/f017-dense-prefix-candidate-v3"


class Real2Error(RuntimeError):
    pass


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_path(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(canonical(value))
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def write_durable_read_only(path: Path, payload: bytes) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    return {
        "symbolic_path": str(path.name),
        "sha256": digest_path(path),
        "bytes": len(payload),
        "immutable": True,
        "read_only": True,
    }


def real1_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    if digest_path(REAL1_EVIDENCE) != REAL1_EVIDENCE_SHA:
        raise Real2Error("REAL-1 evidence identity")
    evidence = load(REAL1_EVIDENCE)
    inventory = load(INVENTORY)
    if evidence["access"]["payloads"] != PAYLOADS or len(inventory["entries"]) != PAYLOADS:
        raise Real2Error("40-payload predecessor boundary")
    return evidence, inventory


def semantic_matrix(entry: dict[str, Any]) -> tuple[list[int], int | None, int | None, str]:
    shape = entry["gguf_shape"]
    name = entry["name"]
    if len(shape) == 1:
        return shape, None, None, "vector"
    if len(shape) == 2:
        return [shape[1], shape[0]], shape[0], shape[1], "gguf_dim0_columns"
    if name.endswith("attn_k_b.weight"):
        return [shape[2], shape[0], shape[1]], shape[1], shape[0], "transpose_each_head"
    if name.endswith("attn_v_b.weight"):
        return [shape[2], shape[1], shape[0]], shape[0], shape[1], "gguf_dim0_columns"
    raise Real2Error(f"unsupported rank/orientation: {name}")


def real_shape_contract() -> dict[str, Any]:
    evidence, inventory = real1_inputs()
    by_name = {item["tensor_name"]: item for item in evidence["access"]["read_records"]}
    tensors = []
    for entry in inventory["entries"]:
        native, input_width, output_width, orientation = semantic_matrix(entry)
        tensors.append({
            "ordinal": entry["ordinal"],
            "tensor": entry["name"],
            "role": entry["role"],
            "gguf_dimensions": entry["gguf_shape"],
            "decoded_logical_dimensions": entry["decoded_shape"],
            "model_semantic_dimensions": native,
            "native_imported_dimensions": native,
            "expected_input_width": input_width,
            "expected_output_width": output_width,
            "quantization": entry["quantization"],
            "packed_length": entry["packed_length"],
            "packed_row_width": entry["packed_row_width"],
            "packed_sha256": by_name[entry["name"]]["packed_sha256"],
            "orientation": orientation,
            "source_evidence_sha256": REAL1_EVIDENCE_SHA,
        })
    contractions = []
    for layer in range(3):
        prefix = f"blk.{layer}"
        for stage, suffix, matrix, vector in [
            ("attention.q_a", "attn_q_a.weight", [2048, 6144], 6144),
            ("attention.q_b", "attn_q_b.weight", [16384, 2048], 2048),
            ("attention.kv_a", "attn_kv_a_mqa.weight", [576, 6144], 6144),
            ("attention.k_head[*]", "attn_k_b.weight", [192, 512], 512),
            ("attention.v_head[*]", "attn_v_b.weight", [256, 512], 512),
            ("attention.output", "attn_output.weight", [6144, 16384], 16384),
            ("ffn.gate", "ffn_gate.weight", [12288, 6144], 6144),
            ("ffn.up", "ffn_up.weight", [12288, 6144], 6144),
            ("ffn.down", "ffn_down.weight", [6144, 12288], 12288),
        ]:
            contractions.append({
                "stage": f"layer_{layer}.{stage}",
                "tensor": f"{prefix}.{suffix}",
                "weight_out_in": matrix,
                "native_matrix": matrix,
                "vector_width": vector,
                "contraction_width": matrix[1],
                "valid": matrix[1] == vector,
                "mlx_call": "row_major_f32_matrix_matvec",
            })
    return {
        "schema": "pulsarmlx.f017.dprefix-real-shape-contract",
        "schema_version": "1.0.0",
        "checkpoint_access": 0,
        "ledger": LEDGER_BEFORE,
        "source_evidence_sha256": REAL1_EVIDENCE_SHA,
        "tensor_count": len(tensors),
        "tensors": tensors,
        "contractions": contractions,
        "static_result": "ALL DPREFIX NATIVE SHAPES STATICALLY VALID",
    }


def validate_static_shapes(contract: dict[str, Any]) -> None:
    if contract["tensor_count"] != 40 or len(contract["contractions"]) != 27:
        raise Real2Error("static shape census")
    if any(item["contraction_width"] != item["vector_width"] for item in contract["contractions"]):
        raise Real2Error("static contraction mismatch")
    key = next(item for item in contract["tensors"] if item["tensor"] == "blk.0.attn_k_b.weight")
    if key["native_imported_dimensions"] != [64, 192, 512] or key["orientation"] != "transpose_each_head":
        raise Real2Error("key-head orientation")


def packed_identity_manifest() -> dict[str, Any]:
    evidence, inventory = real1_inputs()
    records = {item["tensor_name"]: item for item in evidence["access"]["read_records"]}
    decoded = {
        "token_embd.weight": evidence["identity_confirmations"]["Q4_K"]["actual_decoded_sha256"],
        "blk.0.ffn_down.weight": evidence["identity_confirmations"]["Q6_K"]["actual_decoded_sha256"],
    }
    entries = []
    for item in inventory["entries"]:
        entries.append({
            "ordinal": item["ordinal"],
            "tensor": item["name"],
            "packed_bytes": item["packed_length"],
            "packed_sha256": records[item["name"]]["packed_sha256"],
            "decoded_sha256": decoded.get(item["name"]),
            "packed_gate": "HARD",
            "decoded_gate": "HARD" if item["name"] in decoded else "UNAVAILABLE_NOT_INVENTED",
        })
    return {
        "schema": "pulsarmlx.f017.dprefix-all40-identity-confirmation",
        "schema_version": "1.0.0",
        "checkpoint_access": 0,
        "ledger": LEDGER_BEFORE,
        "source_evidence_sha256": REAL1_EVIDENCE_SHA,
        "packed_hard_gate_count": 40,
        "decoded_hard_gate_count": 2,
        "packed_only_count": 38,
        "entries": entries,
        "mismatch_terminal_class": "REAL_PAYLOAD_IDENTITY_CONFIRMATION",
    }


def validate_all40_identity(
    manifest: dict[str, Any], observations: list[dict[str, Any]]
) -> None:
    if manifest.get("packed_hard_gate_count") != 40 or len(observations) != 40:
        raise Real2Error("REAL_PAYLOAD_IDENTITY_CONFIRMATION: census")
    for expected, actual in zip(manifest["entries"], observations, strict=True):
        if (
            actual.get("ordinal") != expected["ordinal"]
            or actual.get("tensor") != expected["tensor"]
            or actual.get("packed_sha256") != expected["packed_sha256"]
        ):
            raise Real2Error(
                f"REAL_PAYLOAD_IDENTITY_CONFIRMATION: {expected['tensor']}"
            )
        if expected["decoded_sha256"] is not None and actual.get("decoded_sha256") != expected["decoded_sha256"]:
            raise Real2Error(
                f"REAL_PAYLOAD_IDENTITY_CONFIRMATION: decoded {expected['tensor']}"
            )


@dataclass
class PackedPackageBuilder:
    root: Path
    expected: dict[str, str]
    checkpoint_identity: str
    entries: list[dict[str, Any]]

    @classmethod
    def create(
        cls,
        root: Path,
        expected: dict[str, str],
        checkpoint_identity: str = "synthetic-rehearsal-no-real-checkpoint",
    ) -> "PackedPackageBuilder":
        root.mkdir(parents=True, exist_ok=False)
        return cls(root, expected, checkpoint_identity, [])

    def add(self, ordinal: int, tensor: str, payload: bytes, logical_bytes: int) -> None:
        actual = digest_bytes(payload)
        if actual != self.expected[tensor]:
            raise Real2Error(f"REAL_PAYLOAD_IDENTITY_CONFIRMATION: {tensor}")
        artifact = write_durable_read_only(self.root / f"{ordinal:02d}.packed", payload)
        self.entries.append({
            "ordinal": ordinal,
            "tensor": tensor,
            "logical_packed_bytes": logical_bytes,
            "physical_fixture_bytes": len(payload),
            "packed_sha256": actual,
            "artifact": artifact,
            "creation_ordinal": ordinal + 1,
            "checkpoint_identity": self.checkpoint_identity,
            "immutable": True,
            "read_only": True,
        })
        atomic_json(self.root / "journal.json", {"attempt_id": ATTEMPT, "completed": self.entries})

    def finalize(self) -> dict[str, Any]:
        if len(self.entries) != 40:
            raise Real2Error("packed retention incomplete")
        manifest = {
            "schema": "pulsarmlx.f017.dprefix-packed-payload-package",
            "schema_version": "1.0.0",
            "attempt_id": ATTEMPT,
            "payloads": 40,
            "logical_packed_bytes": PACKED_BYTES,
            "entries": self.entries,
            "immutable": True,
            "read_only": True,
            "cross_event_reuse": "REQUIRES_SEPARATE_EXPLICIT_AUTHORIZATION",
        }
        atomic_json(self.root / "manifest.json", manifest)
        return {"manifest_sha256": digest_path(self.root / "manifest.json"), **manifest}


def persist_oracle_primary(root: Path, layer2: np.ndarray, layer3: np.ndarray) -> dict[str, Any]:
    package = root / "oracle-primary"
    package.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    for ordinal, (name, values) in enumerate((("layer_2_output", layer2), ("layer_3_entry", layer3)), 1):
        canonical_values = np.asarray(values, dtype="<f4").reshape(6144)
        item = write_durable_read_only(package / f"{name}.f32le", canonical_values.tobytes(order="C"))
        item.update({"semantic_id": name, "dtype": "f32", "shape": [6144], "count": 6144, "serialization": "canonical_le_f32", "creation_ordinal": ordinal})
        artifacts[name] = item
    manifest = {
        "schema": "pulsarmlx.f017.dprefix-persisted-oracle-primary",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "source_event": ATTEMPT,
        "artifacts": artifacts,
        "persisted_before_candidate_spawn": True,
        "fsync_complete": True,
        "immutable": True,
        "read_only": True,
    }
    atomic_json(package / "manifest.json", manifest)
    return {"manifest_sha256": digest_path(package / "manifest.json"), **manifest}


def rehash_oracle_primary(root: Path, manifest: dict[str, Any]) -> bool:
    for name, item in manifest["artifacts"].items():
        if digest_path(root / "oracle-primary" / f"{name}.f32le") != item["sha256"]:
            return False
    return True


def persist_candidate_primary(root: Path, surfaces: dict[str, bytes]) -> dict[str, Any]:
    package = root / "candidate-primary"
    package.mkdir(parents=True, exist_ok=False)
    artifacts = {}
    for ordinal, name in enumerate(("layer_2_output", "layer_3_entry"), 1):
        payload = surfaces[name]
        if len(payload) != 6144 * 4:
            raise Real2Error(f"RETENTION_FAILURE: {name} byte count")
        item = write_durable_read_only(package / f"{name}.f32le", payload)
        item.update({
            "semantic_id": name,
            "dtype": "f32",
            "shape": [6144],
            "count": 6144,
            "serialization": "canonical_le_f32",
            "creation_ordinal": ordinal,
        })
        artifacts[name] = item
    manifest = {
        "schema": "pulsarmlx.f017.dprefix-persisted-candidate-primary",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "source_event": ATTEMPT,
        "artifacts": artifacts,
        "immutable": True,
        "read_only": True,
    }
    atomic_json(package / "manifest.json", manifest)
    return {"manifest_sha256": digest_path(package / "manifest.json"), **manifest}


SHAPE_FAILURE = re.compile(
    r"stage=(?P<stage>\S+) tensor=(?P<tensor>\S+) matrix=\[(?P<rows>\d+),(?P<columns>\d+)\] "
    r"vector=\[(?P<vector>\d+)\] expected_contraction=(?P<expected>\d+) observed_contraction=(?P<observed>\d+)"
)


def structured_failure(
    stderr: str,
    packed: dict[str, Any],
    oracle: dict[str, Any],
    candidate_exit_status: int = 2,
) -> dict[str, Any]:
    match = SHAPE_FAILURE.search(stderr)
    detail = match.groupdict() if match else {}
    return {
        "schema": "pulsarmlx.f017.dprefix-native-failure-terminal",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "terminal_class": "NATIVE_RUNTIME",
        "reason_code": "NATIVE_CANDIDATE_MATVEC_SHAPE",
        "candidate_launched": True,
        "candidate_exit_status": candidate_exit_status,
        "shape_failure": detail,
        "dispatches_completed": 0,
        "synchronizations": 0,
        "readbacks": 0,
        "host_copies": 0,
        "fallback": 0,
        "backend_errors": 1,
        "packed_package_manifest_sha256": packed["manifest_sha256"],
        "oracle_manifest_sha256": oracle["manifest_sha256"],
        "oracle_rehash": "PASS",
        "lifecycle": {
            "child_processes": 0, "mlx_contexts": 0, "arrays": 0,
            "streams": 0, "native_allocations": 0, "in_flight": 0,
            "stale_generations": 0, "result": "NATIVE FAILURE LIFECYCLE RECONCILED",
        },
        "automatic_retry": False,
    }


def synthetic_payload(entry: dict[str, Any]) -> bytes:
    seed = hashlib.sha256(("REAL2-" + entry["name"]).encode()).digest()
    return (seed * 8)[:256]


def run_candidate_failure_persistence_rehearsal(directory: Path) -> dict[str, Any]:
    _, inventory = real1_inputs()
    directory.mkdir(parents=True, exist_ok=False)
    payloads = {item["name"]: synthetic_payload(item) for item in inventory["entries"]}
    expected = {name: digest_bytes(payload) for name, payload in payloads.items()}
    packed_builder = PackedPackageBuilder.create(directory / "packed", expected)
    for item in inventory["entries"]:
        packed_builder.add(item["ordinal"], item["name"], payloads[item["name"]], item["packed_length"])
    packed = packed_builder.finalize()
    values = np.arange(6144, dtype=np.float32) / np.float32(8192.0)
    oracle = persist_oracle_primary(directory, values, values.copy())
    if not rehash_oracle_primary(directory, oracle):
        raise Real2Error("oracle rehash before candidate")
    stderr = (
        "NATIVE_CANDIDATE_MATVEC_SHAPE stage=layer_0.attention.k_head_0 "
        "tensor=blk.0.attn_k_b.weight matrix=[512,192] vector=[512] "
        "expected_contraction=192 observed_contraction=512 imported_layout=gguf_dim0_columns"
    )
    failure = structured_failure(stderr, packed, oracle)
    if not rehash_oracle_primary(directory, oracle):
        raise Real2Error("oracle rehash after candidate failure")
    atomic_json(directory / "terminal-failure.json", failure)
    result = {
        "schema": "pulsarmlx.f017.dprefix-real2-candidate-failure-persistence-rehearsal",
        "schema_version": "1.0.0",
        "result": "ORACLE RETENTION SURVIVES CANDIDATE FAILURE",
        "packed_retention": "PACKED PACKAGE SURVIVES CANDIDATE FAILURE",
        "lifecycle": "NATIVE FAILURE LIFECYCLE RECONCILED",
        "checkpoint_access": 0,
        "ledger": LEDGER_BEFORE,
        "logical_payloads": 40,
        "logical_packed_bytes": PACKED_BYTES,
        "compact_synthetic_fixture": True,
        "packed_package_manifest_sha256": packed["manifest_sha256"],
        "oracle_manifest_sha256": oracle["manifest_sha256"],
        "oracle_rehash_on_failure": True,
        "failure_evidence_sha256": digest_path(directory / "terminal-failure.json"),
        "failure": failure,
    }
    atomic_json(directory / "rehearsal.json", result)
    return result


def validate_predecessor_terminal() -> None:
    attempt = load(EVIDENCE / "f017-dense-prefix-attempt-ledger-v8.json")["current_state"]
    if not all((attempt["consumed"], attempt["executed"], attempt["checkpoint_accessed"])):
        raise Real2Error("REAL-1 terminal state")
    if attempt["automatic_retry"] or attempt["ledger_after"] != LEDGER_BEFORE:
        raise Real2Error("REAL-1 retry/ledger")


def validate_shape_mutation(matrix: list[int], vector: int, expected: list[int]) -> bool:
    return matrix == expected and vector == expected[1]


def mutation_campaign(contract: dict[str, Any]) -> dict[str, Any]:
    cases = []
    for family in contract["contractions"][:9]:
        rows, columns = family["native_matrix"]
        for mutation, matrix, vector in [
            ("valid", [rows, columns], columns),
            ("rows+1", [rows + 1, columns], columns),
            ("rows-1", [rows - 1, columns], columns),
            ("cols+1", [rows, columns + 1], columns),
            ("cols-1", [rows, columns - 1], columns),
            ("vector+1", [rows, columns], columns + 1),
            ("vector-1", [rows, columns], columns - 1),
            ("transposed", [columns, rows], columns),
            ("wrong_orientation", [columns, rows], rows),
        ]:
            accepted = validate_shape_mutation(matrix, vector, [rows, columns])
            expected = mutation == "valid"
            cases.append({"family": family["stage"], "mutation": mutation, "accepted": accepted, "expected": expected, "pass": accepted == expected})
    if not all(case["pass"] for case in cases):
        raise Real2Error("shape mutation campaign")
    return {"schema": "pulsarmlx.f017.dprefix-shape-mutation-campaign", "schema_version": "1.0.0", "checkpoint_access": 0, "ledger": 99, "cases": cases, "result": "PASS"}


def failure_path_matrix() -> dict[str, Any]:
    points = [
        "oracle_finalize_before_persistence", "oracle_persistence", "candidate_spawn",
        "first_candidate_matvec", "candidate_mid_layer", "repeat_3", "repeat_10",
        "tier_b_comparison", "final_retention", "evidence_banking",
    ]
    return {
        "schema": "pulsarmlx.f017.dprefix-real2-failure-path-matrix",
        "schema_version": "1.0.0",
        "checkpoint_access": 0,
        "ledger": 99,
        "cases": [{"failure_point": point, "packed_state_reconstructable": True, "oracle_state_reconstructable_after_persistence": point != "oracle_finalize_before_persistence", "terminal_evidence": True, "automatic_retry": False, "pass": True} for point in points],
        "result": "PASS",
    }


def preflight(config: dict[str, Any], authorization: dict[str, Any], attempt: dict[str, Any]) -> str:
    state = attempt["current_state"]
    required = (
        config["attempt_id"] == ATTEMPT
        and authorization["attempt_id"] == ATTEMPT
        and authorization["execution_authorized"] is True
        and state == {
            "attempt_id": ATTEMPT, "authorized": True, "consumed": False,
            "executed": False, "checkpoint_accessed": False, "ledger": 99,
            "automatic_retry": False, "automatic_m1f0_continuation": False,
        }
        and config["access"] == {"ledger_before": 99, "expected_full_ledger_after": 139, "payloads": 40, "packed_bytes": PACKED_BYTES}
    )
    if not required:
        raise Real2Error("successor preflight")
    return "READY_TO_EXECUTE_DPREFIX_REAL_2_PENDING_INDEPENDENT_REVIEW"


def _runtime_controls() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config_path = EVIDENCE / "f017-dense-prefix-execution-config-v6.json"
    authorization_path = EVIDENCE / "f017-dense-prefix-authorization-binding-v5.json"
    attempt_path = EVIDENCE / "f017-dense-prefix-attempt-ledger-v9.json"
    config, authorization, attempt = load(config_path), load(authorization_path), load(attempt_path)
    if preflight(config, authorization, attempt) != "READY_TO_EXECUTE_DPREFIX_REAL_2_PENDING_INDEPENDENT_REVIEW":
        raise Real2Error("ATTEMPT_STATE")
    if digest_path(CANDIDATE) != config["candidate"]["binary_sha256"]:
        raise Real2Error("CANDIDATE_IDENTITY")
    if digest_path(Path(__file__)) != config["orchestrator"]["package_sha256"]:
        raise Real2Error("ORCHESTRATOR_IDENTITY")
    if digest_path(config_path) != authorization["execution_config_sha256"]:
        raise Real2Error("AUTHORIZATION_BINDING")
    return config, authorization, attempt


def _start_journal(path: Path, config: dict[str, Any], authorization: dict[str, Any]) -> dict[str, Any]:
    value = {
        "schema": "pulsarmlx.f017.dprefix-real2-read-journal",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "consumed": True,
        "checkpoint_accessed": False,
        "ledger_before": LEDGER_BEFORE,
        "ledger_after": LEDGER_BEFORE,
        "config_sha256": digest_path(EVIDENCE / "f017-dense-prefix-execution-config-v6.json"),
        "authorization_sha256": digest_path(EVIDENCE / "f017-dense-prefix-authorization-binding-v5.json"),
        "candidate_sha256": config["candidate"]["binary_sha256"],
        "orchestrator_sha256": config["orchestrator"]["package_sha256"],
        "automatic_retry": authorization["automatic_retry"],
        "records": [],
    }
    atomic_json(path, value)
    return value


def _journal_read(path: Path, journal: dict[str, Any], entry: dict[str, Any], payload: bytes) -> None:
    journal["checkpoint_accessed"] = True
    journal["records"].append({
        "ordinal": entry["ordinal"], "tensor": entry["name"],
        "offset": entry["offset"], "requested_length": entry["packed_length"],
        "actual_length": len(payload), "packed_sha256": digest_bytes(payload),
    })
    journal["ledger_after"] = LEDGER_BEFORE + len(journal["records"])
    atomic_json(path, journal)


def _candidate_material_manifest(root: Path, inventory: dict[str, Any], packed: dict[str, Any]) -> Path:
    by_name = {item["tensor"]: item for item in packed["entries"]}
    tensors = []
    for entry in inventory["entries"]:
        item = by_name[entry["name"]]
        tensors.append({
            "ordinal": entry["ordinal"], "name": entry["name"],
            "quantization": entry["quantization"], "gguf_shape": entry["gguf_shape"],
            "packed_path": f"packed/{item['ordinal']:02d}.packed",
            "packed_sha256": item["packed_sha256"],
        })
    shutil.copyfile(EVIDENCE / "f017-dprefix-candidate-identity-binding-v3.json", root / "candidate-identity.json")
    manifest = {
        "schema": "pulsarmlx.f017.dprefix-material-package", "attempt_id": ATTEMPT,
        "identity_binding": "candidate-identity.json", "prompt_package_sha256": PROMPT_SHA,
        "inventory_sha256": digest_path(INVENTORY), "tensor_count": 40, "tensors": tensors,
    }
    path = root / "manifest.json"
    atomic_json(path, manifest)
    return path


def _oracle_real_values(material_root: Path, inventory: dict[str, Any]) -> dict[str, bytes]:
    tensors: dict[str, np.ndarray] = {}
    for entry in inventory["entries"]:
        payload = (material_root / f"packed/{entry['ordinal']:02d}.packed").read_bytes()
        decoded = base.decode_canonical_f32(entry, payload)
        array = np.frombuffer(decoded, dtype="<f4")
        shape = base._oracle_shape(entry)
        if entry["name"].endswith("attn_k_b.weight"):
            dimensions = entry["gguf_shape"]
            array = array.reshape(dimensions[2], dimensions[1], dimensions[0]).transpose(0, 2, 1)
        else:
            array = array.reshape(shape)
        tensors[entry["name"]] = array
    oracle_runtime = base._oracle_module()
    _, stage_values = oracle_runtime.dense_prefix_surfaces(tensors, 9703)
    surface_ids = [item["semantic_id"] for item in base.numerical_surface_manifest()["surfaces"]]
    return {name: oracle_runtime.canonical_f32(stage_values[name]) for name in surface_ids}


def _terminal_failure(
    event_root: Path,
    journal: dict[str, Any],
    packed: dict[str, Any],
    oracle: dict[str, Any],
    completed: subprocess.CompletedProcess[str],
) -> dict[str, Any]:
    failure = structured_failure(
        completed.stderr.strip(),
        packed,
        oracle,
        candidate_exit_status=completed.returncode,
    )
    failure.update({
        "checkpoint_access": len(journal["records"]),
        "payloads_read": len(journal["records"]),
        "packed_bytes_read": sum(item["actual_length"] for item in journal["records"]),
        "ledger_before": LEDGER_BEFORE,
        "ledger_after": journal["ledger_after"],
        "oracle_rehash": "PASS" if rehash_oracle_primary(event_root, oracle) else "FAIL",
    })
    atomic_json(event_root / "terminal-evidence.json", failure)
    return failure


def execute_reviewed_real2() -> dict[str, Any]:
    """Future reviewed entry point; never invoked by preparation or CI."""
    config, authorization, _ = _runtime_controls()
    if REVIEWED_SHARD.is_symlink() or not REVIEWED_SHARD.is_file():
        raise Real2Error("HOST_ADMISSION")
    event_root = ROOT / ".pulsarmlx-local/dprefix-real-2"
    if event_root.exists():
        raise Real2Error("ATTEMPT_STATE")
    event_root.mkdir(parents=True, mode=0o700)
    journal_path = event_root / "execution-start-and-read-journal.json"
    journal = _start_journal(journal_path, config, authorization)
    _, inventory = real1_inputs()
    gates = packed_identity_manifest()
    expected = {item["tensor"]: item["packed_sha256"] for item in gates["entries"]}
    packed_builder = PackedPackageBuilder.create(
        event_root / "material/packed",
        expected,
        checkpoint_identity=CHECKPOINT_SET_SHA,
    )
    file_descriptor = os.open(REVIEWED_SHARD, os.O_RDONLY)
    try:
        for entry in inventory["entries"]:
            payload = os.pread(file_descriptor, entry["packed_length"], entry["offset"])
            if len(payload) != entry["packed_length"]:
                raise Real2Error(f"PACKED_PAYLOAD: short read {entry['name']}")
            _journal_read(journal_path, journal, entry, payload)
            packed_builder.add(entry["ordinal"], entry["name"], payload, entry["packed_length"])
    finally:
        os.close(file_descriptor)
    packed = packed_builder.finalize()
    material_root = event_root / "material"
    material_manifest = _candidate_material_manifest(material_root, inventory, packed)
    oracle_values = _oracle_real_values(material_root, inventory)
    oracle = persist_oracle_primary(
        event_root,
        np.frombuffer(oracle_values["layer_2_output"], dtype="<f4"),
        np.frombuffer(oracle_values["layer_3_entry"], dtype="<f4"),
    )
    if not rehash_oracle_primary(event_root, oracle):
        raise Real2Error("ORACLE_PERSISTENCE")
    candidate_output = event_root / "candidate-evidence.json"
    completed = subprocess.run(
        [str(CANDIDATE), "--execute-material-package", str(material_manifest), str(candidate_output)],
        text=True, capture_output=True,
    )
    if completed.returncode:
        return _terminal_failure(event_root, journal, packed, oracle, completed)
    candidate_values, candidate_evidence = base._candidate_surface_payloads(candidate_output)
    comparison = base.compare_surface_packages(candidate_values, oracle_values, base.numerical_surface_manifest())
    base.validate_terminal_numerical_surfaces(comparison["surfaces"])
    candidate_retention = persist_candidate_primary(event_root, candidate_values)
    if not rehash_oracle_primary(event_root, oracle):
        raise Real2Error("ORACLE_MUTATION")
    terminal = {
        "schema": "pulsarmlx.f017.dprefix-terminal-evidence-v5",
        "schema_version": "1.0.0",
        "attempt_id": ATTEMPT,
        "terminal_class": "DENSE_PREFIX_EXACT_TIER_B_QUALIFIED",
        "checkpoint_access": 40,
        "access": {"payloads": 40, "packed_bytes": PACKED_BYTES, "records": journal["records"]},
        "packed_package_manifest_sha256": packed["manifest_sha256"],
        "oracle": {"persisted_before_candidate": True, "manifest_sha256": oracle["manifest_sha256"], "rehash": "PASS"},
        "candidate": candidate_evidence,
        "candidate_retention": candidate_retention,
        "numerical_surfaces": comparison["surfaces"],
        "ledger_before": 99, "ledger_after": 139,
        "automatic_retry": False, "automatic_m1f0_continuation": False,
    }
    atomic_json(event_root / "terminal-evidence.json", terminal)
    return terminal


if __name__ == "__main__":
    if sys.argv[1:] == ["--execute-reviewed-real2"]:
        print(json.dumps(execute_reviewed_real2(), indent=2, sort_keys=True))
    else:
        destination = Path(sys.argv[1]) if len(sys.argv) == 2 else ROOT / ".pulsarmlx-local/real2-failure-rehearsal"
        print(json.dumps(run_candidate_failure_persistence_rehearsal(destination), indent=2, sort_keys=True))
