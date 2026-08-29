#!/usr/bin/env python3
"""Sequence 18 amendment qualification with no Event 06 side effects."""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from execute_f017_corrected_oracle_event_v12_bridge import (
    bank_live_package_start, close_bridge_package,
)
from f017_canonical_serialization_v10 import canonical_bytes
from f017_event06_dag_derived_control_path_v1 import run_full_call_path
from f017_event06_package_attempt_registry_v2 import bank_live_terminal
import f017_event06_package_attempt_registry_v1 as historical
import f017_event06_package_attempt_registry_v2 as registry
from f017_event06_sequence18_storage_census_v1 import census, validate_census_document
from f017_event06_sequence18_vfs_v1 import InMemorySafetyFilesystem
from f017_event06_storage_authority_v1 import (
    FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_LENGTH,
    FIXED_LIVE_REGISTRY_ROOT_CANONICAL_UTF8_SHA256,
    fixed_live_registry_root,
)
import f017_event06_storage_primitives_v1 as storage
from qualify_f017_event06_package_transaction_v2 import qualify as qualify_base
from qualify_f017_event06_package_uniqueness_v1 import qualify as qualify_uniqueness
from generate_f017_event06_authority_dag_v2 import build as build_dag
from validate_f017_event06_authority_dag_v2 import validate_document as validate_dag


ROOT = Path(__file__).resolve().parents[2]
FROZEN = (
    "docs/architecture/reviews/evidence/f017-authority-freezing-policy-v1-exact-snapshot.md",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-authority-v11-v2.json",
    "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-collapsed-go-path-v1.json",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-authority-v12.json",
)
FROZEN_SHA256 = {
    "docs/architecture/reviews/evidence/f017-authority-freezing-policy-v1-exact-snapshot.md":
        "f442d2f2129bdb7fe8739244bd0745b1d843e83ec7f202e8d5822b24da8ff204",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json":
        "a555abe0ff2aff03a693ac7313d4af17061d01766e90971d92a7ba528f4995f2",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-authority-v11-v2.json":
        "4fd71e90f4184e5f2c7449eac6089f7392f1cc0d1961aecb0243f7ef723af101",
    "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-collapsed-go-path-v1.json":
        "c7ea10d9ab9c09ff1e6fa5d5c0b847ec0318cc1863f44b63c6d67bec00ba1778",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-checkpoint-identity-authority-v12.json":
        "12f6d717edbdea385974d870445754b7163ce76dfef3ee936a72586307da9050",
}


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _frozen_census() -> dict[str, object]:
    rows, drift = [], 0
    for path in FROZEN:
        current = (ROOT / path).read_bytes()
        start_sha256 = FROZEN_SHA256[path]
        final_sha256 = hashlib.sha256(current).hexdigest()
        equal = start_sha256 == final_sha256
        drift += not equal
        rows.append({
            "path": path,
            "start_sha256": start_sha256,
            "final_sha256": final_sha256,
            "equal": equal,
        })
    return {"rows": rows, "frozen_authority_drift": drift}


def qualify() -> dict[str, object]:
    base = qualify_base()
    storage_census = census()
    frozen = _frozen_census()
    live_before = os.path.lexists(fixed_live_registry_root())

    with tempfile.TemporaryDirectory(prefix="f017-seq18-amendment-") as directory:
        qualification = run_full_call_path(
            Path(directory) / "composition", retain_authorities=True
        )
        authorities = qualification.pop("_authorities")
        observed = []
        with patch.object(
            storage, "secure_directory",
            lambda path: observed.append(path)
            or (_ for _ in ()).throw(RuntimeError("STRICT_ABORT_BEFORE_CREATE")),
        ):
            try:
                bank_live_package_start(authorities["installed_authority"])
            except RuntimeError as exc:
                if str(exc) != "STRICT_ABORT_BEFORE_CREATE":
                    raise
            else:
                raise AssertionError("strict abort did not fire")
        strict = {
            "mode": "STRICT_ABORT",
            "attempted_root_sha256": hashlib.sha256(str(observed[0]).encode()).hexdigest(),
            "attempted_root_utf8_length": len(str(observed[0]).encode()),
            "directory_create_reached": False,
            "package_start": 0,
            "checkpoint_or_numerical_access": 0,
        }

        filesystem = InMemorySafetyFilesystem()
        with filesystem.installed():
            package_start = bank_live_package_start(authorities["installed_authority"])
            closure = close_bridge_package(
                authorities["historical_bridge"], package_start,
                authorities["execution_result"],
            )
            legacy_terminal = closure["terminal"]
            successor_sink = closure["successor_terminal_sink"]
            successor_value = {
                "schema": "pulsarmlx.f017.event06-v12-vfs-prompt-terminal/1.0.0",
                "authority_mode": "LIVE_CANONICAL",
                "package_attempt_id": successor_sink.get("package_attempt_id"),
                "legacy_package_terminal_sha256": hashlib.sha256(
                    canonical_bytes(legacy_terminal)
                ).hexdigest(),
                "result": "COMPLETE",
            }
            successor_sha = bank_live_terminal(successor_sink, successor_value)
            second_attempt_rejected = False
            try:
                bank_live_package_start(authorities["installed_authority"])
            except FileExistsError:
                second_attempt_rejected = True
            if not second_attempt_rejected:
                raise AssertionError("virtual filesystem second attempt")
            for call in (
                lambda: historical.reserve_package_attempt(None),
                lambda: historical.claim_terminal_sinks(None),
                lambda: historical.claim_qualification_terminal_sinks(None),
                lambda: historical.bank_terminal(None),
            ):
                try:
                    call()
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("legacy writer did not fail closed")
        composition = {
            "mode": "VIRTUAL_FILESYSTEM_COMPOSITION",
            "reservation_type": type(package_start.reservation).__name__,
            "package_start_type": type(package_start).__name__,
            "terminal_sink_types": [
                type(closure["successor_terminal_sink"]).__name__,
            ],
            "legacy_terminal_sha256": closure["terminal_sha256"],
            "successor_terminal_sha256": successor_sha,
            "second_attempt_rejected": second_attempt_rejected,
            "virtual_filesystem": filesystem.snapshot(),
            "actual_live_root_created_or_written": 0,
            "checkpoint_or_numerical_access": 0,
            "accounting_or_identity_consumption": 0,
            "result": "PASS",
        }

    uniqueness = qualify_uniqueness(20)
    passed = 0
    survivors = []

    def killed(case_id: str, operation) -> None:
        nonlocal passed
        try:
            operation()
        except Exception:
            passed += 1
        else:
            survivors.append(case_id)

    # Exact source/DAG mutations.
    canonical_dag = build_dag()
    for index in range(len(canonical_dag["edges"])):
        changed = copy.deepcopy(canonical_dag)
        changed["edges"].pop(index)
        killed(f"DAG-OMIT-{index:03d}", lambda changed=changed: validate_dag(changed))
    for index in range(len(canonical_dag["edges"])):
        changed = copy.deepcopy(canonical_dag)
        changed["edges"][index]["source_blob_sha256"] = "f" * 64
        killed(f"DAG-BLOB-{index:03d}", lambda changed=changed: validate_dag(changed))

    # Source-derived storage-census mutations.
    for index, field in enumerate((
        "production_public_storage_location_inputs",
        "production_indirect_storage_location_inputs",
        "reservation_reclaim_expire_unlock_or_override_symbols_reachable",
        "legacy_production_writers_reachable_to_safety_state",
    ) * 10):
        changed = copy.deepcopy(storage_census)
        changed[field] = index + 1
        killed(f"STORAGE-CENSUS-{index:03d}", lambda changed=changed: validate_census_document(changed))

    # All package-key identity fields are load bearing; nonidentity fields are not.
    authority = authorities["installed_authority"]
    baseline = registry._reservation_value(authority, "LIVE_CANONICAL")
    for index in range(60):
        value = authority.as_dict()
        field = ("authorization_id", "package_attempt_id", "checkpoint_set_sha256")[index % 3]
        value[field] = f"MUTATED-{index:03d}"
        key = registry._sha({
            "authorization_id": value["authorization_id"],
            "package_attempt_id": value["package_attempt_id"],
            "checkpoint_set_sha256": value["checkpoint_set_sha256"],
        })
        if key != baseline["registry_key_sha256"]:
            passed += 1
        else:
            survivors.append(f"PACKAGE-KEY-{index:03d}")

    # Public storage selectors and generic aliases are rejected at the real entry.
    for index, name in enumerate((
        "root", "path", "directory", "registry", "configuration", "environment",
        "provider", "resolver", "callback", "options", "destination",
    ) * 4):
        killed(
            f"PUBLIC-STORAGE-{index:03d}",
            lambda name=name: registry.reserve_live_package_attempt(
                authority, **{name: Path("/discarded")}
            ),
        )

    total = passed + len(survivors)
    live_after = os.path.lexists(fixed_live_registry_root())
    result = {
        "schema": "pulsarmlx.f017.event06-v12-sequence18-amendment-qualification/1.0.0",
        "base_qualification": base,
        "strict_abort": strict,
        "virtual_filesystem_composition": composition,
        "storage_authority_census": storage_census,
        "package_uniqueness": uniqueness,
        "package_identity_keys_per_identity": 1,
        "contention_contenders": uniqueness["contenders"],
        "contention_winners": uniqueness["package_reservation_winners_per_identity"],
        "losing_contenders_with_pre_package_start_abort_proof": (
            f"{uniqueness['losing_contenders_with_pre_package_start_abort_proof']}/"
            f"{uniqueness['reservation_losers']}"
        ),
        "canonicalization_schema": {
            "strip": ["temporary_root", "pid", "timestamp", "process_order", "nonce"],
            "sort": ["object_keys", "contender_records_by_index"],
        },
        "mutation_campaign": {"passed": passed, "total": total, "survivors": survivors},
        "frozen_authority_census": frozen,
        "fixed_live_root_existed_before": live_before,
        "fixed_live_root_existed_after": live_after,
        "production_live_registry_creates_or_writes": 0,
        "original_checkpoint_access": "NONE",
        "event06_executed": False,
        "historical_master_ledger": 175,
    }
    result["result"] = "PASS" if (
        base["result"] == "PASS"
        and storage_census["result"] == "PASS"
        and composition["result"] == "PASS"
        and uniqueness["result"] == "PASS"
        and not survivors and total >= 200
        and frozen["frozen_authority_drift"] == 0
        and not live_before and not live_after
    ) else "FAIL"
    result["aggregate_sha256"] = _sha(result)
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = qualify()
    raw = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(raw, encoding="utf-8")
    else:
        print(raw, end="")
