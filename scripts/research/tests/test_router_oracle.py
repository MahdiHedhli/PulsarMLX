"""Contract tests for the independent Feature 002 router oracle.

The fixtures in this module are generated scalars, scheduler logs, and stub
capture records. They never resolve or open a model or external source tree.
"""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ORACLE_PATH = REPOSITORY_ROOT / "scripts" / "research" / "router_oracle.py"
CAPTURE_SCRIPT = (
    REPOSITORY_ROOT / "scripts" / "research" / "capture_router_oracle.sh"
)
CAPTURE_HELPER = (
    REPOSITORY_ROOT
    / "scripts"
    / "research"
    / "llama_capture"
    / "router_capture.cpp"
)
PINNED_LLAMA_CPP_REVISION = "b06aa774c03dbbb624e726664b714a57d1f49815"
PINNED_MODEL_SHA256 = "4ad960d180b16f56024f5b704697e5dd5b0837167c2e515ef0569abfc599743c"


def _load_oracle_module():
    if not ORACLE_PATH.is_file():
        return None

    specification = importlib.util.spec_from_file_location(
        "pulsarmlx_router_oracle", ORACLE_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load router oracle module: {ORACLE_PATH}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    try:
        specification.loader.exec_module(module)
    finally:
        sys.modules.pop(specification.name, None)
    return module


oracle = _load_oracle_module()


def _cancellation_trace(**changes: object) -> dict[str, object]:
    trace: dict[str, object] = {
        "backend": "cpu",
        "scheduler_trace_format": "ggml_sched_debug_marker_v1",
        "scheduler_split_count": 1,
        "scheduler_split_ids": [0],
        "scheduler_backends": ["cpu"],
        "scheduler_input_count": 0,
        "scheduler_trace_sha256": "d" * 64,
        "retained_scheduler_trace_byte_length": 96,
        "retained_scheduler_trace_sha256": "e" * 64,
        "target": "ffn_norm-0",
        "target_ask_count": 1,
        "target_observation_count": 1,
        "target_complete": True,
        "callback_returned_false": True,
        "abort_guard_armed": True,
        "abort_callback_call_count": 12,
        "abort_callback_calls_after_target": 0,
        "abort_callback_true_count": 0,
        "decode_status": 0,
        "nodes_after_target": [],
    }
    trace.update(changes)
    return trace


def _capture_record(*, capture_hash: str = "a" * 64) -> dict[str, object]:
    return {
        "source_revision": PINNED_LLAMA_CPP_REVISION,
        "capture_node": "ffn_norm-0",
        "capture_sha256": capture_hash,
        "row_sha256": ["b" * 64, "c" * 64],
        "shape": [2, 2048],
        "dtype": "float32_little_endian",
        "direct_token_ids": [0, 1],
        "positions": [0, 1],
        "context": 2,
        "batch": 2,
        "ubatch": 2,
        "threads": 1,
        "input_adapter": "direct_token_ids_v1",
        "tokenizer": "not_used_direct_token_ids",
        "model_identity": _model_identity(),
        "cancellation": _cancellation_trace(),
    }


def _model_identity(**changes: object) -> dict[str, object]:
    identity: dict[str, object] = {
        "device": 17,
        "inode": 23,
        "size_bytes": 32_483_931_648,
        "sha256": PINNED_MODEL_SHA256,
        "pre_post_match": True,
    }
    identity.update(changes)
    return identity


def _capture_provenance() -> dict[str, object]:
    model = _model_identity()
    helper = {
        "device": 17,
        "inode": 29,
        "size_bytes": 4096,
        "sha256": "e" * 64,
    }
    return {
        "schema": "pulsarmlx.research.router-capture-provenance",
        "schema_version": "1.0.0",
        "binding_strategy": "pre_post_full_sha256_plus_device_inode_size",
        "admitted_model": model,
        "build": {
            "attempt_scoped_fresh": True,
            "source_revision": PINNED_LLAMA_CPP_REVISION,
            "source_tree": "f" * 40,
            "source_clean_before": True,
            "source_clean_after": True,
            "capture_source_repository_sha256": "1" * 64,
            "capture_source_overlay_sha256": "1" * 64,
            "cmake_lists_sha256": "2" * 64,
            "cmake_cache_sha256": "3" * 64,
            "configure_log_sha256": "4" * 64,
            "build_log_sha256": "5" * 64,
            "configure_command": "cmake -S $ATTEMPT_SOURCE -B $ATTEMPT_BUILD",
            "build_command": "cmake --build $ATTEMPT_BUILD",
            "tools": [
                {"name": "cmake", "version": "cmake version test", "executable_sha256": "6" * 64},
                {"name": "cxx", "version": "clang version test", "executable_sha256": "7" * 64},
                {
                    "name": "cmake-build-tool",
                    "version": "ninja version test",
                    "executable_sha256": "8" * 64,
                },
            ],
            "helper": helper,
        },
        "consumers": [
            {
                "consumer_id": consumer_id,
                "model_before": model,
                "model_after": model,
                "helper_before": helper,
                "helper_after": helper,
            }
            for consumer_id in ("capture-a", "capture-b")
        ],
    }


def _write_complete_candidate(
    candidate: Path,
    *,
    scheduler_suffix: str = "",
) -> None:
    candidate.mkdir(mode=0o700)
    trace = "\n".join(
        (
            "PULSARMLX_SCHED_TRACE_BEGIN_V1",
            f"## SPLIT #0: CPU # 0 inputs{scheduler_suffix}",
            "PULSARMLX_SCHED_TRACE_END_V1",
            "",
        )
    )
    capture_bytes = struct.pack(
        "<4096f",
        *([0.0] * 2048),
        *([1.0] * 2048),
    )
    record = _capture_record()
    record.pop("capture_sha256")
    record.pop("row_sha256")
    record["decode_status"] = 0
    for attempt in ("a", "b"):
        (candidate / f"capture-{attempt}.f32le").write_bytes(capture_bytes)
        (candidate / f"capture-{attempt}.json").write_text(
            json.dumps(record, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raw_trace = candidate.parent / f".{candidate.name}-{attempt}-raw-trace.log"
        raw_trace.write_text(
            trace,
            encoding="utf-8",
        )
        oracle.retain_scheduler_trace(
            raw_trace,
            candidate / f"capture-{attempt}.scheduler-trace.txt",
        )
        raw_trace.unlink()

    first_rows, first_record = oracle._read_capture(
        candidate / "capture-a.f32le",
        candidate / "capture-a.json",
        candidate / "capture-a.scheduler-trace.txt",
    )
    second_rows, second_record = oracle._read_capture(
        candidate / "capture-b.f32le",
        candidate / "capture-b.json",
        candidate / "capture-b.scheduler-trace.txt",
    )
    if oracle.canonical_f32_bytes(first_rows) != oracle.canonical_f32_bytes(
        second_rows
    ):
        raise AssertionError("test candidate captures differ")
    capture = oracle.validate_capture_pair(first_record, second_record)
    provenance = _capture_provenance()
    validated_provenance = oracle.validate_capture_provenance(provenance)
    provenance_path = candidate / "capture-provenance.json"
    provenance_path.write_text(
        json.dumps(provenance, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    generator_sha256 = "9" * 64
    oracle_path = candidate / "oracle.json"
    oracle_path.write_text(
        json.dumps(
            {
                "schema": "pulsarmlx.research.router-oracle",
                "schema_version": "1.0.0",
                "status": "passed",
                "generator": {"sha256": generator_sha256},
                "capture": capture,
                "capture_provenance": validated_provenance,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    execution = {
        "schema": "pulsarmlx.research.router-oracle-execution-provenance",
        "schema_version": "1.0.0",
        "binding_strategy": "pre_post_full_sha256_plus_device_inode_size",
        "oracle_process_consumer": {
            "consumer_id": "oracle-process",
            "model_before": _model_identity(),
            "model_after": _model_identity(),
        },
        "oracle_source_sha256": generator_sha256,
        "capture_provenance_sha256": hashlib.sha256(
            provenance_path.read_bytes()
        ).hexdigest(),
        "oracle_document_sha256": hashlib.sha256(
            oracle_path.read_bytes()
        ).hexdigest(),
    }
    (candidate / "execution-provenance.json").write_text(
        json.dumps(execution, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    oracle.write_oracle_candidate_manifest(candidate)


class _NumpyProjectionStub:
    """Record the cross-check request without importing a numeric package."""

    def __init__(self, result: list[list[float]]) -> None:
        self.result = result
        self.calls: list[tuple[object, object, str]] = []

    def project_f32(self, hidden_rows, weight_rows, *, dtype: str):
        self.calls.append((hidden_rows, weight_rows, dtype))
        return self.result


class RouterOracleContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(
            oracle,
            "T034 must implement scripts/research/router_oracle.py",
        )

    def assert_oracle_error(self, expected_code: str, callable_, /, *args, **kwargs):
        with self.assertRaises(oracle.RouterOracleError) as caught:
            callable_(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected_code)
        self.assertLessEqual(len(caught.exception.message), 512)

    def test_pinned_source_record_requires_exact_clean_revision_and_cpu_build(self) -> None:
        admitted = {
            "repository": "https://github.com/ggml-org/llama.cpp.git",
            "revision": PINNED_LLAMA_CPP_REVISION,
            "clean": True,
            "license": "MIT",
            "metal": False,
            "gpu_offload": False,
        }
        validated = oracle.validate_pinned_source(admitted)
        self.assertEqual(validated["revision"], PINNED_LLAMA_CPP_REVISION)

        for field, changed in (
            ("revision", "d" * 40),
            ("clean", False),
            ("license", "unknown"),
            ("metal", True),
            ("gpu_offload", True),
        ):
            with self.subTest(field=field):
                self.assert_oracle_error(
                    "source_identity_mismatch",
                    oracle.validate_pinned_source,
                    {**admitted, field: changed},
                )

    def test_capture_provenance_binds_both_consumers_and_fresh_build(self) -> None:
        provenance = _capture_provenance()
        validated = oracle.validate_capture_provenance(provenance)
        self.assertTrue(validated["build"]["attempt_scoped_fresh"])
        self.assertEqual(
            [consumer["consumer_id"] for consumer in validated["consumers"]],
            ["capture-a", "capture-b"],
        )

        changed_model = _model_identity(inode=99)
        changed_consumer = {
            **provenance["consumers"][1],
            "model_after": changed_model,
        }
        self.assert_oracle_error(
            "capture_provenance_invalid",
            oracle.validate_capture_provenance,
            {
                **provenance,
                "consumers": [provenance["consumers"][0], changed_consumer],
            },
        )
        self.assert_oracle_error(
            "capture_provenance_invalid",
            oracle.validate_capture_provenance,
            {
                **provenance,
                "build": {**provenance["build"], "attempt_scoped_fresh": False},
            },
        )

    def test_bounded_json_reader_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text('{"capture": 1, "capture": 2}\n', encoding="utf-8")
            self.assert_oracle_error(
                "duplicate_json_key",
                oracle._read_bounded_json,
                path,
            )

            path.write_text(json.dumps({"capture": 1}) + "\n", encoding="utf-8")
            self.assertEqual(oracle._read_bounded_json(path), {"capture": 1})

    def test_two_independent_captures_must_be_complete_and_byte_identical(self) -> None:
        first = _capture_record()
        second = _capture_record()
        result = oracle.validate_capture_pair(first, second)

        self.assertEqual(result["capture_sha256"], "a" * 64)
        self.assertEqual(result["row_sha256"], ["b" * 64, "c" * 64])
        self.assertTrue(result["rows_distinct"])

        self.assert_oracle_error(
            "capture_mismatch",
            oracle.validate_capture_pair,
            first,
            _capture_record(capture_hash="d" * 64),
        )
        self.assert_oracle_error(
            "capture_mismatch",
            oracle.validate_capture_pair,
            first,
            {**second, "row_sha256": ["b" * 64, "b" * 64]},
        )
        unstable_identity = _model_identity()
        unstable_identity["pre_post_match"] = False
        self.assert_oracle_error(
            "capture_mismatch",
            oracle.validate_capture_pair,
            first,
            {**second, "model_identity": unstable_identity},
        )

    def test_cancellation_trace_proves_one_cpu_split_and_no_later_router_node(self) -> None:
        trace = _cancellation_trace()
        result = oracle.validate_cancellation_trace(trace)
        self.assertEqual(result["target"], "ffn_norm-0")
        self.assertTrue(result["cancelled_before_router_or_expert"])
        self.assertTrue(result["abort_guard_armed"])
        self.assertEqual(result["abort_callback_calls_after_target"], 0)
        self.assertEqual(result["abort_callback_true_count"], 0)

        for changed in (
            {"backend": "gpu"},
            {"scheduler_split_count": 2},
            {"scheduler_split_ids": [0, 1]},
            {"scheduler_backends": ["metal"]},
            {"scheduler_input_count": -1},
            {"retained_scheduler_trace_byte_length": 0},
            {"retained_scheduler_trace_sha256": "invalid"},
            {"target_ask_count": 2},
            {"target_observation_count": 0},
            {"target_complete": False},
            {"callback_returned_false": False},
            {"abort_guard_armed": False},
            {"abort_callback_call_count": 0},
            {"abort_callback_calls_after_target": 1},
            {"abort_callback_true_count": 1},
            {"decode_status": 2},
            {"split_count": 1},
            {"abort_guard_triggered": True},
            {"nodes_after_target": ["ffn_gate_inp-0"]},
            {"nodes_after_target": ["ffn_gate_exps-0"]},
        ):
            with self.subTest(changed=changed):
                self.assert_oracle_error(
                    "cancellation_unproved",
                    oracle.validate_cancellation_trace,
                    {**trace, **changed},
                )

    def test_scheduler_trace_requires_one_marker_delimited_cpu_split(self) -> None:
        valid = "\n".join(
            (
                "context initialization may contain ## SPLIT #9: Metal # 0 inputs",
                "PULSARMLX_SCHED_TRACE_BEGIN_V1",
                "## SPLIT #0: CPU # 0 inputs",
                "PULSARMLX_SCHED_TRACE_END_V1",
                "later output",
                "",
            )
        )
        result = oracle.validate_scheduler_debug_trace(valid)
        self.assertEqual(result["scheduler_split_count"], 1)
        self.assertEqual(result["scheduler_split_ids"], [0])
        self.assertEqual(result["scheduler_backends"], ["cpu"])
        self.assertRegex(result["scheduler_trace_sha256"], r"^[0-9a-f]{64}$")
        retained = oracle.canonical_scheduler_trace_bytes(valid)
        self.assertEqual(
            hashlib.sha256(retained).hexdigest(),
            result["retained_scheduler_trace_sha256"],
        )
        self.assertEqual(
            len(retained),
            result["retained_scheduler_trace_byte_length"],
        )
        self.assertNotIn(b"context initialization", retained)
        self.assertNotIn(b"later output", retained)

        private_path = "/" + "Users" + "/private/checkpoint.gguf"
        private_log = "/" + "Users" + "/private/router.log"
        private_marker_block = valid.replace(
            "## SPLIT #0: CPU # 0 inputs",
            f"## SPLIT #0: CPU # 0 inputs model={private_path}\n"
            f"diagnostic={private_log}",
        )
        sanitized = oracle.canonical_scheduler_trace_bytes(private_marker_block)
        self.assertEqual(sanitized, retained)
        self.assertNotIn(private_path.encode("utf-8"), sanitized)
        self.assertNotIn(private_log.encode("utf-8"), sanitized)
        self.assertEqual(
            oracle.validate_scheduler_debug_trace(private_marker_block)[
                "retained_scheduler_trace_sha256"
            ],
            result["retained_scheduler_trace_sha256"],
        )

        invalid_traces = (
            valid.replace("PULSARMLX_SCHED_TRACE_BEGIN_V1\n", ""),
            valid.replace(
                "PULSARMLX_SCHED_TRACE_BEGIN_V1",
                "PULSARMLX_SCHED_TRACE_END_V1",
                1,
            ),
            valid.replace(
                "## SPLIT #0: CPU # 0 inputs",
                "## SPLIT #0: CPU # 0 inputs\n## SPLIT #1: CPU # 1 inputs",
            ),
            valid.replace("## SPLIT #0: CPU", "## SPLIT #0: Metal"),
            valid.replace("## SPLIT #0: CPU", "## SPLIT #1: CPU"),
            valid.replace("# 0 inputs", "# 1000001 inputs"),
        )
        for trace in invalid_traces:
            with self.subTest(trace=trace):
                self.assert_oracle_error(
                    "scheduler_trace_invalid",
                    oracle.validate_scheduler_debug_trace,
                    trace,
                )

    def test_capture_helper_uses_runtime_evidence_without_manual_abort_probe(self) -> None:
        source = CAPTURE_HELPER.read_text(encoding="utf-8")
        self.assertNotIn("capture_abort_callback(&capture)", source)
        self.assertNotIn("abort_guard_triggered", source)
        self.assertNotIn('"split_count"', source)
        self.assertIn(
            "flash_attn_type = LLAMA_FLASH_ATTN_TYPE_DISABLED",
            source,
        )
        self.assertIn("load_mode = LLAMA_LOAD_MODE_MMAP", source)
        self.assertIn("abort_callback_calls_after_target", source)
        self.assertIn("state.nodes_after_target[index]", source)
        self.assertIn('option == "--model-device"', source)
        self.assertIn('option == "--model-inode"', source)
        self.assertIn('option == "--model-sha256"', source)
        self.assertIn("inspect_model_identity(arguments.model, model_identity_before)", source)
        self.assertIn("inspect_model_identity(arguments.model, model_identity_after)", source)
        begin = source.index("kSchedulerTraceBegin.data()")
        decode = source.index("llama_decode(context, batch)")
        end = source.index("kSchedulerTraceEnd.data()")
        self.assertLess(begin, decode)
        self.assertLess(decode, end)

    def test_scalar_projection_rounds_each_multiply_and_accumulate_to_f32(self) -> None:
        hidden = [[16_777_216.0, 1.0, -16_777_216.0]]
        weights = [
            [1.0, 1.0, 1.0],
            [0.5, -2.0, 0.25],
        ]
        result = oracle.scalar_f32_projection(hidden, weights)

        # Sequential float32 accumulation loses the middle +1 in row zero.
        self.assertEqual(result[0][0], 0.0)
        self.assertEqual(result[0][1], 4_194_302.0)
        encoded = oracle.canonical_f32_bytes(result)
        self.assertEqual(encoded, struct.pack("<ff", 0.0, 4_194_302.0))

    def test_numpy_projection_is_a_separate_injected_f32_cross_check(self) -> None:
        hidden = [[1.0, 2.0], [-1.0, 0.5]]
        weights = [[3.0, 4.0], [5.0, -2.0]]
        scalar = oracle.scalar_f32_projection(hidden, weights)
        numpy_stub = _NumpyProjectionStub([row.copy() for row in scalar])

        comparison = oracle.cross_check_numpy_f32(
            hidden,
            weights,
            scalar,
            numpy_adapter=numpy_stub,
        )
        self.assertTrue(comparison["passed"])
        self.assertEqual(comparison["mismatch_count"], 0)
        self.assertEqual(len(numpy_stub.calls), 1)
        self.assertEqual(numpy_stub.calls[0][2], "float32")

        disagreeing = _NumpyProjectionStub(
            [[value + (1.0 if column == 0 else 0.0) for column, value in enumerate(row)]
             for row in scalar]
        )
        self.assert_oracle_error(
            "numpy_cross_check_failed",
            oracle.cross_check_numpy_f32,
            hidden,
            weights,
            scalar,
            numpy_adapter=disagreeing,
        )

    def test_oracle_source_rejects_mlx_and_worker_imports(self) -> None:
        oracle.assert_independent_source(ORACLE_PATH.read_text(encoding="utf-8"))

        for forbidden in (
            "import mlx.core as mx\n",
            "from mlx import core\n",
            "import pulsar_mlx_worker.router\n",
            "from pulsar_mlx_worker import model_slice\n",
        ):
            with self.subTest(source=forbidden.strip()):
                self.assert_oracle_error(
                    "oracle_not_independent",
                    oracle.assert_independent_source,
                    forbidden,
                )

    def test_capture_entrypoint_cannot_auto_download_a_model(self) -> None:
        self.assertTrue(
            CAPTURE_SCRIPT.is_file(),
            "T034 must implement scripts/research/capture_router_oracle.sh",
        )
        source = CAPTURE_SCRIPT.read_text(encoding="utf-8")
        oracle.assert_no_model_download(source)
        self.assertIn("--model", source)
        self.assertIn("--capture-a-scheduler-trace", source)
        self.assertIn("--capture-b-scheduler-trace", source)
        self.assertIn("--capture-provenance", source)
        self.assertIn('capture-$attempt_id.stderr', source)
        self.assertIn('mktemp -d "$work_dir/router-capture-attempt.', source)
        self.assertNotIn('mkdir -p "$generated_dir"', source)
        self.assertIn('capture_model_before=$(file_snapshot "$model_path")', source)
        self.assertIn('capture_model_after=$(file_snapshot "$model_path")', source)
        self.assertIn('oracle_model_before=$(file_snapshot "$model_path")', source)
        self.assertIn('oracle_model_after=$(file_snapshot "$model_path")', source)
        self.assertIn("PULSARMLX_HELPER_IDENTITY", source)
        self.assertIn("execution-provenance.json", source)
        self.assertIn("capture-a.f32le", source)
        self.assertIn("capture-b.f32le", source)
        self.assertIn("capture-a.scheduler-trace.txt", source)
        self.assertIn("capture-b.scheduler-trace.txt", source)
        self.assertIn("publish_oracle_candidate", source)
        self.assertNotIn('mkdir "$output_dir"', source)
        for pin in (
            "pinned_python_version=3.12.13",
            "pinned_numpy_version=2.4.5",
            "pinned_pyyaml_version=6.0.3",
            "pinned_tqdm_version=4.67.1",
            "pinned_requests_version=2.32.5",
        ):
            self.assertIn(pin, source)
        self.assertIn('importlib.import_module("gguf")', source)
        self.assertIn("pinned oracle Python dependencies differ", source)
        self.assertLess(
            source.index('importlib.import_module("gguf")'),
            source.index("# Model I/O begins only after"),
        )
        self.assertLess(
            source.index('importlib.import_module("gguf")'),
            source.index('admitted_model=$(file_snapshot "$model_path")'),
        )
        for forbidden in (
            "hf_hub_download",
            "huggingface-cli download",
            "curl ",
            "wget ",
        ):
            self.assertNotIn(forbidden, source)

    def test_dependency_failure_is_bounded_and_precedes_model_io(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            work = root / "oracle-work"
            source = work / "llama.cpp"
            output = root / "oracle-output"
            fake_bin = root / "bin"
            source.joinpath(".git").mkdir(parents=True)
            source.joinpath("LICENSE").write_text("MIT License\n", encoding="utf-8")
            fake_bin.mkdir()

            private_marker = "/" + "Users" + "/private/oracle-work/gguf.py"
            oracle_python = work / "oracle-python" / "bin" / "python"
            oracle_python.parent.mkdir(parents=True)
            oracle_python.write_text(
                "#!/bin/sh\n"
                f"echo 'dependency traceback at {private_marker}' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            oracle_python.chmod(0o700)

            fake_git = fake_bin / "git"
            fake_git.write_text(
                "#!/bin/sh\n"
                "case \"$*\" in\n"
                "  *\"rev-parse HEAD^{tree}\"*) printf '%040d\\n' 0 ;;\n"
                f"  *\"rev-parse HEAD\"*) printf '%s\\n' '{PINNED_LLAMA_CPP_REVISION}' ;;\n"
                "  *\"status --porcelain\"*) exit 0 ;;\n"
                "  *\"config --get remote.origin.url\"*) "
                "printf '%s\\n' 'https://github.com/ggml-org/llama.cpp' ;;\n"
                "  *) exit 3 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            fake_git.chmod(0o700)

            model = root / "Qwen3-30B-A3B-Q8_0.gguf"
            model.write_bytes(b"sentinel-not-a-model")
            model_io_marker = root / "model-io-occurred"
            fake_shasum = fake_bin / "shasum"
            fake_shasum.write_text(
                "#!/bin/sh\n"
                f"case \"${{3-}}\" in *Qwen3-30B-A3B-Q8_0.gguf) : >'{model_io_marker}' ;; esac\n"
                "exec /usr/bin/shasum \"$@\"\n",
                encoding="utf-8",
            )
            fake_shasum.chmod(0o700)

            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
            completed = subprocess.run(
                [
                    str(CAPTURE_SCRIPT),
                    "--model",
                    str(model),
                    "--work-dir",
                    str(work),
                    "--output-dir",
                    str(output),
                ],
                cwd=REPOSITORY_ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(completed.returncode, 2)
            self.assertEqual(completed.stdout, "")
            self.assertEqual(
                completed.stderr,
                "router oracle capture: pinned oracle Python dependencies differ\n",
            )
            self.assertNotIn(private_marker, completed.stderr)
            self.assertFalse(model_io_marker.exists())
            self.assertFalse(output.exists())

    def test_complete_candidate_publication_is_atomic_and_failure_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            candidate = parent / ".pulsarmlx-router-oracle.success"
            destination = parent / "oracle-result"
            private_path = "/" + "Users" + "/private/checkpoint.gguf"
            _write_complete_candidate(
                candidate,
                scheduler_suffix=f" model={private_path}",
            )
            manifest = oracle.validate_oracle_candidate_bundle(candidate)
            self.assertTrue(manifest["complete"])
            self.assertEqual(
                [attempt["attempt_id"] for attempt in manifest["attempts"]],
                ["a", "b"],
            )
            oracle.publish_oracle_candidate(candidate, destination)
            self.assertFalse(candidate.exists())
            self.assertTrue(destination.is_dir())
            for artifact in destination.iterdir():
                self.assertNotIn(private_path.encode("utf-8"), artifact.read_bytes())
            self.assertEqual(
                frozenset(path.name for path in destination.iterdir()),
                oracle._COMPLETE_CANDIDATE_FILES,
            )

            overwrite_candidate = parent / ".pulsarmlx-router-oracle.overwrite"
            _write_complete_candidate(overwrite_candidate)
            existing_manifest = (destination / "bundle-manifest.json").read_bytes()
            self.assert_oracle_error(
                "overwrite_refused",
                oracle.publish_oracle_candidate,
                overwrite_candidate,
                destination,
            )
            self.assertTrue(overwrite_candidate.is_dir())
            self.assertEqual(
                (destination / "bundle-manifest.json").read_bytes(),
                existing_manifest,
            )

            failed_candidate = parent / ".pulsarmlx-router-oracle.incomplete"
            failed_destination = parent / "must-remain-absent"
            _write_complete_candidate(failed_candidate)
            (failed_candidate / "capture-b.scheduler-trace.txt").unlink()
            self.assert_oracle_error(
                "output_invalid",
                oracle.publish_oracle_candidate,
                failed_candidate,
                failed_destination,
            )
            self.assertTrue(failed_candidate.is_dir())
            self.assertFalse(failed_destination.exists())


if __name__ == "__main__":
    unittest.main()
