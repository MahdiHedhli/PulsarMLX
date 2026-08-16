from __future__ import annotations

import copy
import json
import math
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.research import f017_dprefix_numerical_surface_closure as C
from scripts.research.f017_dprefix_metric_engine import compare_f32le


def packed(values: list[float]) -> bytes:
    return b"".join(struct.pack("<f", value) for value in values)


class MetricEngineTests(unittest.TestCase):
    def test_directed_metric_cases(self) -> None:
        exact = compare_f32le(packed([1.0, -2.0]), packed([1.0, -2.0]), [2])
        self.assertEqual(exact.max_absolute_error, 0.0)
        self.assertEqual(exact.rmse, 0.0)
        self.assertEqual(exact.cosine_similarity, 1.0)

        one_ulp = compare_f32le(packed([1.0]), struct.pack("<I", 0x3F800001), [1])
        self.assertEqual(one_ulp.max_absolute_error, 2.0**-23)

        signed = compare_f32le(struct.pack("<I", 0), struct.pack("<I", 0x80000000), [1])
        self.assertEqual(signed.signed_zero_mismatch_count, 1)

        outlier = compare_f32le(packed([0.0, 0.0, 8.0]), packed([0.0, 0.0, 0.0]), [3])
        self.assertEqual(outlier.max_absolute_error, 8.0)
        self.assertAlmostEqual(outlier.rmse, math.sqrt(64.0 / 3.0))

        distributed = compare_f32le(packed([1.0, -1.0, 1.0, -1.0]), packed([0.0] * 4), [4])
        self.assertEqual(distributed.rmse, 1.0)

        near = compare_f32le(packed([1.0, 2.0]), packed([1.0, 2.000001]), [2])
        self.assertGreater(near.cosine_similarity, 0.999999999)

        orthogonal = compare_f32le(packed([1.0, 0.0]), packed([0.0, 1.0]), [2])
        self.assertEqual(orthogonal.cosine_similarity, 0.0)

        zero = compare_f32le(packed([0.0, 0.0]), packed([0.0, 0.0]), [2])
        self.assertEqual(zero.cosine_similarity, 1.0)

    def test_metric_engine_fails_closed(self) -> None:
        for value in [math.nan, math.inf, -math.inf]:
            with self.assertRaisesRegex(ValueError, "non-finite"):
                compare_f32le(packed([value]), packed([0.0]), [1])
        with self.assertRaisesRegex(ValueError, "shape"):
            compare_f32le(packed([1.0]), packed([1.0]), [2])
        with self.assertRaisesRegex(ValueError, "byte length"):
            compare_f32le(b"x", packed([1.0]), [1])


class SurfaceClosureTests(unittest.TestCase):
    def test_successor_binary_self_verifies_and_refuses_scope_expansion(self) -> None:
        identity = C.EVIDENCE / "f017-dprefix-candidate-identity-binding-v2.json"
        if not C.CANDIDATE_V2.is_file():
            banked = json.loads(identity.read_text())
            build = json.loads((C.EVIDENCE / "f017-dprefix-candidate-build-manifest-v2.json").read_text())
            self.assertEqual(banked["binary_sha256"], build["binary"]["sha256"])
            self.assertEqual(len(banked["binary_sha256"]), 64)
            return
        verified = subprocess.run(
            [str(C.CANDIDATE_V2), "--self-verify", str(identity)],
            text=True,
            capture_output=True,
        )
        self.assertEqual(verified.returncode, 0, verified.stderr)
        self.assertEqual(json.loads(verified.stdout)["checkpoint_reads"], 0)
        for mode in ("--layer-3", "--router", "--logits", "--prompt", "--token", "--inventory"):
            refused = subprocess.run(
                [str(C.CANDIDATE_V2), mode, str(identity)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(refused.returncode, 0, mode)
        with tempfile.TemporaryDirectory() as directory:
            changed = json.loads(identity.read_text())
            changed["binary_sha256"] = "0" * 64
            binding = Path(directory) / "identity.json"
            binding.write_text(json.dumps(changed))
            refused = subprocess.run(
                [str(C.CANDIDATE_V2), "--self-verify", str(binding)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("CANDIDATE_IDENTITY", refused.stderr)

    def test_banked_successor_artifacts_regenerate_exactly(self) -> None:
        manifest = json.loads((C.EVIDENCE / "f017-dprefix-candidate-source-manifest-v2.json").read_text())
        candidate_entry = next(
            entry for entry in manifest["files"]
            if entry["path"].endswith("f017-dense-prefix-candidate.rs")
        )
        candidate_source_is_historical = C.sha(C.ROOT / candidate_entry["path"]) != candidate_entry["sha256"]
        if not C.CANDIDATE_V2.is_file() or candidate_source_is_historical:
            rehearsal = json.loads((C.EVIDENCE / "f017-dprefix-full-tier-b-synthetic-rehearsal-v1.json").read_text())
            C.validate_terminal_numerical_surfaces(rehearsal["surfaces"])
            self.assertEqual(rehearsal["result"], "FULL_TIER_B_SURFACE_INSTANTIABLE_CHECKPOINT_FREE")
            self.assertTrue(rehearsal["overall_pass"])
            return
        values = C._successor_artifacts()
        original_load = C.load
        historical_ledger = json.loads(subprocess.check_output([
            "git", "-C", str(C.ROOT), "show",
            "87492cc670bcb46348cda0a72b6481690b907dd3:docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json",
        ]))

        def historical_load(path):
            if Path(path).name == "f017-real-payload-access-ledger-v1.json":
                return copy.deepcopy(historical_ledger)
            return original_load(path)

        with patch.object(C, "load", side_effect=historical_load):
            C.validate_artifacts(values)
        for path, expected in values.items():
            self.assertEqual(json.loads(path.read_text()), expected, path.name)

    def test_contract_drives_complete_surface_manifest(self) -> None:
        manifest = C.numerical_surface_manifest()
        self.assertEqual(manifest["tier_b_sha256"], C.TIER_B_SHA)
        ids = [surface["semantic_id"] for surface in manifest["surfaces"]]
        self.assertEqual(
            ids,
            [
                "embedding",
                "layer_0_attention",
                "layer_0_output",
                "layer_1_attention",
                "layer_1_output",
                "layer_2_attention",
                "layer_2_output",
                "layer_3_entry",
            ],
        )
        self.assertEqual(manifest["surfaces"][-1]["alias_of"], "layer_2_output")
        self.assertEqual(manifest["surfaces"][-1]["retention_class"], "A")
        self.assertEqual(manifest["surfaces"][0]["required_metrics"], [])

    def test_instantiability_guard_rejects_missing_or_hash_only_values(self) -> None:
        manifest = C.numerical_surface_manifest()
        broken = copy.deepcopy(manifest)
        broken["surfaces"][1]["candidate_producer"] = None
        with self.assertRaisesRegex(ValueError, "candidate producer"):
            C.validate_surface_manifest(broken)
        broken = copy.deepcopy(manifest)
        broken["surfaces"][1]["retention_class"] = "D"
        with self.assertRaisesRegex(ValueError, "hash-only"):
            C.validate_surface_manifest(broken)

    def test_metric_localizes_major_stage_failures(self) -> None:
        manifest = C.numerical_surface_manifest()
        baseline = packed([1.0, 2.0] * 3072)
        changed = packed([1.0, 100.0] + [1.0, 2.0] * 3071)
        values = {surface["semantic_id"]: baseline for surface in manifest["surfaces"]}
        for target in [
            "embedding",
            "layer_0_attention",
            "layer_0_output",
            "layer_1_output",
            "layer_2_output",
            "layer_3_entry",
        ]:
            candidate = dict(values)
            candidate[target] = changed
            result = C.compare_surface_packages(candidate, values, manifest, synthetic=True)
            self.assertFalse(result["overall_pass"])
            self.assertIn(target, result["failed_surfaces"])

    def test_same_attempt_and_frozen_semantics(self) -> None:
        continuation = C.continuation_adjudication()
        self.assertEqual(continuation["decision"], "SAME UNCONSUMED DPREFIX ATTEMPT MAY CONTINUE")
        self.assertFalse(continuation["consumed"])
        self.assertEqual(continuation["ledger"], 59)
        self.assertEqual(C.frozen_semantics()["payloads"], 40)
        self.assertEqual(C.frozen_semantics()["packed_bytes"], 1_431_263_232)

    def test_evidence_schema_requires_all_surfaces(self) -> None:
        schema = C.evidence_schema()
        surfaces = schema["properties"]["numerical_surfaces"]
        self.assertEqual(surfaces["minItems"], 8)
        self.assertEqual(surfaces["maxItems"], 8)
        self.assertTrue(surfaces["uniqueItems"])
        self.assertEqual(len(surfaces["allOf"]), 8)
        self.assertIn("numerical_surfaces", schema["required"])

    def test_terminal_surface_guard_rejects_missing_duplicate_and_null_metric(self) -> None:
        manifest = C.numerical_surface_manifest()
        baseline = packed([1.0] * 6144)
        values = {surface["semantic_id"]: baseline for surface in manifest["surfaces"]}
        complete = C.compare_surface_packages(values, values, manifest)["surfaces"]
        C.validate_terminal_numerical_surfaces(complete)
        with self.assertRaisesRegex(ValueError, "MISSING_OR_DUPLICATE"):
            C.validate_terminal_numerical_surfaces(complete[:-1])
        duplicate = copy.deepcopy(complete)
        duplicate[-1]["semantic_id"] = duplicate[-2]["semantic_id"]
        with self.assertRaisesRegex(ValueError, "MISSING_OR_DUPLICATE"):
            C.validate_terminal_numerical_surfaces(duplicate)
        missing_metric = copy.deepcopy(complete)
        del missing_metric[1]["rmse"]
        with self.assertRaisesRegex(ValueError, "NUMERICAL_SURFACE_MISSING"):
            C.validate_terminal_numerical_surfaces(missing_metric)

    def test_retention_package_rehearsal_is_real_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            values = packed([float(index) for index in range(6144)])
            result = C.rehearse_retention(Path(directory), values)
            self.assertEqual(result["shape"], [6144])
            self.assertEqual(result["count"], 6144)
            self.assertTrue(result["immutable"])
            self.assertTrue(result["read_only"])
            self.assertEqual(Path(result["private_path"]).read_bytes(), values)


if __name__ == "__main__":
    unittest.main()
