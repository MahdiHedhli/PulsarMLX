"""Model-free contracts for public-safe environment collection."""

from __future__ import annotations

from datetime import datetime, timezone
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts.research.tests.test_validate_evidence import SOURCE_COMMIT, valid_evidence
from scripts.research.validate_evidence import EvidenceValidationError, validate_record


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "research" / "environment.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("pulsarmlx_environment", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("environment collector could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


environment = _load_module()


class FixtureRunner:
    def __init__(self, *, pressure: str = "1", power: str = "0", thermal: str = "nominal"):
        self.pressure = pressure
        self.power = power
        self.thermal = thermal
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, argv):
        command = tuple(argv)
        self.calls.append(command)
        if command[:3] == ("git", "-C", str(REPOSITORY_ROOT)):
            if command[-2:] == ("rev-parse", "HEAD"):
                return 0, "a" * 40 + "\n"
            if "status" in command:
                return 0, ""
        values = {
            ("/usr/bin/sw_vers", "-productVersion"): "26.0\n",
            ("/usr/bin/sw_vers", "-buildVersion"): "25A123\n",
            ("/usr/bin/uname", "-m"): "arm64\n",
            ("/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"): "Apple M1 Ultra\n",
            ("/usr/sbin/sysctl", "-n", "hw.memsize"): "137438953472\n",
            ("/usr/sbin/sysctl", "-n", "hw.physicalcpu"): "20\n",
            ("/usr/sbin/sysctl", "-n", "hw.logicalcpu"): "20\n",
            (
                "/usr/sbin/sysctl",
                "-n",
                "kern.memorystatus_vm_pressure_level",
            ): self.pressure + "\n",
            ("/usr/bin/pmset", "-g", "live"): f" lowpowermode {self.power}\n",
            ("/usr/bin/pmset", "-g", "therm"): (
                "No thermal warning level has been recorded\n"
                if self.thermal == "nominal"
                else self.thermal + " thermal warning\n"
            ),
            ("rustc", "--version"): "rustc 1.97.1 (fixture)\n",
            ("cargo", "--version"): "cargo 1.97.1 (fixture)\n",
        }
        if command in values:
            return 0, values[command]
        if command[:2] == ("/bin/df", "-P"):
            return 0, (
                "Filesystem 512-blocks Used Available Capacity Mounted on\n"
                "/dev/disk-fixture 1000 100 900 10% /fixture\n"
            )
        if command == ("/usr/sbin/diskutil", "info", "/dev/disk-fixture"):
            return 0, "   File System Personality:   APFS\n"
        if command[:3] == ("/bin/ps", "-o", "rss="):
            return 0, "1\n"
        return 127, ""


def _collect(**overrides):
    runner = overrides.pop("runner", FixtureRunner())
    ticks = iter((1_000, 2_500))
    kwargs = {
        "repository_root": REPOSITORY_ROOT,
        "storage_root": Path("/private/external-model-location"),
        "storage_role": "model_storage",
        "storage_locator": "$PULSARMLX_MODEL_STORAGE_ROOT",
        "capture_phase": "before",
        "workload_category": "none",
        "benchmark_concurrency": 1,
        "execution_environment": {
            "PULSARMLX_MODEL_GGUF": "/private/model.gguf",
            "PULSARMLX_MODEL_STORAGE_ROOT": "/private/external-model-location",
            "PULSARMLX_ROUTER_EVIDENCE": "/private/evidence",
        },
        "runner": runner,
        "statvfs": lambda _path: SimpleNamespace(
            f_bavail=300,
            f_frsize=environment.GIB,
        ),
        "load_average": lambda: (1.0, 0.5, 0.25),
        "now": lambda: datetime(2026, 8, 6, 4, 5, 6, tzinfo=timezone.utc),
        "monotonic_ns": lambda: next(ticks),
    }
    kwargs.update(overrides)
    with mock.patch.object(environment.importlib.metadata, "version", return_value="0.32.0"):
        return environment.collect_environment(**kwargs)


class EnvironmentCollectorContractTests(unittest.TestCase):
    maxDiff = None

    def test_complete_snapshot_is_public_safe_and_path_free(self) -> None:
        snapshot = _collect()

        self.assertEqual(snapshot["snapshot_schema"], "pulsarmlx.research.environment")
        self.assertEqual(snapshot["snapshot_schema_version"], "1.0.0")
        self.assertEqual(snapshot["requested_backend"], "apple-mlx")
        self.assertEqual(snapshot["requested_device"], "gpu")
        self.assertEqual(snapshot["storage_role"], "model_storage")
        self.assertEqual(
            snapshot["storage_locator"], "$PULSARMLX_MODEL_STORAGE_ROOT"
        )
        self.assertEqual(snapshot["interference_admission"], "admitted")
        self.assertEqual(snapshot["admission_reasons"], [])
        self.assertEqual(
            snapshot["safe_environment"],
            {
                "PULSARMLX_MODEL_GGUF": "$PULSARMLX_MODEL_GGUF",
                "PULSARMLX_MODEL_STORAGE_ROOT": "$PULSARMLX_MODEL_STORAGE_ROOT",
                "PULSARMLX_ROUTER_EVIDENCE": "$PULSARMLX_ROUTER_EVIDENCE",
            },
        )
        observations = snapshot["observations"]
        self.assertEqual(observations["memory_pressure"]["value"], "normal")
        self.assertEqual(observations["power_mode"]["value"], "automatic")
        self.assertEqual(observations["thermal_state"]["value"], "nominal")
        self.assertEqual(observations["filesystem_type"]["value"], "apfs")
        self.assertEqual(
            observations["available_storage_bytes"]["value"], 300 * environment.GIB
        )
        self.assertEqual(observations["capture_wall_time_ns"]["value"], 1_500)
        encoded = json.dumps(snapshot, sort_keys=True)
        self.assertNotIn("/private/external-model-location", encoded)
        self.assertNotIn("/private/model.gguf", encoded)
        environment.assert_public_safe(snapshot)

    def test_conditional_probes_retain_unavailable_reason_and_method(self) -> None:
        runner = FixtureRunner()

        def missing_power_and_thermal(argv):
            command = tuple(argv)
            if command[:2] == ("/usr/bin/pmset", "-g"):
                return 1, "/" + "Users/private-user must not leak"
            return runner(command)

        snapshot = _collect(runner=missing_power_and_thermal)
        for name in ("power_mode", "thermal_state", "collector_process_bytes_read"):
            item = snapshot["observations"][name]
            self.assertEqual(item["status"], "unavailable")
            self.assertTrue(item["reason"])
            self.assertTrue(item["attempted_method"])
        self.assertNotIn("private-user", json.dumps(snapshot))
        self.assertEqual(snapshot["interference_admission"], "admitted")

    def test_resource_and_interference_admission_fail_closed(self) -> None:
        snapshot = _collect(
            runner=FixtureRunner(pressure="2", power="1", thermal="serious"),
            workload_category="local_inference",
            statvfs=lambda _path: SimpleNamespace(f_bavail=10, f_frsize=environment.GIB),
        )

        self.assertEqual(snapshot["interference_admission"], "postponed")
        self.assertEqual(
            snapshot["admission_reasons"],
            [
                "storage_admission_failed",
                "memory_pressure_not_normal",
                "low_power_mode_active",
                "thermal_state_not_nominal",
                "material_concurrent_workload_declared",
            ],
        )

    def test_high_normalized_load_is_not_admitted(self) -> None:
        snapshot = _collect(load_average=lambda: (16.0, 16.0, 1.0))

        self.assertEqual(snapshot["interference_admission"], "postponed")
        self.assertEqual(
            snapshot["admission_reasons"],
            [
                "load_average_1m_admission_failed",
                "load_average_5m_admission_failed",
            ],
        )

    def test_post_run_admission_failure_is_observed_interference(self) -> None:
        snapshot = _collect(
            capture_phase="after",
            workload_category="large_build",
        )

        self.assertEqual(snapshot["interference_admission"], "observed_interference")
        self.assertEqual(
            snapshot["admission_reasons"],
            ["material_concurrent_workload_declared"],
        )

    def test_secret_shaped_and_unknown_environment_keys_are_rejected(self) -> None:
        for values in (
            {"HF_TOKEN": "not-published"},
            {"PULSARMLX_AUTH_HEADER": "not-published"},
            {"UNREVIEWED_PATH": "/tmp/value"},
        ):
            with self.subTest(values=tuple(values)):
                with self.assertRaises(environment.EnvironmentCollectionError):
                    environment.sanitize_execution_environment(values)

    def test_recursive_privacy_guard_rejects_identifiers_and_private_paths(self) -> None:
        forbidden = (
            {"user" + "name": "fixture-user"},
            {"account" + "_id": "private-account"},
            {"nested": {"value": "/" + "Users/fixture-user/model.gguf"}},
            {"nested": "550e8400-e29b-41d4-" + "a716-446655440000"},
            {"nested": "aa:bb:cc:" + "dd:ee:ff"},
            {"nested": "192.168.1.10"},
            {"nested": "fixture-host.local"},
            {"operator_contact": "private.user@example.com"},
            {"nested": "file:///" + "Users/fixture-user/model.gguf"},
            {"nested": "rustc (.../" + "Users/fixture-user/toolchain)"},
            {"nested": "/" + "Volumes/PrivateModel/checkpoint.gguf"},
            {"nested": "h" + "f_" + "abcdefghijklmnopqrstuvwxyz"},
        )
        for value in forbidden:
            with self.subTest(value=value):
                with self.assertRaises(environment.EnvironmentCollectionError):
                    environment.assert_public_safe(value)

    def test_paths_normalize_to_repository_relative_or_symbolic_values(self) -> None:
        self.assertEqual(
            environment.normalize_public_path(
                REPOSITORY_ROOT / "docs" / "research" / "RESULTS.md",
                repository_root=REPOSITORY_ROOT,
                external_symbol="$PULSARMLX_EXTERNAL_PATH",
            ),
            "docs/research/RESULTS.md",
        )
        self.assertEqual(
            environment.normalize_public_path(
                Path("/" + "Users/private-user/checkpoint.gguf"),
                repository_root=REPOSITORY_ROOT,
                external_symbol="$PULSARMLX_MODEL_GGUF",
            ),
            "$PULSARMLX_MODEL_GGUF",
        )

    def test_output_is_exclusive_and_does_not_overwrite(self) -> None:
        snapshot = _collect()
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-environment-test-") as temp:
            output = Path(temp) / "environment.json"
            with mock.patch.object(environment, "collect_environment", return_value=snapshot):
                first = environment.main(
                    [
                        "capture",
                        "--storage-root",
                        str(Path(temp)),
                        "--storage-role",
                        "candidate_evidence_storage",
                        "--storage-locator",
                        "$PULSARMLX_ROUTER_EVIDENCE",
                        "--capture-phase",
                        "before",
                        "--workload-category",
                        "none",
                        "--output",
                        str(output),
                    ]
                )
                second = environment.main(
                    [
                        "capture",
                        "--storage-root",
                        str(Path(temp)),
                        "--storage-role",
                        "candidate_evidence_storage",
                        "--storage-locator",
                        "$PULSARMLX_ROUTER_EVIDENCE",
                        "--capture-phase",
                        "before",
                        "--workload-category",
                        "none",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(first, 0)
            self.assertEqual(second, 1)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), snapshot)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)

    def test_atomic_writer_leaves_no_partial_destination_on_preinstall_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-environment-test-") as temp:
            output = Path(temp) / "environment.json"
            with mock.patch.object(environment.os, "fsync", side_effect=OSError("fixture")):
                with self.assertRaises(OSError):
                    environment.write_json_exclusive_atomic(output, "{\"complete\":true}\n")
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(temp).glob(".*.tmp")), [])

    def test_atomic_writer_rolls_back_install_when_directory_sync_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-environment-test-") as temp:
            output = Path(temp) / "environment.json"
            with mock.patch.object(
                environment.os,
                "fsync",
                side_effect=(None, OSError("directory sync fixture"), None),
            ):
                with self.assertRaises(OSError):
                    environment.write_json_exclusive_atomic(
                        output, "{\"complete\":true}\n"
                    )
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(temp).glob(".*.tmp")), [])

    def test_concurrent_atomic_writers_install_exactly_one_complete_document(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-environment-test-") as temp:
            output = Path(temp) / "environment.json"

            def write(payload: str) -> str:
                try:
                    environment.write_json_exclusive_atomic(output, payload)
                    return "installed"
                except FileExistsError:
                    return "exists"

            payloads = ('{"writer":1}\n', '{"writer":2}\n')
            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(write, payloads))
            self.assertEqual(sorted(outcomes), ["exists", "installed"])
            self.assertIn(output.read_text(encoding="utf-8"), payloads)

    def test_capture_retains_postponed_snapshot_and_returns_nonzero(self) -> None:
        snapshot = _collect(workload_category="local_inference")
        self.assertEqual(snapshot["interference_admission"], "postponed")
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-environment-test-") as temp:
            output = Path(temp) / "environment.json"
            with mock.patch.object(environment, "collect_environment", return_value=snapshot):
                result = environment.main(
                    [
                        "capture",
                        "--storage-root",
                        temp,
                        "--storage-role",
                        "candidate_evidence_storage",
                        "--storage-locator",
                        "$PULSARMLX_ROUTER_EVIDENCE",
                        "--capture-phase",
                        "before",
                        "--workload-category",
                        "local_inference",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(result, 2)
            retained = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(retained["interference_admission"], "postponed")

    def test_cli_never_probes_the_model_environment_value(self) -> None:
        snapshot = _collect()
        private_model = "/" + "Users/private-user/Qwen3-30B-A3B-Q8_0.gguf"
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-environment-test-") as temp:
            output = Path(temp) / "environment.json"
            with (
                mock.patch.dict(
                    environment.os.environ,
                    {"PULSARMLX_MODEL_GGUF": private_model},
                    clear=False,
                ),
                mock.patch.object(environment, "collect_environment", return_value=snapshot) as collect,
            ):
                result = environment.main(
                    [
                        "capture",
                        "--storage-root",
                        temp,
                        "--storage-role",
                        "candidate_evidence_storage",
                        "--storage-locator",
                        "$PULSARMLX_ROUTER_EVIDENCE",
                        "--capture-phase",
                        "before",
                        "--workload-category",
                        "none",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(result, 0)
            serialized_call = repr(collect.call_args)
            self.assertNotIn(private_model, serialized_call)

    def test_model_looking_storage_operand_is_rejected_before_probe(self) -> None:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-environment-test-") as temp:
            model = Path(temp) / "checkpoint.gguf"
            model.write_bytes(b"fixture-not-a-model")
            with self.assertRaises(environment.EnvironmentCollectionError):
                environment._validate_storage_root(
                    model,
                    storage_role="model_storage",
                    repository_root=REPOSITORY_ROOT,
                )

    def test_storage_observation_is_bound_to_the_declared_symbolic_root(self) -> None:
        statvfs = mock.Mock(
            return_value=SimpleNamespace(f_bavail=300, f_frsize=environment.GIB)
        )
        with self.assertRaises(environment.EnvironmentCollectionError):
            _collect(
                execution_environment={
                    "PULSARMLX_MODEL_GGUF": "/private/model.gguf",
                    "PULSARMLX_MODEL_STORAGE_ROOT": "/private/different-storage",
                },
                statvfs=statvfs,
            )
        statvfs.assert_not_called()

    def test_filesystem_probe_never_treats_stat_file_type_as_filesystem(self) -> None:
        def old_incorrect_probe(argv):
            command = tuple(argv)
            if command[:2] == ("/bin/df", "-P"):
                return 0, "Filesystem 512-blocks Used Available Capacity Mounted on\n/dev/disk-x 1 1 1 1% /\n"
            if command == ("/usr/sbin/diskutil", "info", "/dev/disk-x"):
                return 0, "   Type: Directory\n"
            return 127, ""

        result = environment._filesystem_type(Path("/fixture"), old_incorrect_probe)
        self.assertEqual(result["status"], "unavailable")

    def test_snapshot_integrates_with_evidence_and_private_values_fail_closed(self) -> None:
        before = _collect()
        after = _collect(capture_phase="after")
        for snapshot in (before, after):
            for name in ("repository_commit", "pulsarmlx_version"):
                snapshot["observations"][name]["value"] = SOURCE_COMMIT
        benchmark_resources = {
            "process_footprint_bytes": environment.observed(1024, "worker_process_footprint"),
            "mlx_active_memory_bytes": environment.observed(256, "mlx_active_memory"),
            "mlx_cache_memory_bytes": environment.observed(128, "mlx_cache_memory"),
            "mlx_peak_memory_bytes": environment.observed(512, "mlx_peak_memory"),
            "process_cpu_time_seconds": environment.unavailable(
                "the benchmark did not expose a bounded CPU-time gauge",
                "worker_process_cpu_time",
            ),
            "process_bytes_read": environment.unavailable(
                "the benchmark did not expose reliable process bytes read",
                "worker_process_bytes_read",
            ),
            "worker_backend": environment.observed("apple-mlx", "worker"),
            "worker_requested_device": environment.observed("gpu", "worker"),
            "worker_selected_device": environment.observed("gpu", "worker"),
            "worker_fallback_used": environment.observed(False, "worker"),
            "worker_evaluated": environment.observed(True, "worker"),
            "worker_synchronized": environment.observed(True, "worker"),
        }
        combined = environment.combine_environment_evidence(
            before_snapshot=before,
            after_snapshot=after,
            after_unavailable_reason=None,
            benchmark_resources=benchmark_resources,
        )
        record = valid_evidence("f002-router-fixture-environment-0001")
        record["environment"] = combined

        validate_record(record)

        polluted = deepcopy(record)
        polluted["environment"]["before_snapshot"]["observations"]["chip_model"]["value"] = (
            "/" + "Users/private-user/private-chip-record"
        )
        with self.assertRaises(EvidenceValidationError) as captured:
            validate_record(polluted)
        self.assertEqual(captured.exception.code, "private_value")

    def test_pair_detects_pressure_power_thermal_and_workload_transitions(self) -> None:
        before = _collect()
        after = _collect(capture_phase="after")
        transitions = {
            "memory_pressure": "warning",
            "power_mode": "low_power",
            "thermal_state": "serious",
            "workload_category": "local_inference",
            "material_concurrent_workload": True,
        }
        for name, value in transitions.items():
            after["observations"][name] = environment.observed(value, "fixture_transition")
        after["interference_admission"] = "observed_interference"
        after["admission_reasons"] = [
            "memory_pressure_not_normal",
            "low_power_mode_active",
            "thermal_state_not_nominal",
            "material_concurrent_workload_declared",
        ]
        resources = {
            "process_footprint_bytes": environment.observed(1024, "worker"),
            "mlx_active_memory_bytes": environment.observed(256, "worker"),
            "mlx_cache_memory_bytes": environment.observed(128, "worker"),
            "mlx_peak_memory_bytes": environment.observed(512, "worker"),
            "process_cpu_time_seconds": environment.unavailable("not observed", "worker"),
            "process_bytes_read": environment.unavailable("not observed", "worker"),
            "worker_backend": environment.observed("apple-mlx", "worker"),
            "worker_requested_device": environment.observed("gpu", "worker"),
            "worker_selected_device": environment.observed("gpu", "worker"),
            "worker_fallback_used": environment.observed(False, "worker"),
            "worker_evaluated": environment.observed(True, "worker"),
            "worker_synchronized": environment.observed(True, "worker"),
        }

        combined = environment.combine_environment_evidence(
            before_snapshot=before,
            after_snapshot=after,
            after_unavailable_reason=None,
            benchmark_resources=resources,
        )

        self.assertEqual(combined["interference_admission"], "observed_interference")
        self.assertIn("power_mode_changed_during_batch", combined["interference_reasons"])
        self.assertIn("thermal_state_changed_during_batch", combined["interference_reasons"])
        self.assertIn("workload_changed_during_batch", combined["interference_reasons"])

    def test_combiner_rejects_unvalidated_snapshot_admission_labels(self) -> None:
        forged = {
            "capture_phase": "before",
            "interference_admission": "admitted",
            "admission_reasons": [],
        }
        resources = {
            "process_footprint_bytes": environment.observed(1024, "worker"),
            "mlx_active_memory_bytes": environment.observed(256, "worker"),
            "mlx_cache_memory_bytes": environment.observed(128, "worker"),
            "mlx_peak_memory_bytes": environment.observed(512, "worker"),
            "process_cpu_time_seconds": environment.unavailable("not observed", "worker"),
            "process_bytes_read": environment.unavailable("not observed", "worker"),
            "worker_backend": environment.observed("apple-mlx", "worker"),
            "worker_requested_device": environment.observed("gpu", "worker"),
            "worker_selected_device": environment.observed("gpu", "worker"),
            "worker_fallback_used": environment.observed(False, "worker"),
            "worker_evaluated": environment.observed(True, "worker"),
            "worker_synchronized": environment.observed(True, "worker"),
        }
        with self.assertRaises(environment.EnvironmentCollectionError):
            environment.combine_environment_evidence(
                before_snapshot=forged,
                after_snapshot={**forged, "capture_phase": "after"},
                after_unavailable_reason=None,
                benchmark_resources=resources,
            )

    def test_combiner_rejects_semantically_forged_complete_snapshots(self) -> None:
        resources = {
            "process_footprint_bytes": environment.observed(1024, "worker"),
            "mlx_active_memory_bytes": environment.observed(256, "worker"),
            "mlx_cache_memory_bytes": environment.observed(128, "worker"),
            "mlx_peak_memory_bytes": environment.observed(512, "worker"),
            "process_cpu_time_seconds": environment.unavailable("not observed", "worker"),
            "process_bytes_read": environment.unavailable("not observed", "worker"),
            "worker_backend": environment.observed("apple-mlx", "worker"),
            "worker_requested_device": environment.observed("gpu", "worker"),
            "worker_selected_device": environment.observed("gpu", "worker"),
            "worker_fallback_used": environment.observed(False, "worker"),
            "worker_evaluated": environment.observed(True, "worker"),
            "worker_synchronized": environment.observed(True, "worker"),
        }
        for observation_name, forged_value in (
            ("power_mode", "turbo"),
            ("thermal_state", "unknown-hot-state"),
            ("captured_at_utc", "not-a-time"),
        ):
            with self.subTest(observation_name=observation_name):
                before = _collect()
                after = _collect(capture_phase="after")
                before["observations"][observation_name] = environment.observed(
                    forged_value, "forged_complete_snapshot"
                )
                after["observations"][observation_name] = environment.observed(
                    forged_value, "forged_complete_snapshot"
                )
                with self.assertRaises(environment.EnvironmentCollectionError):
                    environment.combine_environment_evidence(
                        before_snapshot=before,
                        after_snapshot=after,
                        after_unavailable_reason=None,
                        benchmark_resources=resources,
                    )

    def test_combine_cli_hands_snapshots_and_worker_resources_to_evidence(self) -> None:
        before = _collect()
        after = _collect(capture_phase="after")
        resources = {
            "process_footprint_bytes": environment.observed(1024, "worker"),
            "mlx_active_memory_bytes": environment.observed(256, "worker"),
            "mlx_cache_memory_bytes": environment.observed(128, "worker"),
            "mlx_peak_memory_bytes": environment.observed(512, "worker"),
            "process_cpu_time_seconds": environment.unavailable("not observed", "worker"),
            "process_bytes_read": environment.unavailable("not observed", "worker"),
            "worker_backend": environment.observed("apple-mlx", "worker"),
            "worker_requested_device": environment.observed("gpu", "worker"),
            "worker_selected_device": environment.observed("gpu", "worker"),
            "worker_fallback_used": environment.observed(False, "worker"),
            "worker_evaluated": environment.observed(True, "worker"),
            "worker_synchronized": environment.observed(True, "worker"),
        }
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-environment-test-") as temp:
            root = Path(temp)
            before_path = root / "before.json"
            after_path = root / "after.json"
            resources_path = root / "resources.json"
            output = root / "combined.json"
            before_path.write_text(json.dumps(before), encoding="utf-8")
            after_path.write_text(json.dumps(after), encoding="utf-8")
            resources_path.write_text(json.dumps(resources), encoding="utf-8")

            result = environment.main(
                [
                    "combine",
                    "--before",
                    str(before_path),
                    "--after",
                    str(after_path),
                    "--benchmark-resources",
                    str(resources_path),
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(result, 0)
            combined = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(combined["interference_admission"], "admitted")
            self.assertEqual(combined["before_snapshot"]["capture_phase"], "before")
            self.assertEqual(combined["after_snapshot"]["capture_phase"], "after")

    def test_resource_extractor_uses_all_worker_gauges_and_retains_unavailable_reasons(self) -> None:
        candidate = {
            "positive_cases": [
                {
                    "backend": "apple-mlx",
                    "requested_device": "gpu",
                    "selected_device": "gpu",
                    "fallback_used": False,
                    "evaluated": True,
                    "synchronized": True,
                    "memory_gauges": {
                        "process_footprint_bytes": 1024,
                        "mlx_active_bytes": 256,
                        "mlx_cache_bytes": 128,
                        "mlx_peak_bytes": 512,
                    }
                },
                {
                    "backend": "apple-mlx",
                    "requested_device": "gpu",
                    "selected_device": "gpu",
                    "fallback_used": False,
                    "evaluated": True,
                    "synchronized": True,
                    "memory_gauges": {
                        "process_footprint_bytes": 2048,
                        "mlx_active_bytes": 384,
                        "mlx_cache_bytes": 192,
                        "mlx_peak_bytes": 768,
                    }
                },
            ]
        }

        resources = environment.extract_benchmark_resources(candidate)

        self.assertEqual(resources["process_footprint_bytes"]["value"], 2048)
        self.assertEqual(resources["mlx_peak_memory_bytes"]["value"], 768)
        self.assertEqual(resources["worker_backend"]["value"], "apple-mlx")
        self.assertEqual(resources["worker_selected_device"]["value"], "gpu")
        self.assertEqual(resources["process_cpu_time_seconds"]["status"], "unavailable")
        self.assertEqual(resources["process_bytes_read"]["status"], "unavailable")

        fallback = deepcopy(candidate)
        fallback["positive_cases"][0]["fallback_used"] = True
        with self.assertRaises(environment.EnvironmentCollectionError):
            environment.extract_benchmark_resources(fallback)

        unbound = deepcopy(candidate)
        del unbound["positive_cases"][0]["selected_device"]
        with self.assertRaises(environment.EnvironmentCollectionError):
            environment.extract_benchmark_resources(unbound)

        wrong_backend = deepcopy(candidate)
        wrong_backend["positive_cases"][0]["backend"] = "cpu"
        with self.assertRaises(environment.EnvironmentCollectionError):
            environment.extract_benchmark_resources(wrong_backend)


if __name__ == "__main__":
    unittest.main()
