#!/usr/bin/env python3
"""Checkpoint-free admission audit for the DPREFIX-REAL-1 package.

This module deliberately has no checkpoint, shard, positional-read, decoder,
or MLX entry point.  It proves the metadata-only 40 -> (2 reused + 38 new)
partition and fails closed unless the two reused tensors have a resolvable,
hash-bound private package.  A hash-only descriptor is not a reusable tensor.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from scripts.research import f017_m1f_minus1_dense_prefix_prep as BASE


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
Q4_PATH = EVIDENCE / "f017-q4-k-real-byte-qualification-attempt-1-v1.json"
Q6_PATH = EVIDENCE / "f017-q6-k-real-byte-qualification-attempt-1-v1.json"
LEDGER_PATH = EVIDENCE / "f017-real-payload-access-ledger-v1.json"
PROMPT_PATH = EVIDENCE / "f017-m1f-minus1-prompt-token-package-v1.json"

REQUIRED_PRIVATE_BINDING_FIELDS = (
    "private_package_identity",
    "private_package_manifest_sha256",
    "path_kind",
    "symbolic_name",
    "creation_ordinal",
    "immutable",
    "read_only",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(BASE.canonical_bytes(value)).hexdigest()


def reusable_binding_gaps(evidence: Mapping[str, Any]) -> list[str]:
    """Return semantic binding gaps; never infer paths from private hashes."""
    private = evidence.get("identity", {}).get("private_artifacts", {})
    packed = private.get("packed", {})
    decoded = private.get("decoded", [])
    gaps: list[str] = []
    for field in ("private_package_identity", "private_package_manifest_sha256"):
        if field not in private:
            gaps.append(f"private_artifacts.{field}")
    for field in ("path_kind", "symbolic_name", "creation_ordinal", "immutable"):
        if field not in packed:
            gaps.append(f"private_artifacts.packed.{field}")
    if packed.get("path_kind") not in (None, "private_package_relative"):
        gaps.append("private_artifacts.packed.path_kind=private_package_relative")
    if not decoded:
        gaps.append("private_artifacts.decoded[accepted]")
    else:
        accepted_hash = evidence.get("decoder_outputs", [{}])[0].get("decoded_sha256")
        accepted = next((row for row in decoded if row.get("sha256") == accepted_hash), None)
        if accepted is None:
            gaps.append("private_artifacts.decoded[accepted_sha256]")
        else:
            for field in ("path_kind", "symbolic_name", "creation_ordinal", "immutable"):
                if field not in accepted:
                    gaps.append(f"private_artifacts.decoded[accepted].{field}")
            if accepted.get("path_kind") not in (None, "private_package_relative"):
                gaps.append("private_artifacts.decoded[accepted].path_kind=private_package_relative")
    return gaps


def _component(evidence_path: Path, expected_name: str) -> dict[str, Any]:
    evidence = _load(evidence_path)
    identity = evidence["identity"]
    if evidence["verdict"] != "EXACT_REAL_BYTE_QUALIFIED":
        raise ValueError(f"{expected_name} qualification verdict")
    if identity["tensor_name"] != expected_name:
        raise ValueError(f"{expected_name} tensor identity")
    decoded_hashes = {row["decoded_sha256"] for row in evidence["decoder_outputs"]}
    if len(decoded_hashes) != 1:
        raise ValueError(f"{expected_name} decoded truth")
    return {
        "tensor_name": expected_name,
        "evidence_path": evidence_path.relative_to(ROOT).as_posix(),
        "evidence_sha256": _sha(evidence_path),
        "checkpoint_set_sha256": identity["checkpoint_set_sha256"],
        "catalog_sha256": identity["catalog_sha256"],
        "tensor_map_sha256": identity["tensor_map_sha256"],
        "offset": identity["offset"],
        "packed_length": identity["packed_length"],
        "packed_sha256": identity["packed_sha256"],
        "decoded_sha256": next(iter(decoded_hashes)),
        "format_contract_sha256": identity["format_contract_sha256"],
        "descriptor_gaps": reusable_binding_gaps(evidence),
        "qualification_status": evidence["verdict"],
        "reusable_private_package_status": "UNRESOLVABLE_HASH_ONLY_DESCRIPTOR",
    }


def audit() -> dict[str, Any]:
    inventory = BASE.reconstruct_inventory()
    prompt = _load(PROMPT_PATH)
    ledger = _load(LEDGER_PATH)
    if ledger["cumulative_tensor_payloads"] != 59:
        raise ValueError("real-payload ledger must be 59")
    if prompt != BASE.prompt_package():
        raise ValueError("prompt package drift")

    reused_names = ("token_embd.weight", "blk.0.ffn_down.weight")
    reused = [
        _component(Q4_PATH, reused_names[0]),
        _component(Q6_PATH, reused_names[1]),
    ]
    remaining = [row for row in inventory["tensors"] if row["name"] not in reused_names]
    if len(remaining) != 38 or len({row["name"] for row in remaining}) != 38:
        raise ValueError("38-read allowlist partition")
    if any(row["name"] in reused_names for row in remaining):
        raise ValueError("qualified target leaked into new-read allowlist")
    remaining_packed = sum(row["packed_length"] for row in remaining)
    allowlist = [
        {
            key: row[key]
            for key in (
                "ordinal", "name", "role", "layer", "shard_ordinal", "offset",
                "packed_length", "packed_row_width", "quantization", "gguf_shape",
                "decoded_f32_bytes", "catalog_entry_sha256", "map_contract_sha256",
            )
        }
        | {"allowed_read_count": 1}
        for row in remaining
    ]
    gaps = {row["tensor_name"]: row["descriptor_gaps"] for row in reused if row["descriptor_gaps"]}
    status = "BLOCKED_QUALIFIED_REUSE" if gaps else "REUSE_BINDINGS_COMPLETE"
    return {
        "schema": "pulsarmlx.f017.dense-prefix-authorization-preparation-audit",
        "schema_version": "1.0.0",
        "status": status,
        "authoritative_start_head": "1f494fcd0d890797fadb4ac898d794ac02b7fa99",
        "boundary": {
            "attempt_id": "DPREFIX-REAL-1",
            "honest_name": BASE.GATE_NAME,
            "semantic_scope": [
                "tokenize frozen prompt Hello", "consume token 9703 at position 0",
                "embedding lookup", "complete dense layer 0", "complete dense layer 1",
                "complete dense layer 2", "retain layer-3 entry hidden state", "stop",
            ],
            "forbidden": ["layer-3 attention", "layer-3 router", "experts", "logits", "output head", "token generation"],
        },
        "prompt": {
            "artifact_path": PROMPT_PATH.relative_to(ROOT).as_posix(),
            "artifact_sha256": _sha(PROMPT_PATH),
            "payload_sha256": prompt["payload_sha256"],
            "prompt_utf8_sha256": prompt["payload"]["prompt_utf8_sha256"],
            "token_id": 9703,
            "position": 0,
            "dsa": "range_fill([0])",
        },
        "inventory": {
            "source_artifact_sha256": _sha(EVIDENCE / "f017-m1f-minus1-exact-inventory-v1.json"),
            "regenerated_tensor_count": inventory["tensor_count"],
            "packed_bytes": inventory["access_budget"]["packed_bytes"],
            "aggregate_decoded_f32_bytes": inventory["access_budget"]["decoded_f32_bytes_upper_bound"],
            "quantization_counts": {family: row["tensor_count"] for family, row in inventory["quantization_table"].items()},
        },
        "qualified_components": reused,
        "proposed_new_read_allowlist": {
            "status": "DERIVED_BUT_NOT_EXECUTION_AUTHORIZED",
            "ordered_entries": allowlist,
            "ordered_entries_sha256": _canonical_sha(allowlist),
            "shard_opens": len({row["shard_ordinal"] for row in remaining}),
            "positional_reads": len(remaining),
            "tensor_payloads": len(remaining),
            "packed_bytes": remaining_packed,
        },
        "reuse_admission": {
            "policy": "SEPARATE_ORACLE_AND_CANDIDATE_PACKAGES_REQUIRED",
            "required_private_binding_fields": list(REQUIRED_PRIVATE_BINDING_FIELDS),
            "blocking_gaps": gaps,
            "automatic_reread_fallback": False,
            "contradiction_disposition": "PACKET CLAIMS REJECTED — BANKED EVIDENCE CONTRADICTS PACKET",
        },
        "authorization": {
            "execution_config_created": False,
            "authorization_binding_created": False,
            "attempt_ledger_entry_created": False,
            "preflight_result": "NOT_READY — QUALIFIED_PAYLOAD_REUSE_INVALID",
            "reason": "accepted Q4_K/Q6_K evidence has content hashes but no resolvable immutable private-package manifest or package-relative artifact descriptors",
        },
        "ledger": {"before": 59, "after_preparation": 59, "hypothetical_after_38_reads": 97},
        "isolation": {"checkpoint_access": 0, "dense_prefix_executed": False, "representative_m1f0_authorized": False},
        "internal_review_verdict": "NO-GO",
    }


def validate(value: Mapping[str, Any]) -> None:
    if value["status"] != "BLOCKED_QUALIFIED_REUSE":
        raise ValueError("audit must fail closed on unresolved reuse")
    if value["proposed_new_read_allowlist"]["tensor_payloads"] != 38:
        raise ValueError("allowlist count")
    if value["proposed_new_read_allowlist"]["packed_bytes"] != 834_066_432:
        raise ValueError("allowlist packed bytes")
    if value["ledger"] != {"before": 59, "after_preparation": 59, "hypothetical_after_38_reads": 97}:
        raise ValueError("ledger")
    if any(value["authorization"].get(field) for field in (
        "execution_config_created", "authorization_binding_created", "attempt_ledger_entry_created"
    )):
        raise ValueError("blocked audit cannot authorize execution")
    if value["isolation"]["checkpoint_access"] != 0 or value["isolation"]["dense_prefix_executed"]:
        raise ValueError("checkpoint-free preparation isolation")


if __name__ == "__main__":
    value = audit()
    validate(value)
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))
