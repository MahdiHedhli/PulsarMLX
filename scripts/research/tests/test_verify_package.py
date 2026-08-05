from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


RESEARCH_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FULL_FIXTURE = (
    REPOSITORY_ROOT
    / "fixtures"
    / "research"
    / "router-v1"
    / "evidence"
    / "f002-router-fixture-0001.json"
)
VERIFY_COMMAND = RESEARCH_DIR / "verify_package.py"
if str(RESEARCH_DIR) not in sys.path:
    # Preserve standard-library import precedence during full test discovery.
    sys.path.append(str(RESEARCH_DIR))


def _candidate(experiment_id: str = "fixture-publish-v1") -> dict:
    return {
        "schema_id": "pulsarmlx.research.experiment",
        "schema_version": "1.0.0",
        "experiment_id": experiment_id,
        "feature_id": "002-qwen-router-parity",
        "status": "passed",
        "scope": "synthetic_fixture_only",
        "source": {
            "commit": "a" * 40,
            "clean": True,
        },
        "command": {
            "display": "validate-router-fixtures --manifest fixtures/research/router-v1/manifest.json",
            "exit_code": 0,
        },
        "raw_observations": [
            {
                "observation_id": "fixture-publish-v1-warm-000",
                "case_id": "generated-router-single-row-v1",
                "batch_id": "fixture-batch-v1",
                "observation_kind": "measurement",
                "condition": "warm",
                "instrumentation_mode": "minimally_instrumented",
                "duration_ns": 123_457,
                "status": "passed",
            }
        ],
        "unsupported_interpretations": [
            "real_checkpoint_routing",
            "expert_execution",
            "model_inference",
        ],
        "_local": {
            "candidate_directory": "/private/tmp/router-candidate",
            "model_path": "/private/models/checkpoint.gguf",
        },
    }


class PublicationBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.publisher = importlib.import_module("publish_evidence")
            self.verifier = importlib.import_module("verify_package")
        except ModuleNotFoundError as error:
            self.fail(f"planned publication module is not implemented: {error}")

    def _write_candidate(self, directory: Path, record: dict) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "candidate.json"
        path.write_text(
            json.dumps(record, allow_nan=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def test_candidate_sanitization_drops_only_declared_local_metadata(self) -> None:
        record = _candidate()
        sanitized = self.publisher.sanitize_candidate(record)

        self.assertNotIn("_local", sanitized)
        self.assertEqual(sanitized["experiment_id"], record["experiment_id"])
        self.assertEqual(sanitized["raw_observations"], record["raw_observations"])
        serialized = json.dumps(sanitized, allow_nan=False, sort_keys=True)
        self.assertNotIn("/private/", serialized)
        self.assertNotIn("checkpoint.gguf", serialized)

        leaked = _candidate("fixture-private-leak-v1")
        leaked["command"]["display"] = "/private/tmp/run --token secret-value"
        with self.assertRaises(self.publisher.PublicationError):
            self.publisher.sanitize_candidate(leaked)

    def test_publish_is_append_only_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path = self._write_candidate(root / "candidate", _candidate())
            raw_dir = root / "raw"

            installed = self.publisher.publish_candidate(candidate_path, raw_dir)
            original = installed.read_bytes()
            self.assertEqual(installed.name, "fixture-publish-v1.json")
            self.assertNotIn("_local", json.loads(original))

            changed = _candidate()
            changed["status"] = "failed"
            changed_path = self._write_candidate(root / "changed", changed)
            with self.assertRaises(FileExistsError):
                self.publisher.publish_candidate(changed_path, raw_dir)
            self.assertEqual(installed.read_bytes(), original)

    def test_failed_validation_leaves_no_partial_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            malformed = _candidate("")
            malformed_path = self._write_candidate(root / "candidate", malformed)
            raw_dir = root / "raw"

            with self.assertRaises(self.publisher.PublicationError):
                self.publisher.publish_candidate(malformed_path, raw_dir)

            self.assertFalse(raw_dir.exists() and any(raw_dir.iterdir()))
            self.assertEqual(list(root.rglob("*.tmp")), [])

    def test_symlink_destination_is_rejected_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path = self._write_candidate(root / "candidate", _candidate())
            private_dir = root / "private"
            private_dir.mkdir()
            marker = private_dir / "marker.txt"
            marker.write_text("unchanged", encoding="utf-8")
            alias = root / "raw-alias"
            alias.symlink_to(private_dir, target_is_directory=True)

            with self.assertRaises(self.publisher.PublicationError):
                self.publisher.publish_candidate(candidate_path, alias)
            self.assertEqual(marker.read_text(encoding="utf-8"), "unchanged")
            self.assertEqual(sorted(path.name for path in private_dir.iterdir()), ["marker.txt"])

    def test_candidate_verification_is_read_only_and_reports_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path = self._write_candidate(root, _candidate())
            before = candidate_path.read_bytes()

            result = self.verifier.verify_candidate(
                candidate_path,
                expected_feature="002-qwen-router-parity",
            )

            self.assertTrue(result["passed"])
            self.assertEqual(result["experiment_id"], "fixture-publish-v1")
            self.assertRegex(result["candidate_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(candidate_path.read_bytes(), before)
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["candidate.json"])

    def test_full_schema_fixture_uses_the_semantic_validator(self) -> None:
        before = FULL_FIXTURE.read_bytes()
        result = self.verifier.verify_candidate(
            FULL_FIXTURE,
            expected_feature="002-qwen-router-parity",
        )

        self.assertTrue(result["passed"])
        self.assertEqual(result["experiment_id"], "f002-router-fixture-0001")
        self.assertEqual(FULL_FIXTURE.read_bytes(), before)

    def test_fixture_only_package_cli_is_model_independent_and_read_only(self) -> None:
        before = {
            path.relative_to(REPOSITORY_ROOT): path.read_bytes()
            for path in FULL_FIXTURE.parent.glob("*.json")
        }
        environment = os.environ.copy()
        environment["PULSARMLX_MODEL_GGUF"] = ""
        completed = subprocess.run(
            [
                sys.executable,
                str(VERIFY_COMMAND),
                "--feature",
                "002-qwen-router-parity",
                "--fixture-only",
            ],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["passed"])
        self.assertTrue(result["fixture_only"])
        self.assertEqual(result["record_count"], 1)
        after = {
            path.relative_to(REPOSITORY_ROOT): path.read_bytes()
            for path in FULL_FIXTURE.parent.glob("*.json")
        }
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
