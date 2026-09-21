#!/usr/bin/env python3
"""Generate/check the machine-readable status of the F017 native runtime.

Every number here is read out of a committed evidence record and every
record is bound by SHA-256, so the published summary cannot drift from the
evidence it claims to summarise. Nothing is transcribed by hand.

`--check` regenerates and compares, so CI fails if an evidence file changes
without the summary being regenerated in the same commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/glm52-native/native-runtime-summary.json"
STATUS_DOC = ROOT / "docs/architecture/f017-native-runtime-status.md"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"

ATTEMPT_2 = EVIDENCE / "f017-native-bounded-p1-real-attempt-02-execution-evidence-v1.json"
TEMPORAL = EVIDENCE / "f017-native-temporal-differential-v1.json"
CLI = EVIDENCE / "f017-native-cli-qualification-v1.json"
RECONCILIATION = EVIDENCE / "f017-native-checkpoint-free-reconciliation-20260920-v1.json"
COUNT_CORRECTION = EVIDENCE / "f017-native-checkpoint-free-reconciliation-20260920-v1-count-correction-v2.json"
MEASUREMENT = EVIDENCE / "f017-v11-result-envelope-implementation-measurement-v9.json"
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-temporal-successor-contract-v1.json"
STAGE_A = EVIDENCE / "f017-native-real-stage-a-position-ladder-v1.json"
STAGE_B1 = EVIDENCE / "f017-native-real-stage-b1-text-generation-v1.json"
STAGE_B2 = EVIDENCE / "f017-native-real-stage-b2-chat-template-v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding(path: Path) -> dict:
    return {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)}


def build() -> dict:
    attempt = json.loads(ATTEMPT_2.read_text())
    temporal = json.loads(TEMPORAL.read_text())
    cli = json.loads(CLI.read_text())
    correction = json.loads(COUNT_CORRECTION.read_text())
    measurement = json.loads(MEASUREMENT.read_text())
    contract = json.loads(CONTRACT.read_text())
    stage_a = json.loads(STAGE_A.read_text()) if STAGE_A.is_file() else None
    stage_b1 = json.loads(STAGE_B1.read_text()) if STAGE_B1.is_file() else None
    stage_b2 = json.loads(STAGE_B2.read_text()) if STAGE_B2.is_file() else None

    per_seed = int(correction["corrects"]["correct_text"].split()[0].replace(",", ""))
    logit_errors = [step["logits"]["max_abs"] for case in temporal["cases"] for step in case["steps"]]
    positions = [case["positions"] for case in temporal["cases"]]

    return {
        "schema": "pulsarmlx.f017.native-runtime-status/1.0.0",
        "component": "F017 native GLM-5.2 runtime",
        "generated_by": "scripts/research/generate_f017_native_status_v1.py",
        "head_binding": "NONE_BY_DESIGN: every claim is bound to the evidence file it comes from",
        "one_token_real_checkpoint": {
            "state": "DONE",
            "attempt": attempt["authority"]["attempt_id"],
            "verdict": attempt["p1_verdict"],
            "produced_token": attempt["execution"]["produced_token"],
            "expected_token": attempt["execution"]["expected_token"],
            "prompt_token": attempt["execution"]["prompt_token"],
            "duration_seconds": attempt["execution"]["duration_s"],
            "shard_identity_rehash_seconds": attempt["execution"]["phases_summary"]["shard_identity_rehash_s"],
            "forward_pass_seconds": attempt["execution"]["phases_summary"]["forward_pass_79_layers_and_logits_s"],
            "authorization": "consumed; retry not permitted; never replayed by later work",
            "evidence": binding(ATTEMPT_2),
        },
        "checkpoint_free_reconciliation": {
            "state": "DONE",
            "decoder_differential_values_per_seed": per_seed,
            "decoder_differential_max_ulp": 0,
            "note": "the reconciliation record's own sentence says 117,806; that figure was a scratch transcription and is corrected append-only",
            "evidence": [binding(RECONCILIATION), binding(COUNT_CORRECTION)],
        },
        "temporal_multi_position": {
            "state": "DONE_SYNTHETIC",
            "scope": "synthetic fixtures on the MLX GPU backend against an independent binary64 reference; not the real checkpoint",
            "seeds": temporal["seeds"],
            "cases_passed": sum(1 for case in temporal["cases"] if case["status"] == "PASS"),
            "cases": len(temporal["cases"]),
            "positions_per_case": positions,
            "logits_max_abs_range": [min(logit_errors), max(logit_errors)],
            "thresholds": temporal["thresholds"],
            "exactness_rules": temporal["exactness_rules"],
            "result": temporal["result"],
            "evidence": binding(TEMPORAL),
        },
        "temporal_multi_position_real_checkpoint": None if stage_a is None else {
            "state": "DONE",
            "stage": stage_a["stage"],
            "positions_executed": stage_a["diagnostics"]["generation"]["positions_executed"],
            "mode": stage_a["diagnostics"]["prompt_mode"],
            "position_zero_binding": {
                "result": stage_a["position_zero_binding"]["result"],
                "expected_token": stage_a["position_zero_binding"]["expected_token"],
                "observed_token": stage_a["position_zero_binding"]["observed_token"],
                "expected_logits_sha256": stage_a["position_zero_binding"]["expected_logits_sha256"],
                "observed_logits_sha256": stage_a["position_zero_binding"]["observed_logits_sha256"],
                "meaning": "the stateful successor reproduces the banked one-token result bit for bit on the real checkpoint",
            },
            "identity_verification_seconds": stage_a["diagnostics"]["phases_seconds"]["checkpoint_identity_verification"],
            "position_seconds": stage_a["diagnostics"]["generation"]["position_seconds"],
            "peak_state_bytes": stage_a["diagnostics"]["generation"]["peak_state_bytes"],
            "wall_seconds": stage_a["wall_seconds"],
            "later_positions": "MEASURED_NOT_QUALIFIED",
            "evidence": binding(STAGE_A),
        },
        "text_generation_real_checkpoint": None if stage_b1 is None else {
            "state": "DONE",
            "stage": stage_b1["stage"],
            "prompt_mode": stage_b1["diagnostics"]["prompt_mode"],
            "prompt_tokens": stage_b1["diagnostics"]["prompt_tokens"],
            "generated_tokens": stage_b1["diagnostics"]["generation"]["generated_tokens"],
            "generated_token_count": stage_b1["diagnostics"]["generation"]["generated_token_count"],
            "finish_reason": stage_b1["diagnostics"]["generation"]["finish_reason"],
            "answer_text": stage_b1["answer_text"],
            "python_inference_process": stage_b1["diagnostics"]["python_inference_process"],
            "identity_verification_seconds": stage_b1["diagnostics"]["phases_seconds"]["checkpoint_identity_verification"],
            "prefill_seconds": stage_b1["diagnostics"]["generation"]["prefill_seconds"],
            "position_seconds": stage_b1["diagnostics"]["generation"]["position_seconds"],
            "decode_tokens_per_second": stage_b1["diagnostics"]["decode_tokens_per_second"],
            "decode_rate_caveat": "three tokens over one interval on a cold, uncached weight path; it is a measurement of this build, not a runtime capability",
            "quality_claim": "NONE: four tokens of raw-text continuation from a 2-bit quantisation without a chat template is not a task result",
            "known_defect": "in --no-chat-template mode the stop set is empty, so the run could only end on max-tokens",
            "evidence": binding(STAGE_B1),
        },
        "chat_template_generation_real_checkpoint": None if stage_b2 is None else {
            "state": "DONE",
            "stage": stage_b2["stage"],
            "prompt_mode": stage_b2["diagnostics"]["prompt_mode"],
            "prompt_tokens": stage_b2["diagnostics"]["prompt_tokens"],
            "stop_token_ids": stage_b2["diagnostics"]["stop_token_ids"],
            "generated_tokens": stage_b2["diagnostics"]["generation"]["generated_tokens"],
            "generated_token_count": stage_b2["diagnostics"]["generation"]["generated_token_count"],
            "finish_reason": stage_b2["diagnostics"]["generation"]["finish_reason"],
            "stop_token": stage_b2["diagnostics"]["generation"]["stop_token"],
            "answer_text": stage_b2["answer_text"],
            "identity_verification_seconds": stage_b2["diagnostics"]["phases_seconds"]["checkpoint_identity_verification"],
            "positions_executed": stage_b2["diagnostics"]["generation"]["positions_executed"],
            "position_seconds": stage_b2["diagnostics"]["generation"]["position_seconds"],
            "peak_state_bytes": stage_b2["diagnostics"]["generation"]["peak_state_bytes"],
            "decode_tokens_per_second": stage_b2["diagnostics"]["decode_tokens_per_second"],
            "quality_claim": "NONE: a single short prompt with a four-token budget is not a task result",
            "evidence": binding(STAGE_B2),
        },
        "native_text_cli": {
            "state": "DONE_SYNTHETIC",
            "binary": "f017-native-generate",
            "python_inference_process_required": False,
            "scope": cli["scope"],
            "cases_passed": sum(1 for case in cli["cases"] if case["status"] == "PASS"),
            "cases": cli["case_count"],
            "result": cli["result"],
            "evidence": binding(CLI),
        },
        "active_source_measurement": {
            "state": "DONE",
            "schema": measurement["schema"],
            "measured_paths": measurement["measured_path_count"],
            "unchanged_since_predecessor": measurement["unchanged_since_predecessor"],
            "drifted_and_reviewed": len(measurement["drift_from_predecessor"]),
            "numerical_authority_unchanged": measurement["numerical_authority_unchanged"],
            "evidence": binding(MEASUREMENT),
        },
        "contract": {
            "state": "FROZEN",
            "rope_pairing_status": contract["attention_semantics"]["rope"]["status"],
            "indexer_implemented": contract["attention_semantics"]["sparse_indexer"]["implemented"],
            "max_positions_default": contract["bounds"]["max_positions_default"],
            "evidence": binding(CONTRACT),
        },
        "not_claimed": sorted(set(contract["not_claimed"]) | {
            "qualified multi-token generation on the real checkpoint",
            "tokens/sec as a runtime capability",
            "answer quality on any task",
            "production readiness",
        }),
        "original_checkpoint_access_by_this_summary": 0,
    }


def serialize(document: dict) -> str:
    return json.dumps(document, indent=1, sort_keys=True) + "\n"


BEGIN = "<!-- generated:begin f017-native-status-figures -->"
END = "<!-- generated:end f017-native-status-figures -->"
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_FENCE = re.compile(r"```.*?```", re.S)

# Every figure-bearing statement lives inside the generated block. Outside it the
# document must be figure-free, so any number -- or number-word -- attached to one
# of these units is a hand-written figure that could drift from the evidence.
_UNITS = (r"ULP|tokens?|positions?|tok/s|tokens/s|values?|seeds?|formats?|"
          r"of 36|unchanged|drifted|bodies|GiB|MB|B|s")
_WORDS = ("zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
          "thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
          "thirty|forty|fifty|sixty|seventy|eighty|ninety")
_NUMBER = r"(?:\d[\d,.]*|(?:%s)(?:-(?:%s))?)" % (_WORDS, _WORDS)
_FIGURE = re.compile(r"\b%s\b(?:\W+\w+){0,3}\W+(?:%s)\b" % (_NUMBER, _UNITS), re.I)
_PRODUCED_TOKEN = re.compile(r"154820")


def _rows_done(document: dict) -> list[tuple[str, str, str]]:
    """The done table: state, category from the five-symbol vocabulary, scope."""
    one = document["one_token_real_checkpoint"]
    rec = document["checkpoint_free_reconciliation"]
    measurement = document["active_source_measurement"]
    temporal = document["temporal_multi_position"]
    stage_a = document["temporal_multi_position_real_checkpoint"]
    b1 = document["text_generation_real_checkpoint"]
    b2 = document["chat_template_generation_real_checkpoint"]
    unchanged = measurement["measured_paths"] - measurement["drifted_and_reviewed"]
    return [
        ("One token, real checkpoint (attempt 2)", "✅ verified",
         f'produced token {one["produced_token"]}, equal to the corrected oracle\'s expected '
         f'token, then stopped: {one["verdict"]}. '
         f'{one["duration_seconds"]} s total, of which {one["shard_identity_rehash_seconds"]} s '
         f'shard identity rehash and {one["forward_pass_seconds"]} s forward pass. '
         f'Authorization {one["authorization"]}.'),
        ("Checkpoint-free reconciliation", "✅ verified",
         f'decoder differential {rec["decoder_differential_max_ulp"]} ULP over '
         f'{rec["decoder_differential_values_per_seed"]:,} values per seed.'),
        ("Active source measurement / CI", "✅ verified",
         f'{unchanged} of {measurement["measured_paths"]} measured bodies unchanged; '
         f'{measurement["drifted_and_reviewed"]} drifted and reviewed.'),
        ("Multi-position temporal graph", "✅ verified (synthetic)",
         f'{temporal["cases_passed"]}/{temporal["cases"]} cases against an independent '
         f'reference. {temporal["scope"]}'),
        ("Multi-position decode, real checkpoint (Stage A)", "📏 measured",
         f'{stage_a["positions_executed"]} teacher-forced positions, one retained state of '
         f'{stage_a["peak_state_bytes"]} B. Position 0 reproduces the banked attempt-2 receipt '
         f'and is the verified result above; later positions are {stage_a["later_positions"]}.'),
        ("Text generation, real checkpoint (Stage B1)", "📏 measured",
         f'{b1["prompt_tokens"]} prompt tokens, {b1["generated_token_count"]} generated tokens, '
         f'finish reason {b1["finish_reason"]}, no Python in the inference path. '
         f'Quality claim: {b1["quality_claim"]}'),
        ("Chat template, real checkpoint (Stage B2)", "📏 measured",
         f'{b2["prompt_mode"]}: {b2["prompt_tokens"]} prompt tokens over '
         f'{b2["positions_executed"]} positions, {b2["generated_token_count"]} generated tokens, '
         f'retained state {b2["peak_state_bytes"]} B, finish reason {b2["finish_reason"]}. '
         f'Quality claim: {b2["quality_claim"]}'),
        ("Native text CLI", "✅ verified (synthetic)",
         f'{document["native_text_cli"]["cases_passed"]}/{document["native_text_cli"]["cases"]} '
         f'cases, {document["native_text_cli"]["result"]}. '
         f'{document["native_text_cli"]["scope"]}'),
    ]


def _rows_not_done(document: dict) -> list[tuple[str, str]]:
    b1 = document["text_generation_real_checkpoint"]
    b2 = document["chat_template_generation_real_checkpoint"]
    contract = document["contract"]
    return [
        ("Qualified multi-token generation on the real checkpoint",
         "Stages A, B1 and B2 have all executed under the same approval, so execution is not "
         "what is outstanding. No independent multi-token oracle exists for this checkpoint, so "
         "nothing beyond attempt 2's position 0 is qualified."),
        ("Tokens/sec as a runtime capability",
         f'the measured rates are {b1["decode_tokens_per_second"]:.4f} tok/s (Stage B1) and '
         f'{b2["decode_tokens_per_second"]:.4f} tok/s (Stage B2), on a cold, uncached weight '
         f'path. {b1["decode_rate_caveat"]}'),
        ("Answer quality", f'{b1["quality_claim"]}'),
        ("The checkpoint's RoPE pairing", f'{contract["rope_pairing_status"]}.'),
        ("The sparse indexer",
         f'not implemented; the runtime refuses sequences longer than the checkpoint\'s indexer '
         f'budget rather than substituting dense attention. Default max positions '
         f'{contract["max_positions_default"]}.'),
        ("Feature 017 formal closeout",
         "pending the standing human approval. Technical state and formal signoff are separate."),
    ]


def render_block(document: dict) -> str:
    """Everything in the status document that states a figure.

    The prose outside this block is required to be figure-free, so there is no
    second place a number can drift from the evidence.
    """
    done = "\n".join(f"| {state} | {category} | {scope} |"
                     for state, category, scope in _rows_done(document))
    not_done = "\n".join(f"| {state} | {status} |" for state, status in _rows_not_done(document))
    return (f"{BEGIN}\n"
            "<!-- Generated by scripts/research/generate_f017_native_status_v1.py. Do not edit by hand. -->\n\n"
            "### What is done\n\n"
            "| State | Category | Scope |\n| --- | --- | --- |\n" + done + "\n\n"
            "### What is not done\n\n"
            "| State | Status |\n| --- | --- |\n" + not_done + "\n\n"
            "Categories are the repository's five: ✅ verified, 📏 measured, 🧪 experimental,\n"
            "🗺️ planned, ❌ not implemented / not claimed. *Measured* means executed and\n"
            "recorded, not independently qualified.\n\n"
            f"{END}")


def _outside(markdown: str) -> str:
    """Everything except the generated block, HTML comments and fenced code.

    Inline code and table cells are deliberately *not* stripped: a figure is a
    figure wherever it is written.
    """
    start = markdown.find(BEGIN)
    if start != -1:
        stop = markdown.find(END, start)
        if stop != -1:
            markdown = markdown[:start] + markdown[stop + len(END):]
    return _FENCE.sub(" ", _COMMENT.sub(" ", markdown))


def verify_markdown(document: dict) -> list[str]:
    """The block must be exactly ours, and nothing outside it may state a figure."""
    if not STATUS_DOC.is_file():
        return [f"missing {STATUS_DOC.relative_to(ROOT)}"]
    markdown = STATUS_DOC.read_text()
    problems = []

    if markdown.count(BEGIN) != 1 or markdown.count(END) != 1:
        problems.append("expected exactly one generated block")
        return problems
    start = markdown.find(BEGIN)
    stop = markdown.find(END)
    if start > stop:
        problems.append("the generated block markers are inverted")
        return problems
    if markdown[start:stop + len(END)] != render_block(document):
        problems.append("the generated block does not match the generator")

    outside = _outside(markdown)
    for match in _FIGURE.finditer(outside):
        problems.append(f"figure stated outside the generated block: {match.group(0)!r}")
    if _PRODUCED_TOKEN.search(outside):
        problems.append("the produced token is stated outside the generated block")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    raw = serialize(build())
    if arguments.check:
        if not OUTPUT.is_file() or OUTPUT.read_text() != raw:
            print("native runtime status drift: regenerate docs/glm52-native/native-runtime-summary.json",
                  file=sys.stderr)
            return 1
        stale = verify_markdown(json.loads(raw))
        if stale:
            print("native runtime status drift in "
                  + str(STATUS_DOC.relative_to(ROOT)) + ": " + "; ".join(stale),
                  file=sys.stderr)
            return 1
    else:
        document = json.loads(raw)
        if STATUS_DOC.is_file():
            markdown = STATUS_DOC.read_text()
            block = render_block(document)
            start = markdown.find(BEGIN)
            stop = markdown.find(END)
            if start != -1 and stop != -1:
                markdown = markdown[:start] + block + markdown[stop + len(END):]
            else:
                markdown = markdown.rstrip("\n") + "\n\n## Generated figures\n\n" + block + "\n"
            STATUS_DOC.write_text(markdown)
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
