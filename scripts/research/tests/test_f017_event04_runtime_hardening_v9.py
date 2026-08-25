from __future__ import annotations

import copy
import ast
import json
import hashlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))

from check_f017_descriptor_type_safety_v9 import _validate_descriptors as independent_validate
from f017_corrected_oracle_event_accounting_v9 import validate_snapshot
from f017_descriptor_lease_manager_v9 import LeaseRecord, LeaseSet, validate_descriptors
from f017_descriptor_lease_manager_v9 import acquire_synthetic_leases
from f017_event04_tensor_plan_v9 import build_plan, validate_plan
from f017_runtime_outcome_realizer_v9 import realize
from f017_canonical_serialization_v8 import bank_exclusive
from f017_synthetic_checkpoint_v9 import prepare
from execute_f017_corrected_oracle_event_v9 import execute_event04, _terminalize
import validate_f017_corrected_oracle_access_v9 as authorizer
from f017_memory_gate_v9 import THRESHOLD_BYTES
from f017_corrected_oracle_authorization_v9 import _memory_gate, parse_candidate_bytes, production_shards
from f017_canonical_serialization_v8 import canonical_bytes


def descriptors() -> list[dict]:
    return [{"device": 1, "inode": 1000 + ordinal, "mode": 0o100600, "size": 10 + ordinal,
             "mtime_ns": 1, "ctime_ns": 1, "shard_ordinal": ordinal, "role": "GRAPH_PAYLOAD",
             "lease_id": f"LEASE-F017-V9-UNIT-{ordinal}"} for ordinal in range(2, 7)]


def production_receipt(emergency: Path, fallback: Path) -> dict:
    return {"schema": "pulsarmlx.f017.corrected-oracle-installation-receipt/9.0.0", "authority": True,
            "installation_kind": "CANONICAL_EVENT04_NO_REPLACE", "authorization_id": "F017-EVENT04-AUTHORIZATION-04",
            "package_attempt_id": "F017-EVENT04-PACKAGE-04", "candidate_sha256": "0" * 64,
            "installed_sha256": "0" * 64, "installed_path": "/future/installed.json",
            "operator_approval_sha256": "1" * 64, "execution_readiness_declaration_sha256": "2" * 64,
            "emergency_evidence_root": str(emergency), "terminal_fallback_evidence_root": str(fallback),
            "candidate_install_bytes_equal": True, "result": "PASS"}


@pytest.mark.parametrize("value", [None, [], (), set(), 1, True, "", b""])
def test_non_dictionary_descriptors_fail_controlled(value: object) -> None:
    sample = descriptors(); sample[0] = value
    for validator in (validate_descriptors, independent_validate):
        with pytest.raises(ValueError): validator(copy.deepcopy(sample))


@pytest.mark.parametrize("value", [[], {}, set(), (), True, 1, 1.0, b"x", None])
def test_unhashable_or_non_string_lease_ids_fail_controlled(value: object) -> None:
    sample = descriptors(); sample[0]["lease_id"] = value
    for validator in (validate_descriptors, independent_validate):
        with pytest.raises(ValueError): validator(copy.deepcopy(sample))


def test_release_is_idempotent_and_continues_after_failure() -> None:
    handles = [os.open(__file__, os.O_RDONLY) for _ in range(5)]
    leases = LeaseSet([LeaseRecord(identity, descriptor) for identity, descriptor in zip(descriptors(), handles, strict=True)], "0" * 64, ["0" * 64] * 5)
    failed = set()
    def close(descriptor: int, lease_id: str) -> None:
        if lease_id.endswith("-4") and lease_id not in failed:
            failed.add(lease_id); raise OSError(5, "injected")
        os.close(descriptor)
    first = leases.release(close_function=close); second = leases.release(close_function=close, retry_failed=True); third = leases.release()
    assert first["attempted_closures"] == 5 and first["successful_closures"] == 4 and first["live_leases_after_release"] == 1
    assert second["attempted_closures"] == 1 and second["live_leases_after_release"] == 0
    assert third["attempted_closures"] == 0 and third["idempotent_noop"] is True


def test_release_continues_when_close_event_banking_fails_after_close() -> None:
    handles = [os.open(__file__, os.O_RDONLY) for _ in range(5)]
    leases = LeaseSet([LeaseRecord(identity, descriptor) for identity, descriptor in zip(descriptors(), handles, strict=True)], "0" * 64, ["0" * 64] * 5)
    failed = False
    def bank(event: dict) -> str:
        nonlocal failed
        if not failed:
            failed = True
            raise OSError(5, "injected close-event banking failure")
        return "1" * 64
    first = leases.release(event_function=bank)
    assert first["attempted_closures"] == 5 and first["successful_closures"] == 5
    assert first["live_leases_after_release"] == 0 and first["evidence_banking_failures"] == 1
    recovered = leases.release(event_function=bank)
    assert recovered["attempted_closures"] == 0 and recovered["evidence_banking_failures"] == 0
    assert recovered["result"] == "PASS" and all(record.close_attempt_count == 1 for record in leases.records)


def test_production_tensor_plan_exact_census() -> None:
    plan = validate_plan(build_plan())
    assert plan["graph_tensor_count"] == 1410 and plan["non_access_tensor_count"] == 399
    assert plan["graph_shards"] == [2, 3, 4, 5, 6]


def test_accounting_snapshot_fails_closed() -> None:
    expected = {"authorization": 0, "package": 1, "primary": 1, "secondary": 0, "historical_before": 175, "historical_after": 175}
    validate_snapshot(expected, expected)
    with pytest.raises(ValueError): validate_snapshot({**expected, "primary": 0}, expected)


def test_production_preparse_failure_is_terminalized_in_bound_fallback(tmp_path: Path) -> None:
    installed = tmp_path / "installed.json"; installed.write_bytes(b"not-json\n")
    fallback = tmp_path / "emergency"; fallback.mkdir(mode=0o700)
    terminal_fallback = tmp_path / "terminal-fallback"; terminal_fallback.mkdir(mode=0o700)
    receipt = tmp_path / "receipt.json"; receipt.write_bytes(canonical_bytes(production_receipt(fallback, terminal_fallback)))
    result = execute_event04(installed, receipt, tmp_path / "state", fallback, terminal_fallback)
    assert result["result"] == "CONTROLLED_FAILURE" and result["generic_fallback"] is True
    assert (fallback / "failure-terminal-capsule.json").is_file()
    assert result["terminal_evidence"]["target"] == "PRIMARY"


def test_production_terminalization_uses_second_bound_root_on_collision_or_symlink(tmp_path: Path) -> None:
    installed = tmp_path / "installed.json"; installed.write_bytes(b"not-json\n")
    emergency = tmp_path / "emergency"; emergency.mkdir(); (emergency / "failure-terminal-capsule.json").write_text("occupied")
    fallback = tmp_path / "terminal-fallback"; fallback.mkdir()
    receipt = tmp_path / "receipt.json"; receipt.write_bytes(canonical_bytes(production_receipt(emergency, fallback)))
    result = execute_event04(installed, receipt, tmp_path / "state", emergency, fallback)
    assert result["terminal_evidence"]["result"] == "PASS" and result["terminal_evidence"]["target"] == "FALLBACK"
    assert (fallback / "failure-terminal-capsule.json").is_file()

    second_target = tmp_path / "symlink-target"; second_target.mkdir()
    symlink = tmp_path / "symlink-emergency"; symlink.symlink_to(second_target, target_is_directory=True)
    second_fallback = tmp_path / "second-fallback"; second_fallback.mkdir()
    receipt.write_bytes(canonical_bytes(production_receipt(symlink, second_fallback)))
    result = execute_event04(installed, receipt, tmp_path / "second-state", symlink, second_fallback)
    assert result["terminal_evidence"]["target"] == "FALLBACK"
    assert not (second_target / "failure-terminal-capsule.json").exists()


def test_production_terminalization_rejects_replaced_symlink_ancestor(tmp_path: Path) -> None:
    base = tmp_path.resolve(); installed = base / "installed.json"; installed.write_bytes(b"not-json\n")
    approved_parent = base / "approved"; approved_parent.mkdir(); emergency = approved_parent / "emergency"; emergency.mkdir()
    fallback = base / "fallback"; fallback.mkdir()
    receipt = base / "receipt.json"; receipt.write_bytes(canonical_bytes(production_receipt(emergency, fallback)))
    emergency.rmdir(); approved_parent.rmdir()
    attacker_parent = base / "attacker"; attacker_parent.mkdir(); (attacker_parent / "emergency").mkdir()
    approved_parent.symlink_to(attacker_parent, target_is_directory=True)
    result = execute_event04(installed, receipt, base / "state", emergency, fallback)
    assert result["terminal_evidence"]["target"] == "FALLBACK"
    assert not (attacker_parent / "emergency" / "failure-terminal-capsule.json").exists()


def test_terminalization_releases_leases_when_no_evidence_root_is_usable() -> None:
    handles = [os.open(__file__, os.O_RDONLY) for _ in range(5)]
    leases = LeaseSet([LeaseRecord(identity, descriptor) for identity, descriptor in zip(descriptors(), handles, strict=True)],
                      "0" * 64, ["0" * 64] * 5)
    result = _terminalize(None, None, {}, ValueError("injected"), leases, "INTERNAL", "NONE",
                          root_authority_status="INSTALLATION_RECEIPT_UNREADABLE")
    assert result["release"]["attempted_closures"] == 5
    assert result["release"]["live_leases_after_release"] == 0
    assert result["terminal_evidence"]["result"] == "MAXIMAL_CONSTRUCTIBLE_NO_DURABLE_WRITE"
    assert result["terminal_evidence"]["errors"] == [
        {"target": "PRIMARY", "error": "INSTALLATION_RECEIPT_UNREADABLE"},
        {"target": "FALLBACK", "error": "INSTALLATION_RECEIPT_UNREADABLE"},
    ]


def test_modeled_failure_requires_independent_transition_observation() -> None:
    with tempfile.TemporaryDirectory() as raw:
        result = realize("PRIMARY_POST_START_FAILURE__AFTER_RANK_030", Path(raw) / "positive")
    assert result["failed_transition_id"] == "FAIL_PRIMARY_POST_START_FAILURE__AFTER_RANK_030"
    assert result["capsule_source"] == "COORDINATOR_CAUSAL_BANK_INJECTION"


def test_runtime_failure_realizer_is_not_generic() -> None:
    with tempfile.TemporaryDirectory() as raw:
        result = realize("PRIMARY_POST_START_FAILURE__AFTER_RANK_030", Path(raw) / "case")
    assert result["result"] == "PASS" and result["generic_fallback"] is False
    assert result["accounting"] == {"package": 1, "primary": 1, "secondary": 0}


def test_target_sources_have_no_graph_path_open_primitive() -> None:
    for name in ("f017_corrected_oracle_primary_target_source_v9.py", "f017_corrected_oracle_secondary_target_source_v9.py"):
        tree = ast.parse((RESEARCH / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert not (isinstance(node.func.value, ast.Name) and node.func.value.id == "os" and node.func.attr == "open")
                assert node.func.attr != "open"


def test_future_live_candidate_is_renderable_but_not_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = __import__("time").time_ns()
    observation = {"parser_version": "UNIT", "page_size_bytes": 16384, "pages_free": 0, "pages_inactive": 0,
                   "pages_speculative": 0, "pages_purgeable": 0, "available_bytes": THRESHOLD_BYTES,
                   "canonical_observation": "UNIT", "stdout_sha256": "0" * 64, "observed_at_unix_ns": now}
    monkeypatch.setattr(authorizer, "observe", lambda *, enforce: {"result": "PASS", "enforced": enforce,
                        "threshold_bytes": THRESHOLD_BYTES, "sample_age_ns": 0, "observation": observation})
    plan = Path("specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-production-tensor-plan-v9.json").resolve()
    readiness = tmp_path / "readiness.json"
    bank_exclusive(readiness, {"schema": "pulsarmlx.f017.event04-execution-readiness-declaration/9.0.0",
                               "F017_CORRECTED_ORACLE_EVENT04_EXECUTION_READINESS": "ACCEPTED",
                               "READY_FOR_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_04_EXECUTION_GO": "YES",
                               "ACTIVE_CORRECTED_ORACLE_GENERATION": "V9", "accepted_implementation_head": authorizer._implementation_head(),
                               "accepted_authority_manifest_sha256": authorizer._sha(authorizer.RUNTIME_MANIFEST), "accepted_at_unix_ns": now})
    approval = tmp_path / "approval.json"; shards = production_shards(); readiness_sha = hashlib.sha256(readiness.read_bytes()).hexdigest()
    bank_exclusive(approval, {"schema": "pulsarmlx.f017.corrected-oracle-event04-operator-approval/9.0.0",
        "result": "APPROVED_FOR_ONE_EVENT_04", "active_generation": "V9",
        "authorization_id": "F017-EVENT04-AUTHORIZATION-04", "package_attempt_id": "F017-EVENT04-PACKAGE-04",
        "primary_event_id": "F017-EVENT04-PRIMARY-04", "secondary_event_id": "F017-EVENT04-SECONDARY-04",
        "checkpoint_root": "/future/operator/approved/checkpoint", "shards": shards,
        "canonical_authorization_path": str(tmp_path / "canonical" / "authorization.json"),
        "installation_receipt_path": str(tmp_path / "canonical" / "receipt.json"),
        "emergency_evidence_root": str(tmp_path / "emergency"),
        "terminal_fallback_evidence_root": str(tmp_path / "terminal-fallback"),
        "authority_manifest_sha256": authorizer._sha(authorizer.RUNTIME_MANIFEST),
        "readiness_declaration_sha256": readiness_sha, "approved_at_unix_ns": now,
        "approval_expires_at_unix_ns": now + 60_000_000_000})
    output = tmp_path / "candidate.json"
    result = authorizer.render_operator_go_candidate(approval, readiness, plan, output)
    assert result["result"] == "PASS" and result["authority_created"] is False
    assert result["candidate"]["state"] == "OPERATOR_APPROVED_CANDIDATE" and result["candidate"]["live"] is False
    assert not Path(result["candidate"]["canonical_authorization_path"]).exists()
    delayed = copy.deepcopy(result["candidate"])
    delayed["mint_memory_gate"]["observation"]["observed_at_unix_ns"] -= 120_000_000_000
    assert parse_candidate_bytes(canonical_bytes(delayed))["scope"] == "PRODUCTION_EVENT_04"

    alias = Path("/tmp") / tmp_path.relative_to("/private/tmp") / "noncanonical" if str(tmp_path).startswith("/private/tmp/") else None
    if alias is not None and str(alias.resolve(strict=False)) != str(alias):
        alias_approval = json.loads(approval.read_bytes()); alias_approval["canonical_authorization_path"] = str(alias)
        alias_path = tmp_path / "alias-approval.json"; bank_exclusive(alias_path, alias_approval)
        with pytest.raises(ValueError, match="must be canonical"):
            authorizer.render_operator_go_candidate(alias_path, readiness, plan, tmp_path / "alias-candidate.json")

    bad_readiness_value = json.loads(readiness.read_bytes())
    bad_readiness_value["accepted_implementation_head"] = "0" * 40
    bad_readiness = tmp_path / "bad-readiness.json"; bank_exclusive(bad_readiness, bad_readiness_value)
    rebound_approval = json.loads(approval.read_bytes())
    rebound_approval["readiness_declaration_sha256"] = hashlib.sha256(bad_readiness.read_bytes()).hexdigest()
    rebound_path = tmp_path / "rebound-approval.json"; bank_exclusive(rebound_path, rebound_approval)
    with pytest.raises(ValueError, match="accepted implementation authority binding"):
        authorizer.render_operator_go_candidate(rebound_path, bad_readiness, plan, tmp_path / "bad-head-candidate.json")

    mutated = json.loads(output.read_bytes())
    mutated["canonical_authorization_path"] = str(alias) if alias is not None else "/tmp/../tmp/f017-noncanonical.json"
    mutated_path = tmp_path / "mutated-live-candidate.json"; mutated_path.write_bytes(canonical_bytes(mutated))
    assert parse_candidate_bytes(mutated_path.read_bytes())["scope"] == "PRODUCTION_EVENT_04"
    with pytest.raises(ValueError):
        authorizer.validate_live_candidate_for_install(mutated_path)


def test_complete_runtime_import_closure_is_byte_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest = json.loads(authorizer.RUNTIME_MANIFEST.read_bytes())
    bound_paths = {binding["path"] for binding in manifest["implementation"].values()}
    closure = authorizer._local_import_closure()
    assert "scripts/research/f017_canonical_serialization_v8.py" in closure
    assert len(closure) == 30 and closure.issubset(bound_paths)
    head = authorizer._implementation_head(); manifest_sha = authorizer._sha(authorizer.RUNTIME_MANIFEST)
    report = authorizer._validate_implementation_authority(head, manifest_sha)
    assert report["runtime_import_closure_count"] == 30
    original = Path.read_bytes
    target = (authorizer.ROOT / "scripts/research/f017_canonical_serialization_v8.py").resolve()
    def altered(path: Path) -> bytes:
        raw = original(path)
        return raw + b"# injected working-tree drift\n" if path.resolve() == target else raw
    monkeypatch.setattr(Path, "read_bytes", altered)
    with pytest.raises(ValueError, match="implementation byte binding"):
        authorizer._validate_implementation_authority(head, manifest_sha)


def test_absent_synthetic_root_normalizes_to_value_error() -> None:
    candidate = {"scope": "SYNTHETIC_QUALIFICATION", "live": False,
                 "checkpoint_root": "/definitely/absent/f017-v9-root"}
    with pytest.raises(ValueError, match="synthetic root resolution"):
        acquire_synthetic_leases(candidate)


def test_live_candidate_rejects_non_authoritative_shard_census(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Reuse the accepted renderer test as the positive control, then prove the
    # live parser rejects one changed size before any checkpoint access.
    gate = {"parser_version": "UNIT", "page_size_bytes": 16384, "pages_free": 0, "pages_inactive": 0,
            "pages_speculative": 0, "pages_purgeable": 0, "available_bytes": THRESHOLD_BYTES,
            "canonical_observation": "UNIT", "stdout_sha256": "0" * 64, "observed_at_unix_ns": __import__("time").time_ns()}
    value = {"schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/9.0.0",
        "state": "OPERATOR_APPROVED_CANDIDATE", "live": False, "scope": "PRODUCTION_EVENT_04", "authority_generation": 9,
        "authorization_id": "F017-EVENT04-AUTHORIZATION-04", "package_attempt_id": "F017-EVENT04-PACKAGE-04",
        "primary_event_id": "F017-EVENT04-PRIMARY-04", "secondary_event_id": "F017-EVENT04-SECONDARY-04",
        "causal_dag_sha256": "0"*64, "numerical_contract_sha256": "1"*64, "primary_numerical_sha256": "2"*64,
        "secondary_numerical_sha256": "3"*64, "checkpoint_root": "/future/checkpoint", "shards": production_shards(),
        "attempts": 1, "retries": 0, "resume": False, "active_generation": "V9", "synthetic_root_manifest_path": None,
        "synthetic_root_manifest_sha256": None, "tensor_catalog_path": "/future/plan", "tensor_catalog_sha256": "4"*64,
        "mint_memory_gate": {"result":"PASS","enforced":True,"threshold_bytes":THRESHOLD_BYTES,"sample_age_ns":0,"observation":gate},
        "operator_approval_path": "/future/approval", "operator_approval_sha256":"5"*64,
        "canonical_authorization_path":"/future/authorization", "installation_receipt_path":"/future/receipt",
        "emergency_evidence_root":"/future/emergency", "terminal_fallback_evidence_root":"/future/terminal-fallback",
        "authority_manifest_sha256":"6"*64,
        "execution_readiness_declaration_path":"/future/readiness", "execution_readiness_declaration_sha256":"7"*64}
    value["shards"][1]["size_bytes"] += 1
    with pytest.raises(ValueError, match="live checkpoint shard authority"):
        parse_candidate_bytes(canonical_bytes(value))


@pytest.mark.parametrize("gate", [None, [], {}, True, 1])
def test_live_candidate_malformed_memory_gate_fails_controlled(gate: object) -> None:
    value = {"schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/9.0.0",
        "state": "OPERATOR_APPROVED_CANDIDATE", "live": False, "scope": "PRODUCTION_EVENT_04", "authority_generation": 9,
        "authorization_id": "F017-EVENT04-AUTHORIZATION-04", "package_attempt_id": "F017-EVENT04-PACKAGE-04",
        "primary_event_id": "F017-EVENT04-PRIMARY-04", "secondary_event_id": "F017-EVENT04-SECONDARY-04",
        "causal_dag_sha256": "0"*64, "numerical_contract_sha256": "1"*64, "primary_numerical_sha256": "2"*64,
        "secondary_numerical_sha256": "3"*64, "checkpoint_root": "/future/checkpoint", "shards": production_shards(),
        "attempts": 1, "retries": 0, "resume": False, "active_generation": "V9", "synthetic_root_manifest_path": None,
        "synthetic_root_manifest_sha256": None, "tensor_catalog_path": "/future/plan", "tensor_catalog_sha256": "4"*64,
        "mint_memory_gate": gate, "operator_approval_path": "/future/approval", "operator_approval_sha256":"5"*64,
        "canonical_authorization_path":"/future/authorization", "installation_receipt_path":"/future/receipt",
        "emergency_evidence_root":"/future/emergency", "terminal_fallback_evidence_root":"/future/terminal-fallback",
        "authority_manifest_sha256":"6"*64,
        "execution_readiness_declaration_path":"/future/readiness", "execution_readiness_declaration_sha256":"7"*64}
    with pytest.raises(ValueError):
        parse_candidate_bytes(canonical_bytes(value))


@pytest.mark.parametrize("field,value", [("threshold_bytes", 0), ("threshold_bytes", True),
                                           ("sample_age_ns", -1), ("sample_age_ns", True),
                                           ("sample_age_ns", 60_000_000_001)])
def test_immutable_memory_gate_scalars_are_exact(field: str, value: object) -> None:
    now = __import__("time").time_ns()
    observation = {"parser_version": "UNIT", "page_size_bytes": 16384, "pages_free": 0, "pages_inactive": 0,
                   "pages_speculative": 0, "pages_purgeable": 0, "available_bytes": THRESHOLD_BYTES,
                   "canonical_observation": "UNIT", "stdout_sha256": "0" * 64, "observed_at_unix_ns": now}
    gate = {"result": "PASS", "enforced": True, "threshold_bytes": THRESHOLD_BYTES,
            "sample_age_ns": 0, "observation": observation}
    gate[field] = value
    with pytest.raises(ValueError, match="scalar binding"):
        _memory_gate(gate, live_posture=True)


def test_synthetic_manifest_catalog_binding_and_hardlinks_fail_closed(tmp_path: Path) -> None:
    package_root = tmp_path / "package"; package_root.mkdir()
    checkpoint, shards, catalog, manifest = prepare(package_root, 18101, "ISOLATION", True)
    candidate_path = tmp_path / "candidate.json"
    rendered = authorizer.render_rehearsal_candidate(checkpoint, shards, catalog, candidate_path, "ISOLATION",
                                                      scope="SYNTHETIC_QUALIFICATION", manifest_path=manifest)
    candidate = rendered["candidate"]
    manifest_value = json.loads(manifest.read_bytes()); manifest_value["catalog_sha256"] = "f" * 64
    manifest.write_bytes(canonical_bytes(manifest_value))
    candidate["synthetic_root_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="synthetic catalog binding"):
        acquire_synthetic_leases(candidate)

    # Restore the valid manifest binding and prove a second hardlink to any
    # shard makes the file-backed synthetic authority fail closed.
    manifest_value["catalog_sha256"] = candidate["tensor_catalog_sha256"]
    manifest.write_bytes(canonical_bytes(manifest_value))
    candidate["synthetic_root_manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    os.link(checkpoint / shards[1]["filename"], tmp_path / "hardlink-to-shard-2")
    with pytest.raises(ValueError, match="synthetic shard hardlink prohibited"):
        acquire_synthetic_leases(candidate)
