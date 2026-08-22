from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.research.validate_f017_native_bounded_p1_d0_v1 import D0Error, validate


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v1.json"


class D0Mutations(unittest.TestCase):
    def mutate(self, fn) -> Path:
        value = json.loads(CONTRACT.read_text())
        fn(value)
        directory = Path(tempfile.mkdtemp(prefix="f017-d0-mutation-"))
        self.addCleanup(shutil.rmtree, directory)
        path = directory / "d0.json"
        path.write_text(json.dumps(value, sort_keys=True) + "\n")
        return path

    def rejected(self, fn) -> None:
        with self.assertRaises(D0Error):
            validate(self.mutate(fn), ROOT)

    def test_committed_contract(self) -> None:
        self.assertEqual(validate(CONTRACT, ROOT)["stages"], 34)

    def test_enlarged_tolerance(self) -> None:
        self.rejected(lambda v: v["metric_profiles"]["native_intermediate_tier_b"].update(max_absolute_error=0.02))

    def test_safety_or_post_hoc_leak(self) -> None:
        self.rejected(lambda v: v["tolerance_epistemics"].update(d3_5_may_set_or_tune_value=True))

    def test_retained_corpus_for_thresholds(self) -> None:
        self.rejected(lambda v: v["tolerance_epistemics"].update(future_empirical_corpora="RETAINED_REPRESENTATIVE"))

    def test_oracle_hash(self) -> None:
        self.rejected(lambda v: v["bound_oracles"][0].update(sha256="0" * 64))

    def test_structural_gate_removed(self) -> None:
        self.rejected(lambda v: v["route_gate_order"].pop(0))

    def test_class_unresolved(self) -> None:
        self.rejected(lambda v: v["stage_rows"][2].update(**{"class": "UNRESOLVED_NUMERIC_SEMANTICS"}))

    def test_stage_renamed(self) -> None:
        self.rejected(lambda v: v["stage_rows"][12].update(id="attention_residual"))

    def test_gpu_policy_changed(self) -> None:
        self.rejected(lambda v: v["execution_policy"].update(matvec_device="CPU"))

    def test_determinism_weakened(self) -> None:
        self.rejected(lambda v: v["metric_profiles"]["pinned_environment_reproduction"].update(numeric_tolerance_may_hide_repeat_failure=True))

    def test_scope_overclaim(self) -> None:
        self.rejected(lambda v: v["scope_limitations"].update(full_forward_qualified_by_d3_5=True))

    def test_observed_result_before_execution(self) -> None:
        self.rejected(lambda v: v["common_acceptance"].update(unexecuted_observed_results="BYTE_EQUIVALENT"))


if __name__ == "__main__":
    unittest.main()
