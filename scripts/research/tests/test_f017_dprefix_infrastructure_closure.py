from __future__ import annotations

import ast
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scripts.research import f017_dprefix_infrastructure_closure as M


class InfrastructureClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._original_load = M.load
        historical_ledger = json.loads(__import__("subprocess").check_output([
            "git", "-C", str(M.ROOT), "show",
            "87492cc670bcb46348cda0a72b6481690b907dd3:docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json",
        ]))

        def historical_load(path):
            if Path(path).name == "f017-real-payload-access-ledger-v1.json":
                return deepcopy(historical_ledger)
            return cls._original_load(path)

        cls._load_patcher = patch.object(M, "load", side_effect=historical_load)
        cls._load_patcher.start()
        cls.values = M.committed_artifacts()
        M.validate(cls.values)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._load_patcher.stop()

    def test_predecessor_source_manifests_remain_immutable(self) -> None:
        for suffix in ("candidate-source-manifest-v1.json", "oracle-source-manifest-v1.json"):
            manifest = next(v for p, v in self.values.items() if p.name.endswith(suffix))
            banked = next(p for p in self.values if p.name.endswith(suffix))
            self.assertEqual(M.canonical_sha(manifest), M.sha(banked))

    def test_successor_source_manifests_bind_current_sources_exactly(self) -> None:
        evidence = M.EVIDENCE
        for suffix in ("candidate-source-manifest-v2.json", "oracle-source-manifest-v2.json"):
            path = next(evidence.glob(f"*{suffix}"))
            manifest = json.loads(path.read_text())
            for entry in manifest["files"]:
                # v2 remains the immutable REAL-1 execution surface.  The
                # candidate path now holds the append-only REAL-2 successor,
                # whose current-source binding is checked by the v3 tests.
                if suffix.startswith("candidate-") and entry["path"].endswith("f017-dense-prefix-candidate.rs"):
                    continue
                self.assertEqual(M.sha(M.ROOT / entry["path"]), entry["sha256"], entry["path"])

    def test_prior_nonexecution_is_immutable(self) -> None:
        self.assertEqual(M.sha(M.EVIDENCE / "f017-dense-prefix-real-attempt-1-not-executed-v1.json"), M.NONEXECUTION_SHA)

    def test_same_attempt_continues_unconsumed(self) -> None:
        continuation = next(v for p, v in self.values.items() if p.name.endswith("continuation-v1.json"))
        self.assertEqual(continuation["decision"], "SAME UNCONSUMED DPREFIX ATTEMPT MAY CONTINUE")
        config = next(v for p, v in self.values.items() if p.name.endswith("config-v3.json"))
        self.assertTrue(config["execution_authorized"])
        self.assertFalse(config["consumed"] or config["executed"] or config["checkpoint_accessed"])

    def test_candidate_has_narrow_scope(self) -> None:
        build = next(v for p, v in self.values.items() if p.name.endswith("build-manifest-v1.json"))
        self.assertIn("layer3_attention", build["structurally_absent"])
        source = (M.ROOT / "crates/f017-runner/src/bin/f017-dense-prefix-candidate.rs").read_text()
        for option in ("--layer-3", "--router", "--logits", "--prompt", "--token", "--inventory"):
            self.assertNotIn(f'"{option}" =>', source)

    def test_oracle_imports_no_candidate_rust_ffi_or_mlx(self) -> None:
        path = M.ROOT / "scripts/research/f017_dprefix_oracle_runtime.py"
        tree = ast.parse(path.read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): imports.extend(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom): imports.append(node.module or "")
        self.assertFalse(any(name.startswith(("mlx", "ctypes", "cffi", "f017_runner")) for name in imports))
        oracle = next(v for p, v in self.values.items() if p.name.endswith("oracle-package-v1.json"))
        self.assertEqual(oracle["independence"]["verdict"], "ORACLE PACKAGE INDEPENDENT")

    def test_actual_binary_rehearsal_is_ten_repeat_and_retains_6144(self) -> None:
        result = next(v for p, v in self.values.items() if p.name.endswith("synthetic-rehearsal-v1.json"))
        self.assertEqual(result["result"], "SYNTHETIC_ACTUAL_BINARY_10_REPEAT_PASS")
        self.assertEqual(result["hidden_width"], 6144)
        self.assertEqual(result["repeats"], 10)
        self.assertTrue(result["deterministic"] and result["lifecycle_reconciled"])
        self.assertEqual(result["retained_state"]["shape"], [6144])
        self.assertEqual(result["dispatch"]["fallback"], 0)
        self.assertEqual(set(result["quantization_family_decoded_sha256"]), {"F32", "Q8_0", "Q4_K", "Q5_K", "Q6_K"})

    def test_actual_candidate_and_independent_oracle_qualify(self) -> None:
        parity = next(v for p, v in self.values.items() if p.name.endswith("candidate-oracle-synthetic-parity-v1.json"))
        self.assertTrue(parity["tier_b_checkpoint_free_pass"])
        self.assertLessEqual(parity["max_abs"], 0.0625)
        self.assertLessEqual(parity["rmse"], 0.03125)
        self.assertGreaterEqual(parity["cosine"], 0.999)

    def test_oracle_before_candidate_and_rehash_bound(self) -> None:
        config = next(v for p, v in self.values.items() if p.name.endswith("config-v3.json"))
        self.assertTrue(config["oracle"]["finalized_before_candidate"])
        self.assertTrue(config["oracle"]["post_candidate_rehash"])
        early = deepcopy(config); early["oracle"]["finalized_before_candidate"] = False
        self.assertNotEqual(M.canonical_sha(early), M.canonical_sha(config))

    def test_candidate_and_oracle_mutations_change_bound_identity(self) -> None:
        candidate = next(v for p, v in self.values.items() if p.name.endswith("candidate-source-manifest-v1.json"))
        oracle = next(v for p, v in self.values.items() if p.name.endswith("oracle-source-manifest-v1.json"))
        for original in (candidate, oracle):
            changed = deepcopy(original); changed["files"][0]["sha256"] = "0" * 64
            self.assertNotEqual(M.canonical_sha(changed), M.canonical_sha(original))

    def test_q4_q6_synthetic_hard_identity_gates(self) -> None:
        for packed, decoded in (("a" * 64, "b" * 64), ("c" * 64, "d" * 64)):
            M.validate_identity_confirmation(packed, decoded, packed, decoded)
            for actual_packed, actual_decoded in (("0" * 64, decoded), (packed, "0" * 64)):
                with self.assertRaises(ValueError):
                    M.validate_identity_confirmation(packed, decoded, actual_packed, actual_decoded)

    def test_authorization_mutations_fail_consistency(self) -> None:
        cases = []
        for field, value in (("consumed", True), ("executed", True), ("checkpoint_accessed", True), ("ledger_before", 58), ("expected_ledger_after", 97), ("automatic_retry", True), ("automatic_m1f0_continuation", True)):
            mutated = deepcopy(self.values)
            path = next(p for p in mutated if p.name.endswith("config-v3.json"))
            mutated[path][field] = value
            cases.append(mutated)
        for mutated in cases:
            with self.assertRaises(ValueError): M.validate(mutated)

    def test_memory_floor_not_lowered(self) -> None:
        memory = next(v for p, v in self.values.items() if p.name.endswith("memory-admission-v1.json"))
        self.assertEqual(memory["minimum_free_memory_gib"], 27)
        self.assertFalse(memory["floor_lowered"])

    def test_ledger_remains_59(self) -> None:
        result = M.validate(self.values)
        self.assertEqual(result, {"result": "READY_TO_EXECUTE_DENSE_PREFIX_REAL_CAPTURE", "attempt": "DPREFIX-REAL-1", "checkpoint_reads": 0, "ledger": 59})


if __name__ == "__main__":
    unittest.main()
