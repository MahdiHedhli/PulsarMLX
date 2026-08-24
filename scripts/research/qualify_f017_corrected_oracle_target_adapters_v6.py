#!/usr/bin/env python3
"""File-backed synthetic qualification of both v6 target adapters."""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts/research"
sys.path.insert(0, str(RESEARCH))

import f017_corrected_oracle_primary_numerics_v2 as primary_numerical
import f017_corrected_oracle_secondary_numerics_v2 as secondary_numerical
from f017_corrected_oracle_authorization_v6 import canonical_bytes, sha256_path
from validate_f017_corrected_oracle_access_v6 import construct_candidate_from_inert, install_candidate, render_candidate, validate_candidate
from generate_f017_corrected_oracle_fixtures import fixture

ZERO = "0" * 64
INTERFACE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v6.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bank(path: Path, value: dict) -> None:
    path.write_bytes(canonical_bytes(value))


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", float(value)))[0]


def tensor_shape(name: str, values: list[float], geometry: dict) -> tuple[int, int, bool]:
    h = geometry["hidden"]
    if name.endswith(".bias") or name.endswith("_norm.weight") or name == "output_norm.weight":
        return 1, len(values), True
    if name == "token_embd.weight": return geometry["vocab"], h, False
    if name == "output.weight": return geometry["vocab"], h, False
    if "attn_q_a.weight" in name: return geometry["q_rank"], h, False
    if "attn_q_b.weight" in name: return geometry["heads"] * (geometry["qk_nope"] + geometry["qk_rope"]), geometry["q_rank"], False
    if "attn_kv_a_mqa.weight" in name: return geometry["kv_rank"] + geometry["qk_rope"], h, False
    if "attn_k_b.weight" in name: return geometry["kv_rank"], geometry["qk_nope"], False
    if "attn_v_b.weight" in name: return geometry["value_dim"], geometry["kv_rank"], False
    if "attn_output.weight" in name: return h, geometry["heads"] * geometry["value_dim"], False
    if "ffn_gate_inp.weight" in name: return geometry["experts"], h, False
    if "_gate" in name or "_up" in name:
        rows = geometry["dense_ffn"] if "_exps." not in name and "_shexp." not in name else geometry["expert_ffn"]
        return rows, h, False
    if "_down" in name:
        columns = geometry["dense_ffn"] if "_exps." not in name and "_shexp." not in name else geometry["expert_ffn"]
        return h, columns, False
    raise ValueError(f"unclassified tensor: {name}")


def checkpoint(work: Path, document: dict) -> tuple[Path, Path, Path, list[dict], dict]:
    root = work / "checkpoint"; root.mkdir()
    names = [f"synthetic-{index:05}-of-00006.gguf" for index in range(1, 7)]
    payloads = {name: bytearray() for name in names}
    grouped: dict[str, list[tuple[int, list[float]]]] = {}
    plain: list[tuple[str, list[float]]] = []
    for name, values in document["tensors"].items():
        if "#" in name:
            base, ordinal = name.rsplit("#", 1); grouped.setdefault(base, []).append((int(ordinal), values))
        else:
            plain.append((name, values))
    records = []
    decoded = {}
    entries: list[tuple[str, list[float], int | None]] = [(name, values, None) for name, values in plain]
    for base, experts in grouped.items():
        entries.append((base, [value for _, values in sorted(experts) for value in values], len(experts)))
        for ordinal, values in experts: decoded[f"{base}#{ordinal}"] = [f32(v) for v in values]
    for ordinal, (name, values, experts) in enumerate(sorted(entries)):
        shard = names[1 + ordinal % 5]
        offset = len(payloads[shard])
        payloads[shard].extend(b"".join(struct.pack("<f", f32(value)) for value in values))
        sample = document["tensors"].get(name) or document["tensors"][f"{name}#0"]
        rows, columns, vector = tensor_shape(name, sample, document["geometry"])
        dims = [columns] if vector else [columns, rows] + ([experts] if experts is not None else [])
        records.append({"name": name, "type": "F32", "dims": dims, "file": shard, "data_offset_abs": offset})
        if experts is None: decoded[name] = [f32(v) for v in values]
    shards = []
    for index, name in enumerate(names):
        path = root / name; path.write_bytes(payloads[name])
        shards.append({"filename": name, "size_bytes": path.stat().st_size, "sha256": sha(path), "access_role": "IDENTITY_ONLY" if index == 0 else "GRAPH_PAYLOAD"})
    catalog = work / "catalog.json"; bank(catalog, {"schema": "synthetic-catalog/1", "tensors": records})
    geometry = work / "geometry.json"; bank(geometry, document["geometry"])
    identity = work / "identity.json"
    return root, catalog, geometry, shards, decoded


def grant(role: str, event: str, wrapper: Path, capability_path: Path, target: Path, numerical: Path, decoder: Path, prefix: str, work: Path) -> dict:
    return {
        "event_id": event, "durable_start_id": f"{prefix}-START", "ledger_entry_id": f"{prefix}-LEDGER",
        "ledger_index_id": f"{prefix}-INDEX", "receipt_id": f"{prefix}-RECEIPT", "terminal_id": f"{prefix}-TERMINAL",
        "role": role, "producer_path": wrapper.relative_to(ROOT).as_posix(), "producer_sha256": sha(wrapper),
        "capability_path": str(capability_path), "capability_sha256": sha(capability_path),
        "target_source_path": target.relative_to(ROOT).as_posix(), "target_source_sha256": sha(target),
        "numerical_path": numerical.relative_to(ROOT).as_posix(), "numerical_sha256": sha(numerical),
        "decoder_path": decoder.relative_to(ROOT).as_posix(), "decoder_sha256": sha(decoder),
        "state_root": str(work / "package-state" / prefix.lower()),
        "output_root": str(work / "package-output" / prefix.lower()),
        "attempts": 1, "retries": 0, "resume": False,
        "accounting_class": f"CORRECTED_ORACLE_{prefix}_EVENT_LEDGER",
        "receipt_schema": "pulsarmlx.f017.corrected-oracle-consumer-receipt/6.0.0",
        "terminal_schema": "pulsarmlx.f017.corrected-oracle-consumer-terminal/6.0.0",
    }


def run_once(work: Path, seed: int) -> dict:
    document = fixture(seed)
    root, catalog, geometry, shards, decoded = checkpoint(work, document)
    synthetic_interface = work / "interface.json"
    interface = json.loads(INTERFACE.read_text()); interface["interface_scope"] = "SYNTHETIC_QUALIFICATION"
    interface["pinned_values"] = {
        **interface["pinned_values"],
        "authority_scope": "SYNTHETIC_QUALIFICATION",
        "prompt_token": document["token"],
        "position": document["position"],
    }
    interface["pinned_context"] = {**interface["pinned_context"], "prompt_token": document["token"], "position": document["position"]}
    interface["pinned_limits"] = {**interface["pinned_limits"], "graph_tensor_count": len(json.loads(catalog.read_text())["tensors"]), "non_access_tensor_count": 0}
    interface["pinned_values"] = {
        **interface["pinned_values"],
        "graph_tensor_count": interface["pinned_limits"]["graph_tensor_count"],
        "non_access_tensor_count": 0,
    }
    bank(synthetic_interface, interface)
    installed = work / "authorization.json"
    candidate = work / "candidate.json"
    primary_wrapper = RESEARCH / "f017_corrected_oracle_primary_v6.py"
    secondary_wrapper = RESEARCH / "f017_corrected_oracle_secondary_v6.py"
    primary_target = RESEARCH / "f017_corrected_oracle_primary_target_source_v6.py"
    secondary_target = RESEARCH / "f017_corrected_oracle_secondary_target_source_v6.py"
    primary_core = RESEARCH / "f017_corrected_oracle_primary_numerics_v2.py"
    secondary_core = RESEARCH / "f017_corrected_oracle_secondary_numerics_v2.py"
    primary_decoder = RESEARCH / "f017_oracle_primary_decoders.py"
    secondary_decoder = RESEARCH / "qualify_f017_quantization_matrix_v1.py"
    primary_capability = work / "primary-capability.json"
    secondary_capability = work / "secondary-capability.json"
    subprocess.run([sys.executable, str(primary_wrapper), "capability", str(synthetic_interface), str(primary_capability)], check=True, cwd=ROOT)
    subprocess.run([sys.executable, str(secondary_wrapper), "capability", str(synthetic_interface), str(secondary_capability)], check=True, cwd=ROOT)
    measurement = work / "measurement.json"; bank(measurement, {"schema": "synthetic-measurement/1", "authority": False})
    checkpoint_manifest = work / "checkpoint-manifest.json"; bank(checkpoint_manifest, {"schema": "synthetic-checkpoint-manifest/1", "shards": shards})
    authority_paths = {
        "implementation_measurement_manifest_path": str(measurement),
        "authorization_interface_path": str(synthetic_interface),
        "scientific_access_contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v6.json",
        "event_accounting_contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event-accounting-v6.json",
        "path_timing_contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-path-timing-v6.json",
        "canonical_serialization_contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-canonical-json-bytes-v6.json",
        "lifecycle_semantic_model_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v6.json",
        "numerical_contract_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json",
        "numerical_capability_policy_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-numerical-capability-policy-v1.json",
        "numerical_requalification_path": "docs/architecture/reviews/evidence/f017-corrected-oracle-numerical-requalification-v3.json",
        "numerical_methodology_path": "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v1.json",
        "checkpoint_manifest_path": str(checkpoint_manifest),
        "checkpoint_catalog_path": str(catalog),
    }
    limits = interface["pinned_limits"]
    auth = {
        "schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/6.0.0",
        "authority_generation": 6, "state": "AUTHORIZED", "live": True, "authority_scope": "SYNTHETIC_QUALIFICATION",
        "authorization_id": "F017-QUALIFICATION-AUTH-06", "operator_approval_id": "F017-QUALIFICATION-APPROVAL-06",
        "operator_approval_sha256": ZERO, "package_attempt_id": "F017-QUALIFICATION-PACKAGE-06",
        "primary_event_id": "F017-QUALIFICATION-PRIMARY-06", "secondary_event_id": "F017-QUALIFICATION-SECONDARY-06",
        "preflight_report_id": "F017-QUALIFICATION-PREFLIGHT-06", "primary_candidate_validation_report_id": "F017-QUALIFICATION-PCV-06",
        "secondary_candidate_validation_report_id": "F017-QUALIFICATION-SCV-06", "installation_receipt_id": "F017-QUALIFICATION-INSTALL-06",
        "primary_installed_validation_report_id": "F017-QUALIFICATION-PIV-06", "secondary_installed_validation_report_id": "F017-QUALIFICATION-SIV-06",
        "coordinator_handshake_id": "F017-QUALIFICATION-HANDSHAKE-06", "comparison_receipt_id": "F017-QUALIFICATION-COMPARE-RECEIPT-06",
        "comparison_terminal_id": "F017-QUALIFICATION-COMPARE-TERMINAL-06", "branch": "CHECKPOINT-FREE-QUALIFICATION",
        "implementation_measurement_head": "84f0d1dc3e60a4151329ed82773880951ee3e618",
        **authority_paths,
        "implementation_measurement_manifest_sha256": sha(measurement),
        "authorization_interface_sha256": sha(synthetic_interface),
        "scientific_access_contract_sha256": sha(ROOT / authority_paths["scientific_access_contract_path"]),
        "event_accounting_contract_sha256": sha(ROOT / authority_paths["event_accounting_contract_path"]),
        "path_timing_contract_sha256": sha(ROOT / authority_paths["path_timing_contract_path"]),
        "canonical_serialization_contract_sha256": sha(ROOT / authority_paths["canonical_serialization_contract_path"]),
        "lifecycle_semantic_model_sha256": sha(ROOT / authority_paths["lifecycle_semantic_model_path"]),
        "numerical_contract_sha256": "84ff9ba061952e4aa9fe4fe2c76ac6cafa3f03eb74a37ac1056c2a44b5003cf9",
        "numerical_capability_policy_sha256": "5ca6576781e269c18671b834b5d115494ec95462a17a59045e930eb256ce4d13",
        "numerical_requalification_sha256": "5a0257803d7af03f091c0dfc438be0727dc567b465c82a8dfcdf83f847e80c49",
        "numerical_methodology_sha256": sha(ROOT / authority_paths["numerical_methodology_path"]), "checkpoint_manifest_sha256": sha(checkpoint_manifest),
        "checkpoint_catalog_sha256": sha(catalog), "checkpoint_set_sha256": ZERO, "historical_ledger_sha256": "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e",
        "historical_ledger_terminal": 175, "historical_ledger_delta": 0, "memory_preflight_sha256": ZERO,
        "memory_observed_at_unix_ns": 1, "memory_sample_max_age_ns": 1, "checkpoint_catalog_path": str(catalog),
        "geometry_path": str(geometry), "geometry_sha256": sha(geometry), "shards": shards, "checkpoint_root": str(root.resolve()),
        "canonical_install_path": str(installed.resolve()),
        "package": {"claim_id": "F017-QUALIFICATION-CLAIM-06", "durable_start_id": "F017-QUALIFICATION-PACKAGE-START-06",
                    "ledger_entry_id": "F017-QUALIFICATION-PACKAGE-LEDGER-06", "ledger_index_id": "F017-QUALIFICATION-PACKAGE-INDEX-06",
                    "receipt_id": "F017-QUALIFICATION-PACKAGE-RECEIPT-06", "terminal_id": "F017-QUALIFICATION-PACKAGE-TERMINAL-06",
                    "state_root": str(work/"package-state"), "output_root": str(work/"package-output"), "attempts": 1, "retries": 0,
                    "resume": False, "accounting_class": "CORRECTED_ORACLE_PACKAGE_ATTEMPT_LEDGER", "receipt_schema": "pulsarmlx.f017.corrected-oracle-package-receipt/6.0.0",
                    "terminal_schema": "pulsarmlx.f017.corrected-oracle-package-terminal/6.0.0"},
        "primary": grant("INDEPENDENT_CPU_REFERENCE", "F017-QUALIFICATION-PRIMARY-06", primary_wrapper, primary_capability, primary_target, primary_core, primary_decoder, "PRIMARY", work),
        "secondary": grant("INDEPENDENT_ACCELERATED_CROSS_CHECK", "F017-QUALIFICATION-SECONDARY-06", secondary_wrapper, secondary_capability, secondary_target, secondary_core, secondary_decoder, "SECONDARY", work),
        "context": interface["pinned_context"], "limits": limits,
    }
    auth = construct_candidate_from_inert({key: value for key, value in auth.items() if key not in {"schema", "authority_generation"}})
    render_candidate(auth, candidate)
    report_root = work / "candidate-reports"; report_root.mkdir()
    handshake = validate_candidate(candidate, synthetic_interface, root, report_root)
    reports = [handshake["primary"]["sha256"], handshake["secondary"]["sha256"]]
    receipt = work / "installation-receipt.json"
    install_candidate(candidate, installed, receipt, handshake, operator_approval_sha256=ZERO, allow_synthetic=True)
    identity = work / "identity.json"; bank(identity, {"authorization_id": auth["authorization_id"], "result": "PASS", "shards": shards})
    outputs = {}
    for role, wrapper in (("primary", primary_wrapper), ("secondary", secondary_wrapper)):
        output = work / f"{role}-result.json"; events = work / f"{role}-events"
        command = [sys.executable, str(wrapper), "target", str(installed), str(synthetic_interface), str(root), str(output), str(receipt), str(catalog), str(geometry), str(identity), str(events)]
        if role == "secondary": command += ["--backend", "numpy"]
        subprocess.run(command, check=True, cwd=ROOT)
        outputs[role] = json.loads(output.read_text())
    decoded_document = {**document, "tensors": decoded}
    expected_primary = primary_numerical.execute(primary_numerical.JsonSource(decoded), primary_numerical.Geometry.from_json(document["geometry"]), document["token"], document["position"])
    expected_primary.pop("result_sha256", None)
    expected_secondary = secondary_numerical.execute(decoded_document, False)
    expected_primary = json.loads(canonical_bytes(expected_primary))
    expected_secondary = json.loads(canonical_bytes(expected_secondary))
    if outputs["primary"] != expected_primary or outputs["secondary"] != expected_secondary:
        primary_drift = sorted(key for key in set(outputs["primary"]) | set(expected_primary) if outputs["primary"].get(key) != expected_primary.get(key))
        secondary_drift = sorted(key for key in set(outputs["secondary"]) | set(expected_secondary) if outputs["secondary"].get(key) != expected_secondary.get(key))
        first_layer = next((index for index, (left, right) in enumerate(zip(outputs["primary"]["layers"], expected_primary["layers"], strict=True)) if left != right), None)
        raise ValueError(f"target adapter numerical equivalence: primary={primary_drift}; secondary={secondary_drift}; first_primary_layer={first_layer}; observed={outputs['primary']['layers'][first_layer] if first_layer is not None else None}; expected={expected_primary['layers'][first_layer] if first_layer is not None else None}")
    return {"candidate_validation_reports": reports, "candidate_installed_byte_identity": candidate.read_bytes() == installed.read_bytes(),
            "process_census": {"candidate_validation": len(reports), "primary_target": 1, "secondary_target": 1},
            "primary_result_sha256": sha(work/"primary-result.json"), "secondary_result_sha256": sha(work/"secondary-result.json"),
            "primary_access_events": len(list((work/"primary-events").glob("*.json"))),
            "secondary_access_events": len(list((work/"secondary-events").glob("*.json"))),
            "original_checkpoint_access": 0, "result": "PASS"}


def main() -> int:
    parser = __import__("argparse").ArgumentParser(); parser.add_argument("--output", type=Path); parser.add_argument("--repeats", type=int, default=1)
    arguments = parser.parse_args(); results = []
    with tempfile.TemporaryDirectory(prefix="f017-v6-target-") as temporary:
        root = Path(temporary)
        for index in range(arguments.repeats):
            work = root / f"run-{index:02}"; work.mkdir(); results.append(run_once(work, 18101 + index % 12))
    summary = {"schema": "pulsarmlx.f017.corrected-oracle-target-adapter-qualification/6.0.0", "result": "PASS",
               "repeat_count": arguments.repeats, "runs": results, "original_checkpoint_shard_opens": 0, "original_checkpoint_payload_reads": 0}
    if arguments.output: arguments.output.write_bytes(canonical_bytes(summary))
    print(json.dumps({"result": "PASS", "repeats": arguments.repeats}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
