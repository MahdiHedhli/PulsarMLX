from __future__ import annotations

import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from scripts.research.f017_representative_shared_expert_recovery_executor_v1 import ExecutorError, OpenOnce, atomic_exclusive, validate_authorization
from scripts.research.validate_f017_representative_shared_expert_recovery_authorization_v1 import AUTH, ValidationError, load, validate


class AuthorizationMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = load(AUTH)

    def rejects(self, mutation) -> None:
        value = copy.deepcopy(self.base)
        mutation(value)
        with self.assertRaises(ValidationError):
            validate(value, repo=False)

    def test_committed_authorization(self) -> None:
        validate(self.base, repo=True)
        validate_authorization(self.base)

    def test_required_mutations(self) -> None:
        mutations = [
            lambda x: x.__setitem__("preparation_base_head", "0" * 40),
            lambda x: x["representative_input"].__setitem__("sha256", "0" * 64),
            lambda x: x["representative_input"].__setitem__("semantic_role", "DIRECT_DPREFIX"),
            lambda x: x["representative_input"].__setitem__("shape", [1, 6144]),
            lambda x: x["retained_parameters"][0].__setitem__("packed_sha256", "0" * 64),
            lambda x: x["retained_parameters"][0].__setitem__("decoded_sha256", "0" * 64),
            lambda x: x["retained_parameters"][0].__setitem__("quantization", "Q6_K"),
            lambda x: x["retained_parameters"][0].__setitem__("decoded_shape", [6144, 2048]),
            lambda x: x["retained_parameters"].__setitem__(slice(0, 2), [x["retained_parameters"][1], x["retained_parameters"][0]]),
            lambda x: x["retained_parameters"].pop(),
            lambda x: x["retained_parameters"].append(copy.deepcopy(x["retained_parameters"][0])),
            lambda x: x["parameter_reuse"].__setitem__("sha256", "0" * 64),
            lambda x: x["parameter_reuse"].__setitem__("checkpoint_fallback", True),
            lambda x: x["computation_contract"].__setitem__("sha256", "0" * 64),
            lambda x: x["output_contract"].__setitem__("dtype", "little-endian-f64"),
            lambda x: x["output_contract"].__setitem__("shape", [2048]),
            lambda x: x["executor"].__setitem__("sha256", "0" * 64),
            lambda x: x["rehearsal"].__setitem__("sha256", "0" * 64),
            lambda x: x["rehearsal"].__setitem__("fresh_processes", 1),
            lambda x: x["one_shot_semantics"].__setitem__("retry", True),
            lambda x: x["one_shot_semantics"].__setitem__("durable_attempt_start", False),
            lambda x: x["access_accounting"].__setitem__("ledger_before", 174),
            lambda x: x["access_accounting"].__setitem__("checkpoint_reads", 1),
            lambda x: x["access_accounting"].__setitem__("shard_opens", 1),
            lambda x: x["access_accounting"].__setitem__("routed_aggregate_executions", 1),
            lambda x: x["access_accounting"].__setitem__("ffn_completions", 1),
            lambda x: x["access_accounting"].__setitem__("s2_constructions", 1),
            lambda x: x["prohibitions"].__setitem__("historical_direct_dprefix_input", False),
            lambda x: x["prohibitions"].__setitem__("historical_shared_output_substitution", False),
            lambda x: x.__setitem__("stop_boundary", "AFTER_FFN"),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.rejects(mutation)


class RetainedObjectTests(unittest.TestCase):
    def test_expected_before_consumed_after(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "object.bin"
            raw = b"retained" * 1024
            path.write_bytes(raw)
            os.chmod(path, 0o400)
            opened = OpenOnce(path, hashlib.sha256(raw).hexdigest(), len(raw), "FIXTURE")
            try:
                self.assertEqual(hashlib.sha256(opened.consume()).hexdigest(), opened.before)
                self.assertEqual(opened.verify_after(), opened.before)
            finally:
                opened.close()

    def test_writable_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "object.bin"
            path.write_bytes(b"x")
            with self.assertRaises(ExecutorError):
                OpenOnce(path, hashlib.sha256(b"x").hexdigest(), 1, "FIXTURE")

    def test_symlink_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real.bin"
            real.write_bytes(b"x")
            os.chmod(real, 0o400)
            link = root / "link.bin"
            link.symlink_to(real.name)
            with self.assertRaises(OSError):
                OpenOnce(link, hashlib.sha256(b"x").hexdigest(), 1, "FIXTURE")

    def test_exclusive_publication_and_second_attempt_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "attempt-start.json"
            atomic_exclusive(path, b"{}\n")
            with self.assertRaises(FileExistsError):
                atomic_exclusive(path, b"{}\n")


if __name__ == "__main__":
    unittest.main()
