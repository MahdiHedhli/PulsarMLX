from __future__ import annotations

import copy
import pickle

import pytest
from unittest.mock import patch

from f017_event06_bridge_synthetic_fixture_v2 import runtime_fixture_values
from f017_event06_numerical_bridge_v2 import (
    PromptBoundConsumerViewV2, PromptBoundIdentityBridgeInputV2,
    ValidatedNumericalBridgeV2, consumer_view, derive_bridge,
    produce_identity_bridge_input,
)
from f017_event06_collapsed_live_installation_v2 import CollapsedLivePromptIdentityV2
import f017_event06_numerical_bridge_v1 as legacy
import f017_corrected_oracle_primary_wrapper_v12_bridge_v2 as primary_adapter
import f017_corrected_oracle_secondary_wrapper_v12_bridge_v2 as secondary_adapter


def test_exact_sealed_input_and_digest_continuity():
    bridge, bridge_input, event_identity, installed, _leases, _report, identity, plan = runtime_fixture_values()
    assert type(event_identity) is CollapsedLivePromptIdentityV2
    assert type(bridge_input) is PromptBoundIdentityBridgeInputV2
    assert type(bridge) is ValidatedNumericalBridgeV2
    assert bridge_input.get("event_identity_plan_sha256") == event_identity.source_sha256
    assert bridge_input.get("preparation_sha256") == event_identity.get("preparation_sha256")
    assert bridge_input.get("collapsed_go_sha256") == event_identity.get("collapsed_go_sha256")
    assert bridge_input.get("authority_mode") == event_identity.get("authority_mode")
    assert bridge.get("event_identity_plan_sha256") == event_identity.source_sha256
    assert bridge.legacy_bridge.get("event_identity_plan_sha256") == event_identity.source_sha256
    assert derive_bridge(bridge_input, installed, identity, plan).sha256 == bridge.sha256


@pytest.mark.parametrize("operation", ["copy", "deepcopy", "pickle"])
def test_sealed_authorities_are_immutable(operation):
    bridge, bridge_input, *_ = runtime_fixture_values()
    for value in (bridge_input, bridge):
        with pytest.raises(TypeError):
            {"copy": copy.copy, "deepcopy": copy.deepcopy,
             "pickle": pickle.dumps}[operation](value)


def test_mapping_and_lookalike_identity_are_rejected():
    bridge, bridge_input, _event_identity, installed, _leases, _report, identity, plan = runtime_fixture_values()
    with pytest.raises(TypeError):
        derive_bridge(bridge_input.as_dict(), installed, identity, plan)
    with pytest.raises(TypeError):
        produce_identity_bridge_input(bridge_input.as_dict(), installed, plan)
    assert bridge.legacy_bridge.sha256 != bridge.sha256


def test_prompt_bound_consumer_view():
    bridge, *_ = runtime_fixture_values()
    historical = legacy.numerical_view(bridge.legacy_bridge, "PRIMARY")
    view = consumer_view(bridge, "PRIMARY_NUMERICAL", historical)
    assert type(view) is PromptBoundConsumerViewV2
    assert view.get("event_identity_plan_sha256") == bridge.get("event_identity_plan_sha256")
    assert view.get("prompt_sha256") == bridge.get("prompt_sha256")
    with pytest.raises(TypeError):
        consumer_view(bridge, "PRIMARY_NUMERICAL", historical.immutable_view())


def test_versioned_wrappers_receive_prompt_bound_views():
    bridge, *_ = runtime_fixture_values()
    primary_numerical = consumer_view(
        bridge, "PRIMARY_NUMERICAL", legacy.numerical_view(bridge.legacy_bridge, "PRIMARY")
    )
    primary_result = consumer_view(
        bridge, "PRIMARY_RESULT", legacy.result_bundle_view(bridge.legacy_bridge, "PRIMARY", "1" * 64)
    )
    primary_calls = []
    with patch.object(primary_adapter, "_execute", lambda *args: primary_calls.append(args) or {"result": "PASS"}):
        assert primary_adapter.execute_bridge_and_bank(primary_numerical, primary_result, [], None)["result"] == "PASS"
    assert len(primary_calls) == 1
    assert type(primary_calls[0][0]) is legacy.ValidatedConsumerView

    from f017_event06_dag_derived_control_path_v1 import _synthetic_bundle
    bundle = _synthetic_bundle("PRIMARY", bridge.legacy_bridge)
    historical_primary = legacy.numerical_view(bridge.legacy_bridge, "PRIMARY")
    historical_result = legacy.result_bundle_view(
        bridge.legacy_bridge, "PRIMARY", "1" * 64
    )
    bundle_binding, _ = legacy.build_bundle_binding(
        historical_primary, historical_result, bundle["index"]
    )
    primary_binding = legacy.primary_terminal_binding(
        bundle, bridge.legacy_bridge, bundle_binding
    )
    secondary_numerical = consumer_view(
        bridge, "SECONDARY_NUMERICAL",
        legacy.numerical_view(bridge.legacy_bridge, "SECONDARY", primary_binding=primary_binding),
    )
    secondary_result = consumer_view(
        bridge, "SECONDARY_RESULT", legacy.result_bundle_view(bridge.legacy_bridge, "SECONDARY", "2" * 64)
    )
    secondary_calls = []
    with patch.object(secondary_adapter, "_execute", lambda *args: secondary_calls.append(args) or {"result": "PASS"}):
        assert secondary_adapter.execute_bridge_and_bank(secondary_numerical, secondary_result, [], None)["result"] == "PASS"
    assert len(secondary_calls) == 1
    assert type(secondary_calls[0][0]) is legacy.ValidatedConsumerView


def _primary_bundle():
    import hashlib
    from f017_canonical_serialization_v10 import canonical_bytes

    manifest = {"payloads": []}
    receipt = {}
    manifest_sha = hashlib.sha256(canonical_bytes(manifest)).hexdigest()
    receipt_sha = hashlib.sha256(canonical_bytes(receipt)).hexdigest()
    terminal_sha = "5" * 64
    terminal = {
        "schema": "pulsarmlx.f017.corrected-oracle-consumer-terminal/11.0.0",
        "role": "PRIMARY", "result": "COMPLETE",
        "result_terminal_sha256": terminal_sha,
        "result_receipt_sha256": receipt_sha,
        "payload_manifest_sha256": manifest_sha, "secondary_eligible": True,
    }
    return {"artifacts": {"consumer_terminal": terminal},
            "index": {"result_terminal_sha256": terminal_sha,
                      "result_receipt_sha256": receipt_sha,
                      "manifest_sha256": manifest_sha, "result": "PASS"},
            "result": "PASS"}
