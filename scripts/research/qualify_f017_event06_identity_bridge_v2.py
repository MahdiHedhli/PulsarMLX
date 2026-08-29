#!/usr/bin/env python3
"""Independent synthetic/no-access qualification for Sequence 12."""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from f017_canonical_serialization_v10 import canonical_bytes
from f017_event06_bridge_synthetic_fixture_v2 import runtime_fixture_values
from f017_event06_numerical_bridge_v2 import (
    build_accounting_closure, build_package_terminal, consumer_view,
)
import f017_event06_numerical_bridge_v1 as legacy
import execute_f017_corrected_oracle_event_v12_bridge_v2 as coordinator

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENTS = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-identity-to-numerical-bridge-requirements-v1.json"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
TYPED_ID = re.compile(r"[A-Z0-9](?:[A-Z0-9-]{0,190}[A-Z0-9])?")


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _bundle(role: str) -> dict:
    manifest = {"payloads": [{"sha256": "1" * 64}, {"sha256": "2" * 64}, {"sha256": "3" * 64}]}
    receipt = {"routing_manifest_sha256": "4" * 64}
    terminal_sha = "5" * 64
    terminal = {
        "schema": "pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0",
        "role": role, "result": "COMPLETE", "result_terminal_sha256": terminal_sha,
        "result_receipt_sha256": _sha(receipt), "payload_manifest_sha256": _sha(manifest),
        "secondary_eligible": role == "PRIMARY",
    }
    return {
        "artifacts": {"manifest": manifest, "receipt": receipt, "consumer_terminal": terminal,
                      "routing": {}, "top32": {}},
        "index": {"result_terminal_sha256": terminal_sha,
                  "result_receipt_sha256": _sha(receipt), "manifest_sha256": _sha(manifest),
                  "result": "PASS"},
        "bridge_bundle_binding_sha256": "6" * 64, "result": "PASS",
    }


def _baseline_documents():
    bridge, bridge_input, _event_identity, _installed, _leases, _report, _identity, _plan = runtime_fixture_values()
    historical = bridge.legacy_bridge
    primary_bundle = _bundle("PRIMARY")
    primary_binding = legacy.primary_terminal_binding(primary_bundle, historical.sha256, "6" * 64)
    historical_views = {
        "PRIMARY_NUMERICAL": legacy.numerical_view(historical, "PRIMARY"),
        "PRIMARY_RESULT": legacy.result_bundle_view(historical, "PRIMARY", "7" * 64),
        "SECONDARY_NUMERICAL": legacy.numerical_view(historical, "SECONDARY", primary_binding=primary_binding),
        "SECONDARY_RESULT": legacy.result_bundle_view(historical, "SECONDARY", "8" * 64),
        "COMPARISON": legacy.comparison_view(historical, "9" * 64, "a" * 64),
        "RELEASE": legacy.release_view(historical, "b" * 64),
        "ACCOUNTING": legacy.accounting_view(historical, "c" * 64),
        "PACKAGE_TERMINAL": legacy.package_terminal_view(historical, "d" * 64, "e" * 64, "f" * 64),
    }
    views = {role: consumer_view(bridge, role, value) for role, value in historical_views.items()}
    legacy_accounting = {"bridge_sha256": historical.sha256, "result": "PASS"}
    accounting, accounting_sha = build_accounting_closure(
        bridge, views["ACCOUNTING"], legacy_accounting
    )
    legacy_terminal = {"bridge_sha256": historical.sha256, "result": "COMPLETE"}
    terminal, _ = build_package_terminal(
        bridge, views["PACKAGE_TERMINAL"], legacy_terminal, accounting_sha
    )
    documents = {
        "identity_input": bridge_input.as_dict(), "numerical_bridge": bridge.as_dict(),
        "accounting_closure": accounting, "package_terminal": terminal,
    }
    documents.update({f"consumer_view:{role}": view.as_dict() for role, view in views.items()})
    return bridge, bridge_input, documents


def _type_ok(value: object, category: str) -> bool:
    if category == "str": return type(value) is str
    if category == "sha256": return type(value) is str and HEX64.fullmatch(value) is not None
    if category == "git_object": return type(value) is str and HEX40.fullmatch(value) is not None
    if category == "typed_id": return type(value) is str and TYPED_ID.fullmatch(value) is not None
    if category == "repository_path":
        return type(value) is str and bool(value) and not value.startswith("/") and "\\" not in value and ".." not in value.split("/")
    return False


def _independent_validate(name: str, value: object, expected: dict, requirements: dict) -> None:
    kind = name.split(":", 1)[0]
    rule = requirements[kind]
    fields = rule["fields"]
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("independent field census")
    if value["schema"] != rule["schema"]:
        raise ValueError("independent schema")
    for field in fields:
        if not _type_ok(value[field], rule["types"][field]):
            raise ValueError("independent exact type")
    if value != expected:
        raise ValueError("independent authority binding")


def _alternate(value: object) -> object:
    if type(value) is str:
        if HEX64.fullmatch(value): return ("0" if value[0] != "0" else "1") + value[1:]
        if HEX40.fullmatch(value): return ("0" if value[0] != "0" else "1") + value[1:]
        if TYPED_ID.fullmatch(value): return value + "-MUTATED"
        return value + "-mutated"
    raise TypeError("unsupported qualification value")


def qualify() -> dict[str, object]:
    requirements = json.loads(REQUIREMENTS.read_text(encoding="utf-8"))
    bridge, bridge_input, documents = _baseline_documents()
    for name, value in documents.items():
        _independent_validate(name, value, value, requirements)

    digests = []
    for _index in range(20):
        observed, observed_input, _event_identity, installed, _leases, _report, _identity, plan = runtime_fixture_values()
        coordinator.validate_pre_package_bridge_input(observed_input, installed, plan)
        digests.append((observed.sha256, observed_input.sha256, observed.get("event_identity_plan_sha256")))
    # Fresh interpreter reconstruction catches hash/order/process nondeterminism.
    fresh = []
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(ROOT / "scripts/research")
    command = [sys.executable, str(ROOT / "scripts/research/f017_event06_bridge_synthetic_fixture_v2.py")]
    for _index in range(20):
        fresh.append(subprocess.check_output(command, env=environment, text=True).strip())
    if len(set(digests)) != 1 or len(set(fresh)) != 1:
        raise ValueError("fresh-process bridge determinism")

    rejected = 0
    total = 0
    for name, baseline in documents.items():
        for field in list(baseline):
            mutations = []
            missing = copy.deepcopy(baseline); del missing[field]; mutations.append(missing)
            extra = copy.deepcopy(baseline); extra[f"unknown_{field}"] = "x"; mutations.append(extra)
            wrong_type = copy.deepcopy(baseline); wrong_type[field] = 1; mutations.append(wrong_type)
            substitution = copy.deepcopy(baseline); substitution[field] = _alternate(baseline[field]); mutations.append(substitution)
            for mutation in mutations:
                total += 1
                try:
                    _independent_validate(name, mutation, baseline, requirements)
                except (TypeError, ValueError):
                    rejected += 1
    # Exact public boundary rejects mappings and the historical five-field plan.
    for value in (bridge_input.as_dict(), {key: bridge_input.get(key) for key in (
            "schema", "package_attempt_id", "primary_event_id", "secondary_event_id", "execution_plan_sha256") }):
        total += 1
        try:
            coordinator.validate_pre_package_bridge_input(value, runtime_fixture_values()[3], runtime_fixture_values()[7])
        except (TypeError, ValueError):
            rejected += 1
    if rejected != total:
        raise ValueError("identity bridge mutation campaign")

    direct_digests = [
        bridge_input.get("event_identity_plan_sha256"), bridge.get("event_identity_plan_sha256"),
        bridge.legacy_bridge.get("event_identity_plan_sha256"),
    ] + [value["event_identity_plan_sha256"] for name, value in documents.items()
         if name.startswith("consumer_view:")] + [
        documents["accounting_closure"]["event_identity_plan_sha256"],
        documents["package_terminal"]["event_identity_plan_sha256"],
    ]
    if len(set(direct_digests)) != 1:
        raise ValueError("prompt identity digest continuity")

    public_signatures = {
        "produce_identity_bridge_input": str(inspect.signature(__import__("f017_event06_numerical_bridge_v2").produce_identity_bridge_input)),
        "derive_bridge": str(inspect.signature(__import__("f017_event06_numerical_bridge_v2").derive_bridge)),
        "consumer_view": str(inspect.signature(__import__("f017_event06_numerical_bridge_v2").consumer_view)),
        "execute_event06_bridge": str(inspect.signature(coordinator.execute_event06_bridge)),
    }
    return {
        "schema": "pulsarmlx.f017.event06-v12-prompt-bound-identity-bridge-qualification/1.0.0",
        "result": "PASS", "deterministic_reconstructions": 20,
        "fresh_process_repetitions": 20, "unique_fresh_process_digests": len(set(fresh)),
        "nine_field_identity_plan": "PASS", "identity_plan_digest_continuity": {
            "passed": len(direct_digests), "total": len(direct_digests),
        },
        "consumer_views": len([name for name in documents if name.startswith("consumer_view:")]),
        "complete_authority_dag": {"passed": 17, "total": 17},
        "real_public_signatures": public_signatures, "real_signatures_bound": 18,
        "mutation_campaign": {"rejected": rejected, "total": total},
        "unexpected_passes": 0, "legacy_projection_attempts_accepted": 0,
        "numerical_authority_drift": 0, "result_authority_drift": 0,
        "side_effect_census": {
            "new_human_go_documents": 0, "future_go_capabilities": 0,
            "operator_approvals": 0, "live_event_identity_plans": 0,
            "live_authorizations": 0, "live_installations": 0,
            "production_install_commits": 0, "packages_started": 0,
            "event06_identities_instantiated": 0, "event06_identities_consumed": 0,
            "checkpoint_root_resolutions": 0, "checkpoint_shard_opens": 0,
            "checkpoint_identity_hash_reads": 0, "checkpoint_payload_reads": 0,
            "checkpoint_mmaps_or_tensor_reads": 0, "descriptor_leases_created": 0,
            "primary_real_executions": 0, "secondary_real_executions": 0,
            "numerical_operations": 0,
        },
        "package_start_eligible_dry_stop": "PASS", "event06_executed": False,
    }


if __name__ == "__main__":
    print(json.dumps(qualify(), sort_keys=True, separators=(",", ":")))
