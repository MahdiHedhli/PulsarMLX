from __future__ import annotations

import copy
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"
sys.path.insert(0, str(RESEARCH))

import execute_f017_corrected_oracle_event_v3 as coordinator
import validate_f017_corrected_oracle_access_v3 as authorizer
from f017_corrected_oracle_authorization_v3 import (
    AUTH_KEYS,
    PRIMARY_ROLE,
    SCHEMA,
    SECONDARY_ROLE,
    canonical_bytes,
    sha256_bytes,
    sha256_path,
    validate_document,
)
from generate_f017_corrected_oracle_fixtures import fixture


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bank_json(path: Path, value: dict) -> None:
    path.write_bytes(canonical_bytes(value))


def tensor_dimensions(geometry: dict) -> dict[str, list[int]]:
    dimensions = {
        "token_embd.weight": [geometry["hidden"], geometry["vocab"]],
        "output_norm.weight": [geometry["hidden"]],
        "output.weight": [geometry["hidden"], geometry["vocab"]],
    }
    qdim = geometry["qk_nope"] + geometry["qk_rope"]
    for layer in range(geometry["layers"]):
        prefix = f"blk.{layer}"
        dimensions.update({
            f"{prefix}.attn_norm.weight": [geometry["hidden"]],
            f"{prefix}.attn_q_a.weight": [geometry["hidden"], geometry["q_rank"]],
            f"{prefix}.attn_q_a_norm.weight": [geometry["q_rank"]],
            f"{prefix}.attn_q_b.weight": [geometry["q_rank"], geometry["heads"] * qdim],
            f"{prefix}.attn_kv_a_mqa.weight": [geometry["hidden"], geometry["kv_rank"] + geometry["qk_rope"]],
            f"{prefix}.attn_kv_a_norm.weight": [geometry["kv_rank"]],
            f"{prefix}.attn_k_b.weight": [geometry["qk_nope"], geometry["kv_rank"], geometry["heads"]],
            f"{prefix}.attn_v_b.weight": [geometry["kv_rank"], geometry["value_dim"], geometry["heads"]],
            f"{prefix}.attn_output.weight": [geometry["heads"] * geometry["value_dim"], geometry["hidden"]],
            f"{prefix}.ffn_norm.weight": [geometry["hidden"]],
        })
        if layer < geometry["dense_layers"]:
            dimensions.update({
                f"{prefix}.ffn_gate.weight": [geometry["hidden"], geometry["dense_ffn"]],
                f"{prefix}.ffn_up.weight": [geometry["hidden"], geometry["dense_ffn"]],
                f"{prefix}.ffn_down.weight": [geometry["dense_ffn"], geometry["hidden"]],
            })
        else:
            dimensions.update({
                f"{prefix}.ffn_gate_inp.weight": [geometry["hidden"], geometry["experts"]],
                f"{prefix}.exp_probs_b.bias": [geometry["experts"]],
                f"{prefix}.ffn_gate_exps.weight": [geometry["hidden"], geometry["expert_ffn"], geometry["experts"]],
                f"{prefix}.ffn_up_exps.weight": [geometry["hidden"], geometry["expert_ffn"], geometry["experts"]],
                f"{prefix}.ffn_down_exps.weight": [geometry["expert_ffn"], geometry["hidden"], geometry["experts"]],
                f"{prefix}.ffn_gate_shexp.weight": [geometry["hidden"], geometry["expert_ffn"]],
                f"{prefix}.ffn_up_shexp.weight": [geometry["hidden"], geometry["expert_ffn"]],
                f"{prefix}.ffn_down_shexp.weight": [geometry["expert_ffn"], geometry["hidden"]],
            })
    return dimensions


def capability(role: str, source: Path, decoder: Path, numerical: Path) -> dict:
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-consumer-capability/1.0.0",
        "oracle_id": "F017_INDEPENDENT_CPU_REFERENCE_V1" if role == PRIMARY_ROLE else "F017_INDEPENDENT_ACCELERATED_CROSS_CHECK_V1",
        "consumer_role": role,
        "authorization_schemas": [SCHEMA],
        "scientific_access_contract_schemas": ["pulsarmlx.f017.corrected-full-checkpoint-oracle-scientific-access-contract/3.0.0"],
        "producer_path": source.relative_to(ROOT).as_posix(),
        "producer_sha256": digest(source),
        "decoder_path": decoder.relative_to(ROOT).as_posix(),
        "decoder_sha256": digest(decoder),
        "target_command": "target",
        "validation_only_command": "validate-live-authorization",
        "numerical_authority_path": numerical.relative_to(ROOT).as_posix(),
        "numerical_authority_sha256": digest(numerical),
    }


class SyntheticPackage:
    def __init__(self, root: Path, ordinal: int = 0):
        self.root = root
        self.checkpoint = root / "checkpoint"
        self.checkpoint.mkdir(parents=True)
        document = fixture(18102)
        self.document = document
        self.geometry = root / "geometry.json"
        bank_json(self.geometry, document["geometry"])
        dimensions = tensor_dimensions(document["geometry"])
        grouped: dict[str, list[tuple[int, list[float]]]] = {}
        for key, values in document["tensors"].items():
            base, separator, expert = key.partition("#")
            grouped.setdefault(base, []).append((int(expert) if separator else 0, values))
        payloads = {f"qualification-{index:02}.gguf": bytearray() for index in range(6)}
        records = []
        for index, name in enumerate(sorted(dimensions)):
            values = [value for _, part in sorted(grouped[name]) for value in part]
            encoded = struct.pack(f"<{len(values)}f", *values)
            shard = tuple(payloads)[index % 6]
            offset = len(payloads[shard])
            payloads[shard].extend(encoded)
            records.append({
                "name": name, "type": "F32", "type_id": 0,
                "dims": dimensions[name], "file": shard, "data_offset_abs": offset,
            })
        for name, payload in payloads.items():
            (self.checkpoint / name).write_bytes(payload)
        self.catalog = root / "catalog.json"
        bank_json(self.catalog, {"tensors": records})
        self.shards = [
            {"filename": name, "size_bytes": len(payload), "sha256": digest(self.checkpoint / name), "access_role": "GRAPH_PAYLOAD"}
            for name, payload in payloads.items()
        ]
        self.manifest = root / "manifest.json"
        bank_json(self.manifest, {"shards": self.shards})
        primary_source = RESEARCH / "f017_corrected_oracle_primary_v3.py"
        secondary_source = RESEARCH / "f017_corrected_oracle_secondary_v3.py"
        primary_decoder = RESEARCH / "f017_oracle_primary_decoders.py"
        secondary_decoder = RESEARCH / "qualify_f017_quantization_matrix_v1.py"
        primary_numerical = RESEARCH / "f017_corrected_oracle_primary.py"
        secondary_numerical = RESEARCH / "f017_corrected_oracle_secondary.py"
        primary_capability = capability(PRIMARY_ROLE, primary_source, primary_decoder, primary_numerical)
        secondary_capability = capability(SECONDARY_ROLE, secondary_source, secondary_decoder, secondary_numerical)
        interface = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v1.json"
        observer = RESEARCH / "f017_macos_memory_observation_v1.py"
        memory_contract = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-macos-memory-observation-contract-v1.json"
        numerical_contract = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v1.json"
        qualification = ROOT / "docs/architecture/reviews/evidence/f017-corrected-oracle-checkpoint-free-qualification-v1.json"
        authorizer_source = RESEARCH / "validate_f017_corrected_oracle_access_v3.py"
        coordinator_source = RESEARCH / "execute_f017_corrected_oracle_event_v3.py"
        checkpoint_set_sha = sha256_bytes(canonical_bytes({"shards": self.shards}))
        historical_sha = "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e"
        bindings = {
            "interface_sha256": digest(interface), "authorizer_sha256": digest(authorizer_source),
            "event_coordinator_sha256": digest(coordinator_source), "memory_observer_sha256": digest(observer),
            "memory_parser_contract_sha256": digest(memory_contract), "geometry_sha256": digest(self.geometry),
            "numerical_contract_sha256": digest(numerical_contract), "synthetic_qualification_sha256": digest(qualification),
            "checkpoint_manifest_sha256": digest(self.manifest), "checkpoint_set_sha256": checkpoint_set_sha,
            "historical_master_ledger_sha256": historical_sha,
        }
        self.contract_document = {
            "schema": "pulsarmlx.f017.corrected-full-checkpoint-oracle-scientific-access-contract/3.0.0",
            "status": "SYNTHETIC_QUALIFICATION_ONLY", "branch": "feat/017-rust-native-inference-runtime",
            "implementation_head": "d40af431511fca1a3f213db57085071d45cb9d13",
            "authorization_bindings": bindings,
            "bindings": {
                "primary": {"path": primary_source.relative_to(ROOT).as_posix(), "sha256": digest(primary_source)},
                "primary_decoders": {"path": primary_decoder.relative_to(ROOT).as_posix(), "sha256": digest(primary_decoder)},
                "secondary": {"path": secondary_source.relative_to(ROOT).as_posix(), "sha256": digest(secondary_source)},
                "secondary_decoder_authority": {"path": secondary_decoder.relative_to(ROOT).as_posix(), "sha256": digest(secondary_decoder)},
                "event_coordinator": {"path": coordinator_source.relative_to(ROOT).as_posix(), "sha256": digest(coordinator_source)},
                "authorizer": {"path": authorizer_source.relative_to(ROOT).as_posix(), "sha256": digest(authorizer_source)},
                "memory_observer": {"path": observer.relative_to(ROOT).as_posix(), "sha256": digest(observer)},
            },
            "unchanged_numerical_authorities": {
                "primary_oracle_sha256": digest(primary_numerical),
                "secondary_oracle_sha256": digest(secondary_numerical),
            },
            "consumer_capabilities": {
                "primary": {"path": "SYNTHETIC_DYNAMIC", "sha256": sha256_bytes(canonical_bytes(primary_capability))},
                "secondary": {"path": "SYNTHETIC_DYNAMIC", "sha256": sha256_bytes(canonical_bytes(secondary_capability))},
            },
            "production_checkpoint": {"shards": self.shards},
            "qualification": {"synthetic_catalog_path": str(self.catalog.resolve()), "synthetic_checkpoint_root": str(self.checkpoint.resolve())},
            "memory_preflight": {"minimum_free_bytes": 1, "sample_freshness_seconds": 60},
            "execution": {"consumer_timeout_seconds": 120},
            "context": {"prompt_token": document["token"], "position": document["position"], "top_n": 32},
            "frozen_thresholds": {"max_abs": 0.0065169706285814755, "rmse": 0.003463567697419031, "cosine_min": 0.9999999985448085},
        }
        self.contract = root / "contract.json"
        bank_json(self.contract, self.contract_document)
        self.package_root = root / "package"
        self.installed = root / "authorization.json"
        self.mint_evidence = root / "mint-evidence.json"
        self.mint_reports = root / "mint-reports"
        live_id = f"F017-CORRECTED-ORACLE-AUTH-QUAL-{ordinal:04d}"
        primary_event = f"F017-CORRECTED-ORACLE-PRIMARY-EVENT-QUAL-{ordinal:04d}"
        secondary_event = f"F017-CORRECTED-ORACLE-SECONDARY-EVENT-QUAL-{ordinal:04d}"
        self.inert_document = {
            "schema": SCHEMA, "state": "INERT_FIXTURE", "live": False,
            "authority_scope": "SYNTHETIC_QUALIFICATION",
            "authorization_id": "F017-CORRECTED-ORACLE-INERT-FIXTURE-3",
            "branch": self.contract_document["branch"], "implementation_head": self.contract_document["implementation_head"],
            "contract_sha256": digest(self.contract), "interface_sha256": bindings["interface_sha256"],
            "authorizer_sha256": bindings["authorizer_sha256"], "event_coordinator_sha256": bindings["event_coordinator_sha256"],
            "memory_observer_sha256": bindings["memory_observer_sha256"], "memory_parser_contract_sha256": bindings["memory_parser_contract_sha256"],
            "geometry_sha256": bindings["geometry_sha256"], "numerical_contract_sha256": bindings["numerical_contract_sha256"],
            "synthetic_qualification_sha256": bindings["synthetic_qualification_sha256"],
            "checkpoint_root": "INERT_NO_CHECKPOINT_PATH", "checkpoint_manifest_sha256": bindings["checkpoint_manifest_sha256"],
            "checkpoint_catalog_path": self.catalog.relative_to(ROOT).as_posix(), "checkpoint_catalog_sha256": digest(self.catalog),
            "checkpoint_set_sha256": bindings["checkpoint_set_sha256"], "shards": self.shards,
            "prompt_token": document["token"], "position": document["position"], "top_n": 32,
            "attempts": 1, "retries": 0, "resume": False, "consumers": [PRIMARY_ROLE, SECONDARY_ROLE],
            "package_state_root": "INERT_NO_STATE_ROOT", "package_output_root": "INERT_NO_OUTPUT_ROOT",
            "primary": {"role": PRIMARY_ROLE, "event_id": "F017-CORRECTED-ORACLE-INERT-PRIMARY-EVENT",
                        "producer_path": primary_source.relative_to(ROOT).as_posix(), "producer_sha256": digest(primary_source),
                        "decoder_path": primary_decoder.relative_to(ROOT).as_posix(), "decoder_sha256": digest(primary_decoder),
                        "state_root": "INERT_NO_STATE_ROOT", "output_root": "INERT_NO_OUTPUT_ROOT", "attempts": 1, "retries": 0, "resume": False},
            "secondary": {"role": SECONDARY_ROLE, "event_id": "F017-CORRECTED-ORACLE-INERT-SECONDARY-EVENT",
                          "producer_path": secondary_source.relative_to(ROOT).as_posix(), "producer_sha256": digest(secondary_source),
                          "decoder_path": secondary_decoder.relative_to(ROOT).as_posix(), "decoder_sha256": digest(secondary_decoder),
                          "state_root": "INERT_NO_STATE_ROOT", "output_root": "INERT_NO_OUTPUT_ROOT", "attempts": 1, "retries": 0, "resume": False},
            "historical_master_ledger_sha256": historical_sha, "historical_master_terminal": 175, "historical_master_delta": 0,
            "event_accounting": {"authorization_mint_delta": 0, "package_attempt_delta_on_durable_start": 1,
                                 "primary_event_delta_on_durable_start": 1, "secondary_event_delta_on_durable_start": 1,
                                 "unstarted_consumer_delta": 0},
            "p1_authority": "PROHIBITED", "operator_approval_sha256": "0" * 64, "memory_preflight_sha256": "0" * 64,
            "memory_observed_at_unix_ns": 0, "memory_available_bytes": 0,
            "candidate_nonce": hashlib.sha256(b"inert-v3").hexdigest(),
        }
        self.inert = root / "inert.json"
        bank_json(self.inert, self.inert_document)
        self.approval_document = {
            "schema": authorizer.APPROVAL_SCHEMA, "approval_id": f"F017-QUAL-APPROVAL-{ordinal:04d}",
            "decision": "GO_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_V3", "branch": self.contract_document["branch"],
            "contract_sha256": digest(self.contract), "live_authorization_id": live_id,
            "primary_event_id": primary_event, "secondary_event_id": secondary_event,
            "package_state_root": str(self.package_root), "checkpoint_root": str(self.checkpoint.resolve()),
            "attempts": 1, "retries": 0, "resume": False, "operator_identity": "SYNTHETIC_QUALIFICATION",
            "approved_at_utc": "2026-08-23T00:00:00Z", "new_go": True, "prior_go_reused": False,
            "p1_attempt_2": "PROHIBITED", "authorization_survives_bound_byte_change": False,
        }
        self.approval = root / "approval.json"
        bank_json(self.approval, self.approval_document)
        self.preflight_document = {
            "schema": authorizer.PREFLIGHT_SCHEMA, "result": "PASS", "branch": self.contract_document["branch"],
            "implementation_head": self.contract_document["implementation_head"], "git_head": self.contract_document["implementation_head"],
            "local_remote_parity": True, "worktree_clean": True, "contract_sha256": digest(self.contract),
            "coordinator_sha256": bindings["event_coordinator_sha256"], "memory_observer_sha256": bindings["memory_observer_sha256"],
            "machine_brand": "SYNTHETIC_QUALIFICATION", "architecture": "arm64", "minimum_free_bytes": 1,
            "observation": {"observed_at_unix_ns": time.time_ns(), "available_bytes": 1_000_000_000},
            "state_created": False, "authorization_created": False, "checkpoint_shard_opens": 0,
            "checkpoint_identity_hash_reads": 0, "checkpoint_payload_reads": 0,
        }
        self.preflight = root / "preflight.json"
        bank_json(self.preflight, self.preflight_document)

    def candidate(self) -> dict:
        return authorizer.build_candidate(
            self.inert_document, self.contract, self.contract_document, self.approval,
            self.preflight, self.checkpoint, self.package_root,
            scope="SYNTHETIC_QUALIFICATION",
        )

    def mint(self) -> dict:
        return authorizer.two_phase_install(
            self.candidate(), self.contract, self.contract_document, self.checkpoint,
            self.installed, self.mint_evidence, self.mint_reports,
        )

    def rewrite_contract_bindings(self) -> None:
        """Rebind synthetic control artifacts after an intentional contract mutation."""
        bank_json(self.contract, self.contract_document)
        contract_sha = digest(self.contract)
        self.inert_document["contract_sha256"] = contract_sha
        self.approval_document["contract_sha256"] = contract_sha
        self.preflight_document["contract_sha256"] = contract_sha
        bank_json(self.inert, self.inert_document)
        bank_json(self.approval, self.approval_document)
        bank_json(self.preflight, self.preflight_document)


class AuthorizationConsumerInstantiabilityV3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = ROOT / ".pulsarmlx-local/research-work"
        cls.scratch.mkdir(parents=True, exist_ok=True)

    def temporary(self):
        return tempfile.TemporaryDirectory(prefix="f017-instantiability-", dir=self.scratch)

    def test_event_02_mismatch_is_exact_and_immutable(self):
        old_primary = (RESEARCH / "f017_corrected_oracle_primary.py").read_text()
        old_secondary = (RESEARCH / "f017_corrected_oracle_secondary.py").read_text()
        old_authorizer = (RESEARCH / "validate_f017_corrected_oracle_access_v2.py").read_text()
        self.assertIn("access-authorization/1.0.0", old_primary)
        self.assertIn("access-authorization/1.0.0", old_secondary)
        self.assertIn("access-authorization/2.0.0", old_authorizer)
        summary = ROOT / "docs/architecture/reviews/evidence/f017-corrected-oracle-event-02-execution-failure-summary-v1.json"
        self.assertEqual(digest(summary), "617cb92605eb93cba3f24e7395a1a12ba0797ac2130213e2a72b5e83b87381eb")

    def test_two_phase_mint_validates_exact_candidate_with_both_consumers(self):
        with self.temporary() as directory:
            package = SyntheticPackage(Path(directory), 1)
            evidence = package.mint()
            self.assertEqual(evidence["result"], "PASS")
            self.assertTrue(evidence["candidate_installed_byte_identity"])
            installed = package.installed.read_bytes()
            self.assertEqual(hashlib.sha256(installed).hexdigest(), evidence["candidate_sha256"])
            self.assertNotIn(b"INERT", json.loads(installed)["authorization_id"].encode())
            self.assertFalse(package.package_root.exists())
            self.assertEqual(evidence["checkpoint_shard_opens"], 0)

    def test_two_phase_mint_requires_both_real_consumer_validations(self):
        with self.temporary() as directory:
            package = SyntheticPackage(Path(directory), 3)
            calls = []
            real = authorizer._run_consumer
            def observe(script, *args, **kwargs):
                calls.append(script.name)
                return real(script, *args, **kwargs)
            with mock.patch.object(authorizer, "_run_consumer", side_effect=observe):
                package.mint()
            self.assertEqual(calls, ["f017_corrected_oracle_primary_v3.py", "f017_corrected_oracle_secondary_v3.py"])

    def test_reused_package_or_consumer_event_identity_is_rejected(self):
        for key in ("live_authorization_id", "primary_event_id", "secondary_event_id"):
            with self.subTest(key=key), self.temporary() as directory:
                fake_root = Path(directory)
                evidence = fake_root / "docs/architecture/reviews/evidence"
                evidence.mkdir(parents=True)
                approval = fake_root / "approval.json"
                identity = f"F017-REUSED-{key.upper()}"
                document = {"live_authorization_id": "F017-UNUSED-AUTHORIZATION",
                            "primary_event_id": "F017-UNUSED-PRIMARY-EVENT",
                            "secondary_event_id": "F017-UNUSED-SECONDARY-EVENT"}
                document[key] = identity
                bank_json(approval, document)
                bank_json(evidence / "prior.json", {"historical_identity": identity})
                with mock.patch.object(authorizer, "ROOT", fake_root), self.assertRaises(ValueError):
                    authorizer._require_unused_live_identities(document, approval)

    def test_validation_only_fresh_processes_are_exact_and_side_effect_free(self):
        with self.temporary() as directory:
            package = SyntheticPackage(Path(directory), 2)
            package.mint()
            summaries = {"primary": [], "secondary": []}
            for name in summaries:
                script = RESEARCH / f"f017_corrected_oracle_{name}_v3.py"
                for index in range(10):
                    output = package.root / f"{name}-fresh-{index}.json"
                    subprocess.run([
                        sys.executable, str(script), "validate-live-authorization", str(package.installed),
                        str(package.contract), str(package.catalog), str(package.checkpoint), str(output),
                    ], cwd=ROOT, check=True, capture_output=True)
                    report = json.loads(output.read_text())
                    self.assertEqual(report["checkpoint_shard_opens"], 0)
                    self.assertEqual(report["checkpoint_identity_hash_reads"], 0)
                    self.assertEqual(report["checkpoint_tensor_reads"], 0)
                    self.assertEqual(report["numerical_operations"], 0)
                    summaries[name].append(canonical_bytes(report))
                self.assertEqual(len(set(summaries[name])), 1)
            self.assertFalse(package.package_root.exists())

    def test_full_successor_coordinator_runs_ten_fresh_synthetic_packages(self):
        classifications = []
        for ordinal in range(10, 20):
            with self.temporary() as directory:
                package = SyntheticPackage(Path(directory), ordinal)
                package.mint()
                handshake = package.root / "handshake.json"
                result = subprocess.run([
                    sys.executable, str(RESEARCH / "execute_f017_corrected_oracle_event_v3.py"),
                    "execute-synthetic", str(package.installed), str(package.contract), str(package.catalog),
                    str(package.checkpoint), str(package.geometry), str(package.package_root), str(handshake),
                ], cwd=ROOT, capture_output=True, text=True, timeout=180)
                self.assertEqual(result.returncode, 0, result.stderr)
                receipt = json.loads((package.package_root / "receipt.json").read_text())
                self.assertEqual(receipt["primary_event_delta"], 1)
                self.assertEqual(receipt["secondary_event_delta"], 1)
                self.assertTrue(receipt["primary"]["started"])
                self.assertTrue(receipt["secondary"]["started"])
                self.assertEqual(json.loads(handshake.read_text())["checkpoint_shard_opens_before_handshake"], 0)
                self.assertEqual(len(list((package.package_root / "checkpoint-identity-events").glob("*.json"))), 30)
                classifications.append(receipt["classification"])
        self.assertEqual(len(set(classifications)), 1)
        self.assertNotEqual(classifications[0], "ORACLE_EXECUTION_FAILURE")

    def test_authorization_mutation_matrix_fails_closed(self):
        with self.temporary() as directory:
            package = SyntheticPackage(Path(directory), 30)
            baseline = package.candidate()
            contract_sha = digest(package.contract)
            mutations = []
            def mutate(name, callback):
                value = copy.deepcopy(baseline)
                callback(value)
                mutations.append((name, value))
            mutate("SCHEMA_V1", lambda value: value.__setitem__("schema", "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/1.0.0"))
            mutate("SCHEMA_V2", lambda value: value.__setitem__("schema", "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/2.0.0"))
            mutate("MISSING_ROLE", lambda value: value["primary"].__setitem__("role", "MISSING"))
            mutate("SWAPPED_ROLES", lambda value: (value["primary"].__setitem__("role", SECONDARY_ROLE), value["secondary"].__setitem__("role", PRIMARY_ROLE)))
            mutate("WRONG_PRIMARY_SHA", lambda value: value["primary"].__setitem__("producer_sha256", "1" * 64))
            mutate("WRONG_SECONDARY_SHA", lambda value: value["secondary"].__setitem__("producer_sha256", "1" * 64))
            mutate("WRONG_DECODER_SHA", lambda value: value["primary"].__setitem__("decoder_sha256", "1" * 64))
            mutate("WRONG_CONTRACT_SHA", lambda value: value.__setitem__("contract_sha256", "1" * 64))
            mutate("WRONG_CATALOG_SHA", lambda value: value.__setitem__("checkpoint_catalog_sha256", "1" * 64))
            mutate("WRONG_CHECKPOINT_ROOT", lambda value: value.__setitem__("checkpoint_root", str(package.root)))
            mutate("WRONG_STATE_ROOT", lambda value: value.__setitem__("package_state_root", str(package.root / "other")))
            mutate("WRONG_OUTPUT_ROOT", lambda value: value.__setitem__("package_output_root", str(package.root / "other")))
            mutate("INERT_LIVE_ID", lambda value: value.__setitem__("authorization_id", "F017-INERT-AUTHORIZATION-03"))
            mutate("FIXTURE_LIVE_ID", lambda value: value.__setitem__("authorization_id", "F017-FIXTURE-AUTHORIZATION-03"))
            mutate("SAME_EVENT_ID", lambda value: value["secondary"].__setitem__("event_id", value["primary"]["event_id"]))
            mutate("UNKNOWN_FIELD", lambda value: value.__setitem__("unknown", 1))
            value = copy.deepcopy(baseline); value.pop("top_n"); mutations.append(("MISSING_FIELD", value))
            mutate("BOOLEAN_ATTEMPTS", lambda value: value.__setitem__("attempts", True))
            mutate("BOOLEAN_RETRIES", lambda value: value["primary"].__setitem__("retries", False))
            mutate("PRIMARY_EVENT_INERT", lambda value: value["primary"].__setitem__("event_id", "F017-INERT-PRIMARY-EVENT-03"))
            mutate("SECONDARY_EVENT_TEST", lambda value: value["secondary"].__setitem__("event_id", "F017-TEST-SECONDARY-EVENT-03"))
            mutate("ACCOUNT_SECONDARY_UNSTARTED", lambda value: value["event_accounting"].__setitem__("unstarted_consumer_delta", 1))
            mutate("RETRY_ENABLED", lambda value: value.__setitem__("retries", 1))
            mutate("RESUME_ENABLED", lambda value: value.__setitem__("resume", True))
            mutate("P1_AUTHORITY", lambda value: value.__setitem__("p1_authority", "ALLOWED"))
            for name, value in mutations:
                with self.subTest(name=name), self.assertRaises((ValueError, FileNotFoundError)):
                    validate_document(value, package.contract_document, ROOT, require_live=True,
                                      expected_scope="SYNTHETIC_QUALIFICATION", contract_sha256=contract_sha)
            self.assertEqual(len(mutations), 25)

    def test_failed_primary_validation_prevents_install_and_state(self):
        with self.temporary() as directory:
            package = SyntheticPackage(Path(directory), 40)
            candidate = package.candidate()
            real = authorizer._run_consumer
            def fail_primary(script, *args, **kwargs):
                if script.name.endswith("primary_v3.py"):
                    raise subprocess.CalledProcessError(1, [str(script)])
                return real(script, *args, **kwargs)
            with mock.patch.object(authorizer, "_run_consumer", side_effect=fail_primary):
                with self.assertRaises(ValueError):
                    package.mint()
            self.assertFalse(package.installed.exists())
            self.assertFalse(package.package_root.exists())
            evidence = json.loads(package.mint_evidence.read_text())
            self.assertEqual(evidence["result"], "FAIL")
            self.assertEqual(evidence["checkpoint_shard_opens"], 0)

    def test_identity_failure_records_zero_consumer_starts(self):
        with self.temporary() as directory:
            package = SyntheticPackage(Path(directory), 50)
            package.mint()
            first = package.checkpoint / package.shards[0]["filename"]
            first.write_bytes(first.read_bytes() + b"corrupt")
            handshake = package.root / "handshake.json"
            result = subprocess.run([
                sys.executable, str(RESEARCH / "execute_f017_corrected_oracle_event_v3.py"),
                "execute-synthetic", str(package.installed), str(package.contract), str(package.catalog),
                str(package.checkpoint), str(package.geometry), str(package.package_root), str(handshake),
            ], cwd=ROOT, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 2)
            receipt = json.loads((package.package_root / "receipt.json").read_text())
            self.assertEqual(receipt["primary_event_delta"], 0)
            self.assertEqual(receipt["secondary_event_delta"], 0)
            self.assertFalse(receipt["primary"]["started"])
            self.assertFalse(receipt["secondary"]["started"])

    def test_capability_mismatch_fails_before_state_and_checkpoint_identity(self):
        with self.temporary() as directory:
            package = SyntheticPackage(Path(directory), 55)
            package.contract_document["consumer_capabilities"]["primary"]["sha256"] = "1" * 64
            package.rewrite_contract_bindings()
            package.mint()
            handshake = package.root / "handshake.json"
            with self.assertRaises(ValueError):
                coordinator.handshake(package.installed, package.contract, package.catalog,
                                      package.checkpoint, handshake, scope="SYNTHETIC_QUALIFICATION")
            self.assertFalse(package.package_root.exists())
            self.assertFalse(handshake.exists())

    def test_handshake_failure_prevents_identity_hash_and_package_state(self):
        with self.temporary() as directory:
            package = SyntheticPackage(Path(directory), 56)
            package.mint()
            arguments = SimpleNamespace(
                authorization=package.installed, contract=package.contract, catalog=package.catalog,
                checkpoint_root=package.checkpoint, geometry=package.geometry,
                package_root=package.package_root, handshake_output=package.root / "handshake.json",
            )
            with mock.patch.object(coordinator, "handshake", side_effect=ValueError("injected handshake failure")), \
                 mock.patch.object(coordinator, "verify_checkpoint_identity") as identity, \
                 self.assertRaises(ValueError):
                coordinator.execute_event(arguments, scope="SYNTHETIC_QUALIFICATION")
            identity.assert_not_called()
            self.assertFalse(package.package_root.exists())

    def test_primary_precompletion_failure_does_not_start_secondary(self):
        with self.temporary() as directory:
            package = SyntheticPackage(Path(directory), 57)
            package.mint()
            arguments = SimpleNamespace(
                authorization=package.installed, contract=package.contract, catalog=package.catalog,
                checkpoint_root=package.checkpoint, geometry=package.geometry,
                package_root=package.package_root, handshake_output=package.root / "handshake.json",
            )
            real_run = subprocess.run
            def fail_primary_target(command, *args, **kwargs):
                if "f017_corrected_oracle_primary_v3.py" in str(command[1]) and "target" in command:
                    raise subprocess.CalledProcessError(9, command)
                return real_run(command, *args, **kwargs)
            with mock.patch.object(coordinator.subprocess, "run", side_effect=fail_primary_target):
                self.assertEqual(coordinator.execute_event(arguments, scope="SYNTHETIC_QUALIFICATION"), 2)
            receipt = json.loads((package.package_root / "receipt.json").read_text())
            self.assertEqual(receipt["primary_event_delta"], 1)
            self.assertEqual(receipt["secondary_event_delta"], 0)
            self.assertTrue(receipt["primary"]["started"])
            self.assertFalse(receipt["secondary"]["started"])

    def test_secondary_runtime_does_not_inherit_native_rust_mlx_linkage(self):
        with self.temporary() as directory:
            package = SyntheticPackage(Path(directory), 58)
            package.mint()
            arguments = SimpleNamespace(
                authorization=package.installed, contract=package.contract, catalog=package.catalog,
                checkpoint_root=package.checkpoint, geometry=package.geometry,
                package_root=package.package_root, handshake_output=package.root / "handshake.json",
            )
            real_run = subprocess.run
            observed = []
            def inspect_secondary(command, *args, **kwargs):
                if "f017_corrected_oracle_secondary_v3.py" in str(command[1]) and "target" in command:
                    environment = kwargs["env"]
                    observed.append(environment["F017_ORACLE_SECONDARY_RUNTIME"])
                    for variable in ("DYLD_LIBRARY_PATH", "MLX_C_PREFIX", "MLX_PREFIX", "RUSTFLAGS"):
                        self.assertNotIn(variable, environment)
                return real_run(command, *args, **kwargs)
            contaminated = {
                "DYLD_LIBRARY_PATH": "/synthetic/incompatible/native-mlx",
                "MLX_C_PREFIX": "/synthetic/native-mlx",
                "MLX_PREFIX": "/synthetic/native-mlx",
                "RUSTFLAGS": "-C link-arg=/synthetic/native-mlx",
            }
            with mock.patch.dict(os.environ, contaminated), \
                 mock.patch.object(coordinator.subprocess, "run", side_effect=inspect_secondary):
                self.assertEqual(coordinator.execute_event(arguments, scope="SYNTHETIC_QUALIFICATION"), 0)
            self.assertEqual(observed, ["LOCKFILE_PYTHON_MLX"])

    def test_candidate_install_byte_mismatch_is_detected(self):
        with self.temporary() as directory:
            package = SyntheticPackage(Path(directory), 60)
            candidate = package.candidate()
            original_bank = authorizer._bank
            def corrupt_install(path, value, mode=0o400):
                result = original_bank(path, value, mode)
                if path == package.installed:
                    path.chmod(0o600)
                    path.write_bytes(path.read_bytes() + b" ")
                return result
            with mock.patch.object(authorizer, "_bank", side_effect=corrupt_install):
                with self.assertRaises(ValueError):
                    authorizer.two_phase_install(candidate, package.contract, package.contract_document,
                                                 package.checkpoint, package.installed, package.mint_evidence,
                                                 package.mint_reports)
            self.assertFalse(package.package_root.exists())


if __name__ == "__main__":
    unittest.main()
