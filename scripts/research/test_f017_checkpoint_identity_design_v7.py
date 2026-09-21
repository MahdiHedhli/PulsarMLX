#!/usr/bin/env python3
from __future__ import annotations

import sys
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_f017_checkpoint_identity_design_v7 as design_validator


REPOSITORY = Path(__file__).resolve().parents[2]


def canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


class DesignTests(unittest.TestCase):
    def test_design_authorities(self):
        self.assertEqual(design_validator.validate()["result"], "PASS")

    def test_load_bearing_mutations_fail_closed(self):
        manifest_path = REPOSITORY / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-v7-authority-manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        cases = [
            ("descriptor_transport", "descriptor_continuity", lambda value: value["consumer_boundary"].__setitem__("descriptor_transport", "PATH_STRING")),
            ("cleanup_false", "descriptor_continuity", lambda value: value["failure"].__setitem__("close_all_live_descriptors", False)),
            ("live_lease", "descriptor_continuity", lambda value: value["terminal"].__setitem__("live_leases_after_close", 1)),
            ("missing_fstat", "descriptor_continuity", lambda value: value["consumer_boundary"]["required_checks"].remove("FSTAT_MATCHES_IDENTITY_MANIFEST")),
            ("identity_only_graph", "checkpoint_identity", lambda value: value["identity_only"].__setitem__("graph_access_permitted", True)),
            ("partial_hash", "checkpoint_identity", lambda value: value["hash"].__setitem__("complete_file_required", False)),
            ("unstable_descriptor", "checkpoint_identity", lambda value: value["hash"].__setitem__("descriptor_pre_post_stability_required", False)),
            ("unchecked_byte_count", "checkpoint_identity", lambda value: value["hash"].__setitem__("exact_byte_count_required", False)),
            ("historical_delta", "checkpoint_identity", lambda value: value["historical_master_ledger"].__setitem__("delta", 1)),
            ("unstarted_delta", "accounting", lambda value: value.__setitem__("unstarted_consumer_delta", 1)),
            ("numerical_pin", "lifecycle_model", lambda value: value["numerical_contract"].__setitem__("sha256", "0" * 64)),
            ("continuity_count", "artifact_schemas", lambda value: value["artifacts"]["checkpoint_descriptor_continuity_report"]["nested"]["descriptor_identities"].__setitem__("count", 4)),
            ("secondary_count", "lifecycle_artifact_schemas", lambda value: value["artifacts"]["secondary_descriptor_continuity_failure"]["nested"]["descriptor_identities"].__setitem__("maximum_count", 6)),
            ("contract_status", "interface", lambda value: value.__setitem__("status", "DRAFT")),
            ("path_namespace", "path_timing", lambda value: value["paths"].__setitem__("attacker_path", {"phase_predicates": {}})),
            ("release_actor", "lifecycle_model", lambda value: next(item for item in value["transitions"] if item["name"] == "RELEASE_DESCRIPTOR_LEASES").__setitem__("actor", "PRIMARY_CONSUMER")),
        ]
        for mutation_id, authority_name, mutate in cases:
            with self.subTest(mutation_id=mutation_id), tempfile.TemporaryDirectory() as raw_root:
                root = Path(raw_root)
                for binding in manifest["authorities"].values():
                    source = REPOSITORY / binding["path"]
                    target = root / binding["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                target_manifest = root / manifest_path.relative_to(REPOSITORY)
                target_manifest.parent.mkdir(parents=True, exist_ok=True)
                mutated_manifest = json.loads(manifest_path.read_bytes())
                binding = mutated_manifest["authorities"][authority_name]
                target = root / binding["path"]
                value = json.loads(target.read_bytes())
                mutate(value)
                target.write_bytes(canonical(value))
                binding["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
                target_manifest.write_bytes(canonical(mutated_manifest))
                old_root, old_contracts = design_validator.ROOT, design_validator.CONTRACTS
                design_validator.ROOT = root
                design_validator.CONTRACTS = root / "specs/017-rust-native-inference-runtime/contracts"
                try:
                    with self.assertRaises(ValueError):
                        design_validator.validate()
                finally:
                    design_validator.ROOT, design_validator.CONTRACTS = old_root, old_contracts


if __name__ == "__main__":
    unittest.main()
