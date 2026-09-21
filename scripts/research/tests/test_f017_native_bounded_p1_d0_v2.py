from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.research.validate_f017_native_bounded_p1_d0_v1 import D0Error
from scripts.research.validate_f017_native_bounded_p1_d0_v2 import validate


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v2.json"


class D0V2Mutations(unittest.TestCase):
    def rejected(self, mutation) -> None:
        value = json.loads(CONTRACT.read_text())
        mutation(value)
        directory = Path(tempfile.mkdtemp(prefix="f017-d0-v2-mutation-"))
        self.addCleanup(shutil.rmtree, directory)
        path = directory / "d0-v2.json"
        path.write_text(json.dumps(value, sort_keys=True) + "\n")
        with self.assertRaises(D0Error):
            validate(path, ROOT)

    def test_committed_overlay(self) -> None:
        self.assertEqual(validate(CONTRACT, ROOT)["source_schema_bindings"], 6)

    def test_base_substitution(self) -> None:
        self.rejected(lambda v: v["base_contract"].update(sha256="0" * 64))

    def test_schema_identity_removed(self) -> None:
        self.rejected(lambda v: v["source_identities"][1].pop("schema"))

    def test_schema_identity_changed(self) -> None:
        self.rejected(lambda v: v["source_identities"][1].update(schema_version="2.0.0"))

    def test_router_normalized_demoted(self) -> None:
        self.rejected(lambda v: v["stage_overrides"][0].update(**{"class":"IMPLEMENTATION_SPECIFIC_REPRODUCIBILITY","metric":"pinned_environment_reproduction"}))

    def test_oracle_label_unbound(self) -> None:
        self.rejected(lambda v: v["stage_overrides"][0].update(oracle="FREE_TEXT"))

    def test_expected_artifact_sha_changed(self) -> None:
        self.rejected(lambda v: v["oracle_registry"][2]["expected_sha256"].__setitem__(0, "0" * 64))

    def test_epistemic_repair_weakened(self) -> None:
        self.rejected(lambda v: v["epistemic_lock"].update(exact_value="EDIT_V1_AFTER_D3_5"))

    def test_dispatch_identity_removed(self) -> None:
        self.rejected(lambda v: v["d3_5_determinism_evidence"]["required_identities"].pop())

    def test_tolerance_hides_repeat_failure(self) -> None:
        self.rejected(lambda v: v["d3_5_determinism_evidence"].update(numeric_tolerance_may_hide_repeat_failure=True))

    def test_retained_execution_claim_rejected(self) -> None:
        self.rejected(lambda v: v.update(retained_qualification_executed=True))

    def test_p1_execution_claim_rejected(self) -> None:
        self.rejected(lambda v: v.update(real_p1_executed=True))


if __name__ == "__main__":
    unittest.main()
