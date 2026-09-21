from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"
sys.path.insert(0, str(RESEARCH))

import f017_corrected_oracle_primary_numerics_v2 as primary_v2
import f017_corrected_oracle_primary_numerics_v3 as primary_v3
import f017_corrected_oracle_secondary_numerics_v2 as secondary_v2
import f017_corrected_oracle_secondary_numerics_v3 as secondary_v3
from generate_f017_corrected_oracle_fixtures import fixture
from validate_f017_numerical_output_interface_implementation_v1 import validate_output_object


def primary_case(seed: int):
    document = fixture(seed)
    geometry2 = primary_v2.Geometry.from_json(document["geometry"])
    geometry3 = primary_v3.Geometry.from_json(document["geometry"])
    old = primary_v2.execute(primary_v2.JsonSource(document["tensors"]), geometry2, document["token"], document["position"])
    new = primary_v3.execute(primary_v3.JsonSource(document["tensors"]), geometry3, document["token"], document["position"])
    output = primary_v3.execute_outputs(primary_v3.JsonSource(document["tensors"]), geometry3, document["token"], document["position"])
    return document, old, new, output


def secondary_case(seed: int):
    document = fixture(seed)
    return document, secondary_v2.execute(document), secondary_v3.execute(document), secondary_v3.execute_outputs(document)


def test_implementation_validator_passes() -> None:
    subprocess.run([sys.executable, str(RESEARCH / "validate_f017_numerical_output_interface_implementation_v1.py")], cwd=ROOT, check=True)


def test_complete_numerical_authority_v4_passes() -> None:
    subprocess.run([sys.executable, str(RESEARCH / "validate_f017_corrected_oracle_numerical_authority_v4.py")], cwd=ROOT, check=True)


@pytest.mark.parametrize("seed", [18101, 18103, 18104, 18106, 17018, 17023])
def test_legacy_results_and_payload_hashes_are_exact(seed: int) -> None:
    document, old, new, output = primary_case(seed)
    assert old == new
    validate_output_object(output, "PRIMARY", document["geometry"]["hidden"], document["geometry"]["vocab"])
    assert hashlib.sha256(output.final_hidden_payload).hexdigest() == old["final_hidden_sha256"]
    assert hashlib.sha256(output.final_normalized_payload).hexdigest() == old["final_norm_sha256"]
    assert hashlib.sha256(output.full_logits_payload).hexdigest() == old["full_logits_sha256"]
    assert list(struct.iter_unpack("<d", output.full_logits_payload)) == [(value,) for value in old["full_logits"]]

    document, old, new, output = secondary_case(seed)
    assert old == new
    validate_output_object(output, "SECONDARY", document["geometry"]["hidden"], document["geometry"]["vocab"])
    assert hashlib.sha256(output.final_hidden_payload).hexdigest() == old["final_hidden_sha256"]
    assert hashlib.sha256(output.final_normalized_payload).hexdigest() == old["final_norm_sha256"]
    assert hashlib.sha256(output.full_logits_payload).hexdigest() == old["full_logits_sha256"]
    assert list(struct.iter_unpack("<f", output.full_logits_payload)) == [(value,) for value in old["full_logits"]]


@pytest.mark.parametrize("module,role,seed", [
    (primary_v3, "PRIMARY", 18103),
    (secondary_v3, "SECONDARY", 18104),
])
def test_one_execution_payloads_match_the_same_internal_state(module, role: str, seed: int, monkeypatch) -> None:
    observed = []
    original = module._execute_graph

    def capture(*args, **kwargs):
        state = original(*args, **kwargs)
        observed.append(state)
        return state

    monkeypatch.setattr(module, "_execute_graph", capture)
    document = fixture(seed)
    if role == "PRIMARY":
        geometry = module.Geometry.from_json(document["geometry"])
        output = module.execute_outputs(module.JsonSource(document["tensors"]), geometry, document["token"], document["position"])
        hidden = tuple(value[0] for value in struct.iter_unpack("<d", output.final_hidden_payload))
        normalized = tuple(value[0] for value in struct.iter_unpack("<d", output.final_normalized_payload))
        logits = tuple(value[0] for value in struct.iter_unpack("<d", output.full_logits_payload))
        assert hidden == tuple(observed[0].hidden)
        assert normalized == tuple(observed[0].final_normalized)
        assert logits == tuple(observed[0].logits)
    else:
        output = module.execute_outputs(document)
        hidden = tuple(value[0] for value in struct.iter_unpack("<f", output.final_hidden_payload))
        normalized = tuple(value[0] for value in struct.iter_unpack("<f", output.final_normalized_payload))
        logits = tuple(value[0] for value in struct.iter_unpack("<f", output.full_logits_payload))
        assert hidden == tuple(float(value) for value in observed[0].hidden)
        assert normalized == tuple(float(value) for value in observed[0].final_normalized)
        assert logits == tuple(float(value) for value in observed[0].logits)
    assert len(observed) == 1
    assert output.core_execution_count == 1


@pytest.mark.parametrize("role,case", [("PRIMARY", primary_case), ("SECONDARY", secondary_case)])
def test_output_objects_are_deeply_immutable_and_control_json_rejects(role: str, case) -> None:
    document, _, _, output = case(18101)
    with pytest.raises(dataclasses.FrozenInstanceError):
        output.selected_token = 0
    with pytest.raises(TypeError):
        memoryview(output.full_logits_payload)[0] = 0
    with pytest.raises(TypeError):
        json.dumps(output)
    copied = dataclasses.asdict(output)
    copied["selected_token"] = -1
    assert output.selected_token >= 0
    assert type(output.layer_captures) is tuple
    assert type(output.top_32) is tuple
    validate_output_object(output, role, document["geometry"]["hidden"], document["geometry"]["vocab"])


def test_sixty_distinct_payload_geometry_mutations_fail_closed() -> None:
    document, _, _, output = primary_case(18101)
    fields = ("final_hidden_payload", "final_normalized_payload", "full_logits_payload")
    rejected = []
    for field in fields:
        payload = getattr(output, field)
        for width in range(1, 11):
            mutations = (
                (f"{field}_SHORT_{width}", dataclasses.replace(output, **{field: payload[:-width]})),
                (f"{field}_EXTRA_{width}", dataclasses.replace(output, **{field: payload + bytes([width]) * width})),
            )
            for mutation_id, mutated in mutations:
                with pytest.raises(ValueError):
                    validate_output_object(mutated, "PRIMARY", document["geometry"]["hidden"], document["geometry"]["vocab"])
                rejected.append(mutation_id)
    assert len(rejected) == 60
    assert len(set(rejected)) == 60
