"""Synthetic narrow 45-layer Route B comparisons; no checkpoint or real reference."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import studio019_grade as grade
import test_studio017_grade as fixture

GEOMETRY = (45, *fixture.TINY[1:])
FAILED = [23, 33, 34]


def synthetic(path, role, changes=None):
    with patch.object(fixture, "TINY", GEOMETRY):
        fixture.dataset(path, role, changes)
    path.chmod(0o700)
    report_path = path / "report.json"
    report = json.loads(report_path.read_bytes())
    report["layer_count"] = GEOMETRY[0]
    if changes and changes.get("weights_only"):
        row = next(row for row in report["routes"] if row["layer"] == 44)
        row["weights"][0] += .0625
        row["weights"][1] -= .0625
    for name, (layer, _, _, kind) in grade.original.layout(GEOMETRY).items():
        if kind != "corrected" or layer not in FAILED:
            continue
        file = path / name
        values = np.frombuffer(file.read_bytes(), dtype="<f4").copy()
        values[1] = values[2]
        file.chmod(0o600); file.write_bytes(values.tobytes()); file.chmod(0o400)
        report["files"][name]["sha256"] = grade.hashlib.sha256(values.tobytes()).hexdigest()
        row = next(row for row in report["routes"] if row["layer"] == layer)
        row["ids"] = sorted(range(len(values)), key=lambda index: (-values[index], index))[:8]
        row["cutoff_gap"] = 0.0
    report_path.chmod(0o600)
    report_path.write_bytes(fixture.encode(report)); report_path.chmod(0o400)
    path.chmod(0o500)


class RouteBGrade(unittest.TestCase):
    def test_invalid_sizes_do_not_abort_partial_grade_of_other_coordinates(self):
        with tempfile.TemporaryDirectory() as tmp:
            reference, native = Path(tmp).resolve()/'reference', Path(tmp).resolve()/'native'
            try:
                synthetic(reference, 'reference'); synthetic(native, 'native')
                native.chmod(0o700)
                names = ['00.state.offset.f32', '00.attention.output.f32']
                for name, size in zip(names, (0, (8 << 20) + 1)):
                    file = native/name; file.chmod(0o600)
                    with file.open('wb') as stream: stream.truncate(size)
                    file.chmod(0o400)
                native.chmod(0o500)
                with patch.object(grade.original, 'REAL', GEOMETRY):
                    result = grade.grade_pair(reference, native)
                self.assertFalse(result['complete']); self.assertFalse(result['qualified'])
                self.assertEqual(set(result['partial_errors']), set(names))
                self.assertTrue(all(result['stages'][name] is None for name in names))
                self.assertEqual(result['stages']['logits.f32']['outside'], 0)
            finally:
                for directory in (reference, native):
                    if directory.exists(): directory.chmod(0o700)

    def test_invalid_partial_sizes_are_hashed_errors_without_array_allocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp).resolve() / 'partial'; directory.mkdir(mode=0o700)
            names = list(grade.original.layout(GEOMETRY))[:2]
            (directory / names[0]).write_bytes(b'')
            payload = b'x' * ((8 << 20) + 1)
            (directory / names[1]).write_bytes(payload)
            for file in directory.iterdir(): file.chmod(0o400)
            directory.chmod(0o500)
            try:
                with patch.object(grade.np, 'frombuffer', side_effect=AssertionError('oversized allocation')):
                    arrays, records, errors = grade.bounded_partial(directory, GEOMETRY)
                self.assertEqual(arrays, {})
                self.assertEqual(set(errors), set(names))
                for name, raw in zip(names, (b'', payload)):
                    self.assertEqual(records[name], dict(bytes=len(raw), sha256=grade.hashlib.sha256(raw).hexdigest()))
            finally: directory.chmod(0o700)

    def test_partial_aggregate_budget_still_refuses_oversized_population(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp).resolve() / 'partial'; directory.mkdir(mode=0o700)
            file = directory / next(iter(grade.original.layout(GEOMETRY)))
            with file.open('wb') as stream: stream.truncate((256 << 20) + 1)
            file.chmod(0o400); directory.chmod(0o500)
            try:
                with self.assertRaisesRegex(grade.original.Refusal, 'partial output byte budget'):
                    grade.bounded_partial(directory, GEOMETRY)
            finally: directory.chmod(0o700)

    def run_case(self, changes=None, missing=False):
        with tempfile.TemporaryDirectory() as tmp:
            reference, native = Path(tmp).resolve() / "reference", Path(tmp).resolve() / "native"
            try:
                synthetic(reference, "reference")
                synthetic(native, "native", changes)
                if missing:
                    native.chmod(0o700)
                    (native / "00.state.offset.f32").unlink()
                    native.chmod(0o500)
                with patch.object(grade.original, "REAL", GEOMETRY):
                    return grade.grade_pair(reference, native)
            finally:
                for path in (reference, native):
                    if path.exists(): path.chmod(0o700)

    def test_equal_all_layers_remain_nonqualifying(self):
        result = self.run_case()
        self.assertTrue(result["complete"])
        self.assertTrue(result["empirical_agreement"])
        self.assertFalse(result["qualified"])
        self.assertFalse(result["original_frozen_qualification"])
        self.assertFalse(result["reference_eligible"])
        self.assertEqual(result["reference_failed_route_layers"], FAILED)
        self.assertEqual(set(result["routes"]), set(range(3, 45)))
        self.assertEqual(set(result["stages"]), set(grade.original.layout(GEOMETRY)))
        self.assertEqual(result["checked_values"], sum(row[2] for row in grade.original.layout(GEOMETRY).values()))
        self.assertIsNone(result["first_observed_divergence"])
        for layer in FAILED:
            self.assertFalse(result["routes"][layer]["pass_all"])

    def test_same_winner_nonwinner_and_state_mismatch_compared_completely(self):
        result = self.run_case(dict(wrong_nonwinner=True, state=True, bad_route=True))
        self.assertTrue(result["complete"])
        self.assertFalse(result["empirical_agreement"])
        self.assertFalse(result["qualified"])
        self.assertEqual(result["reference_token"]["winner"], result["native_token"]["winner"])
        self.assertGreaterEqual(result["outside"], 4)
        self.assertFalse(result["routes"][3]["membership_match"])
        self.assertEqual(len(result["routes"]), 42)
        self.assertEqual(set(result["stages"]), set(grade.original.layout(GEOMETRY)))
        self.assertIsNotNone(result["first_observed_divergence"])
        self.assertIsNone(result["observed_cause"])

    def test_weight_only_mismatch_has_a_first_observed_divergence(self):
        result = self.run_case(dict(weights_only=True))
        self.assertTrue(result["complete"])
        self.assertEqual(result["outside"], 0)
        self.assertFalse(result["routes"][44]["weights_match"])
        self.assertFalse(result["empirical_agreement"])
        self.assertFalse(result["qualified"])
        self.assertEqual(result["first_observed_divergence"], "44.moe.corrected.f32")

    def test_partial_output_preserves_missing_and_available_metrics(self):
        result = self.run_case(dict(wrong_nonwinner=True), missing=True)
        self.assertFalse(result["complete"])
        self.assertFalse(result["qualified"])
        self.assertIsNone(result["empirical_agreement"])
        self.assertIsNone(result["stages"]["00.state.offset.f32"])
        logits = next(name for name, row in grade.original.layout(GEOMETRY).items() if row[3] == "logits")
        self.assertEqual(result["stages"][logits]["outside"], 1)
        self.assertEqual(result["reference_failed_route_layers"], FAILED)
        self.assertEqual(set(result["routes"]), set(range(3, 45)))
        self.assertTrue(all(value is None for value in result["routes"].values()))
        self.assertEqual(len(result["partial_files"]), len(grade.original.layout(GEOMETRY)))


if __name__ == "__main__": unittest.main()
