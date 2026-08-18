#!/usr/bin/env python3
"""Validate the public F017 canonical expert-output recovery evidence."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
REVIEW = EVIDENCE / "f017-canonical-expert-output-recovery-evidence-review-v1.json"
RESULT = EVIDENCE / "f017-canonical-expert-recovery-result-v1.json"
LEDGER = EVIDENCE / "f017-real-payload-access-ledger-v1.json"
AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-canonical-expert-output-recovery-v1.json"


def load(path: Path) -> dict:
    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate key: {key}")
            value[key] = item
        return value
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate() -> str:
    review = load(REVIEW)
    result = load(RESULT)
    ledger = load(LEDGER)
    authorization = load(AUTHORIZATION)
    require(review["classification"] == "CANONICAL EXPERT OUTPUT RECOVERY COMPLETE", "classification")
    require(review["release_head"] == "8233396c6aa07ef05474f37db470ff44044ed5cd", "release head")
    require(review["production_contract_sha256"] == "c921bca7f4d42a6e42ae1b4b337bf3baea7e7088d5e442d271ec9838665e19d8", "production contract")
    require(review["public_result"] == {"path": RESULT.relative_to(ROOT).as_posix(), "sha256": digest(RESULT)}, "public result binding")
    require(result["classification"] == "COMPLETE" and result["reason_code"] == "COMPLETE", "terminal result")
    require(review["checkpoint_access"] == {
        "shard_sha256": "d94adaa58ddd5abbcf2514192958084416b1aa36bd4d21409028a164341bac36",
        "shard_open_count": 1, "payload_reads": 24, "packed_bytes": 90_439_680,
    }, "checkpoint totals")
    payloads = review["payloads"]
    inventory = authorization["payload_inventory"]
    require(len(payloads) == len(inventory) == 24, "payload count")
    require(sum(item["packed_bytes"] for item in payloads) == 90_439_680, "packed bytes")
    require(len({item["packed_sha256"] for item in payloads}) == 24, "packed identities")
    for sequence, (payload, inventory_item) in enumerate(zip(payloads, inventory), start=1):
        require(payload["sequence"] == sequence, "payload sequence")
        for key in ("checkpoint_key", "expert_id", "role", "offset", "quantization"):
            require(payload[key] == inventory_item[key], f"payload inventory {key}")
        require(payload["packed_bytes"] == inventory_item["packed_length"], "payload length")
        require(payload["logical_shape"] == inventory_item["logical_decoded_shape"], "payload shape")
        require(payload["exact_agreement"] is True and payload["retained_immutable_read_only"] is True, "payload gates")
        for key in ("packed_sha256", "decoded_sha256", "decoder_a_identity", "decoder_b_identity"):
            require(re.fullmatch(r"[0-9a-f]{64}", payload[key]) is not None, f"payload hash: {key}")
        require(payload["decoder_a_identity"] != payload["decoder_b_identity"], "decoder independence")
    outputs = review["outputs"]
    require([item["expert_id"] for item in outputs] == authorization["selected_expert_ids"], "output IDs")
    require(len(outputs) == 8 and all(item["shape"] == [6144] and item["dtype"] == "f32" and item["byte_length"] == 24_576 for item in outputs), "output surfaces")
    require({str(item["expert_id"]): item["sha256"] for item in outputs} == result["output_sha256_by_expert"], "output identities")
    require(review["dual_decoder"] == {"agreement_count": 24, "required_count": 24, "result": "PASS"}, "dual decoder")
    require(review["reproduction"] == {"fresh_processes": 2, "exact_outputs": 8, "required_outputs": 8, "result": "PASS"}, "reproduction")
    require(review["ledger"] == {"before": 139, "after": 163, "delta": 24, "reconciled": True}, "review ledger")
    require(ledger["cumulative_tensor_payloads"] == 163, "current ledger")
    events = [item for item in ledger["events"] if item["attempt"] == review["attempt_id"]]
    require(len(events) == 1 and events[0]["tensor_payload_count"] == 24 and events[0]["cumulative_tensor_payloads_after_event"] == 163, "ledger event")
    require(review["aggregate_evaluation"] is False and review["automatic_retry"] is False and review["second_attempt_authorized"] is False, "scope")
    require(review["historical_immutability"]["route_disposition"] == "ROUTE NOT PROVEN INVARIANT", "route disposition")
    public = REVIEW.read_text() + RESULT.read_text()
    require(not re.search(r"(?:/Users/|/home/|file://|\.pulsarmlx-local)", public), "private path leak")
    return digest(REVIEW)


def main() -> int:
    print(validate())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
