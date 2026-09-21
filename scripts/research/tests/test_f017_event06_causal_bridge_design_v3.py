#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts/research"
sys.path.insert(0, str(SCRIPTS))

from construct_f017_event06_causal_bridge_design_v3 import (  # noqa: E402
    construct_design_candidate_v3,
    mutation_campaign,
    witness_bytes,
)
from generate_f017_event06_causal_bridge_v3 import candidate_bytes  # noqa: E402
from validate_f017_event06_causal_bridge_v3 import (  # noqa: E402
    validate_causal_bridge_candidate_v3,
    validate_witness_instances,
)


def test_generator_check_and_independent_checker() -> None:
    subprocess.run([sys.executable, str(SCRIPTS / "generate_f017_event06_causal_bridge_v3.py"), "--check"], check=True)
    requirements, contract = candidate_bytes()
    report = validate_causal_bridge_candidate_v3(requirements, contract)
    assert report["node_count"] == 18
    assert report["edge_count"] == 34
    assert report["future_references"] == 0


def test_one_pass_constructibility_is_deterministic() -> None:
    _, contract = candidate_bytes()
    outputs = [witness_bytes(construct_design_candidate_v3(contract)) for _ in range(20)]
    assert len({hashlib.sha256(raw).hexdigest() for raw in outputs}) == 1
    assert validate_witness_instances(contract, outputs[0])["result"] == "PASS"


def test_successor_bridge_is_strictly_post_identity() -> None:
    _, contract_raw = candidate_bytes()
    contract = json.loads(contract_raw)
    order = [node["node_id"] for node in contract["nodes"]]
    assert order.index("PACKAGE_DURABLE_START") < order.index("V12_CHECKPOINT_IDENTITY_STAGE")
    assert order.index("V12_CHECKPOINT_IDENTITY_STAGE") < order.index("POST_IDENTITY_NUMERICAL_BRIDGE")
    pre_identity = contract["nodes"][: order.index("V12_CHECKPOINT_IDENTITY_STAGE")]
    forbidden = set(contract["pre_package_forbidden_fields"])
    assert all(not (set(node["required_fields"]) & forbidden) for node in pre_identity)


def test_exact_type_and_coercion_fail_closed() -> None:
    _, contract = candidate_bytes()
    witness = json.loads(witness_bytes(construct_design_candidate_v3(contract)))
    witness["instances"][0]["value"]["attempts"] = True
    witness["instances"][0]["sha256"] = hashlib.sha256(
        (json.dumps(witness["instances"][0]["value"], sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    raw = (json.dumps(witness, sort_keys=True, separators=(",", ":")) + "\n").encode()
    with pytest.raises(ValueError):
        validate_witness_instances(contract, raw)


def test_full_mutation_campaign() -> None:
    requirements, contract = candidate_bytes()
    witness = witness_bytes(construct_design_candidate_v3(contract))
    report = mutation_campaign(requirements, contract, witness)
    assert report["total"] >= 200
    assert report["passed"] == report["total"]
    assert report["unexpected_passes"] == 0


def test_no_production_or_checkpoint_imports() -> None:
    names = {
        "execute_f017_corrected_oracle_event_v12",
        "f017_checkpoint_identity_producer_v12",
        "f017_corrected_oracle_primary_numerics_v3",
        "f017_corrected_oracle_secondary_numerics_v3",
    }
    for filename in (
        "generate_f017_event06_causal_bridge_v3.py",
        "validate_f017_event06_causal_bridge_v3.py",
        "construct_f017_event06_causal_bridge_design_v3.py",
    ):
        source = (SCRIPTS / filename).read_text(encoding="utf-8")
        assert not any(f"import {name}" in source or f"from {name}" in source for name in names)
