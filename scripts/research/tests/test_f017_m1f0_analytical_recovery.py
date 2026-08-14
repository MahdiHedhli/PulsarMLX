from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RECOVERY = load("f017_m1f0_recovery", "scripts/research/recover_f017_m1f0_analytics.py")
BANK = load("f017_m1f0_recovery_bank", "scripts/research/bank_f017_m1f0_analytical_recovery.py")
PREPARE = load("f017_m1f0_recovery_prepare", "scripts/research/prepare_f017_m1f0_analytical_recovery.py")


class M1F0AnalyticalRecoveryTests(unittest.TestCase):
    def test_recovery_config_maps_ordered_public_tensor_records(self):
        import subprocess

        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        config = PREPARE.build_config(ROOT, head)
        names = [item["name"] for item in config["tensor_allowlist"]]
        self.assertEqual(list(config["expected_identities"]["tensor_payload_sha256"]), names)
        self.assertEqual(list(config["expected_identities"]["decoded_tensor_sha256"]), names)
        self.assertEqual(len(names), 12)

    def test_route_stability_contract_is_frozen_before_values_and_requires_headroom(self):
        contract = json.loads(
            (
                ROOT
                / "specs/017-rust-native-inference-runtime/contracts/m1f-route-stability-v1.json"
            ).read_text()
        )
        self.assertTrue(contract["frozen_before_recovered_margin_observation"])
        self.assertEqual(contract["rank_bounds"]["stability_condition"], "margin > B8+B9")
        self.assertEqual(contract["interpretation_bands"][-1]["minimum_inclusive"], 4.0)
        self.assertEqual(contract["guards"]["post_observation_retuning"], "forbidden")

    def test_analytical_retention_rejects_hash_only_selection_objects_by_policy(self):
        contract = json.loads(
            (
                ROOT
                / "specs/017-rust-native-inference-runtime/contracts/f017-analytical-evidence-retention-v1.json"
            ).read_text()
        )
        self.assertEqual(contract["pass_requirements"]["hash_only_small_selection_objects"], "forbidden")
        for required in ("complete_score_vector", "complete_ranking_vector", "first_unselected_id"):
            self.assertIn(required, contract["mandatory_small_objects"])

    def test_matvec_and_rms_bounds_are_finite_nonnegative_and_monotone(self):
        matrix = np.asarray([[1.0, -2.0, 0.5], [-0.25, 3.0, -4.0]], dtype=np.float32)
        vector = np.asarray([0.5, -1.0, 2.0], dtype=np.float32)
        zero = np.zeros(3, dtype=np.float64)
        perturbed = np.asarray([1e-7, 2e-7, 3e-7], dtype=np.float64)
        baseline = RECOVERY.matvec_bound(matrix, vector, zero)
        widened = RECOVERY.matvec_bound(matrix, vector, perturbed)
        self.assertTrue(np.all(np.isfinite(baseline)))
        self.assertTrue(np.all(baseline >= 0))
        self.assertTrue(np.all(widened >= baseline))
        weights = np.asarray([0.75, 1.0, 1.25], dtype=np.float32)
        norm_zero = RECOVERY.rms_norm_bound(vector, weights, zero)
        norm_wide = RECOVERY.rms_norm_bound(vector, weights, perturbed)
        self.assertTrue(np.all(np.isfinite(norm_zero)))
        self.assertTrue(np.all(norm_wide >= norm_zero))

    def test_authorization_is_exact_and_fail_closed(self):
        config = {
            "source_identities": {"tooling_commit_sha": "a" * 40, "tooling_tree_oid": "b" * 40},
            "accepted_bindings": {"route": {"sha256": "c" * 64}},
            "access_budget": {"tensor_payloads": 12},
        }
        config_sha = "d" * 64
        expected = {
            "schema": "pulsarmlx.f017.m1f0-analytical-recovery-authorization",
            "schema_version": "1.0.0",
            "status": "AUTHORIZED FOR EXACTLY ONE ACCEPTED-BOUNDARY EVIDENCE RECOVERY / NOT EXECUTED",
            "execution_config_sha256": config_sha,
            "tooling_commit_sha": "a" * 40,
            "tooling_tree_oid": "b" * 40,
            "accepted_route_sha256": "c" * 64,
            "payload_budget": {"tensor_payloads": 12},
            "route_discovery_attempt_consumed": False,
            "new_route_authorized": False,
            "m1_f_authorized": False,
            "q6_k_qualification_authorized": False,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "authorization.json"
            raw = RECOVERY.canonical_json(expected)
            path.write_bytes(raw)
            RECOVERY.validate_authorization(config, config_sha, path, hashlib.sha256(raw).hexdigest())
            expected["new_route_authorized"] = True
            raw = RECOVERY.canonical_json(expected)
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                RECOVERY.validate_authorization(config, config_sha, path, hashlib.sha256(raw).hexdigest())

    def test_banker_preserves_full_values_and_evaluates_prefrozen_rule(self):
        probabilities = [0.25 + index / 4096.0 for index in range(256)]
        bias = [0.0] * 256
        scores = list(probabilities)
        ranking = sorted(range(256), key=lambda index: (-scores[index], index))
        top8 = ranking[:8]
        weights = [0.3125] * 8
        bounds = [1e-5] * 256
        payloads = {
            "router-probabilities.lef64": b"".join(struct.pack("<d", value) for value in probabilities),
            "router-bias.lef32": b"".join(struct.pack("<f", value) for value in bias),
            "router-scores.lef64": b"".join(struct.pack("<d", value) for value in scores),
            "ranking.leu16": b"".join(struct.pack("<H", value) for value in ranking),
            "top8.leu16": struct.pack("<8H", *top8),
            "routing-weights.lef64": b"".join(struct.pack("<d", value) for value in weights),
            "router-score-bounds.lef64": b"".join(struct.pack("<d", value) for value in bounds),
        }
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "package"
            package.mkdir()
            artifacts = {}
            for name, raw in payloads.items():
                (package / name).write_bytes(raw)
                artifacts[name] = {"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}
            config = {
                "accepted_bindings": {
                    "route": {"sha256": "1" * 64},
                    "attempt_2_evidence": {"sha256": "2" * 64},
                    "router_margin_blocker": {"sha256": "3" * 64},
                },
                "contracts": {
                    "route_stability": {"sha256": "4" * 64},
                    "analytical_retention": {"sha256": "5" * 64},
                },
            }
            config_path = Path(directory) / "config.json"
            config_path.write_bytes(BANK.canonical_json(config))
            manifest = {
                "execution_config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
                "private_artifacts": artifacts,
                "canonical_analytics": {
                    "probabilities": probabilities,
                    "bias": bias,
                    "scores": scores,
                    "ranking": ranking,
                    "top8_ids": top8,
                    "routing_weights": weights,
                    "router_score_abs_error_bounds": bounds,
                },
                "accepted_identities_reproduced": {},
                "access": {"tensor_payloads": 12},
                "scope": {"new_route": False},
            }
            (package / "recovery-manifest.json").write_bytes(BANK.canonical_json(manifest))
            recovery, ledger, audit = BANK.bank(package, config_path)
            self.assertEqual(len(recovery["canonical_analytics"]["values"]["scores"]), 256)
            self.assertEqual(len(recovery["canonical_analytics"]["values"]["ranking"]), 256)
            self.assertGreater(recovery["route_stability"]["safety_factor"], 4.0)
            self.assertEqual(recovery["route_stability"]["result"], "ROUTE_STABILITY_QUALIFIED")
            self.assertEqual(ledger["payload_count_before_recovery"], 25)
            self.assertEqual(ledger["payload_count_after_recovery"], 37)
            self.assertEqual(audit["boundaries"][-1]["classification"], "SUFFICIENT")


if __name__ == "__main__":
    unittest.main()
