import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BASELINE = "a572a2d560f5bc33f823e74c3bbc95ff2b164314"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"


def load(path: Path):
    return json.loads(path.read_text(), object_pairs_hook=_reject_duplicates)


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def git_bytes(relative: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{BASELINE}:{relative}"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout


class ContractVersionAuditTests(unittest.TestCase):
    def test_generator_is_deterministic(self):
        subprocess.run(
            [sys.executable, "scripts/research/reconcile_f017_contract_versions.py"],
            cwd=ROOT,
            check=True,
        )

    def test_r9_r10_v1_are_byte_identical_history(self):
        expected = {
            "production-r9-tier-b-v1.json":
                "fe6e95d2ea2eb31184cb5617ec27727262ac132812add75933e22a376acf80a8",
            "production-r10-tier-b-v1.json":
                "dc11769af639a207c1528ae6756a315f585a04438d5e5f5115883e0323ebd81f",
        }
        for name, digest in expected.items():
            relative = f"specs/017-rust-native-inference-runtime/contracts/{name}"
            data = (CONTRACTS / name).read_bytes()
            self.assertEqual(data, git_bytes(relative))
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)

    def test_v2_tightens_semantics_without_retuning(self):
        r9_v1 = load(CONTRACTS / "production-r9-tier-b-v1.json")
        r9_v2 = load(CONTRACTS / "production-r9-tier-b-v2.json")
        r10_v1 = load(CONTRACTS / "production-r10-tier-b-v1.json")
        r10_v2 = load(CONTRACTS / "production-r10-tier-b-v2.json")

        for old, new in ((r9_v1, r9_v2), (r10_v1, r10_v2)):
            self.assertEqual(old["required_repeats"], new["required_repeats"])
            self.assertEqual(old["intermediate"], new["intermediate"])
            self.assertEqual(old["final"], new["final"])
            self.assertEqual(old["exact_requirements"], new["exact_requirements"])
            self.assertTrue(new["versioning"]["thresholds_unchanged"])
            self.assertFalse(new["versioning"]["rerun_required"])

        self.assertEqual(
            r9_v2["classification"]["selection_divergence"],
            "numerically_failed",
        )
        self.assertEqual(
            r10_v2["classification"]["routing_divergence"],
            "numerically_failed",
        )

    def test_evidence_binds_v2_and_retains_no_checkpoint_result(self):
        r9 = load(EVIDENCE / "f017-r9-mla-dsa-production-v1.json")
        r10 = load(EVIDENCE / "f017-r10-complete-layer-production-v1.json")
        self.assertEqual(
            r9["frozen_contract_version"], "f017-production-r9-tier-b-v2"
        )
        self.assertEqual(
            r10["frozen_contract_versions"],
            [
                "f017-production-expert-tier-b-v1",
                "f017-production-r9-tier-b-v2",
                "f017-production-r10-tier-b-v2",
            ],
        )
        self.assertFalse(r9["checkpoint_accessed"])
        self.assertFalse(r10["checkpoint_accessed"])

    def test_r7_amendment_and_r8_audit_are_explicit(self):
        amendment = load(
            CONTRACTS / "production-expert-tier-b-v1-amendment-001.json"
        )
        reconciliation = load(
            EVIDENCE / "f017-contract-version-reconciliation-v2.json"
        )
        self.assertTrue(amendment["thresholds_unchanged"])
        self.assertTrue(amendment["numerical_payload_unchanged"])
        self.assertFalse(amendment["contract_version_bumped"])
        self.assertFalse(
            reconciliation["r8_audit"]["version_or_amendment_required"]
        )


if __name__ == "__main__":
    unittest.main()
