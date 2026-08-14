import json
import tempfile
import unittest
from pathlib import Path

from scripts.research.f017_post_m1f_downstream import (
    CATALOG,
    dense_prefix_inventory,
    downstream_config_template,
    roadmap,
    scaffolding_template,
    validate_downstream_config,
    validate_downstream_evidence,
)


class DensePrefixInventoryTests(unittest.TestCase):
    def test_exact_metadata_only_boundary(self) -> None:
        result = dense_prefix_inventory()
        self.assertEqual(result["checkpoint_access"], 0)
        self.assertEqual(
            result["access_budget"],
            {
                "tensor_payloads": 40,
                "shard_count": 1,
                "shards": ["GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf"],
                "positional_reads": 40,
                "packed_bytes": 1_431_263_232,
                "decoded_f32_bytes_upper_bound": 8_504_653_824,
                "largest_single_decoded_tensor_bytes": 3_806_330_880,
            },
        )
        self.assertEqual(result["new_real_decoder_gates"], ["Q4_K", "Q6_K"])
        self.assertTrue(all("indexer" not in row["name"] for row in result["tensors"]))
        self.assertTrue(all("exps" not in row["name"] for row in result["tensors"]))

    def test_banked_dense_prefix_summary_matches_derivation(self) -> None:
        root = Path(__file__).resolve().parents[3]
        banked = json.loads(
            (root / "docs/architecture/reviews/evidence/f017-dense-prefix-fallback-inventory-v1.json").read_text()
        )
        result = dense_prefix_inventory()
        self.assertEqual(banked["access_budget"], result["access_budget"])
        self.assertEqual(banked["quantization_inventory"], result["quantization_inventory"])
        self.assertEqual(banked["new_real_decoder_gates"], result["new_real_decoder_gates"])
        from scripts.research.f017_post_m1f_downstream import sha256_file

        self.assertEqual(
            banked["inventory_derivation"]["generator_sha256"],
            sha256_file(root / banked["inventory_derivation"]["generator_path"]),
        )

    def test_catalog_identity_and_quant_alignment_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "catalog.json"
            value = json.loads(CATALOG.read_text())
            value["tensor_count"] = 1808
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "catalog identity"):
                dense_prefix_inventory(path)

            value = json.loads(CATALOG.read_text())
            tensor = next(t for t in value["tensors"] if t["name"] == "token_embd.weight")
            tensor["dims"][0] -= 1
            tensor["dims"][1] -= 1
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "unaligned"):
                dense_prefix_inventory(path)


class RoadmapTests(unittest.TestCase):
    def test_t017_141_and_real_phases_remain_blocked(self) -> None:
        result = roadmap()
        by_gate = {row["gate"]: row for row in result["gates"]}
        self.assertEqual(result["checkpoint_access"], 0)
        self.assertEqual(result["ledger"], 57)
        self.assertEqual(
            by_gate["T017-141"]["state"],
            "OPEN_UNTIL_M1_A_THROUGH_M1_G_REVIEW_GATES_PASS",
        )
        self.assertEqual(by_gate["P1"]["classification"], "REQUIRES_NEW_REAL_ACCESS")
        self.assertTrue(result["feature_018_dependency"].startswith("NONE"))
        self.assertFalse(result["canonical_p1_fields"]["literal_command_published"])

    def test_banked_roadmap_and_scaffolds_regenerate_exactly(self) -> None:
        root = Path(__file__).resolve().parents[3]
        banked = json.loads(
            (root / "docs/architecture/reviews/evidence/f017-post-m1f-to-p1-roadmap-v1.json").read_text()
        )
        self.assertEqual(banked, roadmap())
        for phase, name in (
            ("M1_G_FINAL_OUTPUT", "f017-m1g-admission-scaffold-v1.json"),
            ("P1_ONE_TOKEN", "f017-p1-admission-scaffold-v1.json"),
        ):
            with self.subTest(phase=phase):
                actual = json.loads((root / "docs/architecture/reviews/evidence" / name).read_text())
                self.assertEqual(actual, scaffolding_template(phase))

    def test_contract_schemas_are_strict_and_parseable(self) -> None:
        root = Path(__file__).resolve().parents[3]
        for name in (
            "f017-downstream-execution-config-v1.schema.json",
            "f017-downstream-evidence-v1.schema.json",
        ):
            with self.subTest(name=name):
                schema = json.loads(
                    (root / "specs/017-rust-native-inference-runtime/contracts" / name).read_text()
                )
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(schema["type"], "object")


class DownstreamScaffoldTests(unittest.TestCase):
    def test_scaffolds_are_prepared_not_authorized(self) -> None:
        for phase in ("M1_G_FINAL_OUTPUT", "P1_ONE_TOKEN"):
            with self.subTest(phase=phase):
                value = scaffolding_template(phase)
                self.assertEqual(value["status"], "PREPARED_NOT_AUTHORIZED")
                self.assertFalse(value["admission"]["authorized"])
                self.assertFalse(value["attempt"]["consumed"])
                validate_downstream_evidence(value)

    def test_typed_configs_are_prepared_and_loose_overrides_fail(self) -> None:
        for phase in ("M1_G_FINAL_OUTPUT", "P1_ONE_TOKEN"):
            with self.subTest(phase=phase):
                value = downstream_config_template(phase)
                self.assertEqual(value["status"], "PREPARED_NOT_AUTHORIZED")
                self.assertFalse(value["authorization"]["authorized"])
                value["manual_cli_override"] = "--tensor=unexpected"
                with self.assertRaisesRegex(ValueError, "field set"):
                    validate_downstream_config(value)

    def test_authorized_config_requires_fully_bound_prior_evidence(self) -> None:
        value = downstream_config_template("P1_ONE_TOKEN")
        value["status"] = "AUTHORIZED_NOT_EXECUTED"
        value["authorization"]["authorized"] = True
        with self.assertRaisesRegex(ValueError, "identity incomplete"):
            validate_downstream_config(value)

    @staticmethod
    def nominal_pass():
        value = scaffolding_template("M1_G_FINAL_OUTPUT")
        value["status"] = "PASS"
        value["identity"] = {
            "runtime": "a" * 64,
            "tooling": "b" * 64,
            "authorization": "c" * 64,
            "prior_evidence": {"m1_f": "d" * 64},
        }
        value["admission"]["authorized"] = True
        value["attempt"]["number"] = 1
        value["attempt"]["consumed"] = True
        value["result"] = {"completed": True, "first_failure": None, "classification": "PASS"}
        value["repeat_integrity"]["observed"] = 10
        value["repeat_integrity"]["hashes"] = ["a" * 64] * 10
        value["repeat_integrity"]["all_repeat_hashes_equal"] = True
        value["lifecycle"]["teardown_complete"] = True
        value["numerical"]["classification"] = "PASS"
        value["numerical"]["greedy_identity"] = True
        value["analytical_retention"]["retained"] = list(value["analytical_retention"]["required"])
        return value

    def test_pass_validation_fails_closed(self) -> None:
        mutations = (
            (lambda v: v["admission"].update(authorized=False), "authorized"),
            (lambda v: v["attempt"].update(consumed=False), "attempt"),
            (lambda v: v["repeat_integrity"].update(all_repeat_hashes_equal=False), "repeat"),
            (lambda v: v["lifecycle"].update(in_flight=1), "lifecycle"),
            (lambda v: v["numerical"].update(classification="FAIL"), "numerical"),
            (lambda v: v["analytical_retention"]["retained"].pop(), "retention"),
            (lambda v: v["privacy"].update(absolute_paths_present=True), "absolute path"),
            (lambda v: v["result"].update(completed=False), "incomplete"),
        )
        for mutation, error in mutations:
            with self.subTest(error=error):
                value = self.nominal_pass()
                mutation(value)
                with self.assertRaisesRegex(ValueError, error):
                    validate_downstream_evidence(value)

    def test_unknown_or_loose_field_fails_closed(self) -> None:
        value = scaffolding_template("P1_ONE_TOKEN")
        value["loose_cli_override"] = "--checkpoint-manifest=/tmp/private"
        with self.assertRaisesRegex(ValueError, "field set"):
            validate_downstream_evidence(value)


if __name__ == "__main__":
    unittest.main()
