"""Strict metadata and edge checks for the GLM53-Flash tiny contract."""

import ast
import copy
import json
from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts/research"))

from glm53_flash.contract import (  # noqa: E402
    ContractValidationError,
    load_contract,
    validate_contract,
    validate_contract_document,
)


CONTRACT = REPO / "docs/glm53-flash/tiny-reference-v1/mini-contract.json"
ARITHMETIC = REPO / "scripts/research/tests/test_glm53_flash_arithmetic.py"


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def reject(self, mutate, expected_path):
        document = copy.deepcopy(self.raw)
        mutate(document)
        with self.assertRaisesRegex(ContractValidationError, expected_path):
            validate_contract(document)

    def test_canonical_contract_and_arithmetic_bindings(self):
        document = load_contract(CONTRACT)
        tree = ast.parse(ARITHMETIC.read_text(encoding="utf-8"))
        actual = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        }
        bound = {
            method
            for test in document["tests"]
            if test["id"] not in {"T-CONTRACT-VALID", "T-CONTRACT-REJECT"}
            for method in test["unittest_methods"]
        }
        self.assertEqual(actual, bound)
        self.assertEqual(len(actual), 12)

    def test_metadata_mutations_reject(self):
        cases = [
            (lambda d: d.update(extra=True), r"\$: unsupported fields"),
            (lambda d: d["tensors"][0].pop("role"), r"\$\.tensors\[0\]: missing fields"),
            (lambda d: d["tensors"].append(copy.deepcopy(d["tensors"][0])), r"duplicate id"),
            (lambda d: d["tensors"][0].update(role="unknown_role"), r"\.role:"),
            (lambda d: d["tensors"][0].update(name="runtime.unknown"), r"\.name: unsupported tensor name"),
            (lambda d: d["tensors"][0].update(source_function="unknown.function"), r"\.source_function:"),
            (lambda d: d["tensors"][0].update(precision="bf16-ish"), r"\.precision:"),
            (lambda d: d["tensors"][0].update(state_owner="global_cache"), r"\.state_owner:"),
            (lambda d: next(t for t in d["tensors"] if t["id"] == "TENSOR-ROUTED-GATE")["quant_companions"].reverse(), r"\.quant_companions:"),
            (
                lambda d: next(t for t in d["tests"] if t["id"] == "T-ROUTE")["api_ids"].remove("route_scores"),
                r"lacks reciprocal API reference",
            ),
            (
                lambda d: next(a for a in d["apis"] if a["id"] == "route_scores")["outputs"].append("extra"),
                r"not exactly covered",
            ),
            (
                lambda d: next(t for t in d["tensors"] if t["id"] == "TENSOR-KDA-A-LOG").update(layer=3),
                r"\.layer:",
            ),
            (
                lambda d: next(t for t in d["tensors"] if t["id"] == "TENSOR-KDA-A-LOG").update(
                    name="language_model.model.layers.45.self_attn.forget_gate.A_log",
                    layer=45,
                ),
                r"\.name: unsupported tensor name",
            ),
            (lambda d: d["tensors"][0]["shape"].update(tiny=[33]), r"\.shape\.tiny\[0\]:"),
            (lambda d: d["edges"][0]["tensor_ids"].append("TENSOR-NOT-MAPPED"), r"unmapped reference"),
            (lambda d: d["apis"][0].update(test_ids=[]), r"empty array is unsupported"),
        ]
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                self.reject(mutate, expected)

        duplicate_field = CONTRACT.read_text(encoding="utf-8").replace(
            '"schema": "pulsarmlx.glm53_flash.tiny_mini_contract.v1",',
            '"schema": "pulsarmlx.glm53_flash.tiny_mini_contract.v1",\n  "schema": "duplicate",',
            1,
        )
        with self.assertRaisesRegex(ContractValidationError, "duplicate JSON field"):
            validate_contract_document(duplicate_field)

    def test_semantic_edge_miswire_rejects(self):
        document = copy.deepcopy(self.raw)
        edges = {edge["id"]: edge for edge in document["edges"]}
        edges["E-ROUTE-SCORES-OUT"]["producer"] = "api:route_tokens"
        edges["E-ROUTE-TOKENS-OUT"]["producer"] = "api:route_scores"
        with self.assertRaisesRegex(ContractValidationError, "semantic edge endpoints"):
            validate_contract(document)


if __name__ == "__main__":
    unittest.main(verbosity=2)
