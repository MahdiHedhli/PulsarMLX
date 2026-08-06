"""Model-free contract tests for the T075 router-inspection validator."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts.research import validate_router_inspection as validator
from scripts.research.tests import test_environment as environment_contracts


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCHEMA = REPOSITORY_ROOT / "schemas/research/v1/router-inspection.schema.json"
MODEL_SHA256 = "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c"
TENSOR_SHA256 = "b" * 64
DATA_OFFSET = 5_969_408
RELATIVE_OFFSET = 100_000_000
ABSOLUTE_OFFSET = DATA_OFFSET + RELATIVE_OFFSET
ENCODED_LENGTH = 1_048_576
SOURCE_COMMIT = "a" * 40
ENVIRONMENT_TIME = datetime(2026, 8, 6, 3, 44, tzinfo=timezone.utc)
CANDIDATE_TIME = "2026-08-06T03:45:00Z"
VALIDATION_TIME = datetime(2026, 8, 6, 3, 46, tzinfo=timezone.utc)


def _candidate(*, normalization_present: bool = False) -> dict[str, object]:
    normalization_source = (
        "gguf:qwen3moe.expert_weights_norm"
        if normalization_present
        else (
            "frozen-architecture-contract:"
            "qwen3moe.expert_weights_norm-default-true-key-absent"
        )
    )
    return {
        "schema_version": 1,
        "validation": "qwen3moe-layer0-router-read-only-inspection",
        "status": "admitted_observed",
        "passed": True,
        "recorded_at_utc": CANDIDATE_TIME,
        "source_commit": SOURCE_COMMIT,
        "source_worktree_clean_before_inspection": True,
        "source_worktree_clean_after_inspection": True,
        "artifact": {
            "repository_id": "Qwen/Qwen3-30B-A3B-GGUF",
            "revision": "e4d4bafdfb96a411a163846265362aceb0b9c63a",
            "filename": "Qwen3-30B-A3B-Q8_0.gguf",
            "license_spdx": "Apache-2.0",
            "size_bytes": 32_483_931_648,
            "sha256": MODEL_SHA256,
            "location_symbolic": "<external-model>/Qwen3-30B-A3B-Q8_0.gguf",
            "stored_outside_repository": True,
            "read_only": True,
            "automatic_download": False,
            "identity_rechecked_after_inspection": True,
        },
        "gguf": {
            "version": 3,
            "endianness": "little",
            "data_offset": DATA_OFFSET,
            "tensor_count": 579,
            "tensor_type_counts": {"F32": 241, "Q8_0": 338},
            "metadata": {
                "general.architecture": {"type": "STRING", "value": "qwen3moe"},
                "qwen3moe.embedding_length": {"type": "UINT32", "value": 2048},
                "qwen3moe.expert_feed_forward_length": {
                    "type": "UINT32",
                    "value": 768,
                },
                "qwen3moe.expert_count": {"type": "UINT32", "value": 128},
                "qwen3moe.expert_used_count": {"type": "UINT32", "value": 8},
                "qwen3moe.expert_weights_scale": {
                    "present": False,
                    "type": None,
                    "value": None,
                    "effective_value": 1.0,
                },
                "qwen3moe.expert_weights_norm": {
                    "present": normalization_present,
                    "type": "BOOL" if normalization_present else None,
                    "value": True if normalization_present else None,
                    "effective_value": True,
                },
            },
        },
        "router_tensor": {
            "name": "blk.0.ffn_gate_inp.weight",
            "semantic_role": "layer_0_router_projection",
            "occurrence_count": 1,
            "gguf_dimensions_fastest_axis_first": [2048, 128],
            "reader_shape": [128, 2048],
            "execution_shape": [128, 2048],
            "gguf_type": "F32",
            "quantization": "none_f32",
            "logical_elements": 262_144,
            "relative_data_offset": RELATIVE_OFFSET,
            "absolute_data_offset": ABSOLUTE_OFFSET,
            "encoded_length_bytes": ENCODED_LENGTH,
            "exclusive_end_offset": ABSOLUTE_OFFSET + ENCODED_LENGTH,
            "encoded_range_sha256": TENSOR_SHA256,
            "byte_order": "little",
            "orientation": "expert_major_rows_input_columns",
            "finite_f32_values_verified": True,
            "finite_element_count": 262_144,
        },
        "routing_semantics": {
            "expert_count": 128,
            "selected_expert_count": 8,
            "weight_scale": 1.0,
            "bias_present": False,
            "bias_occurrence_count": 0,
            "correction_bias_present": False,
            "correction_bias_occurrence_count": 0,
            "unexpected_router_alias_occurrence_count": 0,
            "full_softmax": True,
            "selected_probability_renormalization": True,
            "normalization_source": normalization_source,
        },
        "resource_admission": {
            "available_disk_bytes": 200_000_000_000,
            "required_disk_bytes": 134_761_081_856,
            "disk_headroom_satisfied": True,
            "host_unified_memory_bytes": 137_438_953_472,
            "required_host_bytes": 42_949_672_960,
            "unified_memory_headroom_satisfied": True,
            "system_pressure": "normal",
            "memory_pressure_normal": True,
        },
        "execution": {
            "performed": False,
            "worker_spawned": False,
            "mlx_initialized": False,
            "router_projection_performed": False,
            "router_output_produced": False,
            "expert_execution_performed": False,
            "network_access_performed": False,
            "automatic_download_performed": False,
        },
        "warnings": [
            "The inherited Rust GGUF map does not independently retain duplicate metadata keys; the exact full-file SHA-256 and pinned artifact identity close this artifact-specific boundary.",
            "This read-only admission record is a candidate for T075 validation and is not execution evidence or a capability promotion.",
        ],
        "exclusions": [
            "No MLX runtime or worker process was initialized.",
            "No router projection, softmax, top-k selection, expert execution, model output, generation, serving, or benchmark was performed.",
            "No model or tensor bytes, decoded values, private paths, or machine identifiers are included in this record.",
        ],
    }


def _environment_snapshot() -> dict[str, object]:
    return environment_contracts._collect(now=lambda: ENVIRONMENT_TIME)


class RouterInspectionValidatorTests(unittest.TestCase):
    maxDiff = None

    def _write(self, directory: Path, candidate: dict[str, object]) -> Path:
        path = directory / "router-inspection.json"
        path.write_text(
            json.dumps(candidate, allow_nan=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def _run(
        self,
        candidate_path: Path,
        *,
        output: Path | None = None,
        environment_snapshot: dict[str, object] | None = None,
        environment_path: Path | None = None,
        source_state: validator.SourceState | None = None,
        validation_time: datetime = VALIDATION_TIME,
    ) -> SimpleNamespace:
        snapshot = (
            environment_snapshot
            if environment_snapshot is not None
            else _environment_snapshot()
        )

        def invoke(snapshot_path: Path, environment_bytes: bytes) -> SimpleNamespace:
            arguments = [
                "--schema",
                str(SCHEMA),
                "--input",
                str(candidate_path),
                "--environment",
                str(snapshot_path),
            ]
            if output is not None:
                arguments.extend(("--output", str(output)))
            stdout = io.StringIO()
            stderr = io.StringIO()
            state = source_state or validator.SourceState(
                current_head=SOURCE_COMMIT,
                worktree_clean=True,
                candidate_exists=True,
            )
            with redirect_stdout(stdout), redirect_stderr(stderr):
                returncode = validator.main(
                    arguments,
                    source_state_provider=lambda _commit: state,
                    now_provider=lambda: validation_time,
                )
            return SimpleNamespace(
                returncode=returncode,
                stdout=stdout.getvalue(),
                stderr=stderr.getvalue(),
                environment_sha256=hashlib.sha256(environment_bytes).hexdigest(),
            )

        if environment_path is not None:
            return invoke(environment_path, environment_path.read_bytes())
        with tempfile.TemporaryDirectory(
            prefix="pulsarmlx-inspection-environment-test-"
        ) as temporary:
            snapshot_path = Path(temporary) / "environment.json"
            encoded = (
                json.dumps(snapshot, allow_nan=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            snapshot_path.write_bytes(encoded)
            return invoke(snapshot_path, encoded)

    def _assert_rejected(
        self,
        candidate: dict[str, object],
        expected_code: str,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-inspection-test-") as temporary:
            candidate_path = self._write(Path(temporary), candidate)
            completed = self._run(candidate_path)
        self.assertNotEqual(completed.returncode, 0)
        result = json.loads(completed.stderr)
        self.assertEqual(result["passed"], False)
        self.assertEqual(result["code"], expected_code)
        self.assertNotIn("Traceback", completed.stderr)

    def test_schema_is_closed_and_synchronized_with_the_producer_shape(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(set(schema["required"]), validator.ROOT_FIELDS)
        self.assertEqual(set(schema["properties"]), validator.ROOT_FIELDS)
        self.assertEqual(
            set(_candidate()),
            validator.ROOT_FIELDS,
            msg="test candidate no longer matches the closed producer root",
        )
        for definition in ("scaleMetadata", "normalizationMetadata"):
            branches = schema["$defs"][definition]["oneOf"]
            self.assertEqual(len(branches), 2)
            self.assertEqual(
                {branch["properties"]["present"]["const"] for branch in branches},
                {False, True},
            )

    def test_accepts_absent_and_present_normalization_metadata_sources(self) -> None:
        for present in (False, True):
            with self.subTest(present=present):
                with tempfile.TemporaryDirectory(
                    prefix="pulsarmlx-inspection-test-"
                ) as temporary:
                    candidate_path = self._write(Path(temporary), _candidate(
                        normalization_present=present
                    ))
                    completed = self._run(candidate_path)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                report = json.loads(completed.stdout)
                self.assertTrue(report["passed"])
                self.assertTrue(report["public_safe"])
                self.assertEqual(report["artifact"]["sha256"], MODEL_SHA256)
                self.assertEqual(
                    report["router_tensor"]["encoded_range_sha256"], TENSOR_SHA256
                )
                self.assertEqual(
                    report["environment_snapshot"]["sha256"],
                    completed.environment_sha256,
                )
                self.assertEqual(
                    report["environment_snapshot"]["source_commit"], SOURCE_COMMIT
                )

    def test_rejects_missing_unknown_and_wrong_scalar_fields(self) -> None:
        cases: list[tuple[str, dict[str, object], str]] = []
        missing = _candidate()
        del missing["artifact"]
        cases.append(("missing", missing, "schema_violation"))
        unknown = _candidate()
        unknown["unreviewed"] = True
        cases.append(("unknown", unknown, "schema_violation"))
        wrong_type = _candidate()
        wrong_type["schema_version"] = True
        cases.append(("wrong-type", wrong_type, "semantic_mismatch"))
        for name, candidate, code in cases:
            with self.subTest(name=name):
                self._assert_rejected(candidate, code)

    def test_rejects_every_frozen_model_identity_mutation(self) -> None:
        mutations = {
            "repository_id": "another/model",
            "revision": "c" * 40,
            "filename": "another.gguf",
            "license_spdx": "MIT",
            "size_bytes": 32_483_931_647,
            "sha256": "c" * 64,
            "location_symbolic": "Qwen3-30B-A3B-Q8_0.gguf",
            "stored_outside_repository": False,
            "read_only": False,
            "automatic_download": True,
            "identity_rechecked_after_inspection": False,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                candidate = _candidate()
                candidate["artifact"][field] = value
                self._assert_rejected(candidate, "semantic_mismatch")

    def test_rejects_dirty_or_nonimmutable_source_identity(self) -> None:
        mutations = (
            ("source_commit", "deadbeef"),
            ("source_worktree_clean_before_inspection", False),
            ("source_worktree_clean_after_inspection", False),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                candidate = _candidate()
                candidate[field] = value
                expected = "source_identity" if field == "source_commit" else "semantic_mismatch"
                self._assert_rejected(candidate, expected)

    def test_production_source_binding_rejects_unknown_stale_and_dirty_states(self) -> None:
        states = {
            "unknown": validator.SourceState(SOURCE_COMMIT, True, False),
            "stale": validator.SourceState("b" * 40, True, True),
            "dirty": validator.SourceState(SOURCE_COMMIT, False, True),
        }
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-inspection-test-") as temporary:
            candidate_path = self._write(Path(temporary), _candidate())
            for name, state in states.items():
                with self.subTest(name=name):
                    completed = self._run(candidate_path, source_state=state)
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertEqual(
                        json.loads(completed.stderr)["code"], "source_identity"
                    )
                    self.assertNotIn("Traceback", completed.stderr)

    def test_git_source_probe_observes_commit_existence_head_and_cleanliness(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-source-probe-") as temporary:
            root = Path(temporary)
            tracked = root / "tracked.txt"
            tracked.write_text("clean\n", encoding="utf-8")

            def git(*arguments: str) -> subprocess.CompletedProcess[bytes]:
                return subprocess.run(
                    ("git", *arguments),
                    cwd=root,
                    check=False,
                    capture_output=True,
                )

            self.assertEqual(git("init", "--quiet").returncode, 0)
            self.assertEqual(git("add", "tracked.txt").returncode, 0)
            self.assertEqual(
                git(
                    "-c",
                    "user.name=PulsarMLX Test",
                    "-c",
                    "user.email=pulsarmlx-test@example.invalid",
                    "commit",
                    "--quiet",
                    "-m",
                    "fixture",
                ).returncode,
                0,
            )
            head = git("rev-parse", "HEAD").stdout.decode("ascii").strip()
            state = validator._observe_source_state(head, repository_root=root)
            self.assertEqual(state, validator.SourceState(head, True, True))

            unknown = validator._observe_source_state("f" * 40, repository_root=root)
            self.assertFalse(unknown.candidate_exists)
            tracked.write_text("dirty\n", encoding="utf-8")
            dirty = validator._observe_source_state(head, repository_root=root)
            self.assertFalse(dirty.worktree_clean)

    def test_environment_snapshot_admission_is_exact_and_fresh(self) -> None:
        cases: list[tuple[str, dict[str, object], datetime]] = []

        wrong_role = _environment_snapshot()
        wrong_role["storage_role"] = "candidate_evidence_storage"
        wrong_role["storage_locator"] = "$PULSARMLX_ROUTER_EVIDENCE"
        cases.append(("storage-role", wrong_role, VALIDATION_TIME))

        wrong_commit = _environment_snapshot()
        wrong_commit["observations"]["repository_commit"]["value"] = "b" * 40
        wrong_commit["observations"]["pulsarmlx_version"]["value"] = "b" * 40
        cases.append(("source-commit", wrong_commit, VALIDATION_TIME))

        dirty_environment = _environment_snapshot()
        dirty_environment["observations"]["worktree_dirty"]["value"] = True
        dirty_environment["interference_admission"] = "postponed"
        dirty_environment["admission_reasons"] = [
            "source_worktree_admission_failed"
        ]
        cases.append(("worktree", dirty_environment, VALIDATION_TIME))

        material_workload = _environment_snapshot()
        material_workload["observations"]["workload_category"]["value"] = (
            "local_inference"
        )
        material_workload["observations"]["material_concurrent_workload"][
            "value"
        ] = True
        material_workload["interference_admission"] = "postponed"
        material_workload["admission_reasons"] = [
            "material_concurrent_workload_declared"
        ]
        cases.append(("workload", material_workload, VALIDATION_TIME))

        unavailable_thermal = _environment_snapshot()
        unavailable_thermal["observations"]["thermal_state"] = (
            environment_contracts.environment.unavailable(
                "thermal category unavailable", "fixture_probe"
            )
        )
        cases.append(("thermal", unavailable_thermal, VALIDATION_TIME))

        unavailable_power = _environment_snapshot()
        unavailable_power["observations"]["power_mode"] = (
            environment_contracts.environment.unavailable(
                "power mode unavailable", "fixture_probe"
            )
        )
        cases.append(("power", unavailable_power, VALIDATION_TIME))

        high_long_load = _environment_snapshot()
        high_long_load["observations"]["load_average_15m"]["value"] = 100.0
        cases.append(("load", high_long_load, VALIDATION_TIME))

        after_candidate = _environment_snapshot()
        after_candidate["observations"]["captured_at_utc"]["value"] = (
            "2026-08-06T03:46:00Z"
        )
        cases.append(("timestamp-order", after_candidate, VALIDATION_TIME))

        stale_environment = _environment_snapshot()
        stale_environment["observations"]["captured_at_utc"]["value"] = (
            "2026-08-06T03:00:00Z"
        )
        cases.append(("environment-freshness", stale_environment, VALIDATION_TIME))

        cases.append(
            (
                "candidate-freshness",
                _environment_snapshot(),
                datetime(2026, 8, 6, 4, 1, tzinfo=timezone.utc),
            )
        )

        with tempfile.TemporaryDirectory(prefix="pulsarmlx-inspection-test-") as temporary:
            candidate_path = self._write(Path(temporary), _candidate())
            for name, snapshot, validation_time in cases:
                with self.subTest(name=name):
                    completed = self._run(
                        candidate_path,
                        environment_snapshot=snapshot,
                        validation_time=validation_time,
                    )
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertEqual(
                        json.loads(completed.stderr)["code"], "environment_snapshot"
                    )
                    self.assertNotIn("Traceback", completed.stderr)

    def test_environment_argument_is_required(self) -> None:
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            validator._parser().parse_args(["--input", "/tmp/candidate.json"])

    def test_rejects_router_type_shape_range_and_hash_mutations(self) -> None:
        mutations = {
            "name": "blk.0.ffn_gate_exps.weight",
            "semantic_role": "expert_projection",
            "occurrence_count": 2,
            "gguf_dimensions_fastest_axis_first": [128, 2048],
            "reader_shape": [2048, 128],
            "execution_shape": [2048, 128],
            "gguf_type": "Q8_0",
            "quantization": "Q8_0",
            "logical_elements": 262_143,
            "encoded_length_bytes": 1_048_575,
            "encoded_range_sha256": "not-a-hash",
            "byte_order": "big",
            "orientation": "input_major",
            "finite_f32_values_verified": False,
            "finite_element_count": 262_143,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                candidate = _candidate()
                candidate["router_tensor"][field] = value
                expected = (
                    "schema_violation"
                    if field == "encoded_range_sha256"
                    else "semantic_mismatch"
                )
                self._assert_rejected(candidate, expected)

        for field, value in (
            ("absolute_data_offset", ABSOLUTE_OFFSET + 1),
            ("exclusive_end_offset", ABSOLUTE_OFFSET + ENCODED_LENGTH + 1),
        ):
            with self.subTest(field=field):
                candidate = _candidate()
                candidate["router_tensor"][field] = value
                self._assert_rejected(candidate, "invalid_tensor_range")

    def test_rejects_routing_semantic_mutations(self) -> None:
        mutations = {
            "expert_count": 127,
            "selected_expert_count": 7,
            "weight_scale": 0.5,
            "bias_present": True,
            "bias_occurrence_count": 1,
            "correction_bias_present": True,
            "correction_bias_occurrence_count": 1,
            "unexpected_router_alias_occurrence_count": 1,
            "full_softmax": False,
            "selected_probability_renormalization": False,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                candidate = _candidate()
                candidate["routing_semantics"][field] = value
                self._assert_rejected(candidate, "semantic_mismatch")

    def test_normalization_source_must_match_metadata_presence(self) -> None:
        for present in (False, True):
            with self.subTest(present=present):
                candidate = _candidate(normalization_present=present)
                candidate["routing_semantics"]["normalization_source"] = (
                    validator.ABSENT_NORMALIZATION_SOURCE
                    if present
                    else validator.PRESENT_NORMALIZATION_SOURCE
                )
                self._assert_rejected(candidate, "semantic_mismatch")

    def test_rejects_scale_and_normalization_metadata_inconsistency(self) -> None:
        cases = []
        present_scale = _candidate()
        present_scale["gguf"]["metadata"]["qwen3moe.expert_weights_scale"] = {
            "present": True,
            "type": "FLOAT32",
            "value": 0.5,
            "effective_value": 0.5,
        }
        cases.append(present_scale)
        absent_norm_value = _candidate()
        absent_norm_value["gguf"]["metadata"]["qwen3moe.expert_weights_norm"][
            "value"
        ] = True
        cases.append(absent_norm_value)
        for index, candidate in enumerate(cases):
            with self.subTest(index=index):
                self._assert_rejected(candidate, "semantic_mismatch")

    def test_rejects_resource_admission_mutations(self) -> None:
        mutations = {
            "available_disk_bytes": 134_761_081_855,
            "required_disk_bytes": 1,
            "disk_headroom_satisfied": False,
            "host_unified_memory_bytes": 42_949_672_959,
            "required_host_bytes": 1,
            "unified_memory_headroom_satisfied": False,
            "system_pressure": "warning",
            "memory_pressure_normal": False,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                candidate = _candidate()
                candidate["resource_admission"][field] = value
                self._assert_rejected(candidate, "resource_admission")

    def test_rejects_every_forbidden_execution_boolean(self) -> None:
        for field in _candidate()["execution"]:
            with self.subTest(field=field):
                candidate = _candidate()
                candidate["execution"][field] = True
                self._assert_rejected(candidate, "execution_boundary")

    def test_rejects_changed_claim_boundary_text(self) -> None:
        for field in ("warnings", "exclusions"):
            with self.subTest(field=field):
                candidate = _candidate()
                candidate[field][0] += " Unreviewed extension."
                self._assert_rejected(candidate, "claim_boundary")

    def test_malformed_claim_boundary_containers_fail_without_traceback(self) -> None:
        cases = (
            ("warnings-object", "warnings", {"unexpected": "value"}),
            ("warnings-nested-object", "warnings", [{}]),
            ("exclusions-object", "exclusions", {"unexpected": "value"}),
            ("exclusions-nested-list", "exclusions", [[], "a", "b"]),
        )
        for name, field, value in cases:
            with self.subTest(name=name):
                candidate = _candidate()
                candidate[field] = value
                self._assert_rejected(candidate, "schema_violation")

    def test_rejects_private_secret_and_control_values_without_echo(self) -> None:
        private_path = str(Path("/", "Users", "private-operator", "model.gguf"))
        cases = (
            ("private-path", "artifact", "location_symbolic", private_path),
            ("secret-field", "artifact", "access_token", "fixture-sensitive"),
            (
                "control-character",
                "warnings",
                0,
                "bounded warning\u200e",
            ),
        )
        for name, container, field, value in cases:
            with self.subTest(name=name):
                candidate = _candidate()
                candidate[container][field] = value
                with tempfile.TemporaryDirectory(
                    prefix="pulsarmlx-inspection-test-"
                ) as temporary:
                    candidate_path = self._write(Path(temporary), candidate)
                    completed = self._run(candidate_path)
                self.assertNotEqual(completed.returncode, 0)
                self.assertNotIn(private_path, completed.stderr)
                self.assertNotIn("fixture-sensitive", completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)

    def test_duplicate_nonfinite_and_oversized_json_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-inspection-test-") as temporary:
            root = Path(temporary)
            duplicate = root / "duplicate.json"
            duplicate.write_text(
                '{"schema_version":1,"schema_version":1}\n', encoding="utf-8"
            )
            duplicate_result = self._run(duplicate)
            self.assertNotEqual(duplicate_result.returncode, 0)
            self.assertEqual(json.loads(duplicate_result.stderr)["code"], "duplicate_json_field")

            nonfinite = root / "nonfinite.json"
            nonfinite.write_text('{"value":NaN}\n', encoding="utf-8")
            nonfinite_result = self._run(nonfinite)
            self.assertNotEqual(nonfinite_result.returncode, 0)
            self.assertEqual(json.loads(nonfinite_result.stderr)["code"], "invalid_json_number")

            oversized = root / "oversized.json"
            oversized.write_bytes(b'{"value":"' + b"a" * validator.MAX_CANDIDATE_BYTES + b'"}')
            oversized_result = self._run(oversized)
            self.assertNotEqual(oversized_result.returncode, 0)
            self.assertEqual(json.loads(oversized_result.stderr)["code"], "bounded_input")

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links unavailable")
    def test_regular_nonlink_external_input_is_mandatory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-inspection-test-") as temporary:
            root = Path(temporary)
            candidate_path = self._write(root, _candidate())
            alias = root / "alias.json"
            alias.symlink_to(candidate_path)
            completed = self._run(alias)
            self.assertNotEqual(completed.returncode, 0)
            self.assertEqual(json.loads(completed.stderr)["code"], "unsafe_path")

            in_repository = self._run(SCHEMA)
            self.assertNotEqual(in_repository.returncode, 0)
            self.assertEqual(json.loads(in_repository.stderr)["code"], "unsafe_path")

    def test_validation_report_is_public_safe_atomic_and_exclusive(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-inspection-test-") as temporary:
            root = Path(temporary)
            candidate_path = self._write(root, _candidate())
            output = root / "validation.json"
            completed = self._run(candidate_path, output=output)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            before = output.read_bytes()
            report = json.loads(before)
            self.assertTrue(report["passed"])
            self.assertNotIn(str(root), before.decode("utf-8"))
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

            repeated = self._run(candidate_path, output=output)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertEqual(output.read_bytes(), before)

            with self.assertRaises(validator.InspectionValidationError):
                validator._write_exclusive(
                    candidate_path,
                    report,
                    input_paths=(candidate_path,),
                )

    def test_atomic_writer_cleans_temporary_state_on_install_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-inspection-test-") as temporary:
            root = Path(temporary)
            candidate_path = self._write(root, _candidate())
            report = {"passed": True, "public_safe": True}
            output = root / "validation.json"
            with (
                mock.patch.object(validator.os, "link", side_effect=OSError("bounded")),
                self.assertRaises(validator.InspectionValidationError),
            ):
                validator._write_exclusive(
                    output,
                    report,
                    input_paths=(candidate_path,),
                )
            self.assertFalse(output.exists())
            self.assertEqual(
                sorted(path.name for path in root.iterdir()),
                [candidate_path.name],
            )

    def test_atomic_writer_anchors_creation_and_installation_to_one_parent_dirfd(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-inspection-test-") as temporary:
            root = Path(temporary)
            candidate_path = self._write(root, _candidate())
            output = root / "validation.json"
            with (
                mock.patch.object(validator.os, "open", wraps=os.open) as opened,
                mock.patch.object(validator.os, "link", wraps=os.link) as linked,
                mock.patch.object(validator.os, "fsync", wraps=os.fsync) as synced,
            ):
                validator._write_exclusive(
                    output,
                    {"passed": True, "public_safe": True},
                    input_paths=(candidate_path,),
                )
            temporary_open = [
                call
                for call in opened.call_args_list
                if call.kwargs.get("dir_fd") is not None
            ]
            self.assertEqual(len(temporary_open), 1)
            parent_fd = temporary_open[0].kwargs["dir_fd"]
            self.assertEqual(linked.call_count, 1)
            self.assertEqual(linked.call_args.kwargs["src_dir_fd"], parent_fd)
            self.assertEqual(linked.call_args.kwargs["dst_dir_fd"], parent_fd)
            self.assertFalse(linked.call_args.kwargs["follow_symlinks"])
            self.assertGreaterEqual(synced.call_count, 2)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["passed"], True)


if __name__ == "__main__":
    unittest.main()
