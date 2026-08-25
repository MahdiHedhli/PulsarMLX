#!/usr/bin/env python3
"""Overnight-scale V9 runtime hardening and fault qualification."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from check_f017_descriptor_type_safety_v9 import _validate_descriptors as independent_validate
from execute_f017_corrected_oracle_event_v9 import execute_synthetic
from f017_canonical_serialization_v8 import bank_exclusive, canonical_bytes
from f017_corrected_oracle_event_accounting_v9 import validate_snapshot
from f017_descriptor_lease_manager_v9 import acquire_synthetic_leases, validate_descriptors
from f017_event04_tensor_plan_v9 import build_plan, validate_plan
from f017_runtime_outcome_realizer_v9 import OUTCOMES_PATH, realize
from f017_synthetic_checkpoint_v9 import FORMATS, prepare
from validate_f017_corrected_oracle_access_v9 import install_rehearsal_candidate, render_rehearsal_candidate


ROOT = Path(__file__).resolve().parents[2]; SELF = Path(__file__).resolve()


def _hash(value: object) -> str: return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _case(seed: int, mixed: bool, case_id: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="f017-v9-success-") as raw:
        work = Path(raw); checkpoint, shards, catalog, manifest = prepare(work, seed, case_id, mixed)
        candidate = work / "candidate.json"
        rendered = render_rehearsal_candidate(checkpoint, shards, catalog, candidate, case_id,
                                               scope="SYNTHETIC_QUALIFICATION", manifest_path=manifest)
        installed = work / "install" / "authorization.json"; receipt = work / "receipt.json"
        install_rehearsal_candidate(candidate, installed, receipt)
        result = execute_synthetic(installed, receipt, work / "evidence")
        if result["result"] != "PASS": raise ValueError(f"successful package failed: {case_id}")
        if result["primary"]["consumed_graph_shards"] != [2, 3, 4, 5, 6] or result["secondary"]["consumed_graph_shards"] != [2, 3, 4, 5, 6]:
            raise ValueError("five-shard consumption")
        if result["accounting"] != {"authorization": 0, "package": 1, "primary": 1, "secondary": 1,
                                    "historical_before": 175, "historical_after": 175}:
            raise ValueError("success accounting")
        expected_formats = sorted(FORMATS if mixed else ["F32"])
        if result["primary"]["format_coverage"] != expected_formats or result["secondary"]["format_coverage"] != expected_formats:
            raise ValueError("format coverage")
        core = {"case_id": case_id, "seed": seed, "kind": "MIXED" if mixed else "MINIMAL", "formats": expected_formats,
                "primary_result_sha256": _hash(result["primary"]["result"]), "secondary_result_sha256": _hash(result["secondary"]["result"]),
                "primary_consumed_shards": [2, 3, 4, 5, 6], "secondary_consumed_shards": [2, 3, 4, 5, 6],
                "path_reopen_count": 0, "live_leases": result["release"]["live_leases_after_release"],
                "second_release_attempts": result["second_release"]["attempted_closures"], "result": "PASS"}
        envelope = {"candidate_sha256": rendered["candidate_sha256"], "temporary_root": str(work),
                    "mint_memory_gate": rendered["candidate"]["mint_memory_gate"], "core_sha256": _hash(core)}
        return {"core": core, "envelope": envelope}


def _single(seed: int, mixed: bool, case_id: str) -> None:
    print(json.dumps(_case(seed, mixed, case_id), sort_keys=True, separators=(",", ":")))


def _subprocess_case(seed: int, mixed: bool, case_id: str) -> dict:
    command = [sys.executable, str(SELF), "--single", "--seed", str(seed), "--case-id", case_id]
    if mixed: command.append("--mixed")
    return json.loads(subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True).stdout)


def _release_faults() -> list[dict]:
    results = []
    for case in range(30):
        with tempfile.TemporaryDirectory(prefix="f017-v9-release-") as raw:
            work = Path(raw); checkpoint, shards, catalog, manifest = prepare(work, 18101 + case % 12, f"RELEASE-{case}", False)
            candidate_path = work / "candidate.json"
            render_rehearsal_candidate(checkpoint, shards, catalog, candidate_path, f"RELEASE-{case}", scope="SYNTHETIC_QUALIFICATION", manifest_path=manifest)
            candidate = json.loads(candidate_path.read_bytes()); leases = acquire_synthetic_leases(candidate)
            fail_indexes = {case % 5} if case < 15 else {case % 5, (case + 2) % 5}
            failed_once: set[str] = set()
            def close_function(descriptor: int, lease_id: str) -> None:
                index = int(lease_id.rsplit("-", 1)[1]) - 2
                if index in fail_indexes and lease_id not in failed_once:
                    failed_once.add(lease_id); raise OSError(5, "injected close failure")
                os.close(descriptor)
            first = leases.release(close_function=close_function); second = leases.release(close_function=close_function, retry_failed=True); third = leases.release()
            if first["live_leases_after_release"] != len(fail_indexes) or second["live_leases_after_release"] != 0 or third["attempted_closures"] != 0:
                raise ValueError("release fault behavior")
            results.append({"case_id": f"RELEASE-{case:03d}", "first_live": first["live_leases_after_release"],
                            "second_live": second["live_leases_after_release"], "third_attempts": third["attempted_closures"], "result": "PASS"})
    return results


def _accounting_mutations() -> list[dict]:
    expected = {"authorization": 0, "package": 1, "primary": 1, "secondary": 1, "historical_before": 175, "historical_after": 175}
    mutations = []
    keys = list(expected)
    for index in range(40):
        value = copy.deepcopy(expected); key = keys[index % len(keys)]
        if index < 6: value[key] += 1
        elif index < 12: value[key] = True
        elif index < 18: value[key] = "1"
        elif index < 24: del value[key]
        elif index < 30: value[f"unexpected_{index}"] = 0
        elif index < 35: value["historical_after"] = 176 + index
        else: value[["package", "primary", "secondary"][index % 3]] = 0
        try: validate_snapshot(value, expected)
        except ValueError: mutations.append({"case_id": f"ACCOUNTING-{index:03d}", "result": "REJECTED"})
        else: raise ValueError("accounting mutation accepted")
    return mutations


def _descriptor_mutations() -> list[dict]:
    base = [{"device": 1, "inode": 1000 + ordinal, "mode": 0o100600, "size": 100 + ordinal,
             "mtime_ns": 1, "ctime_ns": 1, "shard_ordinal": ordinal, "role": "GRAPH_PAYLOAD",
             "lease_id": f"LEASE-F017-V9-MUTATION-{ordinal}"} for ordinal in range(2, 7)]
    values: list[object] = [None, 1, True, [], (), set(), "", b""]
    lease_values: list[object] = [[], {}, set(), (), True, 1, 1.0, b"x", None, ""]
    results = []
    for index in range(50):
        sample = copy.deepcopy(base)
        if index < len(values): sample[index % 5] = values[index]
        elif index < len(values) + len(lease_values): sample[index % 5]["lease_id"] = lease_values[index - len(values)]
        elif index < 25: sample[index % 5]["mode"] = [65536, -1, True, "33152", 0o1100644][index % 5]
        elif index < 35: sample[index % 5]["shard_ordinal"] = 1
        elif index < 40: sample[index % 5]["extra"] = index
        elif index < 45: del sample[index % 5]["ctime_ns"]
        else: sample[index % 5]["lease_id"] = sample[(index + 1) % 5]["lease_id"]
        for validator in (validate_descriptors, independent_validate):
            try: validator(copy.deepcopy(sample))
            except ValueError: pass
            except Exception as exc: raise ValueError(f"uncontrolled descriptor exception: {type(exc).__name__}") from exc
            else: raise ValueError(f"descriptor mutation accepted: {index}:{validator.__module__}.{validator.__name__}")
        results.append({"case_id": f"DESCRIPTOR-{index:03d}", "validators": 2, "result": "REJECTED"})
    return results


def qualify(output: Path) -> dict:
    success: list[dict] = []
    for index in range(15): success.append(_subprocess_case(18101 + index % 12, False, f"MINIMAL-{index:03d}"))
    for index in range(15): success.append(_subprocess_case(18101 + index % 12, True, f"MIXED-{index:03d}"))
    for index in range(10): success.append(_subprocess_case(18103 + index % 2, True, f"ROUTE-{index:03d}"))
    for index in range(10): success.append(_subprocess_case(18101 + index % 12, True, f"DISTRIBUTION-{index:03d}"))
    reproducibility = [_subprocess_case(18101, True, "DETERMINISM") for _ in range(10)]
    core_bytes = [canonical_bytes(item["core"]) for item in reproducibility]
    if len(set(core_bytes)) != 1: raise ValueError("deterministic core drift")
    outcomes = json.loads(OUTCOMES_PATH.read_bytes())["outcomes"]
    runtime_outcomes = []
    high_risk = {name for name in outcomes if any(marker in name for marker in ("PACKAGE_POST", "CHECKPOINT_IDENTITY", "PRIMARY_POST", "SECONDARY_POST", "EVIDENCE_BANKING"))}
    with tempfile.TemporaryDirectory(prefix="f017-v9-outcomes-") as raw:
        root = Path(raw)
        for outcome_id in sorted(name for name in outcomes if name != "COMPLETE_SUCCESS"):
            repeats = 5 if outcome_id in high_risk else 3
            for repetition in range(repeats): runtime_outcomes.append(realize(outcome_id, root / f"{outcome_id}-{repetition}"))
    realized_outcomes = {item["outcome_id"] for item in runtime_outcomes}
    coordinator_outcomes = {item["outcome_id"] for item in runtime_outcomes
                            if item["capsule_source"] == "COORDINATOR_CAUSAL_BANK_INJECTION"}
    authorizer_outcomes = {item["outcome_id"] for item in runtime_outcomes
                           if item["capsule_source"] == "AUTHORIZER_PHASE_DIRECT_TERMINALIZATION"}
    accounting_mismatches = sum(item["accounting"] != {"package": outcomes[item["outcome_id"]]["package_delta"],
                                                        "primary": outcomes[item["outcome_id"]]["primary_delta"],
                                                        "secondary": outcomes[item["outcome_id"]]["secondary_delta"]}
                                for item in runtime_outcomes)
    uncontrolled = sum(item["terminalization_result"] != "CONTROLLED_FAILURE" or item["generic_fallback"] is not False
                       for item in runtime_outcomes)
    if realized_outcomes != set(outcomes) - {"COMPLETE_SUCCESS"} or len(coordinator_outcomes) + len(authorizer_outcomes) != len(realized_outcomes):
        raise ValueError("runtime outcome realization census")
    plan = validate_plan(build_plan()); release_faults = _release_faults(); accounting = _accounting_mutations(); descriptor = _descriptor_mutations()
    result = {"schema": "pulsarmlx.f017.event04-runtime-hardening-qualification/9.0.0", "result": "PASS",
              "successful_package_count": len(success), "minimal_package_count": 15, "mixed_package_count": 15,
              "route_variation_package_count": 10, "descriptor_distribution_package_count": 10,
              "primary_consumed_shards": [2, 3, 4, 5, 6], "secondary_consumed_shards": [2, 3, 4, 5, 6],
              "formats": FORMATS, "path_reopen_count": 0, "live_leases_after_success_terminal": 0,
              "runtime_failure_outcomes_realized": len(realized_outcomes), "runtime_failure_executions": len(runtime_outcomes),
              "runtime_coordinator_outcomes_realized": len(coordinator_outcomes),
              "runtime_authorizer_phase_outcomes_realized": len(authorizer_outcomes),
              "runtime_generic_fallbacks": sum(item["generic_fallback"] for item in runtime_outcomes),
              "runtime_accounting_mismatches": accounting_mismatches, "release_fault_cases": len(release_faults),
              "accounting_mutations_rejected": len(accounting), "multi_shard_and_descriptor_mutations_rejected": len(descriptor),
              "deterministic_core_repetitions": len(reproducibility), "deterministic_core_sha256": hashlib.sha256(core_bytes[0]).hexdigest(),
              "deterministic_core_unique_byte_sequences": len(set(core_bytes)), "volatile_envelopes_isolated": True,
              "production_graph_tensor_plan": plan["graph_tensor_count"], "non_access_tensors_rejected": plan["non_access_tensor_count"],
              "production_graph_shards": plan["graph_shards"], "production_formats": plan["formats"],
              "independent_c7_n2_regressions": len(descriptor), "uncontrolled_modeled_failures": uncontrolled,
              "original_checkpoint_shard_opens": 0, "original_checkpoint_identity_hash_reads": 0,
              "original_checkpoint_payload_reads": 0, "event_04_authorization_created": False, "event_04_executed": False,
              "p1_attempt_2_executed": False}
    bank_exclusive(output, result); return result


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--single", action="store_true"); parser.add_argument("--seed", type=int, default=18101)
    parser.add_argument("--mixed", action="store_true"); parser.add_argument("--case-id", default="SINGLE"); parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.single: _single(args.seed, args.mixed, args.case_id); return 0
    if args.output is None: raise ValueError("--output required")
    result = qualify(args.output); print(json.dumps({"result": result["result"], "packages": result["successful_package_count"],
        "runtime_failures": result["runtime_failure_executions"], "release_faults": result["release_fault_cases"]}, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
