#!/usr/bin/env python3
"""Turn one real-checkpoint stage's raw output into a sanitized evidence record.

The stage runner banks stdout, stderr and host snapshots on the Studio. This
reads those, applies the stage's declared binding check, and emits a record
that carries the measurement and says plainly what it does and does not
establish. It never invents a comparison the stage did not make.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ATTEMPT_2 = ROOT / "docs/architecture/reviews/evidence/f017-native-bounded-p1-real-attempt-02-execution-evidence-v1.json"


def _first_input_token(diagnostics: dict, host_before: str):
    """The stage's first input token, read from evidence rather than inferred.

    The runner banks the exact argv it ran; `--raw-tokens` names the inputs
    outright. A text prompt's ids are not recoverable without the tokenizer,
    and no banked receipt covers a text prompt anyway, so it returns None.
    """
    recorded = diagnostics.get("prompt_token_ids")
    if recorded:
        return recorded[0]
    for line in host_before.splitlines():
        if not line.startswith("argv="):
            continue
        parts = line[len("argv="):].split()
        if "--raw-tokens" in parts:
            value = parts[parts.index("--raw-tokens") + 1]
            return int(value.split(",")[0])
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("--host-before", type=Path, required=True)
    parser.add_argument("--host-after", type=Path, required=True)
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--wall-seconds", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)

    raw = arguments.stderr.read_text().strip()
    diagnostics = json.loads(raw.splitlines()[-1]) if raw else {}
    answer = arguments.stdout.read_bytes()

    banked = json.loads(ATTEMPT_2.read_text())
    expected_token = banked["execution"]["produced_token"]
    expected_logits = banked["numerical"]["full_logits_sha256"]

    generation = diagnostics.get("generation", {})
    positions = generation.get("position_selected_tokens", [])
    digests = generation.get("position_logits_sha256", [])
    # The attempt-2 receipt is a statement about prompt token 9703 at position
    # zero and nothing else. Applying it to a stage that starts from a
    # different token would manufacture a mismatch that means nothing.
    first_input = _first_input_token(diagnostics, arguments.host_before.read_text())
    binding = None
    if positions and digests and first_input == banked["execution"]["prompt_token"]:
        binding = {
            "rule": "position 0 must reproduce the banked attempt-2 one-token result",
            "expected_token": expected_token,
            "observed_token": positions[0],
            "expected_logits_sha256": expected_logits,
            "observed_logits_sha256": digests[0],
            "token_match": positions[0] == expected_token,
            "logits_match": digests[0] == expected_logits,
            "source_of_the_expectation": str(ATTEMPT_2.relative_to(ROOT)),
            "what_this_is": "a comparison against existing evidence produced by a different binary with no authorization, no receipt and no ledger entry; it is not a re-execution of the consumed one-shot",
        }
        binding["result"] = "MATCH" if binding["token_match"] and binding["logits_match"] else "MISMATCH"

    record = {
        "schema": "pulsarmlx.f017.native-real-checkpoint-stage/1.0.0",
        "stage": arguments.stage,
        "exit_code": arguments.exit_code,
        "wall_seconds": arguments.wall_seconds,
        "evidence_status": "SANITIZED_PUBLIC_PROJECTION: token ids, digests, timings and counters only; no weight bytes and no logit vectors",
        "diagnostics": diagnostics,
        "answer_bytes": len(answer),
        "answer_sha256": hashlib.sha256(answer).hexdigest(),
        "answer_text": answer.decode("utf-8", "replace") if len(answer) < 4096 else None,
        "position_zero_binding": binding,
        "position_zero_binding_applicability": (
            "applied: this stage begins from the same prompt token the banked one-shot used"
            if binding else
            "not applicable: the banked receipt is a statement about prompt token "
            f"{banked['execution']['prompt_token']} at position zero, and this stage begins from a different token"),
        "host_before_sha256": hashlib.sha256(arguments.host_before.read_bytes()).hexdigest(),
        "host_after_sha256": hashlib.sha256(arguments.host_after.read_bytes()).hexdigest(),
        "qualified": {
            "position_zero": "compared against banked evidence" if binding else "no banked comparison exists for this prompt",
            "later_positions": "MEASURED_NOT_QUALIFIED: no independent multi-token oracle exists for the real checkpoint, and the rope pairing is still a declared parameter",
        },
        "not_claimed": [
            "numerical qualification of positions after 0 on the real checkpoint",
            "the rope pairing of the real checkpoint",
            "any sustained throughput figure",
            "answer quality",
            "readiness for deployment",
        ],
    }
    arguments.output.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"stage": arguments.stage, "exit_code": arguments.exit_code,
                      "binding": binding and binding["result"],
                      "positions": len(positions)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
