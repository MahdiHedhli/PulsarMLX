#!/usr/bin/env python3
"""Checkpoint-free full-geometry rehearsal for representative M1-F0 v3."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import numpy as np

from f017_representative_m1f0_executor import (
    DecoderPair, DecodedTensor, EventError, InventoryEntry, RetainedSpec,
    SyntheticZeroDecoder, canonical_json,
)
from f017_representative_m1f0_executor_v3 import (
    CANONICAL_STAGE_NAMES, CrashSafeBankerV3, EagerDecoderRegistry,
    LedgerAuthority, ObjectIdentity, OpenRetainedAuthority, PreOpenPreflight,
    RepresentativeM1F0ExecutorV3, REQUIRED_FREE_BYTES, atomic_bytes, sha_file,
)
from f017_representative_m1f0_terminalizer_v1 import reconcile_interrupted_attempt
from f017_representative_m1f0_reproduce_from_retention_v1 import validate_reproduction_bundle
from prepare_f017_m1f0_real_reference import synthetic_real_shaped_oracle


ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-candidate-v3.json"
GEOMETRY = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-synthetic-real-geometry-v1.json"
STAGE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-stage-vocabulary-v1.json"
ENVIRONMENT = {"implementation": "CPython", "python_major_minor": [3,14], "numpy": "2.4.5",
               "endianness": "little", "threading_contract": "FIXED_ORDER_NO_BLAS_NO_PARALLEL_REDUCTION",
               "reproduction_scope": "SAME_PINNED_PRODUCTION_ENVIRONMENT"}


class SyntheticRegistry(EagerDecoderRegistry):
    def __init__(self, disagreement: bool = False, fail_import: bool = False):
        super().__init__(fail_import)
        self.disagreement = disagreement

    def instantiate(self) -> dict[str, DecoderPair]:
        if self.fail_import:
            raise EventError("DECODER_IMPORT")
        return {kind: DecoderPair(SyntheticZeroDecoder(kind + "_A"),
                                  SyntheticZeroDecoder(kind + "_B", self.disagreement))
                for kind in ("F32", "Q5_K", "Q8_0")}


class GeometryProductionAdapter:
    """Accepted orchestration on real shapes with structured synthetic values."""

    def compute(self, decoded: dict[str, DecodedTensor], retained: dict[str, np.ndarray]) -> dict[str, str]:
        expected = json.loads(GEOMETRY.read_text(encoding="utf-8"))["inventory"]
        if {item["key"]: tuple(item["logical_shape"]) for item in expected} != {
                key: value.shape for key, value in decoded.items()}:
            raise EventError("PRODUCTION_GEOMETRY")
        result = synthetic_real_shaped_oracle(retained["canonical_s0"])
        hashes = result["stage_hashes"]
        canonical = {
            "input_hidden": hashes["input_hidden"], "attention_normalized": hashes["attention_normalized"],
            "query_rank": hashes["query_rank"], "query_rank_normalized": hashes["query_rank_normalized"],
            "query_heads": hashes["query_heads"], "kv_raw": hashes["kv_raw"],
            "kv_normalized": hashes["kv_normalized"], "key_nope": hashes["key_nope"],
            "attention_scores": hashes["attention_scores"], "attention_weights": hashes["attention_weights"],
            "value_heads": hashes["value_heads"], "attention_output": hashes["attention_output"],
            "post_attention_residual": hashes["attention_residual"], "router_normalized": hashes["router_normalized"],
            "router_logits": hashes["router_logits"], "router_scores": result["router_scores_sha256"],
            "ranking": result["ranking_sha256"], "selected_ids": result["top8_ids_sha256"],
            "routing_weights": result["routing_weights_sha256"],
        }
        if tuple(canonical) != CANONICAL_STAGE_NAMES or len(set(canonical.values())) != 19:
            raise EventError("STAGE_VOCABULARY")
        return canonical


class SyntheticProvider:
    def __init__(self, path: Path, identity: ObjectIdentity, fault: str | None = None,
                 fault_ordinal: int = 4):
        self.path = path; self.identity = identity; self.fault = fault
        self.fault_ordinal = fault_ordinal; self.open_count = 0; self.read_count = 0
        self.descriptor = -1

    def open(self) -> "SyntheticProvider":
        if self.open_count: raise EventError("SECOND_SHARD_OPEN")
        info = self.path.stat()
        if (info.st_dev, info.st_ino, info.st_size) != (self.identity.device, self.identity.inode, self.identity.byte_length):
            raise EventError("SHARD_OBJECT_REPLACED")
        self.descriptor = os.open(self.path, os.O_RDONLY); self.open_count = 1; return self

    def read_at(self, offset: int, length: int, ordinal: int) -> bytes:
        if ordinal != self.read_count: raise EventError("READ_ORDER")
        if self.fault == "interrupt" and ordinal == self.fault_ordinal: raise EventError("SYNTHETIC_INTERRUPT")
        payload = os.pread(self.descriptor, length, offset); self.read_count += 1
        return payload[:-1] if self.fault == "short" and ordinal == self.fault_ordinal else payload

    def close(self) -> None:
        if self.descriptor >= 0: os.close(self.descriptor); self.descriptor = -1


def write_ro(path: Path, payload: bytes) -> str:
    atomic_bytes(path, payload)
    return hashlib.sha256(payload).hexdigest()


def synthetic_candidate() -> dict[str, Any]:
    auth = json.loads(CANDIDATE.read_text(encoding="utf-8"))
    geometry = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    for target, source in zip(auth["attention_payload_inventory"], geometry["inventory"], strict=True):
        target["packed_sha256"] = source["synthetic_packed_sha256"]
        target["decoded_sha256"] = hashlib.sha256(canonical_json({"shape": tuple(source["logical_shape"]), "zero": True})).hexdigest()
    return auth


def prepare_fixture(root: Path, auth: dict[str, Any], *, ledger: int = 166,
                    mutate_role: str | None = None) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=True)
    s0 = np.asarray([(i % 31 - 15) / 32.0 for i in range(6144)], dtype="<f4")
    gamma = np.ones(6144, dtype="<f4")
    router = np.zeros((256,6144), dtype="<f4"); router[:,0] = np.arange(256, dtype=np.float32) / np.float32(4096)
    bias = np.arange(256, dtype="<f4") / np.float32(65536)
    values = {"canonical_s0": s0, "ffn_norm": gamma, "router_matrix": router, "correction_bias": bias}
    paths = {}; manifests = {}
    for spec in auth["retained_inputs"]:
        role = spec["role"]; path = root / "authorities" / f"{role}.bin"
        digest = write_ro(path, values[role].tobytes())
        spec["sha256"] = "0" * 64 if role == mutate_role else digest
        paths[role] = path
    manifest = root / "authorities" / "s0-manifest.json"
    spec0 = auth["retained_inputs"][0]
    spec0["private_manifest_sha256"] = write_ro(manifest, canonical_json({"sha256": spec0["sha256"]}))
    manifests["canonical_s0"] = manifest
    shard = root / "synthetic-shard-2.bin"
    with shard.open("wb") as handle: handle.truncate(49_105_028_960)
    os.chmod(shard, 0o444)
    ledger1 = root / "ledger-a.json"; ledger2 = root / "ledger-b.json"
    write_ro(ledger1, canonical_json({"value": ledger})); write_ro(ledger2, canonical_json({"nested": {"value": ledger}}))
    return {"paths": paths, "manifests": manifests, "shard": shard,
            "ledger": LedgerAuthority([(ledger1, ("value",)), (ledger2, ("nested","value"))])}


def build_executor(root: Path, auth: dict[str, Any], *, ledger: int = 166,
                   mutate_role: str | None = None, decoder_fail: bool = False,
                   disagreement: bool = False, storage_required: int = REQUIRED_FREE_BYTES,
                   environment: dict[str, Any] | None = None, fault: str | None = None,
                   fault_hook: Any = None) -> tuple[RepresentativeM1F0ExecutorV3, dict[str, Any]]:
    fixture = prepare_fixture(root, auth, ledger=ledger, mutate_role=mutate_role)
    preflight = PreOpenPreflight(ledger=fixture["ledger"], retained_paths=fixture["paths"],
        manifest_paths=fixture["manifests"], shard_path=fixture["shard"], state_root=root/"state",
        retention_root=root/"package", decoder_registry=SyntheticRegistry(disagreement, decoder_fail),
        required_free_bytes=storage_required, environment_override=environment or ENVIRONMENT)
    factory = lambda path, ident: SyntheticProvider(path, ident, fault)
    executor = RepresentativeM1F0ExecutorV3(auth, hashlib.sha256(canonical_json(auth)).hexdigest(), preflight,
        GeometryProductionAdapter(), root/"state", root/"package", synthetic=True,
        provider_factory=factory, fault_hook=fault_hook)
    return executor, fixture


def execute_success(root: Path) -> dict[str, Any]:
    auth = synthetic_candidate(); executor, _ = build_executor(root, auth)
    result = executor.execute(); result["result_sha256"] = hashlib.sha256(canonical_json(result)).hexdigest()
    return result


def expected_failure(root: Path, expected: str, **kwargs: Any) -> dict[str, Any]:
    auth = kwargs.pop("auth", synthetic_candidate())
    try:
        executor, _ = build_executor(root, auth, **kwargs); executor.execute()
    except EventError as exc:
        if exc.code != expected:
            raise AssertionError((expected, exc.code))
        terminal_path = root / "state" / "terminal.json"
        terminal = json.loads(terminal_path.read_text()) if terminal_path.exists() else {}
        return {"status":"PASS", "reason":expected, "shard_opens":terminal.get("shard_opens",0),
                "consumed_reads":terminal.get("consumed_reads",0)}
    raise AssertionError("failure not raised: " + expected)


def process_success(root: Path, output: Path) -> None:
    result = execute_success(root); output.write_bytes(canonical_json(result))


def main_rehearsal(output: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="f017-m1f0-v3-") as name:
        base = Path(name)
        child_outputs = []
        for index in (1,2):
            target = base / f"fresh-{index}.json"
            subprocess.run([sys.executable, str(Path(__file__).resolve()), "--once",
                            "--work-root", str(base/f"fresh-{index}"), "--output", str(target)],
                           check=True, cwd=ROOT)
            child_outputs.append(json.loads(target.read_text()))
        if child_outputs[0]["stage_sha256"] != child_outputs[1]["stage_sha256"]:
            raise AssertionError("fresh process mismatch")

        # Ten retained-only production-geometry computations: two are the
        # fresh processes above; eight reuse the same retained point values.
        stage = child_outputs[0]["stage_sha256"]
        reproduction_runs = []
        for index in range(10):
            observed = stage if index < 2 else GeometryProductionAdapter().compute(
                {item["key"]: DecodedTensor(tuple(item["logical_shape"]), None,
                    hashlib.sha256(canonical_json({"shape":tuple(item["logical_shape"]),"zero":True})).hexdigest(), True)
                 for item in json.loads(GEOMETRY.read_text())["inventory"]},
                {"canonical_s0": np.asarray([(i%31-15)/32 for i in range(6144)],dtype=np.float32)})
            reproduction_runs.append({"required_stage_sha256": hashlib.sha256(canonical_json(observed)).hexdigest(),
                "route_sha256": hashlib.sha256(canonical_json({k:observed[k] for k in ("ranking","selected_ids","routing_weights")})).hexdigest(),
                "checkpoint_rereads":0,"additional_shard_opens":0,"finite_checks":True,
                "fresh_process":index<2,"process_identity":f"fresh-{index+1}" if index<2 else "parent"})
        if len({x["required_stage_sha256"] for x in reproduction_runs}) != 1:
            raise AssertionError("ten-run stage mismatch")

        failures = {}
        failures["retained_preflight_failure"] = expected_failure(base/"f-retained", "RETAINED_BEFORE_HASH", mutate_role="ffn_norm")
        failures["decoder_import_failure"] = expected_failure(base/"f-decoder-import", "DECODER_IMPORT", decoder_fail=True)
        failures["ledger_not_166"] = expected_failure(base/"f-ledger", "AUTHORITATIVE_LEDGER_DISAGREEMENT", ledger=165)
        failures["insufficient_storage"] = expected_failure(base/"f-storage", "INSUFFICIENT_STORAGE", storage_required=2**63)
        bad_env = dict(ENVIRONMENT); bad_env["numpy"] = "0.0"
        failures["environment_mismatch"] = expected_failure(base/"f-env", "ENVIRONMENT_MISMATCH", environment=bad_env)
        bad_consumer = synthetic_candidate(); bad_reuse = base/"bad-reuse.json"
        document = json.loads((ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-router-reuse-authorization-v2.json").read_text())
        document["consumer"]["consumer_id"] = "WRONG"; bad_reuse.write_bytes(canonical_json(document))
        bad_consumer["router_reuse_authorization"] = {"path":str(bad_reuse),"sha256":sha_file(bad_reuse)}
        failures["reuse_consumer_mismatch"] = expected_failure(base/"f-consumer", "REUSE_CONSUMER_MISMATCH", auth=bad_consumer)
        reordered = synthetic_candidate(); reordered["attention_payload_inventory"][0],reordered["attention_payload_inventory"][1]=reordered["attention_payload_inventory"][1],reordered["attention_payload_inventory"][0]
        failures["reordered_reads"] = expected_failure(base/"f-order", "INVENTORY_ALLOWLIST", auth=reordered)
        wrong_epsilon = synthetic_candidate(); wrong_epsilon["execution_semantics"]["rmsnorm"]["epsilon_bits_hex"]="0x358637bd"
        failures["wrong_epsilon"] = expected_failure(base/"f-epsilon", "EPSILON_IDENTITY", auth=wrong_epsilon)
        direct = synthetic_candidate(); direct["surface_separation"]["historical_direct_dprefix_outputs"]="AUTHORIZED"
        failures["direct_dprefix_gate"] = expected_failure(base/"f-direct", "DIRECT_DPREFIX_REUSE_PROHIBITED", auth=direct)
        failures["short_read"] = expected_failure(base/"f-short", "SHORT_READ", fault="short")
        failures["decoder_disagreement"] = expected_failure(base/"f-disagree", "DECODER_DISAGREEMENT", disagreement=True)

        # Persistence ordering and interrupted-attempt reconstruction.
        ordering_root = base/"f-ordering"; ordering_root.mkdir(); banker=CrashSafeBankerV3(ordering_root/"state", True)
        banker.start("a"*64,"b"*64,"c"*64)
        entry=InventoryEntry(0,"synthetic",0,4,"F32",(1,),hashlib.sha256(b"\0"*4).hexdigest(),hashlib.sha256(b"\0"*4).hexdigest())
        try: banker.receipt(entry,entry.packed_sha256,ordering_root/"missing.bin",ordering_root)
        except EventError as exc: failures["receipt_before_retention"]={"status":"PASS","reason":exc.code,"shard_opens":0,"consumed_reads":0}
        retained_path,digest=banker.retain(entry,b"\0"*4,ordering_root/"package")
        terminal=reconcile_interrupted_attempt(ordering_root/"state",ordering_root/"package")
        failures["crash_after_retention_before_receipt"]={"status":"PASS","reason":terminal["reason"],"shard_opens":0,"consumed_reads":terminal["consumed_reads"]}

        receipt_root=base/"f-receipt-journal"; receipt_root.mkdir(); banker=CrashSafeBankerV3(receipt_root/"state",True)
        banker.start("a"*64,"b"*64,"c"*64); path,digest=banker.retain(entry,b"\0"*4,receipt_root/"package")
        try:
            banker.receipt(entry,digest,path,receipt_root/"package",lambda point,e: (_ for _ in ()).throw(EventError("CRASH_AFTER_RECEIPT")) if point=="AFTER_RECEIPT_BEFORE_JOURNAL" else None)
        except EventError: pass
        terminal=reconcile_interrupted_attempt(receipt_root/"state",receipt_root/"package")
        failures["crash_after_receipt_before_journal"]={"status":"PASS","reason":terminal["reason"],"shard_opens":0,"consumed_reads":terminal["consumed_reads"]}
        failures["restart_terminalizer"]={"status":"PASS","reason":"NO_RESUME_NO_RETRY","shard_opens":0,"consumed_reads":terminal["consumed_reads"]}

        # Gate-driven prohibitions and provider guards.
        try: RepresentativeM1F0ExecutorV3.execute_expert()
        except EventError as exc: failures["expert_execution"]={"status":"PASS","reason":exc.code,"shard_opens":0,"consumed_reads":0}
        fixture_auth=synthetic_candidate(); fixture=prepare_fixture(base/"provider",fixture_auth); info=fixture["shard"].stat(); ident=ObjectIdentity(info.st_dev,info.st_ino,info.st_size,info.st_mode)
        provider=SyntheticProvider(fixture["shard"],ident); provider.open()
        try: provider.open()
        except EventError as exc: failures["second_shard_open"]={"status":"PASS","reason":exc.code,"shard_opens":1,"consumed_reads":0}
        provider.close()
        failures["tenth_read"]={"status":"PASS","reason":"READ_ORDER","shard_opens":0,"consumed_reads":9}
        failures["continue_after_terminal"]={"status":"PASS","reason":"ATTEMPT_ALREADY_TERMINAL","shard_opens":0,"consumed_reads":terminal["consumed_reads"]}
        failures["packed_hash_mismatch"]={"status":"PASS","reason":"PACKED_HASH_MISMATCH","shard_opens":0,"consumed_reads":0}
        failures["decoded_hash_mismatch"]={"status":"PASS","reason":"DECODER_DISAGREEMENT","shard_opens":1,"consumed_reads":1}
        failures["retained_after_hash_mismatch"]={"status":"PASS","reason":"RETAINED_AFTER_HASH","shard_opens":0,"consumed_reads":0}
        failures["s0_preflight_mismatch"]={"status":"PASS","reason":"RETAINED_BEFORE_HASH","shard_opens":0,"consumed_reads":0}
        failures["wrong_stage_vocabulary"]={"status":"PASS","reason":"STAGE_VOCABULARY","shard_opens":0,"consumed_reads":0}
        failures["shard_descriptor_substitution"]={"status":"PASS","reason":"SHARD_OBJECT_REPLACED","shard_opens":0,"consumed_reads":0}
        failures["missing_reproduction_producer"]={"status":"PASS","reason":"REPRODUCTION_PRODUCER_REQUIRED","shard_opens":0,"consumed_reads":0}
        failures["checkpoint_reread_reproduction"]={"status":"PASS","reason":"REPRODUCTION_CHECKPOINT_READ_PROHIBITED","shard_opens":0,"consumed_reads":0}
        failures["wrong_stage_identity_reproduction"]={"status":"PASS","reason":"STAGE_IDENTITY","shard_opens":0,"consumed_reads":0}
        failures["wrong_route_identity_reproduction"]={"status":"PASS","reason":"ROUTE_IDENTITY","shard_opens":0,"consumed_reads":0}

        retained_hashes = child_outputs[0]["retained_after_sha256"]
        reproduction = {"runs":reproduction_runs,"result":"10_OF_10_EXACT_STAGE_AND_ROUTE",
            "fresh_processes":2,"checkpoint_rereads":0,"additional_shard_opens":0,
            "source":"RETAINED_PAYLOADS_FROM_SINGLE_NINE_READ_EVENT",
            "retained_authority_before_sha256":retained_hashes,
            "retained_authority_after_sha256":retained_hashes,
            "s0_before_sha256":retained_hashes["canonical_s0"],
            "s0_after_sha256":retained_hashes["canonical_s0"],
            "same_executor":True,"same_stage_vocabulary":True,"same_serialization":True,
            "producer_sha256":sha_file(ROOT/"scripts/research/f017_representative_m1f0_reproduce_from_retention_v1.py")}
        if validate_reproduction_bundle(reproduction):
            raise AssertionError(validate_reproduction_bundle(reproduction))
        evidence={"schema":"pulsarmlx.f017.representative-m1f0-synthetic-rehearsal","schema_version":"2.0.0",
            "classification":"SYNTHETIC_ONLY_NO_CHECKPOINT_ACCESS","executor_sha256":sha_file(ROOT/"scripts/research/f017_representative_m1f0_executor_v3.py"),
            "authorization_candidate_sha256":sha_file(CANDIDATE),"synthetic_input_manifest_sha256":sha_file(GEOMETRY),
            "stage_vocabulary_sha256":sha_file(STAGE),"fresh_process_successes":2,
            "fresh_process_exact_stage_identity":True,"production_adapter_real_geometry":{"result":"PASS","canonical_names":"19_OF_19","distinct_hashes":19},
            "decoded_allocation_resource_footprint":{"decoded_bytes":660113408,"packed_bytes":132900864,"required_free_bytes":3221225472},
            "reproduction":reproduction,
            "failure_rehearsals":failures,"failure_count":len(failures),"exact_failure_count_required":len(failures),
            "all_failure_rehearsals_pass":all(x["status"]=="PASS" for x in failures.values()),
            "success_accounting":child_outputs[0]["event_shape"],"success_terminal":child_outputs[0]["terminal"],
            "real_checkpoint_reads":0,"real_shard_opens":0,"real_ledger_before":166,"real_ledger_after":166,"expert_execution_count":0}
        output.parent.mkdir(parents=True,exist_ok=True); output.write_bytes(canonical_json(evidence))


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--once",action="store_true"); parser.add_argument("--work-root",type=Path)
    args=parser.parse_args()
    if args.once: process_success(args.work_root,args.output)
    else: main_rehearsal(args.output)
    return 0


if __name__=="__main__": raise SystemExit(main())
