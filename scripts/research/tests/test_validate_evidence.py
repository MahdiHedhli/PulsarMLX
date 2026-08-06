"""Contract tests for the fail-closed Feature 002 evidence validator.

These tests intentionally exercise the public command-line boundary rather than
importing implementation details.  T006 lands them red; T009 and T011 provide
the closed schemas and validator that make them green.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = REPOSITORY_ROOT / "scripts" / "research" / "validate_evidence.py"
SCHEMA_DIR = REPOSITORY_ROOT / "schemas" / "research" / "v1"
MODEL_MANIFEST = REPOSITORY_ROOT / "docs" / "research" / "MODEL_MANIFEST.json"
PROTOCOL = REPOSITORY_ROOT / "docs" / "research" / "EXPERIMENT_PROTOCOL.md"
ROUTER_MANIFEST = REPOSITORY_ROOT / "fixtures" / "research" / "router-v1" / "manifest.json"
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SOURCE_COMMIT = "d" * 40


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _type7(values: list[int], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    fraction = position - lower
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _summary_values(values: list[int]) -> dict[str, object]:
    mean = statistics.fmean(values)
    sample_standard_deviation = statistics.stdev(values) if len(values) > 1 else None
    return {
        "sample_count": len(values),
        "minimum_ns": min(values),
        "maximum_ns": max(values),
        "mean_ns": mean,
        "sample_standard_deviation_ns": sample_standard_deviation,
        "sample_standard_deviation_reason": (
            None
            if sample_standard_deviation is not None
            else "requires_at_least_two_samples"
        ),
        "p5_ns": _type7(values, 0.05),
        "p25_ns": _type7(values, 0.25),
        "median_ns": _type7(values, 0.50),
        "p75_ns": _type7(values, 0.75),
        "p95_ns": _type7(values, 0.95),
        "coefficient_of_variation": (
            sample_standard_deviation / mean
            if sample_standard_deviation is not None and mean != 0
            else None
        ),
        "coefficient_of_variation_reason": (
            None
            if sample_standard_deviation is not None and mean != 0
            else "sample_standard_deviation_unavailable"
        ),
    }


def _observation(
    observation_id: str,
    run_index: int,
    kind: str,
    duration_ns: int,
    *,
    process_state: str = "reused_process",
) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "run_index": run_index,
        "batch_id": "batch-a",
        "case_id": "qwen3moe-layer0-router-token0-row0-v1",
        "process_replication_id": (
            "process-clean-a" if kind == "clean_process_replication" else "process-warm-a"
        ),
        "observation_kind": kind,
        "process_state": process_state,
        "condition": "warm",
        "instrumentation_mode": "minimally_instrumented",
        "started_at_utc": "2026-08-05T18:00:00Z",
        "completed_at_utc": "2026-08-05T18:00:01Z",
        "monotonic_clock": "perf_counter_ns",
        "durations_ns": {"total_evaluated_router": duration_ns},
        "status": "passed",
        "requested_device": "gpu",
        "selected_device": "gpu",
        "fallback_used": False,
        "evaluated": True,
        "synchronized": True,
        "output_sha256": SHA_B,
        "correctness_passed": True,
    }


def _summary(
    summary_id: str,
    observations: list[dict[str, object]],
    kind: str,
) -> dict[str, object]:
    included = [item for item in observations if item["observation_kind"] == kind]
    values = [
        int(item["durations_ns"]["total_evaluated_router"])  # type: ignore[index]
        for item in included
    ]
    return {
        "summary_id": summary_id,
        "statistics_algorithm": "pulsarmlx-type7-v1",
        "group": {
            "case_id": "qwen3moe-layer0-router-token0-row0-v1",
            "batch_id": "batch-a",
            "observation_kind": kind,
            "condition": "warm",
            "instrumentation_mode": "minimally_instrumented",
            "stage": "total_evaluated_router",
        },
        "included_observation_ids": [item["observation_id"] for item in included],
        "excluded_observation_ids": [],
        "unfiltered_summary": _summary_values(values),
    }


def valid_evidence(experiment_id: str = "f002-router-fixture-0001") -> dict[str, object]:
    model_identity = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))["model_identity"]
    protocol_sha256 = _sha256(PROTOCOL)
    observations = [
        _observation(f"warmup-{index:02d}", index, "warmup", 900 + index)
        for index in range(5)
    ]
    observations.extend(
        _observation(f"measurement-{index:02d}", index, "measurement", 1_000 + index)
        for index in range(10)
    )
    observations.append(
        _observation(
            "clean-process-00",
            0,
            "clean_process_replication",
            1_025,
            process_state="fresh_process",
        )
    )

    return {
        "evidence_schema": "pulsarmlx.research.experiment",
        "evidence_schema_version": "1.1.0",
        "payload_schema": "pulsarmlx.research.router-parity",
        "payload_schema_version": "1.0.0",
        "experiment_id": experiment_id,
        "feature_id": "002-qwen-router-parity",
        "evidence_scope": "synthetic_fixture",
        "record_kind": "combined",
        "actual_status": "passed",
        "started_at_utc": "2026-08-05T17:59:00Z",
        "completed_at_utc": "2026-08-05T18:10:00Z",
        "source_commit": SOURCE_COMMIT,
        "source_worktree_before": "clean",
        "source_worktree_after": {
            "state": "declared_evidence_outputs_only",
            "paths": [f"docs/research/raw/002-router-parity/{experiment_id}.json"],
        },
        "protocol": {
            "protocol_id": "f002-router-protocol-amendment-001",
            "protocol_version": "1.1.0",
            "path": "docs/research/EXPERIMENT_PROTOCOL.md",
            "sha256": protocol_sha256,
            "order_seed": 22002,
        },
        "execution": {
            "shell": "zsh",
            "command": "python3 scripts/research/run_router_experiment.py --model $PULSARMLX_MODEL_GGUF",
            "argv": [
                "python3",
                "scripts/research/run_router_experiment.py",
                "--model",
                "$PULSARMLX_MODEL_GGUF",
            ],
            "working_directory_policy": "repository_root",
            "exit_code": 0,
            "build_profile": "release",
            "features": ["mlx-backend"],
            "benchmark_order_policy": "deterministic_seeded",
        },
        "batch_id": "batch-a",
        "process_replication_id": "process-warm-a",
        "model": {
            field: model_identity[field]
            for field in (
                "repository",
                "revision",
                "filename",
                "size_bytes",
                "sha256",
                "architecture",
                "external_locator",
            )
        },
        "tensor": {
            "name": "blk.0.ffn_gate_inp.weight",
            "semantic_role": "layer_0_router_projection",
            "occurrence_count": 1,
            "gguf_dimensions": [2048, 128],
            "reader_shape": [128, 2048],
            "execution_shape": [2048, 128],
            "dtype": "F32",
            "quantization": "none_f32",
            "absolute_offset": 0,
            "encoded_length": 1_048_576,
            "end_offset": 1_048_576,
            "encoded_sha256": SHA_B,
        },
        "input": {
            "fixture_id": "qwen3moe-layer0-router-direct-tokens-v1",
            "graph_node": "ffn_norm-0",
            "input_adapter": "direct_token_ids_v1",
            "tokenizer_identity": "not_used_direct_token_ids",
            "token_ids": [0, 1],
            "positions": [0, 1],
            "shape": [2, 2048],
            "dtype": "float32",
            "byte_order": "little",
            "byte_length": 16_384,
            "canonical_sha256": SHA_C,
            "selected_rows": [0],
        },
        "oracle": {
            "oracle_id": "f002-scalar-f32-v1",
            "project": "llama.cpp-plus-standalone-scalar-oracle",
            "revision": "b06aa774c03dbbb624e726664b714a57d1f49815",
            "generation_command": "python3 scripts/research/router_oracle.py --fixture $PULSARMLX_ROUTER_FIXTURE",
            "input_fixture_sha256": SHA_C,
            "tensor_sha256": SHA_B,
            "output_sha256": SHA_A,
            "independence_statement": "Does not import or invoke MLX or the PulsarMLX worker.",
        },
        "environment": {
            "platform": "macos-arm64",
            "selected_backend": "apple-mlx",
            "selected_device": "gpu",
            "safe_environment": {"PULSARMLX_MODEL_GGUF": "$PULSARMLX_MODEL_GGUF"},
            "interference_admission": "admitted",
        },
        "correctness": {
            "passed": True,
            "compared_count": 128,
            "id_mismatch_count": 0,
            "order_mismatch_count": 0,
            "numeric_mismatch_count": 0,
            "first_mismatch": None,
            "maximum_absolute_error": 0.0,
            "mean_absolute_error": 0.0,
            "rmse": 0.0,
            "maximum_relative_error": 0.0,
            "absolute_tolerance": 0.0005,
            "relative_tolerance": 0.0005,
            "non_finite_policy": "reject",
            "non_finite_count": 0,
            "deterministic_repeat_count": 10,
            "repeat_output_hashes": [SHA_B] * 10,
        },
        "raw_observations": observations,
        "summaries": [
            _summary("warm-measurement-total", observations, "measurement"),
            _summary(
                "clean-process-total",
                observations,
                "clean_process_replication",
            ),
        ],
        "claim_boundary": {
            "status": "provisional",
            "operation": "layer_0_router_only",
            "capabilities": [
                "router_logits",
                "router_full_softmax",
                "router_top8_selection",
                "router_selected_weight_normalization",
            ],
            "unsupported_interpretations": [
                "expert_execution",
                "routed_moe_aggregation",
                "complete_transformer_layer",
                "language_model_head_or_model_output_logits",
                "generation",
                "full_model_generation",
                "serving",
                "custom_metal",
                "complete_model_inference",
                "full_or_giant_model_inference",
                "projected_tokens_per_second",
                "token_throughput",
                "linux_cuda_runtime_parity",
                "real_checkpoint_routing",
            ],
        },
        "warnings": ["Fixture-only evidence; no real checkpoint measurement."],
        "failures": [],
        "artifacts": [
            {
                "kind": "frozen_protocol",
                "path": "docs/research/EXPERIMENT_PROTOCOL.md",
                "sha256": protocol_sha256,
            },
            {
                "kind": "router_fixture_manifest",
                "path": "fixtures/research/router-v1/manifest.json",
                "sha256": _sha256(ROUTER_MANIFEST),
            },
        ],
    }


class EvidenceValidatorContractTests(unittest.TestCase):
    maxDiff = None

    def _run_validator(self, records: dict[str, dict[str, object]]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory(prefix="pulsarmlx-validator-test-") as temp:
            input_directory = Path(temp) / "evidence"
            input_directory.mkdir()
            for filename, record in records.items():
                (input_directory / filename).write_text(
                    json.dumps(record, sort_keys=True, indent=2, allow_nan=True) + "\n",
                    encoding="utf-8",
                )
            return subprocess.run(
                [
                    sys.executable,
                    str(VALIDATOR),
                    "--schema-dir",
                    str(SCHEMA_DIR),
                    "--input",
                    str(input_directory),
                ],
                cwd=REPOSITORY_ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

    def _assert_accepted(self, record: dict[str, object]) -> None:
        experiment_id = str(record["experiment_id"])
        completed = self._run_validator({f"{experiment_id}.json": record})
        self.assertEqual(
            completed.returncode,
            0,
            msg=f"validator rejected valid fixture (exit {completed.returncode})",
        )

    def _assert_rejected(
        self,
        records: dict[str, dict[str, object]],
        expected_code: str,
        *,
        forbidden_output: str | None = None,
    ) -> None:
        completed = self._run_validator(records)
        output = completed.stdout + completed.stderr
        self.assertNotEqual(completed.returncode, 0, msg="validator accepted invalid evidence")
        self.assertIn(
            expected_code,
            output,
            msg=f"validator did not report stable code {expected_code!r}",
        )
        if forbidden_output is not None:
            self.assertNotIn(forbidden_output, output, msg="validator disclosed a private value")

    def test_accepts_a_structurally_and_semantically_valid_fixture(self) -> None:
        self._assert_accepted(valid_evidence())

    def test_rejects_schema_identity_and_version_mutations(self) -> None:
        mutations = (
            ("evidence_schema", "another.research.envelope"),
            ("evidence_schema_version", "2.0.0"),
            ("payload_schema", "another.router.payload"),
            ("payload_schema_version", "1.1.0"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                record = valid_evidence()
                record[field] = value
                self._assert_rejected(
                    {f"{record['experiment_id']}.json": record},
                    "unsupported_schema_identity",
                )

    def test_rejects_missing_required_and_unknown_closed_schema_fields(self) -> None:
        missing = valid_evidence()
        del missing["feature_id"]
        self._assert_rejected(
            {f"{missing['experiment_id']}.json": missing},
            "schema_violation",
        )

        unknown = valid_evidence()
        unknown["unreviewed_extension"] = True
        self._assert_rejected(
            {f"{unknown['experiment_id']}.json": unknown},
            "schema_violation",
        )

    def test_rejects_semantically_inconsistent_identity_and_time_fields(self) -> None:
        abbreviated_commit = valid_evidence()
        abbreviated_commit["source_commit"] = "deadbeef"
        self._assert_rejected(
            {f"{abbreviated_commit['experiment_id']}.json": abbreviated_commit},
            "semantic_relationship",
        )

        reversed_time = valid_evidence()
        reversed_time["completed_at_utc"] = "2026-08-05T17:00:00Z"
        self._assert_rejected(
            {f"{reversed_time['experiment_id']}.json": reversed_time},
            "semantic_relationship",
        )

    def test_rejects_private_paths_without_echoing_the_private_value(self) -> None:
        record = valid_evidence()
        private_path = str(Path("/", "Users", "fixture-user", "private", "checkpoint.gguf"))
        record["model"]["external_locator"] = private_path  # type: ignore[index]
        self._assert_rejected(
            {f"{record['experiment_id']}.json": record},
            "private_value",
            forbidden_output=private_path,
        )

        private_email = "private.user@example.com"
        email_record = valid_evidence("f002-router-fixture-private-email")
        email_record["warnings"].append(private_email)
        self._assert_rejected(
            {f"{email_record['experiment_id']}.json": email_record},
            "private_value",
            forbidden_output=private_email,
        )

        account_record = valid_evidence("f002-router-fixture-private-account")
        account_record["account" + "_id"] = "private-account"
        self._assert_rejected(
            {f"{account_record['experiment_id']}.json": account_record},
            "private_value",
            forbidden_output="private-account",
        )

    def test_rejects_nested_non_finite_values(self) -> None:
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                record = valid_evidence()
                record["correctness"]["maximum_absolute_error"] = value  # type: ignore[index]
                self._assert_rejected(
                    {f"{record['experiment_id']}.json": record},
                    "non_finite_value",
                )

    def test_rejects_insufficient_determinism_and_measurement_repetitions(self) -> None:
        too_few_hashes = valid_evidence()
        too_few_hashes["correctness"]["deterministic_repeat_count"] = 9  # type: ignore[index]
        too_few_hashes["correctness"]["repeat_output_hashes"] = [SHA_B] * 9  # type: ignore[index]
        self._assert_rejected(
            {f"{too_few_hashes['experiment_id']}.json": too_few_hashes},
            "insufficient_repetitions",
        )

        too_few_measurements = valid_evidence()
        too_few_measurements["raw_observations"] = [
            observation
            for observation in too_few_measurements["raw_observations"]  # type: ignore[union-attr]
            if observation["observation_id"] != "measurement-09"
        ]
        self._assert_rejected(
            {f"{too_few_measurements['experiment_id']}.json": too_few_measurements},
            "insufficient_repetitions",
        )

    def test_rejects_duplicate_observation_identities(self) -> None:
        record = valid_evidence()
        observations = record["raw_observations"]  # type: ignore[assignment]
        duplicate = deepcopy(observations[-1])  # type: ignore[index]
        duplicate["run_index"] = 1
        observations.append(duplicate)  # type: ignore[union-attr]
        self._assert_rejected(
            {f"{record['experiment_id']}.json": record},
            "duplicate_observation_id",
        )

    def test_rejects_duplicate_experiment_ids_in_append_only_input(self) -> None:
        first = valid_evidence()
        duplicate = valid_evidence()
        self._assert_rejected(
            {"first.json": first, "attempted-replacement.json": duplicate},
            "duplicate_experiment_id",
        )

    def test_rejects_filename_identity_mismatch_as_append_only_violation(self) -> None:
        record = valid_evidence()
        self._assert_rejected(
            {"different-identity.json": record},
            "append_only_identity_mismatch",
        )

    def test_rejects_raw_summary_mismatch(self) -> None:
        record = valid_evidence()
        record["summaries"][0]["unfiltered_summary"]["mean_ns"] += 1  # type: ignore[index,operator]
        self._assert_rejected(
            {f"{record['experiment_id']}.json": record},
            "raw_summary_mismatch",
        )

    def test_rejects_incompatible_condition_pooling(self) -> None:
        record = valid_evidence()
        for observation in record["raw_observations"]:  # type: ignore[union-attr]
            if observation["observation_id"] == "measurement-09":
                observation["condition"] = "first_read_new_process_os_cache_uncontrolled"
                break
        self._assert_rejected(
            {f"{record['experiment_id']}.json": record},
            "incompatible_summary_group",
        )

    def test_rejects_verified_claims_beyond_the_router_boundary(self) -> None:
        record = valid_evidence()
        record["claim_boundary"]["status"] = "verified"  # type: ignore[index]
        record["claim_boundary"]["operation"] = "full_model_generation"  # type: ignore[index]
        record["claim_boundary"]["capabilities"] = [  # type: ignore[index]
            "generation",
            "token_throughput",
        ]
        self._assert_rejected(
            {f"{record['experiment_id']}.json": record},
            "capability_overclaim",
        )


if __name__ == "__main__":
    unittest.main()
