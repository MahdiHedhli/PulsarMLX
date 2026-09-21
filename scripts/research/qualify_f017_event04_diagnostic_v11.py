#!/usr/bin/env python3
"""Ten isolated, non-authoritative Event 04 diagnostic conversions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]

from f017_event04_diagnostic_converter_v11 import convert, EXPECTED_BYTES, EXPECTED_SHA256


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = ROOT / "docs/architecture/reviews/evidence/f017-event04-v10-terminal-package-v1/package-evidence/primary-consumer-output.json"
    grant_path = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-event04-result-envelope-diagnostic-reuse-grant-v11.json"
    grant = json.loads(grant_path.read_text())
    payload_shas = []
    for _ in range(10):
        with tempfile.TemporaryDirectory() as temporary:
            result = convert(raw, Path(temporary), grant)
            if (result["event04_promotion"] != "PROHIBITED"
                    or result["event04_receipt_created"] is not False
                    or result["event04_terminal_created"] is not False):
                raise ValueError("Event 04 promotion boundary")
            payload_shas.append(result["payload"]["sha256"])
    if len(set(payload_shas)) != 1:
        raise ValueError("diagnostic conversion determinism")
    result = {
        "schema":"pulsarmlx.f017.event04-result-envelope-diagnostic-qualification/11.0.0",
        "grant_path":str(grant_path.relative_to(ROOT)),
        "raw_artifact_available":True,
        "raw_output_size":EXPECTED_BYTES,
        "raw_output_sha256":EXPECTED_SHA256,
        "converted_full_logits_element_count":154_880,
        "converted_full_logits_sha256":payload_shas[0],
        "fresh_conversion_repetitions":10,
        "stable_payload_shas":len(set(payload_shas)),
        "final_hidden":"UNAVAILABLE_SOURCE_CONTAINS_HASH_ONLY",
        "final_normalized":"UNAVAILABLE_SOURCE_CONTAINS_HASH_ONLY",
        "event04_receipt_created":False,
        "event04_terminal_created":False,
        "promotion":"PROHIBITED",
        "original_checkpoint_access":0,
        "result":"PASS",
    }
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(encoded)
    else: print(encoded, end="")
    return 0


if __name__ == "__main__": raise SystemExit(main())
