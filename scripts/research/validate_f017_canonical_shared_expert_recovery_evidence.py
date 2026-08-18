#!/usr/bin/env python3
"""Validate public shared-expert recovery evidence and ledger binding."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
REVIEW = EVIDENCE / "f017-canonical-shared-expert-recovery-evidence-review-v1.json"
RESULT = EVIDENCE / "f017-canonical-shared-expert-recovery-result-v1.json"
LEDGER = EVIDENCE / "f017-real-payload-access-ledger-v1.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(), object_pairs_hook=lambda pairs: _unique(pairs))


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate() -> str:
    review, result, ledger = load(REVIEW), load(RESULT), load(LEDGER)
    require(review["classification"] == "CANONICAL SHARED EXPERT RECOVERY COMPLETE", "classification")
    require(review["release_head"] == "71d341117022c719fe3a51d350b84b21b073da5c", "release head")
    require(review["public_result"] == {"path": RESULT.relative_to(ROOT).as_posix(), "sha256": digest(RESULT)}, "result binding")
    require(result["classification"] == result["reason_code"] == "COMPLETE", "terminal result")
    require(review["checkpoint_access"] == {"shard_sha256": "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36", "shard_open_count": 1, "payload_reads": 3, "packed_bytes": 27_623_424}, "access totals")
    require(len(review["payloads"]) == 3 and sum(item["packed_bytes"] for item in review["payloads"]) == 27_623_424, "payloads")
    require([item["quantization"] for item in review["payloads"]] == ["Q5_K", "Q5_K", "Q6_K"], "quantization order")
    require(all(item["exact_agreement"] and item["retained_immutable_read_only"] for item in review["payloads"]), "payload gates")
    for item in review["payloads"]:
        for key in ("packed_sha256", "decoded_sha256", "decoder_a_identity", "decoder_b_identity"):
            require(re.fullmatch(r"[0-9a-f]{64}", item[key]) is not None, f"hash {key}")
        require(item["decoder_a_identity"] != item["decoder_b_identity"], "decoder independence")
    require(review["dual_decoder"]["result"] == "PASS" and review["dual_decoder"]["agreement_count"] == 3, "dual decoder")
    require(review["shared_output"]["sha256"] == result["output"]["output_sha256"], "output")
    require(review["reproduction"] == {"fresh_processes": 2, "exact_outputs": 2, "required_outputs": 2, "result": "PASS"}, "reproduction")
    require(review["ledger"] == {"before": 163, "after": 166, "delta": 3, "reconciled": True}, "review ledger")
    require(ledger["cumulative_tensor_payloads"] == 166, "ledger total")
    events = [item for item in ledger["events"] if item["attempt"] == review["attempt_id"]]
    require(len(events) == 1 and events[0]["tensor_payload_count"] == 3 and events[0]["cumulative_tensor_payloads_after_event"] == 166, "ledger event")
    require(review["complete_layer_v2_evaluation"] is False and review["historical_immutability"]["route_disposition"] == "ROUTE NOT PROVEN INVARIANT", "scope")
    public = REVIEW.read_text() + RESULT.read_text()
    require(not re.search(r"(?:/Users/|/home/|file://|\.pulsarmlx-local)", public), "private path leak")
    return digest(REVIEW)


if __name__ == "__main__":
    print(validate())
