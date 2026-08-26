#!/usr/bin/env python3
"""Independent mechanical design gates for the F017 V11 result envelope."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-binary-result-envelope-v11.json"
DAG = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-artifact-dag-v11.json"

EXPECTED_PAYLOADS = [
    ("PRIMARY", "final_hidden", "f64le", [6144], 8, 6144, 49152),
    ("PRIMARY", "final_normalized", "f64le", [6144], 8, 6144, 49152),
    ("PRIMARY", "full_logits", "f64le", [154880], 8, 154880, 1239040),
    ("SECONDARY", "final_hidden", "f32le", [6144], 4, 6144, 24576),
    ("SECONDARY", "final_normalized", "f32le", [6144], 4, 6144, 24576),
    ("SECONDARY", "full_logits", "f32le", [154880], 4, 154880, 619520),
]


def _load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if type(value) is not dict: raise ValueError("top-level contract")
    return value


def validate_contract(value: dict) -> None:
    required = {"schema", "generation", "status", "source_event", "geometry", "encoding", "payloads",
                "control_plane", "write_protocol", "read_protocol", "numerical_contract",
                "numerical_formulas_changed", "numerical_methodology_changed", "numerical_thresholds_changed", "original_checkpoint_access"}
    if type(value) is not dict or set(value) != required: raise ValueError("contract key census")
    if value["schema"] != "pulsarmlx.f017.corrected-oracle-binary-result-envelope/11.0.0" or value["generation"] != "V11": raise ValueError("contract identity")
    if value["status"] != "FROZEN_BEFORE_EVENT05_AUTHORIZATION": raise ValueError("contract status")
    if value["geometry"] != {"hidden_size":6144,"vocabulary_size":154880,"top_n":32}: raise ValueError("geometry")
    encoding = value["encoding"]
    expected_encoding = {"container":"RAW_CONTIGUOUS_IEEE754","endianness":"LITTLE","header":"NONE","padding":"NONE",
                         "embedded_path":False,"embedded_sha":False,"finite_values_only":True,
                         "signed_zero":"PRESERVE_IEEE754_BITS","byte_count_rule":"PRODUCT_SHAPE_TIMES_DTYPE_ITEMSIZE"}
    if encoding != expected_encoding: raise ValueError("encoding")
    if type(value["payloads"]) is not list or len(value["payloads"]) != 6: raise ValueError("payload census")
    keys = {"role","kind","dtype","shape","itemsize","element_count","byte_count"}
    for record, expected in zip(value["payloads"], EXPECTED_PAYLOADS, strict=True):
        if type(record) is not dict or set(record) != keys: raise ValueError("payload key census")
        observed = tuple(record[key] for key in ("role","kind","dtype","shape","itemsize","element_count","byte_count"))
        if observed != expected: raise ValueError("payload record")
        product = 1
        for dimension in record["shape"]:
            if type(dimension) is not int or type(dimension) is bool or dimension <= 0: raise ValueError("shape")
            product *= dimension
        if product != record["element_count"] or product * record["itemsize"] != record["byte_count"]: raise ValueError("derived bytes")
    control = value["control_plane"]
    if (control != {"full_numerical_arrays_in_json":"PROHIBITED","general_bounded_decoder_limits_changed":False,
                    "result_control_max_bytes":65536,"result_control_max_array_elements":64,"top_summary_elements":32}): raise ValueError("control separation")
    if value["numerical_formulas_changed"] is not False or value["numerical_methodology_changed"] is not False or value["numerical_thresholds_changed"] is not False or value["original_checkpoint_access"] != 0: raise ValueError("safety")
    expected_write = ["EXCLUSIVE_NO_REPLACE","DETERMINISTIC_CHUNK_ORDER","EXACT_BYTE_COUNTER","FILE_FSYNC","PARENT_DIRECTORY_FSYNC","DESCRIPTOR_RELATIVE_READBACK","SHA256_READBACK","IDENTITY_STABILITY"]
    expected_read = ["NO_FOLLOW","REGULAR_FILE","EXACT_KIND","EXACT_DTYPE","EXACT_ENDIAN","EXACT_SHAPE","EXACT_ELEMENT_COUNT","EXACT_BYTE_COUNT","SHA256","FINITE_VALUES"]
    if value["write_protocol"] != expected_write or value["read_protocol"] != expected_read:
        raise ValueError("I/O protocol")
    if value["numerical_contract"] != {"path":"specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v3.json","sha256":"84ff9ba061952e4aa9fe4fe2c76ac6cafa3f03eb74a37ac1056c2a44b5003cf9"}:
        raise ValueError("numerical contract")
    source = value["source_event"]
    if source != {"event":"EVENT_04","disposition":"IMMUTABLE_TRUTHFUL_TERMINAL_FAILURE","failure_node":"E6","failure_class":"ArtifactDecodeError","failure_message":"artifact bytes exceed bound","retroactive_closure":"PROHIBITED"}: raise ValueError("Event04 immutability")


def validate_dag(value: dict) -> None:
    keys = {"schema","generation","acyclic","self_references","future_references","primary_success_order",
            "secondary_success_order","comparison_order","package_terminal_required_closure","event04"}
    if type(value) is not dict or set(value) != keys: raise ValueError("DAG key census")
    if value["schema"] != "pulsarmlx.f017.corrected-oracle-result-artifact-dag/11.0.0" or value["generation"] != "V11": raise ValueError("DAG identity")
    if value["acyclic"] is not True or value["self_references"] != 0 or value["future_references"] != 0: raise ValueError("DAG acyclicity")
    primary = value["primary_success_order"]
    required_primary = ["PRIMARY_NUMERICAL_COMPUTATION_COMPLETE","PRIMARY_FINAL_HIDDEN_PAYLOAD","PRIMARY_FINAL_NORMALIZED_PAYLOAD",
        "PRIMARY_FULL_LOGITS_PAYLOAD","PRIMARY_PAYLOAD_READBACK_COMPLETE","PRIMARY_PAYLOAD_MANIFEST","PRIMARY_TOP32_SUMMARY",
        "PRIMARY_RESULT_RECEIPT","PRIMARY_RESULT_TERMINAL","PRIMARY_CONSUMER_TERMINAL","SECONDARY_ELIGIBLE"]
    if primary != required_primary: raise ValueError("primary causal order")
    secondary = value["secondary_success_order"]
    required_secondary = ["PRIMARY_CONSUMER_TERMINAL_VALIDATED","SECONDARY_DURABLE_START",
        "SECONDARY_NUMERICAL_COMPUTATION_COMPLETE","SECONDARY_FINAL_HIDDEN_PAYLOAD",
        "SECONDARY_FINAL_NORMALIZED_PAYLOAD","SECONDARY_FULL_LOGITS_PAYLOAD",
        "SECONDARY_PAYLOAD_READBACK_COMPLETE","SECONDARY_PAYLOAD_MANIFEST","SECONDARY_TOP32_SUMMARY",
        "SECONDARY_RESULT_RECEIPT","SECONDARY_RESULT_TERMINAL","SECONDARY_CONSUMER_TERMINAL"]
    if secondary != required_secondary: raise ValueError("secondary gate")
    comparison = value["comparison_order"]
    required_comparison = ["PRIMARY_CONSUMER_TERMINAL","SECONDARY_CONSUMER_TERMINAL",
        "BOTH_MANIFESTS_VALIDATED","ALL_SIX_PAYLOADS_VALIDATED","STRUCTURAL_ROUTING_VALIDATED",
        "STREAMING_NUMERICAL_COMPARISON","COMPARISON_SUMMARY","COMPARISON_RECEIPT",
        "COMPARISON_TERMINAL","DESCRIPTOR_RELEASE_START","DESCRIPTOR_RELEASE_REPORT",
        "DESCRIPTOR_RELEASE_RECEIPT","DESCRIPTOR_RELEASE_TERMINAL","PACKAGE_RECEIPT","PACKAGE_TERMINAL"]
    if comparison != required_comparison: raise ValueError("comparison order")
    closure = value["package_terminal_required_closure"]
    required_closure = ["PRIMARY_FINAL_HIDDEN_PAYLOAD","PRIMARY_FINAL_NORMALIZED_PAYLOAD","PRIMARY_FULL_LOGITS_PAYLOAD",
        "PRIMARY_PAYLOAD_MANIFEST","PRIMARY_TOP32_SUMMARY","PRIMARY_RESULT_RECEIPT","PRIMARY_RESULT_TERMINAL","PRIMARY_CONSUMER_TERMINAL",
        "SECONDARY_FINAL_HIDDEN_PAYLOAD","SECONDARY_FINAL_NORMALIZED_PAYLOAD","SECONDARY_FULL_LOGITS_PAYLOAD",
        "SECONDARY_PAYLOAD_MANIFEST","SECONDARY_TOP32_SUMMARY","SECONDARY_RESULT_RECEIPT","SECONDARY_RESULT_TERMINAL","SECONDARY_CONSUMER_TERMINAL",
        "COMPARISON_SUMMARY","COMPARISON_RECEIPT","COMPARISON_TERMINAL","DESCRIPTOR_RELEASE_START","DESCRIPTOR_RELEASE_REPORT",
        "DESCRIPTOR_RELEASE_RECEIPT","DESCRIPTOR_RELEASE_TERMINAL","PACKAGE_RECEIPT"]
    if closure != required_closure: raise ValueError("closure")
    # Derive the actual graph rather than trusting declarative counters.
    sequences = [primary, secondary, comparison]
    edges: set[tuple[str, str]] = set()
    nodes: set[str] = set()
    for sequence in sequences:
        if len(sequence) != len(set(sequence)): raise ValueError("self reference")
        nodes.update(sequence); edges.update(zip(sequence, sequence[1:]))
    edges.add(("SECONDARY_ELIGIBLE", "PRIMARY_CONSUMER_TERMINAL_VALIDATED"))
    if any(left == right for left, right in edges): raise ValueError("self reference")
    incoming = {node: 0 for node in nodes}
    outgoing = {node: [] for node in nodes}
    for left, right in edges:
        outgoing[left].append(right); incoming[right] += 1
    frontier = [node for node, count in incoming.items() if count == 0]; visited = 0
    while frontier:
        node = frontier.pop(); visited += 1
        for child in outgoing[node]:
            incoming[child] -= 1
            if incoming[child] == 0: frontier.append(child)
    if visited != len(nodes): raise ValueError("cyclic result graph")
    if not set(closure).issubset(nodes): raise ValueError("undefined closure node")
    if value["event04"] != {"diagnostic_reuse":"EXPLICIT_GRANT_ONLY","promotion":"PROHIBITED","primary_receipt_creation":"PROHIBITED","primary_terminal_creation":"PROHIBITED","comparison_creation":"PROHIBITED"}: raise ValueError("Event04 boundary")


def mutation_campaign(contract: dict, dag: dict) -> list[str]:
    rejected: list[str] = []
    for index in range(6):
        for field, replacement in (
            ("role", "OTHER"), ("kind", "other"), ("dtype", "f16le"), ("shape", [1]),
            ("itemsize", 16), ("element_count", 1), ("byte_count", 1),
        ):
            mutant = copy.deepcopy(contract); mutant["payloads"][index][field] = replacement
            try: validate_contract(mutant)
            except ValueError: rejected.append(f"GEOMETRY_{index}_{field}")
            else: raise AssertionError(f"mutation passed: {index} {field}")
        for field in ("role", "kind", "dtype", "shape", "itemsize", "element_count", "byte_count"):
            mutant = copy.deepcopy(contract); del mutant["payloads"][index][field]
            try: validate_contract(mutant)
            except ValueError: rejected.append(f"PAYLOAD_MISSING_{index}_{field}")
            else: raise AssertionError("missing field passed")
    global_mutations = [
        ("geometry", "hidden_size", 6145), ("geometry", "vocabulary_size", 154879), ("geometry", "top_n", 31),
        ("encoding", "endianness", "BIG"), ("encoding", "finite_values_only", False),
        ("encoding", "signed_zero", "NORMALIZE"), ("encoding", "header", "NATIVE"),
        ("control_plane", "full_numerical_arrays_in_json", "ALLOWED"),
        ("control_plane", "general_bounded_decoder_limits_changed", True),
        ("control_plane", "result_control_max_array_elements", 154880),
        ("source_event", "retroactive_closure", "ALLOWED"),
    ]
    for parent, field, replacement in global_mutations:
        mutant = copy.deepcopy(contract); mutant[parent][field] = replacement
        try: validate_contract(mutant)
        except ValueError: rejected.append(f"GLOBAL_{parent}_{field}")
        else: raise AssertionError("global mutation passed")
    for field in ("write_protocol", "read_protocol"):
        mutant = copy.deepcopy(contract); mutant[field] = mutant[field][:-1]
        try: validate_contract(mutant)
        except ValueError: rejected.append(f"PROTOCOL_{field}_REMOVED")
        else: raise AssertionError("protocol mutation passed")
        mutant = copy.deepcopy(contract); mutant[field][0], mutant[field][1] = mutant[field][1], mutant[field][0]
        try: validate_contract(mutant)
        except ValueError: rejected.append(f"PROTOCOL_{field}_ORDER")
        else: raise AssertionError("protocol order mutation passed")
    for field in ("path", "sha256"):
        mutant = copy.deepcopy(contract); mutant["numerical_contract"][field] = "0" * 64
        try: validate_contract(mutant)
        except ValueError: rejected.append(f"NUMERICAL_CONTRACT_{field}")
        else: raise AssertionError("numerical contract mutation passed")
    for sequence in ("primary_success_order", "secondary_success_order", "comparison_order"):
        for index in range(len(dag[sequence]) - 1):
            mutant = copy.deepcopy(dag); mutant[sequence][index], mutant[sequence][index+1] = mutant[sequence][index+1], mutant[sequence][index]
            try: validate_dag(mutant)
            except ValueError: rejected.append(f"ORDER_{sequence}_{index}")
            else: raise AssertionError("order mutation passed")
    for field, replacement in (("acyclic",False),("self_references",1),("future_references",1)):
        mutant = copy.deepcopy(dag); mutant[field] = replacement
        try: validate_dag(mutant)
        except ValueError: rejected.append(f"DAG_{field}")
        else: raise AssertionError("DAG mutation passed")
    for field in dag["event04"]:
        mutant = copy.deepcopy(dag); mutant["event04"][field] = "ALLOWED"
        try: validate_dag(mutant)
        except ValueError: rejected.append(f"EVENT04_{field}")
        else: raise AssertionError("Event04 mutation passed")
    for index in range(len(dag["package_terminal_required_closure"])):
        mutant = copy.deepcopy(dag); del mutant["package_terminal_required_closure"][index]
        try: validate_dag(mutant)
        except ValueError: rejected.append(f"CLOSURE_MISSING_{index}")
        else: raise AssertionError("closure omission passed")
    return rejected


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); contract = _load(CONTRACT); dag = _load(DAG)
    validate_contract(contract); validate_dag(dag); rejected = mutation_campaign(contract, dag)
    result = {"schema":"pulsarmlx.f017.event05-result-envelope-design-qualification/1.0.0",
              "contract_sha256":hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),
              "dag_sha256":hashlib.sha256(DAG.read_bytes()).hexdigest(),
              "result_geometry_reconstructed":"PASS","primary_payload_bytes_derived":"PASS",
              "secondary_payload_bytes_derived":"PASS","control_json_full_logits_fields":0,
              "binary_format_canonical":"PASS","finite_value_policy":"PASS","signed_zero_policy":"PASS",
              "payload_dag_acyclic":"PASS","self_references":0,"future_references":0,
              "package_terminal_transitive_closure":"PASS","event04_retroactive_closure_mutations_rejected":"ALL",
              "design_mutations_rejected":len(rejected),"mutation_ids":rejected,
              "unexpected_mutation_passes":0,"original_checkpoint_access":0,"result":"PASS"}
    raw = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(raw)
    else: print(raw, end="")
    return 0


if __name__ == "__main__": raise SystemExit(main())
