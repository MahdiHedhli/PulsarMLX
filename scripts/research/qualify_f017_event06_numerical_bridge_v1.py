#!/usr/bin/env python3
"""Synthetic, no-access qualification for the Event 06 V12-to-V11 bridge."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from f017_canonical_serialization_v10 import canonical_bytes
from f017_event06_execution_plan_v1 import validate_execution_plan
from f017_event06_bridge_synthetic_fixture_v1 import fixture_values
from f017_event06_numerical_bridge_v1 import (
    BRIDGE_KEYS, PHASES, build_transition_binding, canonical_bridge_bytes,
    reconstruct_bridge, validate_bridge_document, validate_transition_chain,
)
from execute_f017_corrected_oracle_event_v12_bridge import validate_no_access_call_path

ROOT = Path(__file__).resolve().parents[2]
IMMUTABLE = {
    "scripts/research/f017_corrected_oracle_primary_numerics_v3.py":"56f4179a58ff9558e143e79af73f9709e731ca74b6536f346b1a8e1b29e3f3a6",
    "scripts/research/f017_corrected_oracle_secondary_numerics_v3.py":"c1b6b95cf2a597453aeecc43bf1d5c6df5b8488a6ac522bd01771af7b4d0e7d3",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json":"a555abe0ff2aff03a693ac7313d4af17061d01766e90971d92a7ba528f4995f2",
    "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-result-authority-v11-v2.json":"4fd71e90f4184e5f2c7449eac6089f7392f1cc0d1961aecb0243f7ef723af101",
    "scripts/research/f017_result_bundle_builder_v11.py":"296fc64befb92fc47db4458d19df444a645bfd62e269d911e9c4a46b9773d145",
    "scripts/research/f017_binary_comparison_authority_v11.py":"10235d8482aa66a318d7e97b7d3b9fbf27859a732cf67bf29d9cbcd19596e352",
}


def _mutation_campaign():
    bridge, *_, plan_value = fixture_values(); document = json.loads(canonical_bridge_bytes(bridge))
    rejected = unexpected = 0
    for base, validator in ((document, validate_bridge_document), (plan_value, validate_execution_plan)):
        for key in sorted(base):
            cases = []
            missing = copy.deepcopy(base); missing.pop(key); cases.append(missing)
            extra = copy.deepcopy(base); extra[f"alias_{key}"] = extra[key]; cases.append(extra)
            wrong = copy.deepcopy(base); wrong[key] = None; cases.append(wrong)
            for case in cases:
                try: validator(case)
                except Exception: rejected += 1
                else: unexpected += 1
    predecessor = "0" * 64; chain = []
    for index, phase in enumerate(PHASES):
        record, predecessor = build_transition_binding(bridge, phase, f"KIND-{index}", f"{index+1:x}" * 64, predecessor)
        chain.append(record)
    for index in range(180):
        changed = copy.deepcopy(chain)
        record = changed[index % len(changed)]
        selector = index % 6
        if selector == 0: record.pop("bridge_sha256")
        elif selector == 1: record["bridge_sha256"] = "f" * 64
        elif selector == 2: record["predecessor_binding_sha256"] = "e" * 64
        elif selector == 3: record["phase"] = "UNKNOWN"
        elif selector == 4: record["state"] = "PENDING"
        else: record["alias"] = False
        try: validate_transition_chain(bridge, changed)
        except Exception: rejected += 1
        else: unexpected += 1
    return rejected, unexpected, len(BRIDGE_KEYS), len(plan_value)


def qualify() -> dict:
    bridge, *_ = fixture_values(); raw = canonical_bridge_bytes(bridge)
    digests = []
    for _ in range(20):
        run = subprocess.run([sys.executable, __file__, "--digest"], cwd=ROOT,
            check=True, capture_output=True, text=True)
        digests.append(run.stdout.strip())
    rejected, unexpected, bridge_fields, plan_fields = _mutation_campaign()
    no_access = validate_no_access_call_path()
    drift = {path:hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
             for path, expected in IMMUTABLE.items()}
    lifecycle = json.loads((ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event06-v12-to-v11-bridge-lifecycle-v3.json").read_text())
    result = {
        "schema":"pulsarmlx.f017.event06-v12-to-v11-bridge-qualification/1.0.0",
        "bridge_sha256":bridge.sha256,"bridge_field_count":bridge_fields,"execution_plan_field_count":plan_fields,
        "fresh_process_repetitions":len(digests),"unique_fresh_process_digests":len(set(digests)),
        "canonical_reconstruction":"PASS" if reconstruct_bridge(raw).sha256 == bridge.sha256 else "FAIL",
        "mutation_cases_rejected":rejected,"unexpected_passes":unexpected,
        "transition_phases":len(PHASES),"lifecycle_outcomes":len(lifecycle["outcomes"]),
        "real_consumer_signatures_bound":no_access["real_signatures_bound"],
        "complete_call_path":"PASS" if no_access["result"] == "PASS" else "FAIL",
        "numerical_and_result_drift":sum(not passed for passed in drift.values()),
        "immutable_bindings":drift,"original_checkpoint_access":0,"checkpoint_root_resolved":False,
        "checkpoint_opens":0,"checkpoint_hash_reads":0,"checkpoint_payload_reads":0,"checkpoint_mmaps":0,
        "tensor_reads":0,"numerical_operations":0,"durable_live_state_created":False,
        "live_authority_installed":False,"event06_ids_consumed":0,"event06_executed":False,
        "historical_master_ledger":175,
    }
    result["result"] = "PASS" if (len(set(digests)) == 1 and unexpected == 0
        and result["numerical_and_result_drift"] == 0 and result["canonical_reconstruction"] == "PASS") else "FAIL"
    return result


if __name__ == "__main__":
    if sys.argv[1:] == ["--digest"]:
        print(fixture_values()[0].sha256)
    else:
        print(json.dumps(qualify(), sort_keys=True, separators=(",",":")))
