from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.research.f017_representative_expert_output_reuse_v1 import ReuseError, preflight_and_consume
from scripts.research.validate_f017_representative_expert_output_reuse_v1 import AUTH, ValidationError, load, validate


class AuthorizationMutationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.base = load(AUTH)

    def rejects(self, mutate) -> None:
        value = copy.deepcopy(self.base)
        mutate(value)
        with self.assertRaises(ValidationError):
            validate(value, repo=False)

    def test_base(self) -> None:
        validate(self.base, repo=True)

    def test_required_mutations(self) -> None:
        mutations = [
            lambda x: x.__setitem__("preparation_base_head", "0" * 40),
            lambda x: x["authority"]["expert_execution_evidence"].__setitem__("sha256", "0" * 64),
            lambda x: x["authority"].__setitem__("representative_expert_input_sha256", "0" * 64),
            lambda x: x["atomic_id_weight_output_triples"][3].__setitem__("expert_id", 73),
            lambda x: x["atomic_id_weight_output_triples"][3].__setitem__("routing_weight", x["atomic_id_weight_output_triples"][4]["routing_weight"]),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("output_sha256", "0" * 64),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("byte_length", 24572),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("dtype", "native-f32"),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("shape", [1, 6144]),
            lambda x: x["atomic_id_weight_output_triples"].__setitem__(slice(3, 5), [x["atomic_id_weight_output_triples"][4], x["atomic_id_weight_output_triples"][3]]),
            lambda x: x["atomic_id_weight_output_triples"].pop(),
            lambda x: x["atomic_id_weight_output_triples"].append(copy.deepcopy(x["atomic_id_weight_output_triples"][0])),
            lambda x: x["atomic_id_weight_output_triples"][0].__setitem__("output_sha256", "799ce090e2da9268e0c79c2462d132319757e623b6128984d148bc400d92fba5"),
            lambda x: x["retained_identity_contract"].__setitem__("open_once_consume_same_descriptor", False),
            lambda x: x["accounting"].__setitem__("checkpoint_reads", 1),
            lambda x: x["accounting"].__setitem__("shard_opens", 1),
            lambda x: x["accounting"].__setitem__("expert_executions", 1),
            lambda x: x["accounting"].__setitem__("aggregate_executions", 1),
            lambda x: x["accounting"].__setitem__("real_payload_ledger", 176),
            lambda x: x["prohibitions"].__setitem__("aggregate_execution", False),
            lambda x: x["aggregate_input_contract"].__setitem__("sha256", "0" * 64),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.rejects(mutation)


class OpenOnceResolverTests(unittest.TestCase):
    def synthetic(self, root: Path) -> dict:
        doc = load(AUTH)
        for item in doc["atomic_id_weight_output_triples"]:
            raw = (int(item["expert_id"]).to_bytes(4, "little") * 6144)[:24576]
            path = root / item["private_relative_path"]
            path.write_bytes(raw)
            os.chmod(path, 0o400)
            item["output_sha256"] = hashlib.sha256(raw).hexdigest()
        return doc

    def test_exact_open_once_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = preflight_and_consume(self.synthetic(root), root)
            self.assertEqual(result["disposition"], "REPRESENTATIVE_EXPERT_OUTPUT_REUSE_PREFLIGHT_PASS")
            self.assertEqual(len(result["outputs"]), 8)
            self.assertTrue(all(x["expected_sha256"] == x["before_sha256"] == x["consumed_sha256"] == x["after_sha256"] for x in result["outputs"]))

    def test_writable_output_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = self.synthetic(root)
            os.chmod(root / doc["atomic_id_weight_output_triples"][0]["private_relative_path"], 0o600)
            with self.assertRaises(ReuseError):
                preflight_and_consume(doc, root)

    def test_symlink_output_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = self.synthetic(root)
            target = root / doc["atomic_id_weight_output_triples"][0]["private_relative_path"]
            real = root / "real.bin"
            target.rename(real)
            target.symlink_to(real.name)
            with self.assertRaises((ReuseError, OSError)):
                preflight_and_consume(doc, root)

    def test_hash_substitution_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = self.synthetic(root)
            doc["atomic_id_weight_output_triples"][0]["output_sha256"] = "0" * 64
            with self.assertRaises(ReuseError):
                preflight_and_consume(doc, root)


if __name__ == "__main__":
    unittest.main()
