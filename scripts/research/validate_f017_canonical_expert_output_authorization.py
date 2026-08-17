#!/usr/bin/env python3
"""Validate the checkpoint-free F017 canonical expert-output authorization.

This validator is metadata-only.  It has no checkpoint path resolver, shard
reader, decoder, expert implementation, or real-payload ledger writer.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


CONTRACT_PATH = Path(
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-canonical-expert-output-recovery-v1.json"
)
SCHEMA_PATH = Path(
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-canonical-expert-output-recovery-v1.schema.json"
)
EVIDENCE_PATH = Path(
    "docs/architecture/reviews/evidence/"
    "f017-canonical-expert-output-recovery-authorization-v1.json"
)
CATALOG_PATH = Path("docs/research/glm52/raw/f016-c01-catalog-0001.json")
LEDGER_PATH = Path(
    "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
)
EXACT_DESCRIPTOR_PATH = Path(
    "docs/architecture/reviews/evidence/f017-dprefix-exact1-descriptor-v1.json"
)
ROUTE_EVIDENCE_PATH = Path(
    "docs/architecture/reviews/evidence/"
    "f017-dprefix-route-ambiguity-v31-evaluation-v1.json"
)
PRIVATE_REUSE_PATH = Path(
    "docs/architecture/reviews/evidence/"
    "f017-v2-antecedent-private-reuse-authorization-v1.json"
)
EXPERT_166_CROSSCHECK_PATH = Path(
    "docs/architecture/reviews/evidence/"
    "f017-expert-166-catalog-slice-crosscheck-v2.json"
)
REVIEW_PACKET_PATH = Path(
    "docs/architecture/reviews/"
    "f017-canonical-expert-output-recovery-authorization-packet.md"
)
VALIDATOR_PATH = Path(
    "scripts/research/validate_f017_canonical_expert_output_authorization.py"
)
TEST_PATH = Path(
    "scripts/research/tests/"
    "test_validate_f017_canonical_expert_output_authorization.py"
)

START_HEAD = "81e187a1ce272386041e2d6445786ba14d07f91c"
EVENT_ID = "F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1"
SELECTED_IDS = [250, 10, 237, 73, 62, 177, 218, 28]
CHECKPOINT_SHA = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"
PRODUCTION_CATALOG_SHA = "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0"
PUBLIC_CATALOG_SHA = "135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19"
EXPERT_166_CROSSCHECK_SHA = "5cc9845291ce57741a406c5d1b2417c6d3dbe93b85c3139ef16faf10053d5cec"
SHARD_BASENAME = "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf"
SHARD_SHA = "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36"
SHARD_BYTES = 49_105_028_960
EXACT_STATE_SHA = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
EXACT_PRIVATE_MANIFEST_SHA = "a68316207957bc8f804c167b627c208f068d086aed85506c89d87569b992bc60"
FFN_NORM_SHA = "1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f"
NORMALIZED_F64_DIAGNOSTIC_SHA = "5e9352135d9fb025cbdfd680629534dce98aaebb1fa5b8e42432638de174e5fc"
DECODER_CONTRACT_SHA = "9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84"
AGGREGATE_CONTRACT_SHA = "ff1a15c29b79681458d74452c8c72dde9c9bf5eb44637d05a7e4ea9eb1525fac"
AMENDMENT_START_HEAD = "609be74d9a8af5bd412b1fd6f7d36025ce4a9b51"
RUST_DECODER_SHA = "c1606b39afff3a56334c8f56358c711dcbcb5f2df904d4e86612fd2a09b19161"
IQ2_PYTHON_DECODER_SHA = "9de6b59ce7fa3633e9fc521100badf4f5da2dd37bde037be88e8022904615761"
IQ3_SPEC_DECODER_SHA = "10b2c1eeda4d2955fbc61df659d28a4b2c1b72eb2d730145e74bbad86b347621"


class AuthorizationValidationError(ValueError):
    """The prepared authorization is not exact or fail-closed."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuthorizationValidationError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except AuthorizationValidationError:
        raise
    except Exception as error:  # pragma: no cover - error text is platform-specific
        raise AuthorizationValidationError(f"invalid JSON: {path}") from error
    if not isinstance(value, dict):
        raise AuthorizationValidationError(f"top-level JSON object required: {path}")
    return value


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuthorizationValidationError(message)


def _safe_symbolic_path(value: str) -> bool:
    path = PurePosixPath(value)
    private_home_marker = "/" + "Users/"
    return bool(value) and not path.is_absolute() and ".." not in path.parts and private_home_marker not in value


def derive_inventory(root: Path) -> list[dict[str, Any]]:
    catalog_path = root / CATALOG_PATH
    require(sha256_path(catalog_path) == PUBLIC_CATALOG_SHA, "public catalog identity")
    catalog = load_json(catalog_path)
    roles = {
        "gate": {
            "parent": "blk.3.ffn_gate_exps.weight",
            "quantization": "IQ2_XXS",
            "logical_shape": [2048, 6144],
            "packed_length": 3_244_032,
            "packed_row_width": 1_584,
            "decoded_f32_bytes": 50_331_648,
        },
        "up": {
            "parent": "blk.3.ffn_up_exps.weight",
            "quantization": "IQ2_XXS",
            "logical_shape": [2048, 6144],
            "packed_length": 3_244_032,
            "packed_row_width": 1_584,
            "decoded_f32_bytes": 50_331_648,
        },
        "down": {
            "parent": "blk.3.ffn_down_exps.weight",
            "quantization": "IQ3_XXS",
            "logical_shape": [6144, 2048],
            "packed_length": 4_816_896,
            "packed_row_width": 784,
            "decoded_f32_bytes": 50_331_648,
        },
    }
    parents = {
        item["name"]: item
        for item in catalog["tensors"]
        if item["name"] in {role["parent"] for role in roles.values()}
    }
    require(len(parents) == 3, "catalog parent tensor inventory")
    crosscheck_path = root / EXPERT_166_CROSSCHECK_PATH
    require(sha256_path(crosscheck_path) == EXPERT_166_CROSSCHECK_SHA, "expert-166 crosscheck identity")
    crosscheck = load_json(crosscheck_path)
    require(crosscheck.get("result") == "PASS" and crosscheck.get("checkpoint_payload_access") == 0, "expert-166 crosscheck result")
    for role_name, role in roles.items():
        parent = parents[role["parent"]]
        projection = crosscheck["projections"][role_name]
        require(projection["aggregate_name"] == role["parent"], "expert-166 crosscheck parent")
        require(projection["aggregate_base"] == parent["data_offset_abs"], "expert-166 crosscheck base")
        require(projection["aggregate_dims"] == parent["dims"], "expert-166 crosscheck shape")
        require(projection["quantization"] == role["quantization"], "expert-166 crosscheck quantization")
        require(projection["stride"] == role["packed_length"] and projection["equal"] is True, "expert-166 crosscheck stride")
    inventory: list[dict[str, Any]] = []
    ordinal = 0
    for expert_id in SELECTED_IDS:
        for role_name in ("gate", "up", "down"):
            role = roles[role_name]
            parent = parents[role["parent"]]
            require(parent["file"] == SHARD_BASENAME, "catalog shard identity")
            descriptor = {
                "ordinal": ordinal,
                "positional_payload_index": ordinal,
                "expert_id": expert_id,
                "role": role_name,
                "checkpoint_key": f"{role['parent']}#{expert_id}",
                "parent_tensor": role["parent"],
                "shard_ordinal": 2,
                "shard_basename": SHARD_BASENAME,
                "offset": parent["data_offset_abs"] + expert_id * role["packed_length"],
                "packed_length": role["packed_length"],
                "packed_row_width": role["packed_row_width"],
                "quantization": role["quantization"],
                "gguf_shape": parent["dims"],
                "logical_decoded_shape": role["logical_shape"],
                "decoded_f32_bytes": role["decoded_f32_bytes"],
                "allowed_read_count": 1,
                "expected_packed_sha256": None,
                "packed_identity_policy": "FIRST_OBSERVATION_BANK_AND_REHASH",
            }
            descriptor["metadata_identity_sha256"] = canonical_sha256(descriptor)
            inventory.append(descriptor)
            ordinal += 1
    return inventory


def expected_outputs() -> list[dict[str, Any]]:
    return [
        {
            "expert_id": expert_id,
            "symbolic_path": f"expert_outputs/expert_{expert_id}_down_output.bin",
            "shape": [6144],
            "dtype": "f32",
            "serialization": "canonical_little_endian_ieee754_binary32",
            "count": 6144,
            "byte_length": 24_576,
            "sha256_policy": "GENERATE_THEN_BANK_AND_REHASH",
        }
        for expert_id in SELECTED_IDS
    ]


def _validate_file_bindings(root: Path, items: Any, label: str) -> None:
    require(isinstance(items, list) and items, label)
    for item in items:
        path_value = item.get("path")
        require(isinstance(path_value, str) and _safe_symbolic_path(path_value), f"{label} path")
        require(sha256_path(root / path_value) == item.get("sha256"), label)


def validate_documents(root: Path, contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    require(contract.get("schema") == "pulsarmlx.f017.canonical-expert-output-recovery-contract", "contract schema")
    require(contract.get("schema_version") == "1.0.0", "contract version")
    require(contract.get("event_id") == EVENT_ID, "event identity")
    require(contract.get("status") == "PREPARED_NOT_AUTHORIZED_NOT_EXECUTED", "contract status")
    require(contract.get("starting_head") == START_HEAD, "starting head")
    require(contract.get("selected_expert_ids") == SELECTED_IDS and len(set(SELECTED_IDS)) == 8, "selected expert identity")
    require(contract.get("aggregate_theorem_sha256") == AGGREGATE_CONTRACT_SHA, "aggregate theorem identity")
    _validate_file_bindings(root, contract.get("source_bindings"), "contract source binding")

    expected_inventory = derive_inventory(root)
    require(contract.get("payload_inventory") == expected_inventory, "payload inventory")
    require(len(expected_inventory) == 24, "payload inventory count")
    require(sum(item["packed_length"] for item in expected_inventory) == 90_439_680, "packed-byte budget")
    require(len({item["checkpoint_key"] for item in expected_inventory}) == 24, "payload key uniqueness")

    budget = contract.get("access_budget", {})
    require(budget == {
        "tensor_payloads": 24,
        "positional_reads": 24,
        "packed_bytes": 90_439_680,
        "decoded_f32_bytes": 1_207_959_552,
        "shard_opens": 1,
    }, "access budget")
    shard = contract.get("shard_access", {})
    require(shard.get("checkpoint_set_sha256") == CHECKPOINT_SHA, "shard checkpoint identity")
    require(shard.get("production_catalog_sha256") == PRODUCTION_CATALOG_SHA, "production catalog identity")
    require(shard.get("shard_sha256") == SHARD_SHA and shard.get("shard_bytes") == SHARD_BYTES, "shard identity")
    require(shard.get("shard_ordinal") == 2 and shard.get("maximum_opens") == 1, "shard access budget")
    require(_safe_symbolic_path(shard.get("symbolic_private_path", "")), "private path policy")
    require(shard.get("regular_file_required") is True and shard.get("symlink_forbidden") is True, "shard object policy")

    canonical = contract.get("canonical_input", {})
    require(canonical.get("source_artifact_id") == "DPREFIX-EXACT-1", "canonical input authority")
    require(canonical.get("content_sha256") == EXACT_STATE_SHA, "canonical input identity")
    require(canonical.get("private_manifest_sha256") == EXACT_PRIVATE_MANIFEST_SHA, "canonical input manifest")
    require(canonical.get("shape") == [6144] and canonical.get("dtype") == "f32" and canonical.get("byte_length") == 24_576, "canonical input shape")
    require(canonical.get("ffn_norm_weight_sha256") == FFN_NORM_SHA, "canonical norm identity")
    require(canonical.get("checkpoint_reread_required") is False, "canonical input checkpoint policy")
    require(canonical.get("normalized_f64_route_diagnostic_sha256") == NORMALIZED_F64_DIAGNOSTIC_SHA, "normalized diagnostic identity")
    exact_descriptor = load_json(root / EXACT_DESCRIPTOR_PATH)
    require(exact_descriptor["layer3"]["sha256"] == EXACT_STATE_SHA, "exact descriptor authority")
    route = load_json(root / ROUTE_EVIDENCE_PATH)
    require(route["evaluation"]["exact_route"]["selected_top8"] == SELECTED_IDS, "canonical route identity")
    require(route["evaluation"]["exact_route"]["normalized_state_sha256_lef64"] == NORMALIZED_F64_DIAGNOSTIC_SHA, "route normalized identity")
    reuse = load_json(root / PRIVATE_REUSE_PATH)
    norm = next(item for item in reuse["package"]["artifacts"] if item["symbolic_name"] == "antecedents/ffn_norm_weight.bin")
    require(norm["expected_sha256"] == FFN_NORM_SHA and norm["byte_length"] == 24_576, "norm reuse identity")

    semantics = contract.get("computation_semantics", {})
    require(semantics.get("rmsnorm_epsilon_binary32") == 9.999999747378752e-06, "RMSNorm epsilon")
    require(semantics.get("activation") == "SiLU(gate)*up", "activation semantics")
    require(semantics.get("matrix_orientation") == "row_major_[out,in]_times_[in]", "matrix orientation")
    require(semantics.get("accumulation") == "strict_increasing_column_f32_multiply_then_f32_add", "accumulation semantics")
    require(semantics.get("intermediate_dtype") == "f32" and semantics.get("output_dtype") == "f32", "computation dtype")
    require(semantics.get("decoder_contract_sha256") == DECODER_CONTRACT_SHA, "decoder identity")

    expected_implementations = {
        "IQ2_XXS": {
            "decoder_a": {
                "classification": "ACCEPTED_RUST_CORRECTED_KQUANTS_LINEAGE",
                "source_file": "crates/quant/src/iq_ref.rs",
                "source_sha256": RUST_DECODER_SHA,
                "symbol": "decode_iq2_xxs_matrix",
            },
            "decoder_b": {
                "classification": "INDEPENDENT_PYTHON_SPECIFICATION_TRANSCRIPTION",
                "source_file": "scripts/research/iq2_xxs_dequant.py",
                "source_sha256": IQ2_PYTHON_DECODER_SHA,
                "symbol": "dequantize_matrix_iq2_xxs",
            },
        },
        "IQ3_XXS": {
            "decoder_a": {
                "classification": "ACCEPTED_RUST_M1E_CORRECTED_KQUANTS_LINEAGE",
                "source_file": "crates/quant/src/iq_ref.rs",
                "source_sha256": RUST_DECODER_SHA,
                "symbol": "decode_iq3_xxs_matrix",
            },
            "decoder_b": {
                "classification": "INDEPENDENT_PYTHON_SPECIFICATION_TRANSCRIPTION",
                "source_file": "scripts/research/iq3_xxs_spec_decoder.py",
                "source_sha256": IQ3_SPEC_DECODER_SHA,
                "symbol": "decode_iq3_xxs_spec",
            },
        },
    }
    dual = contract.get("dual_decoder_gate", {})
    require(dual.get("accepted_lineage_contract_sha256") == DECODER_CONTRACT_SHA, "dual decoder lineage")
    require(dual.get("required_payload_count") == 24, "dual decoder payload count")
    require(dual.get("same_retained_packed_bytes_required") is True, "dual decoder packed-byte identity")
    require(dual.get("additional_checkpoint_reads") == 0, "dual decoder checkpoint budget")
    require(dual.get("comparison_rule") == "canonical_f32le_sha256_exact_equality", "dual decoder comparison")
    require(dual.get("decoded_dtype") == "f32", "dual decoder dtype")
    require(dual.get("decoded_serialization") == "row_major_ieee754_binary32_little_endian_no_padding_preserve_signed_zero", "dual decoder serialization")
    require(dual.get("implementations") == expected_implementations, "dual decoder implementations")
    require(all(
        pair["decoder_a"]["source_file"] != pair["decoder_b"]["source_file"]
        for pair in expected_implementations.values()
    ), "dual decoder independence")
    require(dual.get("independence_required") is True, "dual decoder independence")
    require(dual.get("must_complete_before_next_checkpoint_read") is True, "dual decoder ordering")
    require(dual.get("must_complete_before_expert_compute") is True, "dual decoder ordering")
    require(dual.get("disagreement_rule") == "TERMINAL_STOP_NO_SELECTION_NO_FURTHER_READS_NO_OUTPUT_AUTHORITY", "dual decoder disagreement")
    require(dual.get("bank_per_payload") == [
        "packed_sha256", "decoder_a_identity", "decoder_b_identity",
        "decoded_identity_a", "decoded_identity_b", "exact_agreement",
        "logical_shape", "dtype",
    ], "dual decoder evidence")

    conditions = contract.get("pre_execution_conditions", {})
    conditional = conditions.get("conditional_review_go", {})
    require(conditional == {
        "amendment_starting_head": AMENDMENT_START_HEAD,
        "condition_1_dual_decoder_was_previously_load_bearing": False,
        "disposition": "PRE_EXECUTION_CONDITION_LANDED_REQUIRES_RENEWED_INDEPENDENT_REVIEW",
        "execution_permitted_in_amendment_loop": False,
        "review_verdict_received": "GO FOR ONE F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1",
    }, "conditional review gate")
    offsets = conditions.get("total_offset_verification", {})
    require(offsets == {
        "catalog_slice_formula": "parent_data_offset_abs + expert_id * per_expert_packed_length",
        "expert_166_crosscheck_sha256": EXPERT_166_CROSSCHECK_SHA,
        "fields_verified": [
            "checkpoint_key", "expert_id", "role", "offset", "packed_length",
            "quantization", "logical_decoded_shape", "shard_ordinal",
        ],
        "packed_bytes": 90_439_680,
        "public_catalog_sha256": PUBLIC_CATALOG_SHA,
        "result": "PASS",
        "shard_ordinal": 2,
        "verified_payloads": 24,
        "verification_requires_checkpoint_open": False,
    }, "total offset verification")

    ledger = contract.get("ledger", {})
    require(ledger.get("before") == 139 and ledger.get("successful_after") == 163, "ledger transition")
    require(ledger.get("partial_after_formula") == "139 + durable_successful_payload_read_count_N", "partial ledger accounting")
    require(ledger.get("automatic_retry") is False and ledger.get("second_attempt_authorized") is False, "ledger retry policy")

    restrictions = contract.get("scope_restrictions", {})
    required_false = [
        "router_payload_reads", "attention_payload_reads", "dense_prefix_replay",
        "shared_expert_payload_reads", "residual_execution", "candidate_execution",
        "representative_m1f0", "aggregate_evaluation", "fallback_reads",
    ]
    require(all(restrictions.get(key) is False for key in required_false), "scope restrictions")
    require(restrictions.get("unexpected_key_is_terminal") is True and restrictions.get("duplicate_read_is_terminal") is True, "fail-closed restrictions")

    retention = contract.get("output_retention", {})
    require(retention.get("outputs") == expected_outputs(), "output retention")
    require(retention.get("total_bytes") == 196_608 and retention.get("artifact_count") == 8, "output retention total")
    require(retention.get("immutable") is True and retention.get("read_only") is True and retention.get("writable_aliases") is False, "output immutability")
    require(_safe_symbolic_path(retention.get("symbolic_private_package", "")), "output private path")

    packed = contract.get("packed_retention", {})
    require(packed.get("authorized") is True and packed.get("artifact_count") == 24 and packed.get("total_bytes") == 90_439_680, "packed retention")
    require(packed.get("checkpoint_rereads_for_repeats") == 0 and packed.get("decoded_truth_package") is False, "packed replay policy")
    deterministic = contract.get("determinism", {})
    require(deterministic.get("fresh_process_exact_scaffold_repeats") == 2, "deterministic repeat count")
    require(deterministic.get("all_eight_output_sha256_must_match_across_repeats") is True, "deterministic output identity")

    require(evidence.get("schema") == "pulsarmlx.f017.canonical-expert-output-recovery-authorization", "evidence schema")
    require(evidence.get("schema_version") == "1.0.0", "evidence version")
    require(evidence.get("event_id") == EVENT_ID, "evidence event identity")
    require(evidence.get("starting_authoritative_head") == START_HEAD, "evidence starting head")
    state = evidence.get("authorization_state", {})
    require(state == {
        "status": "READY_FOR_INDEPENDENT_ADVERSARIAL_REVIEW",
        "execution_authorized": False,
        "consumed": False,
        "executed": False,
        "checkpoint_accessed": False,
    }, "authorization state")
    require(evidence.get("contract_sha256") == canonical_sha256(contract), "contract canonical identity")
    require(evidence.get("contract_file_sha256") == sha256_path(root / CONTRACT_PATH), "contract file identity")
    require(evidence.get("condition_amendment_starting_head") == AMENDMENT_START_HEAD, "condition amendment head")
    require(evidence.get("pre_execution_condition_disposition") == "LANDED_REQUIRES_RENEWED_INDEPENDENT_REVIEW", "condition amendment disposition")
    require(evidence.get("dual_decoder_gate") == {
        "required_payloads": 24,
        "same_retained_packed_bytes": True,
        "additional_checkpoint_reads": 0,
        "comparison_rule": "canonical_f32le_sha256_exact_equality",
        "disagreement_is_terminal": True,
    }, "evidence dual decoder gate")
    require(evidence.get("total_offset_verification") == {
        "verified_payloads": 24,
        "packed_bytes": 90_439_680,
        "shard_ordinal": 2,
        "result": "PASS",
    }, "evidence total offset verification")
    require(evidence.get("selected_expert_ids") == SELECTED_IDS, "evidence selected experts")
    require(evidence.get("payload_count") == 24 and evidence.get("packed_bytes") == 90_439_680, "evidence access budget")
    require(evidence.get("ledger_plan") == {"before": 139, "successful_after": 163}, "evidence ledger")
    require(evidence.get("retained_output_plan") == {"artifact_count": 8, "bytes_each": 24_576, "total_bytes": 196_608}, "evidence output plan")
    isolation = evidence.get("isolation", {})
    require(isolation == {
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "decoded_real_weights": 0,
        "expert_outputs_generated": 0,
        "candidate_or_model_dispatches": 0,
        "aggregate_evaluations": 0,
        "real_payload_ledger_before": 139,
        "real_payload_ledger_after": 139,
    }, "isolation")
    require(evidence.get("historical_immutability") == {
        "DPREFIX_REAL_1": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_2": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_3": "REJECTED_UNCHANGED",
        "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
        "membership_1984_of_1984": "PASS_UNCHANGED",
        "coefficient_qualification": "FAIL_UNCHANGED_0_OF_8",
        "route_disposition": "ROUTE NOT PROVEN INVARIANT",
    }, "historical immutability")
    bindings = evidence.get("artifact_bindings", [])
    _validate_file_bindings(root, bindings, "authorization artifact binding")
    required_binding_paths = {
        str(CONTRACT_PATH), str(SCHEMA_PATH), str(REVIEW_PACKET_PATH),
        str(VALIDATOR_PATH), str(TEST_PATH),
    }
    require({item.get("path") for item in bindings} == required_binding_paths, "authorization artifact inventory")
    serialized = json.dumps([contract, evidence], sort_keys=True)
    require(("/" + "Users/") not in serialized and "file://" not in serialized, "private path leak")
    ledger_doc = load_json(root / LEDGER_PATH)
    require(ledger_doc.get("cumulative_tensor_payloads") == 139, "real-payload ledger changed")
    return {"inventory_count": 24, "packed_bytes": 90_439_680, "ledger": 139}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    root = args.root.resolve()
    contract = load_json(root / CONTRACT_PATH)
    evidence = load_json(root / EVIDENCE_PATH)
    result = validate_documents(root, contract, evidence)
    print("CANONICAL_EXPERT_OUTPUT_AUTHORIZATION_VALID")
    print(canonical_sha256(contract))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
