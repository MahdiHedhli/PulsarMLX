#!/usr/bin/env python3
"""Validate the checkpoint-free F017 representative M1-F0 epsilon adjudication."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
GRAPH_V1 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-layer3-production-semantic-graph-v1.json"
GRAPH_V2 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-layer3-production-semantic-graph-v2.json"
BOUNDARY_V2 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-boundary-v2.json"
BOUNDARY_V3 = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-boundary-v3.json"
ADJUDICATION = ROOT / "docs/architecture/reviews/evidence/f017-representative-m1f0-rmsnorm-epsilon-adjudication-v1.json"
RATIONALE = ROOT / "docs/architecture/reviews/f017-representative-m1f0-rmsnorm-epsilon-adjudication.md"
FREEZE = ROOT / "docs/architecture/reviews/evidence/f017-representative-m1f0-boundary-v3-freeze.json"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
ORACLE = ROOT / "scripts/research/prepare_f017_m1f0_real_reference.py"
ENGINE = ROOT / "crates/engine/src/lib.rs"
HISTORICAL = ROOT / "docs/architecture/reviews/evidence/f017-m1-f0-real-route-attempt-2-v1.json"

GRAPH_V1_SHA256 = "ece281ecdd7f5d3ad9a06e76304d0d76e63499153960529676ab889059f98a7b"
GRAPH_V2_SHA256 = "1585dad6b989fd0ac9b231f4e66e4d0129021868d027a3352a7b740707561558"
BOUNDARY_V2_SHA256 = "46a065385b110982cb9f5585b57a2f7910d1e12e01232dcae22d60ac4dbb09a1"
BOUNDARY_V3_SHA256 = "a9dc0d9effb3e52844203a34be587d12f0f7b011fb58d33c5dbdbe5b650deed3"
ADJUDICATION_SHA256 = "fc92b11223ee174b5f206a45a6d2b50540b4c82ba5d2c2333010947d525646e4"
RATIONALE_SHA256 = "7002df84661156cbf32ecc71e1ce6f97f828fe5f82d75a073967d1087d3c575d"
ORACLE_SHA256 = "ec9a679b78ccd5adb5353cb689cefe642307a07fdb9a266d65d99dab86c6e48d"
ENGINE_SHA256 = "20f672f194b0076c2634c79248e00b2c8a3121a1920adfaa9dda01afbf45b406"
HISTORICAL_SHA256 = "0eb0030f0345b8b2cabca4b7e690177603ca29e21b0cfade3e0639e356d1b8f9"

EXACT_DECIMAL = "9.999999747378752e-6"
BITS_HEX = "0x3727c5ac"
LITTLE_ENDIAN_HEX = "acc52737"
SITES = {
    "blk.3.attn_norm.weight",
    "blk.3.attn_q_a_norm.weight",
    "blk.3.attn_kv_a_norm.weight",
    "blk.3.ffn_norm.weight",
}


class EpsilonAdjudicationValidationError(ValueError):
    pass


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reject_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise EpsilonAdjudicationValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicates)


def _check_source(path: str, digest: str, root: Path = ROOT) -> None:
    relative = Path(path)
    if relative.is_absolute() or ".." in relative.parts:
        raise EpsilonAdjudicationValidationError("unsafe source path")
    if sha256_path(root / relative) != digest:
        raise EpsilonAdjudicationValidationError(f"source identity: {path}")


def _check_isolation(value: dict[str, Any]) -> None:
    if value != {
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "payload_reads": 0,
        "candidate_or_model_dispatches": 0,
        "gpu_dispatches": 0,
        "real_payload_ledger_before": 166,
        "real_payload_ledger_after": 166,
    }:
        raise EpsilonAdjudicationValidationError("isolation or ledger mutation")


def _validate_epsilon(value: dict[str, Any], *, sites_key: str) -> None:
    if value.get("source_decimal") != "1e-5":
        raise EpsilonAdjudicationValidationError("source epsilon regression")
    if value.get("dtype") != "IEEE-754 binary32":
        raise EpsilonAdjudicationValidationError("epsilon dtype")
    if value.get("exact_decimal") != EXACT_DECIMAL:
        raise EpsilonAdjudicationValidationError("exact epsilon decimal")
    if value.get("bits_hex") != BITS_HEX or value.get("little_endian_hex") != LITTLE_ENDIAN_HEX:
        raise EpsilonAdjudicationValidationError("epsilon bit identity")
    raw_sites = value.get(sites_key)
    actual_sites = set(raw_sites.values()) if isinstance(raw_sites, dict) else set(raw_sites or [])
    if actual_sites != SITES:
        raise EpsilonAdjudicationValidationError("epsilon site coverage")


def validate_graph_dict(graph: dict[str, Any], root: Path = ROOT) -> None:
    if graph.get("schema") != "pulsarmlx.f017.layer3-production-semantic-graph" or graph.get("schema_version") != "2.0.0":
        raise EpsilonAdjudicationValidationError("graph schema")
    if graph.get("status") != "FROZEN_NO_EXECUTION_AUTHORITY":
        raise EpsilonAdjudicationValidationError("graph status")
    supersedes = graph.get("supersedes", {})
    if supersedes.get("sha256") != GRAPH_V1_SHA256:
        raise EpsilonAdjudicationValidationError("graph predecessor")
    _validate_epsilon(graph.get("rmsnorm_epsilon", {}), sites_key="applies_to")
    if graph.get("rmsnorm_epsilon", {}).get("site_specific_override") is not False:
        raise EpsilonAdjudicationValidationError("site-specific epsilon override")
    boundaries = graph.get("boundaries", {})
    if "epsilon=f32(1e-5)" not in boundaries.get("A_norm", {}).get("formula", ""):
        raise EpsilonAdjudicationValidationError("attention epsilon")
    if "q_a_norm and kv_a_norm use epsilon=f32(1e-5)" not in boundaries.get("A", {}).get("formula", ""):
        raise EpsilonAdjudicationValidationError("internal attention epsilon")
    if "epsilon=f32(1e-5)" not in boundaries.get("F_norm", {}).get("formula", ""):
        raise EpsilonAdjudicationValidationError("FFN epsilon")
    if graph.get("representative_m1f0_boundary", {}).get("formula") != "S0->A_norm->A->S1->F_norm->Route":
        raise EpsilonAdjudicationValidationError("representative graph boundary")
    for source in graph.get("semantic_sources", []):
        _check_source(source.get("path", ""), source.get("sha256", ""), root)
    _check_isolation(graph.get("isolation", {}))


def validate_boundary_dict(boundary: dict[str, Any], root: Path = ROOT) -> None:
    if boundary.get("schema") != "pulsarmlx.f017.representative-m1f0-boundary" or boundary.get("schema_version") != "3.0.0":
        raise EpsilonAdjudicationValidationError("boundary schema")
    if boundary.get("status") != "FROZEN_NO_EXECUTION_AUTHORITY":
        raise EpsilonAdjudicationValidationError("boundary status")
    if boundary.get("supersedes", {}).get("sha256") != BOUNDARY_V2_SHA256:
        raise EpsilonAdjudicationValidationError("boundary predecessor")
    effective = boundary.get("effective_contract_construction", {})
    if effective.get("semantic_graph", {}).get("sha256") != GRAPH_V2_SHA256:
        raise EpsilonAdjudicationValidationError("corrected semantic graph binding")
    replacements = effective.get("replace_only", [])
    if [item.get("json_pointer") for item in replacements] != [
        "/attention_semantics/normalization",
        "/attention_semantics/ffn_normalization",
    ] or any("f32(1e-5)" not in item.get("value", "") for item in replacements):
        raise EpsilonAdjudicationValidationError("effective boundary replacement")
    if effective.get("all_other_v2_fields") != "UNCHANGED_AND_LOAD_BEARING":
        raise EpsilonAdjudicationValidationError("unbounded predecessor changes")
    _validate_epsilon(boundary.get("rmsnorm_epsilon", {}), sites_key="sites")
    if boundary.get("rmsnorm_epsilon", {}).get("different_site_values_permitted") is not False:
        raise EpsilonAdjudicationValidationError("different epsilon sites permitted")
    event = boundary.get("future_real_event_shape", {})
    if (event.get("attention_payload_reads"), event.get("packed_bytes"), event.get("maximum_shard_opens"), event.get("ledger_before"), event.get("ledger_after_success")) != (9, 132900864, 1, 166, 175):
        raise EpsilonAdjudicationValidationError("future event shape drift")
    auth = boundary.get("authorization", {})
    if any(auth.get(key) is not False for key in ("real_event_authorized", "checkpoint_access_authorized", "candidate_or_model_dispatch_authorized")):
        raise EpsilonAdjudicationValidationError("execution authority leaked")
    for source in boundary.get("authority_chain", []):
        _check_source(source.get("path", ""), source.get("sha256", ""), root)
    _check_isolation(boundary.get("isolation", {}))


def validate_adjudication_dict(evidence: dict[str, Any], root: Path = ROOT) -> None:
    if evidence.get("schema") != "pulsarmlx.f017.representative-m1f0-rmsnorm-epsilon-adjudication" or evidence.get("result") != "F32_1E_MINUS_5_AUTHORITATIVE":
        raise EpsilonAdjudicationValidationError("adjudication disposition")
    question = evidence.get("question", {})
    if question != {
        "option_a_1e_minus_6": False,
        "option_b_f32_1e_minus_5": True,
        "option_c_legitimate_site_specific_values": False,
        "option_d_insufficient_evidence": False,
    }:
        raise EpsilonAdjudicationValidationError("adjudication choice")
    _validate_epsilon(evidence.get("authoritative_value", {}), sites_key="semantic_sites")
    inventory = evidence.get("evidence_inventory", [])
    if len(inventory) != 14:
        raise EpsilonAdjudicationValidationError("epsilon inventory completeness")
    for item in inventory:
        _check_source(item.get("path", ""), item.get("sha256", ""), root)
    by_path = {item["path"]: item for item in inventory}
    if by_path[str(ORACLE.relative_to(ROOT))].get("epsilon") != "np.float32(9.999999747378752e-6)":
        raise EpsilonAdjudicationValidationError("accepted oracle epsilon evidence")
    if by_path["scripts/research/f017_dense_prefix_preparation.py"].get("kind") != "historical_synthetic_fixture_helper":
        raise EpsilonAdjudicationValidationError("synthetic 1e-6 misclassified")
    if evidence.get("contradiction", {}).get("resolved") is not True or evidence.get("contradiction", {}).get("different_legitimate_site_epsilons") is not False:
        raise EpsilonAdjudicationValidationError("contradiction disposition")
    superseding = evidence.get("superseding_artifacts", {})
    if superseding.get("semantic_graph", {}).get("sha256") != GRAPH_V2_SHA256 or superseding.get("representative_boundary", {}).get("sha256") != BOUNDARY_V3_SHA256:
        raise EpsilonAdjudicationValidationError("superseding artifact binding")
    preparation = evidence.get("preparation_disposition", {})
    if preparation.get("representative_execution_authorization_may_be_prepared") is not True or preparation.get("real_event_authorized") is not False or preparation.get("checkpoint_access_authorized") is not False:
        raise EpsilonAdjudicationValidationError("preparation/authorization disposition")
    _check_isolation(evidence.get("isolation", {}))


def validate_executable_authority() -> None:
    oracle = ORACLE.read_text(encoding="utf-8")
    if "RMS_EPS = np.float32(9.999999747378752e-6)" not in oracle:
        raise EpsilonAdjudicationValidationError("accepted oracle epsilon source")
    required_calls = (
        'rms_norm(hidden, vector("blk.3.attn_norm.weight"))',
        'rms_norm(q_rank, vector("blk.3.attn_q_a_norm.weight"))',
        'rms_norm(kv_raw[:512], vector("blk.3.attn_kv_a_norm.weight"))',
        'rms_norm(attention_residual, vector("blk.3.ffn_norm.weight"))',
    )
    if any(call not in oracle for call in required_calls):
        raise EpsilonAdjudicationValidationError("accepted oracle RMSNorm site")
    engine = ENGINE.read_text(encoding="utf-8")
    if 'rms_eps: f("attention.layer_norm_rms_epsilon")?' not in engine or "let eps = s.rms_eps;" not in engine:
        raise EpsilonAdjudicationValidationError("production epsilon plumbing")
    raw = struct.pack("<f", 1.0e-5)
    if raw.hex() != LITTLE_ENDIAN_HEX or struct.unpack("<I", raw)[0] != int(BITS_HEX, 16):
        raise EpsilonAdjudicationValidationError("host binary32 epsilon identity")


def validate_freeze_evidence() -> None:
    freeze = load_json(FREEZE)
    if freeze.get("schema") != "pulsarmlx.f017.representative-m1f0-boundary-freeze" or freeze.get("result") != "REPRESENTATIVE M1-F0 BOUNDARY V3 FROZEN":
        raise EpsilonAdjudicationValidationError("freeze disposition")
    artifacts = freeze.get("artifacts", {})
    expected = {
        "semantic_graph": (GRAPH_V2, GRAPH_V2_SHA256),
        "representative_boundary": (BOUNDARY_V3, BOUNDARY_V3_SHA256),
        "epsilon_adjudication": (ADJUDICATION, ADJUDICATION_SHA256),
        "rationale": (RATIONALE, RATIONALE_SHA256),
    }
    for key, (path, digest) in expected.items():
        item = artifacts.get(key, {})
        if item.get("sha256") != digest or sha256_path(path) != digest:
            raise EpsilonAdjudicationValidationError(f"freeze artifact: {key}")
    for key, path in (("validator", Path(__file__).resolve()), ("mutation_tests", ROOT / "scripts/research/tests/test_validate_f017_m1f0_rms_epsilon_adjudication.py")):
        if artifacts.get(key, {}).get("sha256") != sha256_path(path):
            raise EpsilonAdjudicationValidationError(f"freeze tool identity: {key}")
    if freeze.get("authorization", {}).get("real_event_authorized") is not False:
        raise EpsilonAdjudicationValidationError("freeze execution authority")
    _check_isolation(freeze.get("isolation", {}))


def validate_file_identities() -> None:
    for path, digest in {
        GRAPH_V1: GRAPH_V1_SHA256,
        GRAPH_V2: GRAPH_V2_SHA256,
        BOUNDARY_V2: BOUNDARY_V2_SHA256,
        BOUNDARY_V3: BOUNDARY_V3_SHA256,
        ADJUDICATION: ADJUDICATION_SHA256,
        RATIONALE: RATIONALE_SHA256,
        ORACLE: ORACLE_SHA256,
        ENGINE: ENGINE_SHA256,
        HISTORICAL: HISTORICAL_SHA256,
    }.items():
        if sha256_path(path) != digest:
            raise EpsilonAdjudicationValidationError(f"file identity: {path.name}")


def validate_privacy() -> None:
    public = "\n".join(path.read_text(encoding="utf-8") for path in (GRAPH_V2, BOUNDARY_V3, ADJUDICATION, RATIONALE, FREEZE))
    if any(token in public for token in ("/Users/", "/home/", "file://", "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf")):
        raise EpsilonAdjudicationValidationError("private path or checkpoint filename leak")


def validate_all() -> None:
    validate_file_identities()
    validate_graph_dict(load_json(GRAPH_V2))
    validate_boundary_dict(load_json(BOUNDARY_V3))
    validate_adjudication_dict(load_json(ADJUDICATION))
    validate_executable_authority()
    validate_freeze_evidence()
    validate_privacy()
    ledger = load_json(LEDGER)
    if ledger.get("cumulative_tensor_payloads") != 166:
        raise EpsilonAdjudicationValidationError("real-payload ledger changed")
    historical = load_json(HISTORICAL)
    if historical.get("verdict") != "M1-F0 ACCEPTED" or historical.get("repeat_integrity", {}).get("all_equal") is not True:
        raise EpsilonAdjudicationValidationError("historical M1-F0 changed")


def main() -> int:
    validate_all()
    print("F017_REPRESENTATIVE_M1F0_RMS_EPSILON_ADJUDICATED_F32_1E_MINUS_5")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
