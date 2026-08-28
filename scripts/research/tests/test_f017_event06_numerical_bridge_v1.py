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
from f017_event06_bridge_synthetic_fixture_v1 import fixture_values
from f017_event06_numerical_bridge_v1 import (
    BRIDGE_KEYS, PHASES, ValidatedConsumerView, ValidatedNumericalBridge,
    accounting_view, build_bundle_binding, build_package_terminal,
    build_transition_binding, canonical_bridge_bytes, comparison_view,
    numerical_view, package_terminal_view, primary_terminal_binding, reconstruct_bridge,
    release_view, result_bundle_view, source_projection, validate_bridge_document,
    validate_consumer_view, validate_package_terminal,
    validate_transition_chain,
)
from execute_f017_corrected_oracle_event_v12_bridge import (
    PRODUCTION_CALL_PATH, validate_no_access_call_path, validate_transition_order,
)

def primary_bundle_fixture():
    manifest_sha, receipt_sha, result_terminal_sha = "1" * 64, "2" * 64, "3" * 64
    terminal = {"schema":"pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0",
        "role":"PRIMARY","result":"COMPLETE","result_terminal_sha256":result_terminal_sha,
        "result_receipt_sha256":receipt_sha,"payload_manifest_sha256":manifest_sha,"secondary_eligible":True}
    index = {"schema":"pulsarmlx.f017.corrected-oracle-result-bundle-index/11.0.0","role":"PRIMARY",
        "authorization_id":"F017-BRIDGE-AUTH-01","package_attempt_id":"F017-BRIDGE-PACKAGE-01",
        "consumer_event_id":"F017-BRIDGE-PRIMARY-01","manifest_sha256":manifest_sha,
        "top32_summary_sha256":"4"*64,"routing_manifest_sha256":"5"*64,
        "result_receipt_sha256":receipt_sha,"result_terminal_sha256":result_terminal_sha,
        "consumer_terminal_sha256":"6"*64,"payload_sha256s":["7"*64,"8"*64,"9"*64],"result":"PASS"}
    return {"artifacts":{"consumer_terminal":terminal},"index":index,"result":"PASS"}


def test_bridge_is_deterministic_and_reconstructible():
    bridge, *_ = fixture_values()
    raw = canonical_bridge_bytes(bridge)
    assert len(json.loads(raw)) == 42
    assert reconstruct_bridge(raw).sha256 == bridge.sha256
    assert all(fixture_values()[0].sha256 == bridge.sha256 for _ in range(20))


def test_sealed_authority_objects_reject_construction_copy_and_pickle():
    bridge, *_ = fixture_values()
    for constructor in (ValidatedExecutionPlan, ValidatedNumericalBridge, ValidatedConsumerView):
        with pytest.raises(TypeError): constructor()
    with pytest.raises(TypeError): copy.copy(bridge)
    with pytest.raises(TypeError): copy.deepcopy(bridge)
    with pytest.raises(TypeError): pickle.dumps(bridge)


def test_bridge_field_mutations_fail_closed():
    bridge, *_ = fixture_values(); value = json.loads(canonical_bridge_bytes(bridge))
    rejected = 0
    for key in sorted(BRIDGE_KEYS):
        missing = copy.deepcopy(value); missing.pop(key)
        wrong = copy.deepcopy(value); wrong[key] = None
        alias = copy.deepcopy(value); alias[f"alias_{key}"] = alias[key]
        for mutation in (missing, wrong, alias):
            with pytest.raises(Exception): validate_bridge_document(mutation)
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


def test_views_close_exact_consumer_authority():
    bridge, *_ = fixture_values()
    primary = numerical_view(bridge, "PRIMARY")
    primary_result = result_bundle_view(bridge, "PRIMARY", "a" * 64)
    fake_bundle = primary_bundle_fixture()
    binding_doc, binding_sha = build_bundle_binding(primary, primary_result, fake_bundle["index"])
    primary_gate = primary_terminal_binding(fake_bundle, bridge.sha256, binding_sha)
    secondary = numerical_view(bridge, "SECONDARY", primary_binding=primary_gate)
    secondary_result = result_bundle_view(bridge, "SECONDARY", "b" * 64)
    _, descriptors = source_projection(primary)
    assert len(descriptors) == 5
    assert set(source_projection(primary)[0]) == {"shards","tensor_catalog_path","tensor_catalog_sha256"}
    assert secondary.get("primary_terminal")["secondary_eligible"] is True
    assert secondary_result.get("bridge_sha256") == bridge.sha256
    compare = comparison_view(bridge, binding_sha, "c" * 64)
    release = release_view(bridge, "d" * 64)
    accounting = accounting_view(bridge, "e" * 64)
    terminal_view = package_terminal_view(bridge, "1" * 64, "2" * 64, "3" * 64)
    terminal = build_package_terminal(terminal_view)
    assert validate_package_terminal(terminal, bridge) == hashlib.sha256(canonical_bytes(terminal)).hexdigest()
    for view in (primary, primary_result, secondary, secondary_result, compare, release, accounting, terminal_view):
        assert view.get("bridge_sha256") == bridge.sha256
    assert binding_doc["bridge_sha256"] == bridge.sha256


def test_transition_chain_is_exact_and_mutation_closed():
    bridge, *_ = fixture_values(); predecessor = "0" * 64; records = []
    for index, phase in enumerate(PHASES):
        record, predecessor = build_transition_binding(bridge, phase, f"KIND-{index}", f"{index+1:x}" * 64, predecessor)
        records.append(record)
    assert validate_transition_chain(bridge, records) == predecessor
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
