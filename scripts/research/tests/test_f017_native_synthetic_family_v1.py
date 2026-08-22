from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/qualify_f017_native_synthetic_family_v1.py"
SPEC = importlib.util.spec_from_file_location("f017_synthetic_family", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_seed_family_is_predeclared_and_covers_route_modes() -> None:
    rows = [MODULE.build(seed)[2] for seed in MODULE.SEEDS]
    assert MODULE.SEEDS == [17018, 17019, 17020, 17021, 17022, 17023]
    modes = {mode for row in rows for mode in row["route_modes"]}
    assert modes == {"VARIED_BY_LAYER", "EXACT_TIE_LOWER_ID", "NEAR_TIE_BIAS"}
    assert {row["layer_count"] for row in rows} == {1, 2, 3, 4}
    assert {row["top_k"] for row in rows} == {1, 2, 3}


def test_exact_route_tie_uses_lower_expert_ids() -> None:
    fixture, expected, _ = MODULE.build(17022)
    routed = [row for row in expected["layers"] if row["selected_expert_ids"]]
    assert routed
    assert all(row["selected_expert_ids"] == [0, 1] for row in routed)
    assert fixture["config"]["expert_top_k"] == 2


def test_output_projection_orientation_controls_argmax() -> None:
    fixture, expected, metadata = MODULE.build(17020)
    assert expected["selected_token"] == metadata["target_token"]
    changed = copy.deepcopy(fixture)
    hidden = changed["config"]["hidden"]
    changed["matrices"]["output.weight"]["values"] = [0.0] * len(
        changed["matrices"]["output.weight"]["values"]
    )
    assert MODULE.oracle(changed)["selected_token"] == 0
    assert MODULE.oracle(changed)["selected_token"] != expected["selected_token"]


def test_missing_layer_tensor_fails_closed() -> None:
    fixture, _, _ = MODULE.build(17021)
    del fixture["matrices"]["blk.3.attn_q_a.weight"]
    with pytest.raises(KeyError):
        MODULE.oracle(fixture)


def test_vector_shape_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="shape"):
        MODULE.compare_vector([1.0], [1.0, 2.0], "mutated")
