#!/usr/bin/env python3
"""Fail-closed public validator for the recovery execution substrate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

_IMPORT_ROOT = Path(__file__).resolve().parents[2]
if str(_IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(_IMPORT_ROOT))

from scripts.research import validate_f017_canonical_expert_output_authorization as auth
from scripts.research.f017_canonical_expert_output_recovery_executor import (
    AUTHORIZATION_SHA256,
    AUTHORIZED_HEAD,
    DECODER_LINEAGE_SHA256,
    EVENT_ID,
    INVENTORY_SHA256,
    LEDGER_BEFORE,
    SHARD_SHA256,
    DecoderPair,
    ExecutorBinding,
    MockOutputStage,
    RecoveryExecutor,
    SyntheticPayload,
    SyntheticShardProvider,
    canonical_sha256,
)


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = Path("specs/017-rust-native-inference-runtime/contracts/f017-canonical-expert-recovery-execution-substrate-v1.json")
EVIDENCE = Path("docs/architecture/reviews/evidence/f017-canonical-expert-recovery-execution-substrate-v1.json")
LEDGER = Path("docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json")
AUTH_CONTRACT = auth.CONTRACT_PATH
EXECUTOR = Path("scripts/research/f017_canonical_expert_output_recovery_executor.py")
EXECUTOR_TEST = Path("scripts/research/tests/test_f017_canonical_expert_output_recovery_executor.py")
VALIDATOR = Path("scripts/research/validate_f017_canonical_expert_output_recovery_substrate.py")
VALIDATOR_TEST = Path("scripts/research/tests/test_validate_f017_canonical_expert_output_recovery_substrate.py")


class SubstrateValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SubstrateValidationError(message)


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise SubstrateValidationError(f"duplicate key: {key}")
        value[key] = item
    return value


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)
    except SubstrateValidationError:
        raise
    except Exception as error:
        raise SubstrateValidationError(f"invalid JSON: {path}") from error
    require(isinstance(value, dict), f"object required: {path}")
    return value


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_relative(value: str) -> bool:
    path = PurePosixPath(value)
    return bool(value) and not path.is_absolute() and ".." not in path.parts


def validate_schema_instance(schema: dict[str, Any], value: dict[str, Any]) -> None:
    required = schema.get("required", [])
    require(all(key in value for key in required), f"schema required fields: {schema.get('$id')}")
    if schema.get("additionalProperties") is False:
        require(set(value) <= set(schema.get("properties", {})), f"schema extra fields: {schema.get('$id')}")
    for key, rules in schema.get("properties", {}).items():
        if key not in value:
            continue
        if "const" in rules:
            require(value[key] == rules["const"], f"schema const: {key}")
        if "enum" in rules:
            require(value[key] in rules["enum"], f"schema enum: {key}")


def synthetic_instantiation(contract: dict[str, Any]) -> dict[str, Any]:
    inventory = contract["payload_inventory"]
    payloads = {
        item["ordinal"]: SyntheticPayload(
            data=f"schema-fixture-{item['ordinal']}".encode(),
            logical_count=item["packed_length"],
        )
        for item in inventory
    }

    def decode(_payload: bytes, entry: dict[str, Any]) -> bytes:
        return f"decoded-{entry['ordinal']}".encode()

    binding = ExecutorBinding(
        AUTHORIZED_HEAD, AUTHORIZATION_SHA256,
        "GO — EXECUTE F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1",
        SHARD_SHA256, DECODER_LINEAGE_SHA256, inventory,
    )
    with tempfile.TemporaryDirectory() as temporary:
        state = Path(temporary) / "state"
        executor = RecoveryExecutor(
            state, binding, SyntheticShardProvider(payloads),
            DecoderPair(decode, decode, "synthetic-a", "synthetic-b", DECODER_LINEAGE_SHA256),
            MockOutputStage(contract["selected_expert_ids"]), mock_only=True,
        )
        terminal = executor.execute()
        samples = {
            "attempt": load(state / "attempt.json"),
            "execution_start": load(state / "execution-start.json"),
            "journal": load(state / "journal/01.json"),
            "terminal": terminal,
        }
        return {"terminal": terminal, "samples": samples}


def validate(root: Path, contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    auth_contract = auth.load_json(root / AUTH_CONTRACT)
    auth_evidence = auth.load_json(root / auth.EVIDENCE_PATH)
    auth.validate_documents(root, auth_contract, auth_evidence)
    require(canonical_sha256(auth_contract) == AUTHORIZATION_SHA256, "authorization identity")
    require(canonical_sha256(auth_contract["payload_inventory"]) == INVENTORY_SHA256, "inventory identity")
    require(contract.get("schema") == "pulsarmlx.f017.canonical-expert-recovery-execution-substrate-contract", "contract schema")
    require(contract.get("event_id") == EVENT_ID, "event identity")
    require(contract.get("starting_authoritative_head") == AUTHORIZED_HEAD, "starting head")
    require(contract.get("authorization_contract_sha256") == AUTHORIZATION_SHA256, "contract authorization")
    require(contract.get("dual_decoder_lineage_sha256") == DECODER_LINEAGE_SHA256, "contract decoder")
    require(contract.get("inventory_sha256") == INVENTORY_SHA256, "contract inventory")
    require(contract.get("access_contract") == {
        "expected_reads": 24, "expected_packed_bytes": 90_439_680,
        "maximum_shard_opens": 1, "ledger_before": 139,
        "successful_ledger_after": 163, "automatic_retry": False,
        "second_attempt_authorized": False,
    }, "access contract")
    source_sha = sha256_path(root / EXECUTOR)
    components = contract.get("component_bindings", {})
    expected_components = {
        "event_executor", "execution_start_writer", "attempt_record", "journal_writer",
        "ledger_writer_reconciler", "terminal_banker", "one_shard_open_guard",
        "retained_at_creation_writer", "dual_decoder_gate",
    }
    require(set(components) == expected_components, "component inventory")
    for name, binding in components.items():
        require(binding.get("implementation_path") == str(EXECUTOR), f"component path: {name}")
        require(binding.get("source_sha256") == source_sha, f"component source: {name}")
        require(binding.get("symbols"), f"component symbols: {name}")
    schemas: dict[str, dict[str, Any]] = {}
    for name, binding in contract.get("schema_bindings", {}).items():
        require(safe_relative(binding.get("path", "")), f"schema path: {name}")
        path = root / binding["path"]
        require(sha256_path(path) == binding.get("sha256"), f"schema identity: {name}")
        schemas[name] = load(path)
    require(set(schemas) == {"attempt", "execution_start", "journal", "terminal"}, "schema inventory")
    isolation = contract.get("test_isolation", {})
    require(isolation == {
        "mock_only_provider_required": True,
        "checkpoint_path_resolver_present": False,
        "checkpoint_basename_present_in_executor_source": False,
        "checkpoint_reads": 0, "shard_opens": 0,
        "real_payload_ledger_before": 139, "real_payload_ledger_after": 139,
    }, "test isolation")
    source = (root / EXECUTOR).read_text(encoding="utf-8")
    require("GLM-5.2-UD-IQ2_XXS" not in source and "symbolic_private_path" not in source, "real path firewall source")
    instantiated = synthetic_instantiation(auth_contract)
    for name, sample in instantiated["samples"].items():
        validate_schema_instance(schemas[name], sample)
    require(instantiated["terminal"]["ledger_after"] == 163, "synthetic terminal ledger")
    require(evidence.get("schema") == "pulsarmlx.f017.canonical-expert-recovery-execution-substrate-evidence", "evidence schema")
    require(evidence.get("contract_sha256") == canonical_sha256(contract), "contract canonical identity")
    require(evidence.get("executor_sha256") == source_sha, "executor identity")
    require(evidence.get("component_identities") == {
        name: canonical_sha256(binding) for name, binding in sorted(components.items())
    }, "component identities")
    require(evidence.get("failure_matrix") == {
        "required_cases": 24, "required_cases_passed": 24,
        "total_executor_tests": 27, "result": "PASS",
        "payload_source": "SYNTHETIC_COMPACT_FIXTURES_ONLY",
    }, "failure matrix")
    require(evidence.get("restart_semantics") == contract.get("restart_policy"), "restart semantics")
    require(evidence.get("isolation") == {
        "checkpoint_reads": 0, "shard_opens": 0,
        "real_payload_ledger_before": 139, "real_payload_ledger_after": 139,
        "real_expert_outputs_generated": 0, "event_executed": False,
    }, "evidence isolation")
    require(evidence.get("historical_immutability") == {
        "DPREFIX_REAL_1": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_2": "REJECTED_UNCHANGED",
        "DPREFIX_REAL_3": "REJECTED_UNCHANGED",
        "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
        "membership_1984_of_1984": "PASS_UNCHANGED",
        "coefficient_qualification": "FAIL_UNCHANGED_0_OF_8",
        "route_disposition": "ROUTE NOT PROVEN INVARIANT",
    }, "historical immutability")
    for item in evidence.get("artifact_bindings", []):
        require(safe_relative(item.get("path", "")), "artifact path")
        current = sha256_path(root / item["path"])
        expected = item.get("sha256")
        if current != expected:
            historical = subprocess.run(
                ["git", "show", f"06a4bafe7b4c1c6685c533e0e773eeb7bccde9c3:{item['path']}"],
                cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
            )
            require(historical.returncode == 0 and hashlib.sha256(historical.stdout).hexdigest() == expected,
                    f"artifact identity: {item.get('path')}")
    required_paths = {str(CONTRACT), str(EXECUTOR), str(EXECUTOR_TEST), str(VALIDATOR), str(VALIDATOR_TEST)} | {
        binding["path"] for binding in contract["schema_bindings"].values()
    }
    require({item["path"] for item in evidence.get("artifact_bindings", [])} == required_paths, "artifact inventory")
    serialized = json.dumps([contract, evidence], sort_keys=True)
    require(("/" + "Users/") not in serialized and "file://" not in serialized, "private path leak")
    ledger = load(root / LEDGER)
    real2 = [item for item in ledger.get("events", []) if item.get("attempt") == "DPREFIX-REAL-2"]
    require(len(real2) == 1 and real2[0].get("cumulative_tensor_payloads_after_event") == LEDGER_BEFORE,
            "substrate authorization ledger boundary")
    require(ledger.get("cumulative_tensor_payloads", 0) >= LEDGER_BEFORE, "real payload ledger")
    return {"result": "RECOVERY_EXECUTION_SUBSTRATE_VALID", "tests": 27, "ledger": 139, "checkpoint_reads": 0, "shard_opens": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    result = validate(root, load(root / CONTRACT), load(root / EVIDENCE))
    print("RECOVERY_EXECUTION_SUBSTRATE_VALID")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
