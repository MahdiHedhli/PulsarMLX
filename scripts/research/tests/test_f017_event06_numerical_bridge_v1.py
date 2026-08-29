from __future__ import annotations

import copy
import hashlib
import json
import pickle

import pytest

from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import validate_candidate_bytes
from f017_checkpoint_identity_lifecycle_v12 import IdentityAuthorityError
from f017_corrected_oracle_primary_wrapper_v11 import validate_candidate_document as validate_primary_v11
from f017_corrected_oracle_secondary_wrapper_v11 import validate_candidate_document as validate_secondary_v11
from f017_event06_execution_plan_v1 import ValidatedExecutionPlan, validate_execution_plan
from f017_event06_bridge_synthetic_fixture_v1 import fixture_values, runtime_fixture_values
from f017_event06_package_attempt_registry_v2 import (
    claim_qualification_terminal_sinks,
    reserve_qualification_package_attempt,
)
from f017_event06_storage_authority_v1 import fixed_live_registry_root
from f017_event06_numerical_bridge_v1 import (
    BRIDGE_KEYS, PHASES, ValidatedConsumerView, ValidatedNumericalBridge,
    accounting_view, bind_identity_stage, bind_v11_closure, build_accounting_binding, build_bundle_binding,
    build_comparison_binding, build_package_terminal, build_release_binding,
    build_transition_binding, canonical_bridge_bytes, comparison_view,
    bundle_kwargs, numerical_view, package_terminal_view, primary_terminal_binding, reconstruct_bridge,
    release_view, result_bundle_view, source_projection,
    validate_package_terminal,
    validate_transition_chain,
)
from execute_f017_corrected_oracle_event_v12_bridge import (
    PRODUCTION_CALL_PATH, ValidatedBridgeExecutionResult, ValidatedDurableStart,
    bank_qualification_package_start, close_bridge_package, validate_no_access_call_path,
    validate_transition_order,
)
from qualify_f017_event06_bridge_call_path_v2 import _release_report, qualify_call_path

def primary_bundle_fixture(role="PRIMARY"):
    manifest_sha, receipt_sha, result_terminal_sha = "1" * 64, "2" * 64, "3" * 64
    terminal = {"schema":"pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0",
        "role":role,"result":"COMPLETE","result_terminal_sha256":result_terminal_sha,
        "result_receipt_sha256":receipt_sha,"payload_manifest_sha256":manifest_sha,"secondary_eligible":role == "PRIMARY"}
    event = "PRIMARY" if role == "PRIMARY" else "SECONDARY"
    index = {"schema":"pulsarmlx.f017.corrected-oracle-result-bundle-index/11.0.0","role":role,
        "authorization_id":"F017-BRIDGE-AUTH-01","package_attempt_id":"F017-BRIDGE-PACKAGE-01",
        "consumer_event_id":f"F017-BRIDGE-{event}-01","manifest_sha256":manifest_sha,
        "top32_summary_sha256":"4"*64,"routing_manifest_sha256":"5"*64,
        "result_receipt_sha256":receipt_sha,"result_terminal_sha256":result_terminal_sha,
        "consumer_terminal_sha256":"6"*64,"payload_sha256s":["7"*64,"8"*64,"9"*64],"result":"PASS"}
    return {"artifacts":{"consumer_terminal":terminal},"index":index,"result":"PASS"}


def _closure_fixture():
    def role(symbols):
        return {
            "manifest_sha256": symbols[0] * 64,
            "receipt_sha256": symbols[1] * 64,
            "terminal_sha256": symbols[2] * 64,
            "result_terminal_sha256": symbols[3] * 64,
            "routing_manifest_sha256": symbols[4] * 64,
            "payload_sha256s": [symbol * 64 for symbol in symbols[5:]],
        }
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-package-result-closure/11.0.0",
        "primary": role("12345678"),
        "secondary": role("9abcdef0"),
        "comparison": {"summary_sha256": "1" * 64,
                       "receipt_sha256": "2" * 64,
                       "terminal_sha256": "3" * 64},
        "release": {"start_sha256": "4" * 64, "report_sha256": "5" * 64,
                    "receipt_sha256": "6" * 64, "terminal_sha256": "7" * 64},
        "package_receipt_sha256": "8" * 64,
        "payload_count": 6,
        "result": "COMPLETE",
    }


def test_bridge_is_deterministic_and_reconstructible():
    bridge, *_ = fixture_values()
    raw = canonical_bridge_bytes(bridge)
    assert len(json.loads(raw)) == 42
    assert reconstruct_bridge(raw, bridge.sha256).sha256 == bridge.sha256
    with pytest.raises(ValueError): reconstruct_bridge(raw, "f" * 64)
    assert all(fixture_values()[0].sha256 == bridge.sha256 for _ in range(20))


def test_sealed_authority_objects_reject_construction_copy_and_pickle():
    import f017_event06_numerical_bridge_v1 as bridge_module
    bridge, *_ = fixture_values()
    assert not hasattr(bridge_module, "validate_consumer_view")
    for constructor in (ValidatedExecutionPlan, ValidatedNumericalBridge, ValidatedConsumerView):
        with pytest.raises(TypeError): constructor()
    with pytest.raises(TypeError): copy.copy(bridge)
    with pytest.raises(TypeError): copy.deepcopy(bridge)
    with pytest.raises(TypeError): pickle.dumps(bridge)
    with pytest.raises(TypeError): bridge._items = ()
    with pytest.raises(TypeError): bridge.sha256 = "0" * 64
    with pytest.raises(TypeError): del bridge.sha256
    with pytest.raises(TypeError): ValidatedBridgeExecutionResult()
    with pytest.raises(TypeError): ValidatedDurableStart()
    with pytest.raises(ValueError): close_bridge_package(bridge, {}, {})


def test_bridge_field_mutations_fail_closed():
    bridge, *_ = fixture_values(); value = json.loads(canonical_bridge_bytes(bridge))
    rejected = 0
    for key in sorted(BRIDGE_KEYS):
        missing = copy.deepcopy(value); missing.pop(key)
        wrong = copy.deepcopy(value); wrong[key] = None
        alias = copy.deepcopy(value); alias[f"alias_{key}"] = alias[key]
        for mutation in (missing, wrong, alias):
            with pytest.raises(Exception): reconstruct_bridge(canonical_bytes(mutation), bridge.sha256)
            rejected += 1
    assert rejected == 126


def test_plan_field_mutations_fail_closed():
    *_, value = fixture_values(); rejected = 0
    for key in sorted(value):
        for mutation in (lambda v,k: v.pop(k), lambda v,k: v.update({k:None}),
                         lambda v,k: v.update({f"alias_{k}":v[k]})):
            changed = copy.deepcopy(value); mutation(changed, key)
            with pytest.raises(Exception): validate_execution_plan(changed)
            rejected += 1
    assert rejected >= 75


def test_views_close_exact_consumer_authority(tmp_path):
    bridge, installed, *_ = fixture_values()
    primary = numerical_view(bridge, "PRIMARY")
    primary_result = result_bundle_view(bridge, "PRIMARY", "a" * 64)
    fake_bundle = primary_bundle_fixture()
    binding_doc, binding_sha = build_bundle_binding(primary, primary_result, fake_bundle["index"])
    primary_gate = primary_terminal_binding(fake_bundle, bridge, binding_doc)
    secondary = numerical_view(bridge, "SECONDARY", primary_binding=primary_gate)
    secondary_result = result_bundle_view(bridge, "SECONDARY", "b" * 64)
    _, descriptors = source_projection(primary)
    assert len(descriptors) == 5
    assert set(source_projection(primary)[0]) == {"shards","tensor_catalog_path","tensor_catalog_sha256"}
    assert secondary.get("primary_terminal")["secondary_eligible"] is True
    assert secondary_result.get("bridge_sha256") == bridge.sha256
    secondary_bundle = primary_bundle_fixture("SECONDARY")
    secondary_binding, _ = build_bundle_binding(secondary, secondary_result, secondary_bundle["index"])
    compare = comparison_view(bridge, binding_doc, secondary_binding)
    summary = {"schema":"pulsarmlx.f017.corrected-oracle-binary-comparison-summary/11.0.0",
        "authorization_id":bridge.get("authorization_id"),
        "package_attempt_id":bridge.get("package_attempt_id"),
        "classification":"EXACT_EXPECTED_TOKEN_STABLE"}
    comparison_binding, _ = build_comparison_binding(compare, summary)
    release = release_view(bridge, comparison_binding)
    release_binding, _ = build_release_binding(release, _release_report(bridge.get("package_attempt_id")))
    accounting = accounting_view(bridge, release_binding)
    accounting_binding, _ = build_accounting_binding(accounting, release_binding)
    assert accounting_binding.get("authorization_delta") == 0
    assert accounting_binding.get("package_delta") == 1
    predecessor = "0" * 64; records = []
    for index, phase in enumerate(PHASES):
        record, predecessor = build_transition_binding(
            bridge, phase, f"KIND-{index}", f"{index + 1:x}" * 64, predecessor
        )
        records.append(record)
    chain = validate_transition_chain(bridge, records)
    closure = _closure_fixture()
    closure_binding = bind_v11_closure(bridge, closure, accounting_binding)
    terminal_view = package_terminal_view(bridge, chain, closure_binding, accounting_binding)
    reservation = reserve_qualification_package_attempt(
        installed, tmp_path / "package-attempt-registry"
    )
    assert reservation.get("authority_mode") == "QUALIFICATION_ONLY"
    with pytest.raises(ValueError, match="intersects live registry"):
        reserve_qualification_package_attempt(installed, fixed_live_registry_root())
    with pytest.raises(FileExistsError):
        reserve_qualification_package_attempt(
            installed, tmp_path / "package-attempt-registry"
        )
    terminal_sink, _ = claim_qualification_terminal_sinks(
        reservation, bridge, terminal_view
    )
    terminal, terminal_sha = build_package_terminal(
        terminal_view, bridge, terminal_sink
    )
    assert terminal_sha == validate_package_terminal(terminal, bridge, terminal_sink)
    assert terminal_sha == hashlib.sha256(canonical_bytes(terminal)).hexdigest()
    with pytest.raises(FileExistsError):
        build_package_terminal(terminal_view, bridge, terminal_sink)
    changed_records = [dict(record) for record in records]
    changed_records[-1]["subject_sha256"] = "e" * 64
    changed_chain = validate_transition_chain(bridge, changed_records)
    changed_view = package_terminal_view(
        bridge, changed_chain, closure_binding, accounting_binding
    )
    with pytest.raises(TypeError, match="terminal sink"):
        build_package_terminal(changed_view, bridge, terminal_sink)
    for view in (primary, primary_result, secondary, secondary_result, compare, release, accounting, terminal_view):
        assert view.get("bridge_sha256") == bridge.sha256
    assert binding_doc.get("bridge_sha256") == bridge.sha256
    for left, right in (
        (binding_doc.as_dict(), secondary_binding.as_dict()),
        (binding_doc, binding_doc),
        (secondary_binding, secondary_binding),
        (secondary_binding, binding_doc),
    ):
        with pytest.raises((TypeError, ValueError)):
            comparison_view(bridge, left, right)
    with pytest.raises(TypeError):
        release_view(bridge, comparison_binding.as_dict())
    with pytest.raises(TypeError):
        accounting_view(bridge, release_binding.as_dict())
    with pytest.raises(TypeError):
        package_terminal_view(bridge, chain, closure_binding, accounting_binding.as_dict())


def test_bundle_binding_requires_exact_producer_kinds_and_authority_mode():
    bridge, *_ = fixture_values()
    numerical = numerical_view(bridge, "PRIMARY")
    result = result_bundle_view(bridge, "PRIMARY", "a" * 64)
    production = primary_bundle_fixture()["index"]
    with pytest.raises(TypeError):
        build_bundle_binding(result, result, production)
    with pytest.raises(ValueError):
        build_bundle_binding(numerical, result, production, "QUALIFICATION_ONLY")


def test_durable_start_terminalization_is_one_shot(tmp_path):
    from f017_event06_sequence14_fixture_v1 import build_sequence14_qualification
    package = build_sequence14_qualification(
        tmp_path / "qualification", now_unix_ns=4_000_000_000_000_000_000
    )
    start = bank_qualification_package_start(
        package["installed"], tmp_path / "package-attempt-registry"
    )
    start.claim_terminalization()
    with pytest.raises(RuntimeError):
        start.claim_terminalization()


def test_transition_chain_is_exact_and_mutation_closed():
    bridge, *_ = fixture_values(); predecessor = "0" * 64; records = []
    for index, phase in enumerate(PHASES):
        record, predecessor = build_transition_binding(bridge, phase, f"KIND-{index}", f"{index+1:x}" * 64, predecessor)
        records.append(record)
    assert validate_transition_chain(bridge, records).get("chain_head_sha256") == predecessor
    for index in range(len(records)):
        changed = copy.deepcopy(records); changed[index]["bridge_sha256"] = "f" * 64
        with pytest.raises(ValueError): validate_transition_chain(bridge, changed)


def test_legacy_admission_is_not_widened():
    bridge, *_ = fixture_values(); document = json.loads(canonical_bridge_bytes(bridge))
    with pytest.raises(ValueError): validate_primary_v11(document)
    with pytest.raises(ValueError): validate_secondary_v11(document)
    with pytest.raises(IdentityAuthorityError): validate_candidate_bytes(canonical_bytes(document))


def test_complete_no_access_call_path_and_order():
    report = validate_no_access_call_path()
    assert report["result"] == "PASS"
    assert report["checkpoint_root_resolved"] is False
    assert report["checkpoint_opens"] == report["numerical_operations"] == report["event06_ids_consumed"] == 0
    assert validate_transition_order(list(PRODUCTION_CALL_PATH))["result"] == "PASS"
    for mutation in (list(PRODUCTION_CALL_PATH[:-1]), list(reversed(PRODUCTION_CALL_PATH)),
                     list(PRODUCTION_CALL_PATH) + ["PRIMARY_SINGLE_CALL"]):
        with pytest.raises(ValueError): validate_transition_order(mutation)


def test_real_identity_producer_adapter_is_exact_and_owner_bound():
    expected, installed, leases, report, _plan, _event_plan = runtime_fixture_values()
    identity = bind_identity_stage(installed, leases, report)
    assert identity.get("lease_owner") == identity.get("package_attempt_id")
    assert identity.get("access_census_sha256") == report["evidence"]["access_journal_sha256"]
    assert expected.get("descriptor_identity_sha256") == identity.get("descriptor_identity_sha256")
    for mutation in (
        lambda value: value["evidence"].pop("access_journal_sha256"),
        lambda value: value.update({"checkpoint_shard_opens":5}),
        lambda value: value.update({"descriptor_identities":list(reversed(value["descriptor_identities"]))}),
    ):
        changed = copy.deepcopy(report); mutation(changed)
        with pytest.raises(ValueError): bind_identity_stage(installed, leases, changed)


def test_foreign_lease_owner_and_direct_bundle_mapping_fail_closed():
    bridge, *_ = fixture_values(); document = json.loads(canonical_bridge_bytes(bridge))
    document["lease_owner"] = "TOTALLY-DIFFERENT-OWNER"
    with pytest.raises(ValueError): reconstruct_bridge(canonical_bytes(document), bridge.sha256)
    with pytest.raises(TypeError): bundle_kwargs({})


def test_valid_execution_plan_substitutions_break_installed_event_plan_binding():
    _bridge, installed, identity, _plan, event_plan, plan_value = fixture_values()
    for key in (
        "source_head", "source_tree", "implementation_measurement_sha256",
        "tensor_catalog_sha256", "primary_numerical_sha256", "secondary_numerical_sha256",
        "numerical_contract_sha256", "result_authority_sha256",
        "result_bundle_builder_sha256", "comparison_authority_sha256",
        "release_authority_sha256", "accounting_authority_sha256",
        "primary_target_source_sha256", "secondary_target_source_sha256",
    ):
        changed = copy.deepcopy(plan_value)
        changed[key] = ("f" if changed[key] != "f" * len(changed[key]) else "e") * len(changed[key])
        substituted = validate_execution_plan(changed)
        with pytest.raises(ValueError):
            from f017_event06_numerical_bridge_v1 import derive_bridge
            derive_bridge(installed, identity, substituted, event_plan)


def test_production_coordinator_is_instantiated_with_release_on_all_modeled_paths():
    result = qualify_call_path()
    assert result["production_coordinator_instantiated"] == "PASS"
    assert result["primary_calls"] == result["secondary_calls"] == 1
    assert result["success_release_passes"] == 1
    assert result["failure_release_paths"] == 4
    assert result["comparison_release_accounting_chain"] == "PASS"
    assert result["original_checkpoint_access"] == result["numerical_operations"] == 0
