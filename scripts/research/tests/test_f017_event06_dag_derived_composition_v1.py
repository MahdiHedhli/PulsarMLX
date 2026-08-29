from __future__ import annotations

import tempfile
from pathlib import Path

from f017_event06_dag_derived_control_path_v1 import EDGE_IDS, run_full_call_path
from qualify_f017_event06_dag_composition_v1 import qualify
from validate_f017_event06_authority_dag_v1 import validate


def test_canonical_dag_is_complete_and_structurally_bound():
    result = validate()
    assert result["result"] == "PASS"
    assert result["dag_edges_total"] == len(EDGE_IDS) == 45
    assert result["signature_bound_edges"] == 45
    assert result["unverified_consumer_type_boundaries"] == 0
    assert result["source_typed_boundaries_absent_from_dag"] == 0
    assert result["extraneous_trace_edges_absent_from_dag"] == 0


def test_full_production_control_path_is_no_access_and_closed():
    with tempfile.TemporaryDirectory(prefix="f017-seq17-test-full-") as directory:
        result = run_full_call_path(Path(directory))
    assert result["result"] == "PASS"
    assert result["dag_edges_traversed"] == list(EDGE_IDS)
    assert result["original_checkpoint_root_resolved"] is False
    assert result["full_model_inference"] == "NONE"
    assert result["live_accounting"] == {
        "authorization": 0, "package": 0, "primary": 0, "secondary": 0
    }
    assert not any(result["live_counters"].values())
    assert result["package_terminal"]["result"] == "COMPLETE"


def test_generated_per_edge_positive_and_negative_coverage():
    result = qualify(repetitions=2)
    assert result["result"] == "PASS"
    assert result["dag_edges_with_composition_tests"] == result["dag_edges_total"] == 45
    assert result["uncovered_typed_boundaries"] == 0
    assert result["mutation_campaign"] == {
        "passed": 180, "total": 180, "unexpected_passes": 0
    }
    assert result["real_binding_consumer_mutations"]["passed"] == 25
    assert result["real_binding_consumer_mutations"]["unexpected_passes"] == 0
    assert result["full_call_path_dry_run_with_synthetic_authority"] == "PASS"
