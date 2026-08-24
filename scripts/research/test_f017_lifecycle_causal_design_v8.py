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

STATIC_DESIGN_MUTATIONS = 179
RUNTIME_CLOSURE_MUTATIONS = 26


class CausalDesignTests(unittest.TestCase):
    @staticmethod
    def _rehash_descendants(package: Path, docs: dict, changed_id: str) -> None:
        changed = {changed_id: hashlib.sha256((package / f"{changed_id}.json").read_bytes()).hexdigest()}
        for node in sorted(docs["artifact_dag"]["nodes"], key=lambda item: item["creation_rank"]):
            path = package / f"{node['artifact_id']}.json"
            if not path.is_file() or node["artifact_id"] == changed_id:
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

    def test_complete_design_and_symbolic_packages(self):
        result = validator.validate_documents(validator.load_documents())
        result["symbolic"] = validate_all()
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["symbolic"]["constructed_outcomes"], 48)

    def test_design_mutations_fail_closed(self):
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
        # One partition mutation for every durable-prefix outcome variant.
        for outcome in sorted(baseline["outcomes"]["outcomes"]):
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
            ("SHARD_DIGEST", lambda d: d["checkpoint_identity"]["shards"][2].__setitem__("sha256", "0" * 64)),
            ("SHARD_FILENAME", lambda d: d["checkpoint_identity"]["shards"][2].__setitem__("filename", "ATTACKER.gguf")),
            ("IDENTITY_PROCESSING_HASH", lambda d: d["checkpoint_identity"]["processing"].__setitem__("hash", "PREFIX_ONLY")),
            ("IDENTITY_PROCESSING_FSTAT", lambda d: d["checkpoint_identity"]["processing"].__setitem__("pre_post_fstat_equal", False)),
            ("IDENTITY_PROCESSING_EMPTY", lambda d: d["checkpoint_identity"].__setitem__("processing", {})),
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
            ("DAG_EDGE_SEMANTICS", lambda d: d["artifact_dag"].__setitem__("edge_semantics", "WARN_ONLY")),
            ("DAG_NODE_ACTOR", lambda d: d["artifact_dag"]["nodes"][11].__setitem__("actor", "PRIMARY_CONSUMER")),
            ("MODEL_TRANSITIONS", lambda d: d["lifecycle_model"].__setitem__("transitions", [{"id": "RETRY"}])),
            ("MODEL_STATES", lambda d: d["lifecycle_model"].__setitem__("states", [])),
            ("MODEL_INVARIANT", lambda d: d["lifecycle_model"]["unconditional_invariants"].__setitem__("evidence_append_only", False)),
            ("ACCOUNTING_PACKAGE_RANK", lambda d: d["accounting"].__setitem__("package_start_rank", 1)),
            ("INVARIANT_SOURCE_POINTER", lambda d: d["safety_invariants"]["invariants"][0].__setitem__("source_json_pointer", "/processing/hash")),
            ("ALL_ACTORS_OPERATOR", lambda d: [item.__setitem__("actor", "OPERATOR") for item in d["artifact_dag"]["nodes"]]),
            ("ROOT_AUTHORITY_REMOVED", lambda d: d["artifact_dag"]["root_authorities"].pop("v7_budget_closeout")),
            ("FINAL_EVENT04_TRUE", lambda d: next(item for item in d["artifact_dag"]["nodes"] if item["artifact_id"] == "final_declaration")["payload_constants"].__setitem__("event_04_executed", True)),
            ("FINAL_ACCESS_42", lambda d: next(item for item in d["artifact_dag"]["nodes"] if item["artifact_id"] == "final_declaration")["payload_constants"].__setitem__("original_checkpoint_access", 42)),
            ("PAYLOAD_RULE_REMOVED", lambda d: next(item for item in d["artifact_dag"]["nodes"] if item["artifact_id"] == "checkpoint_shard_receipt_4")["payload_rules"].pop("observed_checkpoint_digest")),
            ("ACCESS_RECEIPT_ORDER", lambda d: next(item for item in d["artifact_dag"]["nodes"] if item["artifact_id"] == "checkpoint_access_event_2").__setitem__("dependencies", ["checkpoint_access_event_1"])),
            ("PRIMARY_TERMINAL_FAIL", lambda d: next(item for item in d["artifact_dag"]["nodes"] if item["artifact_id"] == "primary_terminal")["payload_constants"].__setitem__("result", "FAIL")),
            ("COORDINATED_OPAQUE_ID_CONSTANT", lambda d: [next(item for item in d[name]["nodes"] if item["artifact_id"] == "package_claim")["payload_constants"].__setitem__("owner_nonce", "PINNED") if name == "artifact_dag" else d[name]["artifacts"]["package_claim"]["payload_constants"].__setitem__("owner_nonce", "PINNED") for name in ("artifact_dag", "artifact_schemas")]),
        ])
        self.assertEqual(len(mutations), STATIC_DESIGN_MUTATIONS)
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
                validate_package(package, "final_declaration", required, docs["artifact_dag"]["root_authorities"], docs["artifact_dag"], docs["artifact_schemas"], "COMPLETE_SUCCESS")

            target = json.loads(target_path.read_bytes())
            target["package_attempt_id"] = "F017-V8-SYMBOLIC-PACKAGE"
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
                validate_package(package, "final_declaration", required, docs["artifact_dag"]["root_authorities"], docs["artifact_dag"], docs["artifact_schemas"], "COMPLETE_SUCCESS")

    def test_runtime_authority_conformance_mutations_fail_closed(self):
        docs = validator.load_documents()
        required = set(docs["outcomes"]["outcomes"]["COMPLETE_SUCCESS"]["required"])
        attacks = [
            ("FORGED_SCHEMA", "checkpoint_identity_receipt", lambda v: v.__setitem__("schema", "attacker/1")),
            ("FORGED_OUTCOME", "package_terminal", lambda v: v.__setitem__("outcome", "PRE_MINT_FAILURE")),
            ("EXTRA_PAYLOAD", "descriptor_release_report", lambda v: v["payload"].__setitem__("attacker", True)),
            ("DROPPED_ROOT", "operator_approval", lambda v: v["root_authorities"].pop("numerical_contract")),
            ("LIVE_LEASES", "descriptor_release_report", lambda v: v["payload"].__setitem__("live_leases_after_release", 5)),
            ("PATH_REOPEN", "primary_descriptor_continuity_report", lambda v: v["payload"].__setitem__("path_reopen_count", 7)),
            ("NOT_SYNTHETIC", "primary_execution_evidence", lambda v: v["payload"].__setitem__("synthetic_only", False)),
            ("OBSERVED_TOTAL", "checkpoint_identity_manifest", lambda v: v["payload"].__setitem__("observed_total_bytes", 1)),
            ("OBSERVED_DIGEST", "checkpoint_shard_receipt_4", lambda v: v["payload"].__setitem__("observed_checkpoint_digest", "0" * 64)),
            ("EMPTY_LEASE_IDS", "descriptor_lease_manifest", lambda v: v["payload"].__setitem__("lease_ids", [])),
            ("EMPTY_DESCRIPTOR_IDENTITIES", "descriptor_lease_manifest", lambda v: v["payload"].__setitem__("descriptor_identities", [])),
            ("EMPTY_RECEIPT_DIGESTS", "checkpoint_identity_manifest", lambda v: v["payload"].__setitem__("ordered_shard_receipt_digests", [])),
            ("PRIMARY_RESULT_FAIL", "primary_terminal", lambda v: v["payload"].__setitem__("result", "FAIL")),
            ("DUPLICATE_DESCRIPTOR_IDENTITY", "descriptor_lease_manifest", lambda v: v["payload"]["descriptor_identities"][1].update({"device": v["payload"]["descriptor_identities"][0]["device"], "inode": v["payload"]["descriptor_identities"][0]["inode"]})),
            ("WRONG_DESCRIPTOR_SIZE", "descriptor_lease_manifest", lambda v: v["payload"]["descriptor_identities"][0].__setitem__("size", 1)),
            ("STRING_DESCRIPTOR_DEVICE", "descriptor_lease_manifest", lambda v: v["payload"]["descriptor_identities"][0].__setitem__("device", "1")),
            ("EMPTY_DESCRIPTOR_LEASE_ID", "descriptor_lease_manifest", lambda v: v["payload"]["descriptor_identities"][0].__setitem__("lease_id", "")),
            ("BLOCKED_DISAGREEMENT_ON_SUCCESS", "comparison_receipt", lambda v: v["payload"].__setitem__("classification", "ORACLE_DISAGREEMENT")),
            ("BLOCKED_EXECUTION_FAILURE_ON_SUCCESS", "comparison_receipt", lambda v: v["payload"].__setitem__("classification", "ORACLE_EXECUTION_FAILURE")),
            ("CANDIDATE_PACKAGE_ID_DIVERGENCE", "candidate_authorization", lambda v: v["payload"].__setitem__("package_attempt_id", "ATTACKER-PACKAGE")),
            ("PRIMARY_TERMINAL_EVENT_DIVERGENCE", "primary_terminal", lambda v: v["payload"].__setitem__("event_id", "ATTACKER-EVENT")),
            ("EMPTY_OWNER_NONCE", "package_claim", lambda v: v["payload"].__setitem__("owner_nonce", "")),
        ]
        self.assertEqual(len(attacks), 22)
        for attack_id, target_id, mutate in attacks:
            with self.subTest(attack_id=attack_id), tempfile.TemporaryDirectory() as raw_root:
                package = Path(raw_root)
                construct_outcome("COMPLETE_SUCCESS", package, docs["artifact_dag"], docs["artifact_schemas"], docs["outcomes"])
                path = package / f"{target_id}.json"
                value = json.loads(path.read_bytes())
                mutate(value)
                path.write_bytes(canonical(value))
                self._rehash_descendants(package, docs, target_id)
                with self.assertRaises(ValueError):
                    validate_package(package, "final_declaration", required, docs["artifact_dag"]["root_authorities"], docs["artifact_dag"], docs["artifact_schemas"], "COMPLETE_SUCCESS")

    def test_identity_prefix_release_is_exact_and_never_duplicated(self):
        docs = validator.load_documents()
        for rank, expected_leases in ((13, 0), (14, 1), (16, 2), (18, 3), (20, 4), (22, 5)):
            outcome = f"CHECKPOINT_IDENTITY_FAILURE__AFTER_RANK_{rank:03d}"
            obligation = docs["outcomes"]["outcomes"][outcome]
            capsules = [item for item in obligation["required"] if item.startswith("failure_terminal_capsule__")]
            self.assertEqual(len(capsules), 1)
            node = next(item for item in docs["artifact_dag"]["nodes"] if item["artifact_id"] == capsules[0])
            self.assertEqual(node["payload_constants"]["expected_leases"], expected_leases)
            self.assertEqual(node["payload_constants"]["lease_ordinals"], list(range(2, 2 + expected_leases)))
            self.assertEqual(node["payload_rules"]["duplicate_closures"], {"kind": "NONNEGATIVE_INTEGER"})
            self.assertEqual(node["payload_rules"]["unknown_leases"], {"kind": "NONNEGATIVE_INTEGER"})
        outcome = "EVIDENCE_BANKING_FAILURE__AFTER_RANK_045"
        capsules = [item for item in docs["outcomes"]["outcomes"][outcome]["required"] if item.startswith("failure_terminal_capsule__")]
        self.assertEqual(len(capsules), 1)
        node = next(item for item in docs["artifact_dag"]["nodes"] if item["artifact_id"] == capsules[0])
        self.assertEqual(node["payload_constants"]["expected_leases"], 0)

    def test_cleanup_anomaly_is_recordable_in_atomic_terminal_capsule(self):
        docs = validator.load_documents()
        outcome = "CHECKPOINT_IDENTITY_FAILURE__AFTER_RANK_014"
        required = set(docs["outcomes"]["outcomes"][outcome]["required"])
        with tempfile.TemporaryDirectory() as raw_root:
            package = Path(raw_root)
            built = construct_outcome(outcome, package, docs["artifact_dag"], docs["artifact_schemas"], docs["outcomes"])
            terminal_id = built["terminal_id"]
            path = package / f"{terminal_id}.json"
            value = json.loads(path.read_bytes())
            value["payload"].update({"attempted_closures": 1, "successful_closures": 0, "duplicate_closures": 1, "unknown_leases": 0})
            path.write_bytes(canonical(value))
            result = validate_package(package, terminal_id, required, docs["artifact_dag"]["root_authorities"], docs["artifact_dag"], docs["artifact_schemas"], outcome)
            self.assertEqual(result["result"], "PASS")

    def test_unknown_lease_cannot_discharge_live_lease_obligation(self):
        docs = validator.load_documents()
        outcome = "CHECKPOINT_IDENTITY_FAILURE__AFTER_RANK_022"
        required = set(docs["outcomes"]["outcomes"][outcome]["required"])
        with tempfile.TemporaryDirectory() as raw_root:
            package = Path(raw_root)
            built = construct_outcome(outcome, package, docs["artifact_dag"], docs["artifact_schemas"], docs["outcomes"])
            terminal_id = built["terminal_id"]
            path = package / f"{terminal_id}.json"
            value = json.loads(path.read_bytes())
            value["payload"].update({"attempted_closures": 5, "successful_closures": 0, "duplicate_closures": 0, "unknown_leases": 5})
            path.write_bytes(canonical(value))
            with self.assertRaisesRegex(ValueError, "closure accounting"):
                validate_package(package, terminal_id, required, docs["artifact_dag"]["root_authorities"], docs["artifact_dag"], docs["artifact_schemas"], outcome)

    def test_top1_uncertainty_is_success_compatible(self):
        docs = validator.load_documents()
        required = set(docs["outcomes"]["outcomes"]["COMPLETE_SUCCESS"]["required"])
        with tempfile.TemporaryDirectory() as raw_root:
            package = Path(raw_root)
            construct_outcome("COMPLETE_SUCCESS", package, docs["artifact_dag"], docs["artifact_schemas"], docs["outcomes"])
            for artifact_id in ("comparison_receipt", "comparison_terminal"):
                path = package / f"{artifact_id}.json"
                value = json.loads(path.read_bytes())
                value["payload"]["classification"] = "TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY"
                path.write_bytes(canonical(value))
                self._rehash_descendants(package, docs, artifact_id)
            result = validate_package(package, "final_declaration", required, docs["artifact_dag"]["root_authorities"], docs["artifact_dag"], docs["artifact_schemas"], "COMPLETE_SUCCESS")
            self.assertEqual(result["result"], "PASS")

    def test_durable_prefix_bytes_do_not_depend_on_future_outcome(self):
        docs = validator.load_documents()
        with tempfile.TemporaryDirectory() as raw_root:
            root = Path(raw_root)
            success = root / "success"
            success.mkdir()
            construct_outcome("COMPLETE_SUCCESS", success, docs["artifact_dag"], docs["artifact_schemas"], docs["outcomes"])
            for outcome, obligation in docs["outcomes"]["outcomes"].items():
                if outcome == "COMPLETE_SUCCESS":
                    continue
                failure = root / outcome.lower()
                failure.mkdir()
                construct_outcome(outcome, failure, docs["artifact_dag"], docs["artifact_schemas"], docs["outcomes"])
                for node in docs["artifact_dag"]["nodes"]:
                    if node["creation_rank"] <= obligation["durable_prefix_rank"] and not node["artifact_id"].startswith("failure_terminal_capsule__"):
                        self.assertEqual((failure / f"{node['artifact_id']}.json").read_bytes(), (success / f"{node['artifact_id']}.json").read_bytes(), f"{outcome}:{node['artifact_id']}")

    def test_capsule_cleanup_count_must_equal_expected_leases(self):
        docs = validator.load_documents()
        outcome = "CHECKPOINT_IDENTITY_FAILURE__AFTER_RANK_022"
        required = set(docs["outcomes"]["outcomes"][outcome]["required"])
        with tempfile.TemporaryDirectory() as raw_root:
            package = Path(raw_root)
            built = construct_outcome(outcome, package, docs["artifact_dag"], docs["artifact_schemas"], docs["outcomes"])
            terminal_id = built["terminal_id"]
            path = package / f"{terminal_id}.json"
            value = json.loads(path.read_bytes())
            value["payload"].update({"attempted_closures": 0, "successful_closures": 0, "duplicate_closures": 0, "unknown_leases": 0})
            path.write_bytes(canonical(value))
            with self.assertRaisesRegex(ValueError, "closure accounting"):
                validate_package(package, terminal_id, required, docs["artifact_dag"]["root_authorities"], docs["artifact_dag"], docs["artifact_schemas"], outcome)


if __name__ == "__main__":
    unittest.main()
