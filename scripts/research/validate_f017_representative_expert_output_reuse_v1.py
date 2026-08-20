#!/usr/bin/env python3
"""Fail-closed validator for representative expert-output reuse v1."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-expert-output-reuse-authorization-v1.json"
AGG = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-routed-aggregate-input-v1.json"
RESOLVER = ROOT / "scripts/research/f017_representative_expert_output_reuse_v1.py"
BASE_HEAD = "26f5fe81e63851a23e40ba432b643b0a24a86d33"
IDS = [250, 10, 237, 62, 73, 177, 218, 28]
WEIGHTS = [0.7487501576296707, 0.3348627106807668, 0.23863270273063697, 0.23688715675086147,
           0.2514906203405492, 0.23059957299763345, 0.22915341148588297, 0.22962366738399842]
OUTPUTS = [
    "0b6036ef2e77142094b673c421b96719619a58e15eee7522347b37f73d9b892b",
    "d9adb474f64c98349dfe0a6c768b2020b27f62ecc85874975c990b880ef304b3",
    "4ac842afb3b1909f9f0e07013c86bbdca90cd246b6190bf190a60fe9767fdd9b",
    "2550cccf9b2f1a83b2e2f03f090ee135dc525a15eaf1bab18d1a2fb97af16128",
    "9aa5e1dae2619c440c65689154de332da313990b4ba07fdac45e78a65ad3a7d3",
    "18260d4936483b6f7d83d2d0ec72d01fc761f2ac5726fa9b7bda243a4db9a201",
    "f4a8fc1e3bb91a8a5635505f766a07ef2cfb135378d224ed5f545617d781537d",
    "45029a47061c43746344d5b0a9366b8129630019a3196d0be146efc5e1a361f0",
]
AUTHORITY = {
    "representative_route_execution": "dc53b458fe9c189b4cfbfd83889e7997aa5decba799c421944ac93edb237f190",
    "concrete_route_values": "6035308cb85a29617abe5dcb18be37ab6d99afb5193d28ed7993d41c2aeb7b49",
    "expert_recovery_authorization": "abbf12bc921c2d28f00a375225b5969145017cfe70da8bfa7486caf502f21c6f",
    "expert_recovery_release": "ccf33fef03c2204fa443b981c273dd795f0bf6ea82ae89d5780e385c20fbdf68",
    "expert_recovery_release_approval": "c1b5f202205fa3930e4b55a1131a2168f6ac4a845a02b14931e067ebd3b921cc",
    "expert_execution_evidence": "fe1cad02405b74d9000afec915bdf7e772e6dd77c13b7e4cc5b5db35606b51e4",
}


class ValidationError(ValueError):
    pass


def req(value: bool, message: str) -> None:
    if not value:
        raise ValidationError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    def no_dups(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            req(key not in out, f"duplicate key: {key}")
            out[key] = value
        return out
    obj = json.loads(path.read_text(), object_pairs_hook=no_dups)
    req(isinstance(obj, dict), "object required")
    return obj


def validate(doc: dict[str, Any], *, repo: bool) -> None:
    req(doc.get("schema_version") == "1.0.0", "schema version")
    req(doc.get("status") == "PREPARED_REVIEW_REQUIRED" and doc.get("real_event_authorized") is False, "state")
    req(doc.get("preparation_base_head") == BASE_HEAD, "wrong head")
    authority = doc.get("authority", {})
    req(authority.get("representative_expert_input_sha256") == "687a692a452e30860c34055942061f4ff368ec0e1c815439c71e457a444fe62c", "expert input")
    for key, identity in AUTHORITY.items():
        req(authority.get(key, {}).get("sha256") == identity, f"authority: {key}")
        if repo:
            req(sha(ROOT / authority[key]["path"]) == identity, f"authority bytes: {key}")
    package = doc.get("private_package", {})
    req(package == {
        "manifest_sha256": "2b3a0ef3bb2d896dd04add67e6fc729b2b400170b58f9038751cee612d58bc7a",
        "output_count": 8, "output_bytes": 196608, "machine_local_root_not_committed": True,
        "machine_local_paths_published": False, "retention_class": "PERSISTED_AUTHORITY_READ_ONLY_SINGLE_LINK",
    }, "private package")
    triples = doc.get("atomic_id_weight_output_triples")
    req(isinstance(triples, list) and len(triples) == 8, "triple count")
    req([x.get("ordinal") for x in triples] == list(range(8)), "ordinals")
    req([x.get("expert_id") for x in triples] == IDS and len(set(IDS)) == 8, "expert order")
    req([x.get("routing_weight") for x in triples] == WEIGHTS, "atomic weights")
    req([x.get("output_sha256") for x in triples] == OUTPUTS, "atomic outputs")
    for i, x in enumerate(triples):
        req(x.get("private_relative_path") == f"{i:02d}-expert-{IDS[i]}-down.f32le", "output path")
        req(x.get("dtype") == "little-endian-f32" and x.get("shape") == [6144] and x.get("byte_length") == 24576, "surface")
        req(x.get("semantic_role") == "REPRESENTATIVE_M1F0_ROUTED_EXPERT_OUTPUT", "semantic role")
    identity = doc.get("retained_identity_contract", {})
    for key in ("expected_equals_before_equals_consumed_equals_after", "open_once_consume_same_descriptor",
                "fstat_before_and_after", "regular_file", "non_symlink", "hard_link_count", "read_only",
                "no_writable_alias", "finite_values"):
        req(identity.get(key) is True or (key == "hard_link_count" and identity.get(key) == 1), f"identity: {key}")
    agg = doc.get("aggregate_input_contract", {})
    req(agg.get("sha256") == sha(AGG), "aggregate contract identity")
    agg_doc = load(AGG)
    req(agg_doc.get("status") == "FROZEN_NOT_EVALUATED", "aggregate evaluated")
    sem = agg_doc.get("semantics", {})
    req(sem.get("accumulation") == "fixed Python-math.fsum-equivalent binary64 accumulation over the eight atomic triples in representative rank order", "aggregate accumulation")
    req(sem.get("output_dtype") == "little-endian-f64" and sem.get("output_shape") == [6144], "aggregate output")
    resolver = doc.get("resolver", {})
    req(resolver.get("sha256") == sha(RESOLVER), "resolver identity")
    for key in ("checkpoint_capability", "shard_capability", "expert_execution_capability", "aggregate_execution_capability"):
        req(resolver.get(key) is False, f"resolver capability: {key}")
    req(doc.get("accounting") == {"real_payload_ledger": 175, "checkpoint_reads": 0, "shard_opens": 0, "expert_executions": 0, "aggregate_executions": 0}, "accounting")
    for key, value in doc.get("prohibitions", {}).items():
        req(value is True, f"prohibition: {key}")
    req(set(doc.get("prohibitions", {})) == {"historical_direct_dprefix_route", "historical_direct_dprefix_expert_outputs", "expert_reexecution_fallback", "checkpoint_reread", "alternate_expert_output", "output_substitution", "weight_reassignment", "aggregate_execution", "shared_expert_execution", "ffn_completion", "s2_construction"}, "prohibition census")
    reproduction = doc.get("reproducibility", {})
    req(reproduction == {"fresh_processes": 2, "exact_output_identity": "8_OF_8_IN_BOTH_PROCESSES", "checkpoint_reads": 0, "shard_opens": 0, "result": "PASS"}, "reproduction")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, default=AUTH)
    parser.add_argument("--no-repo", action="store_true")
    args = parser.parse_args()
    validate(load(args.authorization), repo=not args.no_repo)
    print("REPRESENTATIVE_EXPERT_OUTPUT_REUSE_AUTHORIZATION_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
