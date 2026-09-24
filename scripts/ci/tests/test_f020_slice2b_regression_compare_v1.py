"""Controls for the F020 Slice 2B regression proof (slice2c-plan.md 6.2).

Built on the committed, sha256-verified attempt-3 child report: an exact copy
passes; a change in V1-V4 only passes; any other change, a field present on one
side only, a broken e5 null pattern, a gate-count or test-list difference, or
the composition target in the Slice 2B list fails; a secondary mismatch is
recorded without changing the primary verdict; a tampered reference is refused.
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.ci import f020_slice2b_regression_compare_v1 as rc

ROOT = Path(__file__).resolve().parents[3]
ATTEMPT3 = ROOT / "fixtures" / "f020-slice2b-attempt3" / "child-report.json"
LIST = ["dq_is_exact_on_codes: test", "native_qualification_of_the_frozen_population: test", "", "2 tests, 0 benchmarks"]
COMPOSITION_LIST = [rc.COMPOSITION_TEST, "sealed_plane_interface: test", "", "2 tests, 0 benchmarks"]


class RegressionCompareControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(ATTEMPT3.read_bytes())

    def layout(self, base_report, cand_report, *, base_counts=None, cand_counts=None,
               base_list=None, cand_list=None, composition=None):
        tmp = Path(tempfile.mkdtemp(prefix="f020-regression-"))
        counts = {g: {"cases": n, "passed": n} for g, n in rc.ATTEMPT3_GATE_COUNTS.items()}
        for side, report, gc in (("base", base_report, base_counts), ("candidate", cand_report, cand_counts)):
            q = tmp / side / "qualification"
            (q / "child").mkdir(parents=True)
            (q / "child" / "report.json").write_text(json.dumps(report))
            (q / "summary.json").write_text(json.dumps({"result": "PASS", "failures": [], "gate_counts": gc or counts}))
        lists = tmp / "lists"
        lists.mkdir()
        (lists / "base-list.txt").write_text("\n".join(base_list or LIST) + "\n")
        (lists / "candidate-list.txt").write_text("\n".join(cand_list or LIST) + "\n")
        (lists / "base-doc-list.txt").write_text("0 tests, 0 benchmarks\n")
        (lists / "candidate-doc-list.txt").write_text("0 tests, 0 benchmarks\n")
        (lists / "composition-list.txt").write_text("\n".join(composition or COMPOSITION_LIST) + "\n")
        return tmp

    def run_compare(self, tmp, attempt3=ATTEMPT3):
        out = tmp / "regression.json"
        code = rc.main(["--base", str(tmp / "base"), "--candidate", str(tmp / "candidate"),
                        "--lists", str(tmp / "lists"), "--attempt3", str(attempt3), "--out", str(out)])
        return code, (json.loads(out.read_text()) if out.exists() else None)

    def executed_qmm(self, report):
        return next(i for i, c in enumerate(report["cases"])
                    if c["op"] == "quantized_matmul" and c["outcome"] == "executed")

    def test_identical_reports_pass_and_match_attempt3(self):
        code, doc = self.run_compare(self.layout(self.report, self.report))
        self.assertEqual(code, 0)
        self.assertTrue(doc["primary_b_same_run_differential"]["canonical_reports_equal"])
        self.assertEqual(doc["secondary_a_cross_run"]["result"], "MATCH")

    def test_volatile_fields_only_pass(self):
        cand = copy.deepcopy(self.report)
        cand["provenance"]["build"]["qualify_executable_sha256"] = "0" * 64
        i = self.executed_qmm(cand)
        e5 = cand["cases"][i]["stats"]["e5_peak_memory"]
        e5["active_before"] += 4096
        e5["peak_after"] += 1
        e5["peak_delta_ge_output_nbytes"] = not e5["peak_delta_ge_output_nbytes"]
        code, doc = self.run_compare(self.layout(self.report, cand))
        self.assertEqual(code, 0, doc["primary_b_same_run_differential"]["failures"])

    def test_change_outside_volatile_fails_with_its_path(self):
        for mutate, fragment in (
            (lambda r: r["cases"][self.executed_qmm(r)]["output"].__setitem__("sha256", "0" * 64), "output.sha256"),
            (lambda r: r["provenance"]["build"].__setitem__("rustc", "rustc 0.0.0"), "provenance.build.rustc"),
            (lambda r: r["cases"][self.executed_qmm(r)]["stats"]["e5_peak_memory"].__setitem__("output_nbytes", 1), "output_nbytes"),
            (lambda r: r["canary_end"].__setitem__("output_sha256", "0" * 64), "canary_end.output_sha256"),
            (lambda r: r["cleanup"].__setitem__("array_free_calls", 1), "cleanup.array_free_calls"),
        ):
            cand = copy.deepcopy(self.report)
            mutate(cand)
            code, doc = self.run_compare(self.layout(self.report, cand))
            b = doc["primary_b_same_run_differential"]
            self.assertEqual(code, 1, fragment)
            self.assertFalse(b["canonical_reports_equal"], fragment)
            self.assertTrue(any(fragment in p for p in b["differing_paths"]), (fragment, b["differing_paths"]))

    def test_field_on_one_side_only_fails(self):
        cand = copy.deepcopy(self.report)
        cand["provenance"]["build"]["timestamp"] = "2026-09-24T00:00:00Z"
        code, doc = self.run_compare(self.layout(self.report, cand))
        self.assertEqual(code, 1)
        self.assertTrue(any("present in candidate only" in p for p in doc["primary_b_same_run_differential"]["differing_paths"]))

    def test_e5_pattern_is_validated_before_removal(self):
        refused = next(i for i, c in enumerate(self.report["cases"]) if c["outcome"] == "refused")
        for mutate in (
            lambda e5: e5.__setitem__("active_before", 0),
            lambda e5: e5.__setitem__("extra", None),
            lambda e5: e5.pop("peak_after"),
        ):
            cand = copy.deepcopy(self.report)
            mutate(cand["cases"][refused]["stats"]["e5_peak_memory"])
            code, doc = self.run_compare(self.layout(self.report, cand))
            self.assertEqual(code, 1)
            self.assertTrue(doc["primary_b_same_run_differential"]["e5_pre_removal_validation"]["errors"])

    def test_gate_counts_lists_and_composition_target(self):
        counts = {g: {"cases": n, "passed": n} for g, n in rc.ATTEMPT3_GATE_COUNTS.items()}
        fewer = dict(counts, **{"G-QMM-EXACT": {"cases": 237, "passed": 236}})
        for kwargs in ({"cand_counts": fewer},
                       {"cand_list": LIST[:1] + LIST[2:]},
                       {"base_list": LIST + [rc.COMPOSITION_TEST], "cand_list": LIST + [rc.COMPOSITION_TEST]},
                       {"composition": ["sealed_plane_interface: test"]}):
            code, _ = self.run_compare(self.layout(self.report, self.report, **kwargs))
            self.assertEqual(code, 1, kwargs)

    def test_secondary_mismatch_is_recorded_not_converted(self):
        both = copy.deepcopy(self.report)
        both["cases"][self.executed_qmm(both)]["output"]["sha256"] = "1" * 64
        code, doc = self.run_compare(self.layout(both, both))
        self.assertEqual(code, 0)
        self.assertEqual(doc["secondary_a_cross_run"]["result"], "MISMATCH")
        self.assertEqual(doc["secondary_a_cross_run"]["mismatch_count"], 1)

    def test_tampered_attempt3_reference_is_refused(self):
        tmp = self.layout(self.report, self.report)
        bad = tmp / "attempt3.json"
        bad.write_bytes(ATTEMPT3.read_bytes() + b" ")
        code, doc = self.run_compare(tmp, attempt3=bad)
        self.assertEqual(code, 2)
        self.assertIsNone(doc)


if __name__ == "__main__":
    unittest.main()
