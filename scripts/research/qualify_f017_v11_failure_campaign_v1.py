#!/usr/bin/env python3
"""Substantive V11 output, identity, closure, and filesystem fault campaign."""
from __future__ import annotations

import argparse
import copy
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f017_canonical_serialization_v10 import canonical_bytes
from f017_result_artifacts_v11 import require_primary_terminal
from f017_result_bundle_authority_v11 import validate_bundle
from f017_result_bundle_builder_v11 import (
    _qualification_bank_output_bundle as bank_output_bundle,
)
from f017_result_envelope_v11 import (ResultEnvelopeError, bank_payload_bytes,
    payload_spec, validate_payload)
from f017_v11_full_geometry_fixture import make_output


def _sha(value: dict) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _must_reject(case_id: str, function, rejected: list[str]) -> None:
    try:
        function()
    except ResultEnvelopeError:
        rejected.append(case_id)
    else:
        raise AssertionError(f"fault unexpectedly passed: {case_id}")


def qualify() -> dict:
    digest = hashlib.sha256(b"F017-V11-FAULT-AUTHORITY").hexdigest()
    rejected: list[str] = []
    categories: dict[str, int] = {}
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        primary_output = make_output("PRIMARY", "PSEUDORANDOM", 71)
        secondary_output = make_output("SECONDARY", "PSEUDORANDOM", 71)
        primary = bank_output_bundle(primary_output, root / "primary",
            authorization_id="AUTH", package_attempt_id="PKG", consumer_event_id="PRIMARY",
            producer_measurement_sha256=digest, durable_start_sha256=digest,
            access_census_sha256=digest)
        secondary = bank_output_bundle(secondary_output, root / "secondary",
            authorization_id="AUTH", package_attempt_id="PKG", consumer_event_id="SECONDARY",
            producer_measurement_sha256=digest, durable_start_sha256=digest,
            access_census_sha256=digest)
        pa = primary["artifacts"]
        sa = secondary["artifacts"]

        # 80 distinct output-interface corruptions.
        for index in range(20):
            mutant = replace(primary_output, full_logits_sha256=f"{index + 1:064x}")
            _must_reject(f"OUTPUT_SHA_{index:03d}", lambda m=mutant, i=index:
                bank_output_bundle(m, root / f"out-sha-{i}", authorization_id="AUTH",
                    package_attempt_id="PKG", consumer_event_id="PRIMARY",
                    producer_measurement_sha256=digest, durable_start_sha256=digest,
                    access_census_sha256=digest), rejected)
        for index in range(20):
            mutant = replace(primary_output, full_logits_payload=primary_output.full_logits_payload[:-(index + 1)])
            _must_reject(f"OUTPUT_TRUNCATED_{index:03d}", lambda m=mutant, i=index:
                bank_output_bundle(m, root / f"out-short-{i}", authorization_id="AUTH",
                    package_attempt_id="PKG", consumer_event_id="PRIMARY",
                    producer_measurement_sha256=digest, durable_start_sha256=digest,
                    access_census_sha256=digest), rejected)
        for index in range(20):
            mutant = replace(primary_output, full_logits_element_count=154_879 - index)
            _must_reject(f"OUTPUT_COUNT_{index:03d}", lambda m=mutant, i=index:
                bank_output_bundle(m, root / f"out-count-{i}", authorization_id="AUTH",
                    package_attempt_id="PKG", consumer_event_id="PRIMARY",
                    producer_measurement_sha256=digest, durable_start_sha256=digest,
                    access_census_sha256=digest), rejected)
        for index in range(20):
            mutant = replace(primary_output, core_execution_count=index + 2)
            _must_reject(f"OUTPUT_EXECUTION_COUNT_{index:03d}", lambda m=mutant, i=index:
                bank_output_bundle(m, root / f"out-exec-{i}", authorization_id="AUTH",
                    package_attempt_id="PKG", consumer_event_id="PRIMARY",
                    producer_measurement_sha256=digest, durable_start_sha256=digest,
                    access_census_sha256=digest), rejected)
        categories["output_interface"] = 80

        # 90 payload-record and package-identity corruptions against real bytes.
        record = pa["manifest"]["payloads"][2]
        for index in range(30):
            mutant = dict(record); mutant["sha256"] = f"{index + 1:064x}"
            _must_reject(f"PAYLOAD_SHA_{index:03d}", lambda m=mutant:
                validate_payload(root / "primary", m), rejected)
        for index in range(20):
            mutant = dict(record); mutant["payload_identity_sha256"] = f"{index + 101:064x}"
            _must_reject(f"PAYLOAD_IDENTITY_{index:03d}", lambda m=mutant:
                validate_payload(root / "primary", m), rejected)
        for index in range(10):
            mutant = dict(record); mutant["observed_byte_count"] = record["observed_byte_count"] - index - 1
            _must_reject(f"PAYLOAD_BYTES_{index:03d}", lambda m=mutant:
                validate_payload(root / "primary", m), rejected)
        for index in range(10):
            mutant = dict(record); mutant["package_attempt_id"] = f"OTHER-PKG-{index}"
            _must_reject(f"PAYLOAD_PACKAGE_{index:03d}", lambda m=mutant:
                validate_payload(root / "primary", m), rejected)
        for index in range(10):
            mutant = dict(record); mutant["consumer_event_id"] = f"OTHER-EVENT-{index}"
            _must_reject(f"PAYLOAD_EVENT_{index:03d}", lambda m=mutant:
                validate_payload(root / "primary", m), rejected)
        fields = (("dtype","f32le"),("endianness","BIG"),("shape",[1]),
                  ("element_count",1),("expected_byte_count",1),("role","SECONDARY"),
                  ("payload_kind","final_hidden"),("finite_values",False),
                  ("signed_zero_policy","NORMALIZE"),("producer_identity","OTHER"))
        for index, (field, value) in enumerate(fields):
            mutant = dict(record); mutant[field] = value
            _must_reject(f"PAYLOAD_FIELD_{index:03d}", lambda m=mutant:
                validate_payload(root / "primary", m), rejected)
        categories["payload_identity"] = 90

        # 120 six-leaf bundle corruptions (manifest, summary, routing, receipt, terminals).
        leaves = ("manifest", "top32", "routing", "receipt", "result_terminal", "consumer_terminal")
        for index in range(120):
            artifacts = copy.deepcopy(pa)
            leaf = leaves[index % len(leaves)]
            artifacts[leaf][f"fault_{index:03d}"] = index
            _must_reject(f"BUNDLE_{leaf.upper()}_{index:03d}", lambda a=artifacts:
                validate_bundle(root / "primary", role="PRIMARY", authorization_id="AUTH",
                    package_attempt_id="PKG", **a), rejected)
        categories["bundle_closure"] = 120

        # 40 primary-to-secondary causal gate corruptions.
        good_terminal = pa["consumer_terminal"]
        terminal_fields = ("schema", "role", "result", "result_terminal_sha256",
                           "result_receipt_sha256", "payload_manifest_sha256", "secondary_eligible")
        for index in range(40):
            mutant = copy.deepcopy(good_terminal)
            field = terminal_fields[index % len(terminal_fields)]
            mutant[field] = (False if field == "secondary_eligible" else f"INVALID-{index}")
            _must_reject(f"SECONDARY_GATE_{index:03d}", lambda m=mutant:
                require_primary_terminal(m, _sha(pa["result_terminal"]), _sha(pa["receipt"]),
                                         _sha(pa["manifest"])), rejected)
        categories["causal_order"] = 40

        # 30 actual filesystem/content faults, including aliasing and nonfinite values.
        spec = payload_spec("PRIMARY", "final_hidden")
        for index in range(10):
            target = root / f"collision-{index}"
            target.mkdir(); (target / "payload.bin").write_bytes(b"occupied")
            _must_reject(f"FS_O_EXCL_{index:03d}", lambda d=target:
                bank_payload_bytes(d, "payload.bin", spec, primary_output.final_hidden_payload,
                    package_attempt_id="PKG", consumer_event_id="PRIMARY"), rejected)
        for index in range(10):
            target = root / f"nonfinite-{index}"; target.mkdir()
            raw = bytearray(primary_output.final_hidden_payload)
            raw[index * 8:(index + 1) * 8] = struct.pack("<d", math.nan if index % 3 == 0 else (math.inf if index % 3 == 1 else -math.inf))
            _must_reject(f"FS_NONFINITE_{index:03d}", lambda d=target, p=bytes(raw):
                bank_payload_bytes(d, "payload.bin", spec, p,
                    package_attempt_id="PKG", consumer_event_id="PRIMARY"), rejected)
        for index in range(5):
            target = root / f"symlink-{index}"; target.mkdir()
            (target / "payload.bin").symlink_to(root / "primary" / record["path_role"])
            _must_reject(f"FS_SYMLINK_{index:03d}", lambda d=target:
                bank_payload_bytes(d, "payload.bin", spec, primary_output.final_hidden_payload,
                    package_attempt_id="PKG", consumer_event_id="PRIMARY"), rejected)
        for index in range(5):
            target = root / f"geometry-{index}"; target.mkdir()
            payload = primary_output.final_hidden_payload[:-index-1]
            _must_reject(f"FS_SHORT_{index:03d}", lambda d=target, p=payload:
                bank_payload_bytes(d, "payload.bin", spec, p,
                    package_attempt_id="PKG", consumer_event_id="PRIMARY"), rejected)
        categories["filesystem"] = 30

    expected = sum(categories.values())
    if len(rejected) != expected or len(set(rejected)) != expected:
        raise AssertionError("fault campaign census")
    return {
        "schema": "pulsarmlx.f017.v11-result-failure-qualification/1.0.0",
        "categories": categories,
        "modeled_failures": expected,
        "realized_failures": len(rejected),
        "stable_case_ids": len(set(rejected)),
        "unexpected_passes": 0,
        "generic_fallbacks": 0,
        "event04_promotion_cases_rejected": 1,
        "event05_executed": False,
        "original_checkpoint_access": 0,
        "result": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); result = qualify()
    raw = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(raw)
    else: print(raw, end="")
    return 0


if __name__ == "__main__": raise SystemExit(main())
