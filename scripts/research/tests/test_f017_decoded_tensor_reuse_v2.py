from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "scripts/research/f017_decoded_tensor_reuse_v2.py"
SPEC = importlib.util.spec_from_file_location("f017_decoded_tensor_reuse_v2", PATH)
assert SPEC is not None and SPEC.loader is not None
REUSE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REUSE
SPEC.loader.exec_module(REUSE)


class ReuseContractTests(unittest.TestCase):
    def test_banked_contract_regenerates_exactly(self) -> None:
        path = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-m1f0-decoded-tensor-reuse-v2.json"
        self.assertEqual(path.read_bytes(), REUSE.canonical_json_bytes(REUSE.contract_value(ROOT)))

    def test_real_identity_contract_is_direct_and_economics_are_exact(self) -> None:
        contract = REUSE.contract_value(ROOT)
        self.assertEqual(contract["checkpoint_bindings"]["checkpoint_set_sha256"], REUSE.CHECKPOINT)
        self.assertEqual(contract["checkpoint_bindings"]["catalog_sha256"], REUSE.CATALOG)
        self.assertEqual(contract["checkpoint_bindings"]["tensor_map_sha256"], REUSE.TENSOR_MAP)
        self.assertEqual(len(contract["tensor_allowlist"]), 12)
        self.assertEqual(len({item["name"] for item in contract["tensor_allowlist"]}), 12)
        self.assertEqual(contract["economics"]["naive_payload_reads"], 96)
        self.assertEqual(contract["economics"]["reuse_payload_reads"], 12)
        self.assertEqual(contract["economics"]["payload_reads_avoided"], 84)
        self.assertEqual(contract["economics"]["compressed_bytes_avoided"], 974_525_440)
        self.assertEqual(contract["economics"]["decode_bytes_avoided"], 4_665_013_248)
        self.assertEqual(contract["candidate_oracle_separation"]["review_enum_A4"], "MIXED_POLICY")
        self.assertEqual(contract["review_disposition_A7"], "DECODED_REUSE_READY_FOR_FUTURE_AUTHORIZATION")
        dense_prefix = contract["conditional_dense_prefix_ledger_planning"]
        self.assertEqual(dense_prefix["baseline_without_retained_qualification_components"]["ledger_after"], 99)
        self.assertEqual(dense_prefix["reuse_option"]["ledger_after"], 97)
        self.assertEqual(dense_prefix["reuse_option"]["new_payload_reads"], 40)
        self.assertEqual(dense_prefix["reuse_option"]["shared_writable_alias"], "FORBIDDEN")
        self.assertFalse(dense_prefix["authorization_issued"])
        self.assertFalse(contract["real_execution_authorized"])

    def test_candidate_oracle_separation_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package_root = Path(temporary) / "package"
            REUSE.write_synthetic_package(package_root, ["fixture-0", "fixture-1"])
            package = REUSE.DecodedTensorPackage.load(package_root)
            with package.oracle_lease("fixture-0") as views:
                self.assertEqual(len(views), 12)
                self.assertTrue(all(view.readonly for view in views))
            with self.assertRaisesRegex(ValueError, "cannot alias"):
                package.candidate_lease("fixture-0")
            with self.assertRaisesRegex(ValueError, "not precommitted"):
                with package.oracle_lease("fixture-2"):
                    pass

    def test_content_identity_survives_prestart_relocation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            first_root = Path(temporary) / "first"
            second_root = Path(temporary) / "second"
            REUSE.write_synthetic_package(first_root, ["fixture-0"])
            first = REUSE.DecodedTensorPackage.load(first_root)
            shutil.copytree(first_root, second_root)
            second = REUSE.DecodedTensorPackage.load(second_root)
            self.assertEqual(first.package_sha256, second.package_sha256)
            self.assertEqual([item.sha256 for item in first.payloads], [item.sha256 for item in second.payloads])

    def test_relocation_after_load_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package_root = Path(temporary) / "package"
            moved_root = Path(temporary) / "moved"
            REUSE.write_synthetic_package(package_root, ["fixture-0"])
            package = REUSE.DecodedTensorPackage.load(package_root)
            package_root.rename(moved_root)
            with self.assertRaises(ValueError):
                package.validate_backing()

    def test_payload_mutation_before_and_during_use_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package_root = Path(temporary) / "package"
            REUSE.write_synthetic_package(package_root, ["fixture-0"])
            payload = package_root / "payloads/tensor-03.bin"
            original = payload.read_bytes()
            payload.write_bytes(original + b"mutation")
            with self.assertRaisesRegex(ValueError, "payload identity mismatch"):
                REUSE.DecodedTensorPackage.load(package_root)

            shutil.rmtree(package_root)
            REUSE.write_synthetic_package(package_root, ["fixture-0"])
            package = REUSE.DecodedTensorPackage.load(package_root)
            with self.assertRaisesRegex(ValueError, "payload mutated"):
                with package.oracle_lease("fixture-0"):
                    (package_root / "payloads/tensor-04.bin").write_bytes(b"changed")

    def test_manifest_mutation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            package_root = Path(temporary) / "package"
            REUSE.write_synthetic_package(package_root, ["fixture-0"])
            package = REUSE.DecodedTensorPackage.load(package_root)
            manifest = json.loads((package_root / "manifest.json").read_text())
            manifest["execution_identity"] = "mutated"
            (package_root / "manifest.json").write_bytes(REUSE.canonical_json_bytes(manifest))
            with self.assertRaisesRegex(ValueError, "manifest mutated"):
                package.validate_backing()

    def test_symlink_root_and_payload_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            package_root = base / "package"
            REUSE.write_synthetic_package(package_root, ["fixture-0"])
            root_link = base / "package-link"
            root_link.symlink_to(package_root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink package root"):
                REUSE.DecodedTensorPackage.load(root_link)

            payload = package_root / "payloads/tensor-01.bin"
            real = package_root / "payloads/tensor-01-real.bin"
            payload.rename(real)
            payload.symlink_to(real.name)
            with self.assertRaisesRegex(ValueError, "symlink package component"):
                REUSE.DecodedTensorPackage.load(package_root)

    def test_path_escape_duplicate_and_incomplete_surface_fail(self) -> None:
        manifest, _ = REUSE.synthetic_manifest(["fixture-0"])
        self.assertEqual(len(manifest["tensors"]), 12)
        with self.assertRaises(ValueError):
            REUSE._safe_relative("../escape.bin")
        with self.assertRaises(ValueError):
            REUSE._safe_relative("/absolute.bin")
        with self.assertRaises(ValueError):
            REUSE.synthetic_manifest(["duplicate", "duplicate"])

    def test_authority_mutation_fails_before_contract_creation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            replica = Path(temporary)
            for relative in (REUSE.AUTHORITY_PATH, REUSE.LEDGER_PATH):
                target = replica / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            authority = replica / REUSE.AUTHORITY_PATH
            authority.write_bytes(authority.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "authority mismatch"):
                REUSE.contract_value(replica)

    def test_planning_evidence_and_provenance_amendment_are_fail_closed(self) -> None:
        planning = json.loads(
            (ROOT / "docs/architecture/reviews/evidence/f017-m1f0-decoded-tensor-reuse-v2-planning-v1.json").read_text()
        )
        contract_path = ROOT / planning["contract"]["path"]
        implementation_path = ROOT / planning["implementation"]["path"]
        self.assertEqual(REUSE.sha256_path(contract_path), planning["contract"]["sha256"])
        self.assertEqual(REUSE.sha256_path(implementation_path), planning["implementation"]["sha256"])
        self.assertEqual(planning["candidate_oracle_separation"]["production_candidate_shared_alias"], "FORBIDDEN")
        self.assertEqual(planning["review_dispositions"]["A4"], "MIXED_POLICY")
        self.assertEqual(planning["review_dispositions"]["A7"], "DECODED_REUSE_READY_FOR_FUTURE_AUTHORIZATION")
        self.assertEqual(planning["conditional_dense_prefix_ledger_planning"]["reuse_ledger_after"], 97)
        self.assertEqual(planning["conditional_dense_prefix_ledger_planning"]["baseline_ledger_after"], 99)
        self.assertEqual(planning["checkpoint_access"], 0)

        amendment = json.loads(
            (ROOT / "docs/architecture/reviews/evidence/f017-accelerated-post-v3-provenance-amendment-v1.json").read_text()
        )
        self.assertEqual(
            amendment["reviewed_package"]["actual_reviewed_head"],
            "8031020f2e9480712ff185a53b2e565d25dc6a24",
        )
        self.assertEqual(amendment["stale_unpublished_identity"]["authority"], "NONE")
        self.assertEqual(amendment["ci_binding"]["run"], 31851111967)
        self.assertEqual(amendment["ci_binding"]["conclusion"], "success")
        self.assertEqual(amendment["ci_binding"]["apple_jobs_success"], 2)
        self.assertEqual(amendment["reviewer_heuristic_disposition"]["central_percent_range_intuition"], "CONFIRMED")
        self.assertEqual(amendment["reviewer_heuristic_disposition"]["eight_fixture_viability_conclusion"], "REFUTED")
        self.assertEqual(amendment["reviewer_heuristic_disposition"]["frozen_decision_rule_result"], "EXISTING_FROZEN_LADDER_NOT_VIABLE")
        self.assertEqual(
            REUSE.sha256_path(ROOT / "docs/architecture/reviews/evidence/f017-m1f0-v3-frozen-ladder-estimate-v1.json"),
            amendment["numerical_immutability"]["frozen_ladder_estimate_sha256"],
        )
        self.assertFalse(amendment["numerical_immutability"]["estimator_numerics_changed"])


if __name__ == "__main__":
    unittest.main()
