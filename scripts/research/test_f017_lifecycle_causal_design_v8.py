#!/usr/bin/env python3
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import validate_f017_lifecycle_causal_design_v8 as validator
from construct_f017_lifecycle_v8_symbolically import validate_all
from construct_f017_lifecycle_v8_symbolically import canonical, construct_outcome
from check_f017_transitive_artifact_closure_v8 import validate_package


class CausalDesignTests(unittest.TestCase):
    def test_complete_design_and_symbolic_packages(self):
        result = validator.validate_documents(validator.load_documents())
        result["symbolic"] = validate_all()
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["symbolic"]["constructed_outcomes"], 15)

    def test_120_design_mutations_fail_closed(self):
        baseline = validator.load_documents()
        mutations = []
        nodes = baseline["artifact_dag"]["nodes"]
        # 30 causal-rank mutations.
        for index in range(1, 31):
            def mutate(docs, index=index):
                item = docs["artifact_dag"]["nodes"][index]
                dependency = item["dependencies"][0]
                dependency_node = next(node for node in docs["artifact_dag"]["nodes"] if node["artifact_id"] == dependency)
                item["creation_rank"] = dependency_node["creation_rank"]
            mutations.append((f"CAUSAL_RANK_{index:03d}", mutate))
        # 25 invariant mutations, one per committed invariant.
        for index in range(25):
            def mutate(docs, index=index):
                item = docs["safety_invariants"]["invariants"][index]
                item["expected"] = "ATTACKER_VALUE"
            mutations.append((f"SAFETY_{index:03d}", mutate))
        # 20 path mutations.
        path_ids = list(baseline["path_timing"]["paths"])[:20]
        for artifact_id in path_ids:
            def mutate(docs, artifact_id=artifact_id):
                docs["path_timing"]["paths"][artifact_id]["producer_transition_id"] = "ATTACKER_TRANSITION"
            mutations.append((f"PATH_{artifact_id}", mutate))
        # 15 outcome partition mutations.
        for outcome in sorted(validator.OUTCOMES):
            def mutate(docs, outcome=outcome):
                required = docs["outcomes"]["outcomes"][outcome]["required"]
                required.pop()
            mutations.append((f"OUTCOME_{outcome}", mutate))
        # 10 continuity mutations.
        continuity_mutations = [
            lambda d: d["continuity"].__setitem__("path_reopen_count", 1),
            lambda d: d["continuity"].__setitem__("path_reopen_permitted", True),
            lambda d: d["continuity"].__setitem__("descriptor_transport", "PATH_STRING"),
            lambda d: d["continuity"]["success_reports"]["primary"].__setitem__("count", 0),
            lambda d: d["continuity"]["success_reports"]["secondary"].__setitem__("count", 0),
            lambda d: d["continuity"]["success_reports"]["secondary"].__setitem__("ordinals", [2, 3, 4, 5]),
            lambda d: d["continuity"]["success_reports"]["primary"].__setitem__("self_sha_field_permitted", True),
            lambda d: d["continuity"].__setitem__("identity_only_descriptor_permitted", True),
            lambda d: d["continuity"]["release"].__setitem__("live_leases_after_success", 1),
            lambda d: d["continuity"].__setitem__("descriptor_identity_fields", ["inode"]),
        ]
        mutations.extend((f"CONTINUITY_{index:03d}", mutation) for index, mutation in enumerate(continuity_mutations))
        # 10 shard/census mutations.
        for index in range(6):
            def mutate(docs, index=index):
                docs["checkpoint_identity"]["shards"][index]["size_bytes"] += 1
            mutations.append((f"SHARD_SIZE_{index}", mutate))
        mutations.extend([
            ("SHARD_ROLE", lambda d: d["checkpoint_identity"]["shards"][0].__setitem__("role", "GRAPH_PAYLOAD")),
            ("SHARD_OMIT", lambda d: d["checkpoint_identity"]["shards"].pop()),
            ("CENSUS_TOTAL", lambda d: d["checkpoint_identity"]["derived_census"].__setitem__("expected_total_bytes", 1)),
            ("LEASE_COUNT", lambda d: d["checkpoint_identity"]["derived_census"].__setitem__("expected_retained_lease_count", 4)),
        ])
        # 10 schema/DAG binding mutations.
        schema_ids = list(baseline["artifact_schemas"]["artifacts"])[:10]
        for artifact_id in schema_ids:
            def mutate(docs, artifact_id=artifact_id):
                docs["artifact_schemas"]["artifacts"][artifact_id]["creation_rank"] += 1
            mutations.append((f"SCHEMA_{artifact_id}", mutate))
        mutations.extend([
            ("SELF_REFERENCE", lambda d: d["artifact_dag"]["nodes"][1]["dependencies"].append("candidate_authorization")),
            ("TWO_NODE_CYCLE", lambda d: d["artifact_dag"]["nodes"][0]["dependencies"].append("candidate_authorization")),
            ("THREE_NODE_CYCLE", lambda d: d["artifact_dag"]["nodes"][0]["dependencies"].append("primary_candidate_validation")),
            ("FUTURE_RECEIPT_REFERENCE", lambda d: next(item for item in d["artifact_dag"]["nodes"] if item["artifact_id"] == "checkpoint_identity_receipt")["dependencies"].append("primary_descriptor_continuity_report")),
            ("PRIMARY_REPORT_SELF_REFERENCE", lambda d: next(item for item in d["artifact_dag"]["nodes"] if item["artifact_id"] == "primary_descriptor_continuity_report")["dependencies"].append("primary_descriptor_continuity_report")),
            ("IDENTITY_RECEIPT_DEPENDENCY_REMOVED", lambda d: next(item for item in d["artifact_dag"]["nodes"] if item["artifact_id"] == "checkpoint_identity_receipt").__setitem__("dependencies", [])),
        ])
        self.assertEqual(len(mutations), 126)
        for mutation_id, mutate in mutations:
            with self.subTest(mutation_id=mutation_id):
                docs = copy.deepcopy(baseline)
                mutate(docs)
                with self.assertRaises(ValueError):
                    validator.validate_documents(docs)

    def test_cross_package_splice_and_artifact_cycle_fail_closed(self):
        docs = validator.load_documents()
        required = set(docs["outcomes"]["outcomes"]["COMPLETE_SUCCESS"]["required"])
        with tempfile.TemporaryDirectory() as raw_root:
            package = Path(raw_root)
            construct_outcome("COMPLETE_SUCCESS", package, docs["artifact_dag"], docs["artifact_schemas"], docs["outcomes"])
            target_id = "primary_descriptor_continuity_report"
            target_path = package / f"{target_id}.json"
            target = json.loads(target_path.read_bytes())
            target["package_attempt_id"] = "ATTACKER-PACKAGE"
            target_path.write_bytes(canonical(target))
            changed = {target_id: hashlib.sha256(target_path.read_bytes()).hexdigest()}
            for node in sorted(docs["artifact_dag"]["nodes"], key=lambda item: item["creation_rank"]):
                path = package / f"{node['artifact_id']}.json"
                if not path.is_file() or node["artifact_id"] == target_id:
                    continue
                value = json.loads(path.read_bytes())
                touched = False
                for dependency_id in list(value["dependencies"]):
                    if dependency_id in changed:
                        value["dependencies"][dependency_id] = changed[dependency_id]
                        touched = True
                if touched:
                    path.write_bytes(canonical(value))
                    changed[node["artifact_id"]] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "cross-package artifact splice"):
                validate_package(package, "final_declaration", required, docs["artifact_dag"]["root_authorities"])

            target = json.loads(target_path.read_bytes())
            target["package_attempt_id"] = "F017-V8-SYMBOLIC-COMPLETE_SUCCESS"
            target["dependencies"][target_id] = "0" * 64
            target_path.write_bytes(canonical(target))
            changed = {target_id: hashlib.sha256(target_path.read_bytes()).hexdigest()}
            for node in sorted(docs["artifact_dag"]["nodes"], key=lambda item: item["creation_rank"]):
                path = package / f"{node['artifact_id']}.json"
                if not path.is_file() or node["artifact_id"] == target_id:
                    continue
                value = json.loads(path.read_bytes())
                touched = False
                for dependency_id in list(value["dependencies"]):
                    if dependency_id in changed:
                        value["dependencies"][dependency_id] = changed[dependency_id]
                        touched = True
                if touched:
                    path.write_bytes(canonical(value))
                    changed[node["artifact_id"]] = hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                validate_package(package, "final_declaration", required, docs["artifact_dag"]["root_authorities"])


if __name__ == "__main__":
    unittest.main()
