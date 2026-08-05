from __future__ import annotations

import csv
import hashlib
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


RESEARCH_DIR = Path(__file__).resolve().parents[1]
if str(RESEARCH_DIR) not in sys.path:
    # Keep the standard library ahead of the project directory so the local
    # statistics.py cannot shadow Python's statistics module during discovery.
    sys.path.append(str(RESEARCH_DIR))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _record(experiment_id: str, total_ns: int, max_abs_error: float) -> dict:
    return {
        "schema_id": "pulsarmlx.research.experiment",
        "schema_version": "1.0.0",
        "experiment_id": experiment_id,
        "feature_id": "002-qwen-router-parity",
        "status": "passed",
        "scope": "synthetic_fixture_only",
        "case_id": "generated-router-single-row-v1",
        "correctness": {
            "passed": True,
            "compared_count": 128,
            "mismatch_count": 0,
            "maximum_absolute_error": max_abs_error,
        },
        "summaries": [
            {
                "phase": "total_evaluated_router",
                "condition": "warm",
                "instrumentation_mode": "minimally_instrumented",
                "sample_count": 10,
                "median_ns": total_ns,
                "mean_ns": float(total_ns),
                "minimum_ns": total_ns - 9,
                "maximum_ns": total_ns + 9,
            }
        ],
        "unsupported_interpretations": [
            "real_checkpoint_routing",
            "expert_execution",
            "token_throughput",
        ],
    }


class DeterministicGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.tables = importlib.import_module("generate_tables")
            self.figures = importlib.import_module("generate_figures")
        except ModuleNotFoundError as error:
            self.fail(f"planned research generator is not implemented: {error}")

    def _write_inputs(self, raw_dir: Path) -> None:
        raw_dir.mkdir(parents=True)
        records = [
            _record("fixture-b", 200_003, 0.000002),
            _record("fixture-a", 100_019, 0.000001),
        ]
        for record in records:
            path = raw_dir / f"{record['experiment_id']}.json"
            path.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    def _generate(self, root: Path) -> tuple[Path, Path]:
        raw_dir = root / "raw"
        table_dir = root / "tables"
        figure_dir = root / "figures"
        self._write_inputs(raw_dir)
        self.tables.generate_tables(raw_dir, table_dir)
        self.figures.generate_figures(raw_dir, figure_dir)
        return table_dir, figure_dir

    def test_two_runs_are_byte_identical_with_stable_file_order(self) -> None:
        with tempfile.TemporaryDirectory() as first_temp, tempfile.TemporaryDirectory() as second_temp:
            first_tables, first_figures = self._generate(Path(first_temp))
            second_tables, second_figures = self._generate(Path(second_temp))

            first_files = sorted(
                [path.relative_to(Path(first_temp)) for path in Path(first_temp).rglob("*") if path.is_file()]
            )
            second_files = sorted(
                [path.relative_to(Path(second_temp)) for path in Path(second_temp).rglob("*") if path.is_file()]
            )
            self.assertEqual(first_files, second_files)
            for relative in first_files:
                self.assertEqual(
                    (Path(first_temp) / relative).read_bytes(),
                    (Path(second_temp) / relative).read_bytes(),
                    relative,
                )

            self.assertTrue(any(path.suffix == ".md" for path in first_tables.iterdir()))
            self.assertTrue(any(path.suffix == ".csv" for path in first_tables.iterdir()))
            self.assertTrue(any(path.suffix == ".svg" for path in first_figures.iterdir()))

    def test_tables_derive_values_from_raw_records(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            table_dir, _ = self._generate(Path(temporary))
            csv_path = next(path for path in table_dir.iterdir() if path.suffix == ".csv")
            markdown_path = next(path for path in table_dir.iterdir() if path.suffix == ".md")

            with csv_path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([row["experiment_id"] for row in rows], ["fixture-a", "fixture-b"])
            self.assertEqual([int(row["median_ns"]) for row in rows], [100_019, 200_003])
            self.assertIn("0.000001", markdown_path.read_text(encoding="utf-8"))
            self.assertIn("0.000002", markdown_path.read_text(encoding="utf-8"))

    def test_sidecars_bind_every_input_and_output_without_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            table_dir, figure_dir = self._generate(root)
            sidecars = sorted(root.rglob("*.sources.json"))
            self.assertGreaterEqual(len(sidecars), 2)

            expected_sources = {
                path.name: _sha256(path) for path in sorted((root / "raw").glob("*.json"))
            }
            for sidecar_path in sidecars:
                sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
                self.assertEqual(sidecar["schema_id"], "pulsarmlx.research.generated-sources")
                self.assertEqual(sidecar["schema_version"], "1.0.0")
                self.assertEqual(sidecar["sources"], expected_sources)
                self.assertRegex(sidecar["output_sha256"], r"^[0-9a-f]{64}$")
                serialized = sidecar_path.read_text(encoding="utf-8")
                self.assertNotIn(str(root), serialized)
                self.assertNotIn("generated_at", sidecar)

            output_paths = [
                path
                for directory in (table_dir, figure_dir)
                for path in directory.iterdir()
                if not path.name.endswith(".sources.json")
            ]
            self.assertTrue(output_paths)

    def test_sidecars_name_repository_relative_raw_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous_directory = Path.cwd()
            try:
                os.chdir(root)
                raw_dir = Path("docs/research/raw/002-router-parity")
                table_dir = Path("docs/research/tables")
                figure_dir = Path("docs/research/figures")
                self._write_inputs(raw_dir)
                self.tables.generate_tables(raw_dir, table_dir)
                self.figures.generate_figures(raw_dir, figure_dir)
            finally:
                os.chdir(previous_directory)

            expected_sources = {
                f"docs/research/raw/002-router-parity/{path.name}": _sha256(path)
                for path in sorted((root / raw_dir).glob("*.json"))
            }
            sidecars = sorted((root / "docs/research").rglob("*.sources.json"))
            self.assertTrue(sidecars)
            for sidecar_path in sidecars:
                sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    sidecar["sources"],
                    expected_sources,
                    msg=(
                        "sidecar does not retain repository-relative source links: "
                        f"{sidecar_path.name}"
                    ),
                )

    def test_svg_is_bounded_static_and_changes_when_raw_measurement_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, figure_dir = self._generate(root)
            svg_path = next(path for path in figure_dir.iterdir() if path.suffix == ".svg")
            original = svg_path.read_text(encoding="utf-8")
            self.assertTrue(original.startswith("<svg"))
            self.assertLess(len(original.encode("utf-8")), 128 * 1024)
            self.assertNotIn("<script", original.lower())
            self.assertNotIn(str(root), original)

            changed_root = root / "changed"
            raw_dir = changed_root / "raw"
            raw_dir.mkdir(parents=True)
            changed = _record("fixture-a", 777_777, 0.000001)
            (raw_dir / "fixture-a.json").write_text(
                json.dumps(changed, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            changed_figures = changed_root / "figures"
            self.figures.generate_figures(raw_dir, changed_figures)
            changed_svg = next(path for path in changed_figures.iterdir() if path.suffix == ".svg")
            self.assertNotEqual(original, changed_svg.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
