#!/usr/bin/env python3
"""Build and validate the complete append-only F017 real-payload ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CHECKPOINT = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"
M1F0 = [
    "blk.3.attn_norm.weight", "blk.3.attn_q_a.weight", "blk.3.attn_q_a_norm.weight",
    "blk.3.attn_q_b.weight", "blk.3.attn_kv_a_mqa.weight", "blk.3.attn_kv_a_norm.weight",
    "blk.3.attn_k_b.weight", "blk.3.attn_v_b.weight", "blk.3.attn_output.weight",
    "blk.3.ffn_norm.weight", "blk.3.ffn_gate_inp.weight", "blk.3.exp_probs_b.bias",
]
EXPERT15 = [
    "blk.3.ffn_gate_exps.weight#15", "blk.3.ffn_up_exps.weight#15",
    "blk.3.ffn_down_exps.weight#15",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def event(root: Path, phase: str, attempt: str, reason: str, evidence: str,
          tensors: list[str], consumed: bool, kind: str) -> dict[str, object]:
    path = root / evidence
    if not path.is_file():
        raise ValueError(f"missing evidence: {evidence}")
    return {
        "phase": phase, "attempt": attempt, "reason": reason,
        "checkpoint_set_sha256": CHECKPOINT, "tensor_symbolic_names": tensors,
        "tensor_payload_count": len(tensors), "repeated_payload_access": False,
        "access_kind": kind, "consumed_attempt": consumed,
        "evidence": {"path": evidence, "sha256": digest(path)},
    }


def build_ledger(root: Path) -> dict[str, object]:
    e = []
    e.append(event(root, "M1-C", "1", "real F32 tensor qualification",
        "docs/architecture/reviews/evidence/f017-m1-c-real-tensor-v1.json",
        ["output_norm.weight"], True, "execution"))
    e.append(event(root, "M1-D", "1", "contract-read rejection before payload access",
        "docs/architecture/reviews/evidence/f017-m1-d-real-projection-v1.json", [], True, "execution"))
    e.append(event(root, "M1-D", "2", "activation rejection before payload access",
        "docs/architecture/reviews/evidence/f017-m1-d-real-projection-attempt-2-v1.json", [], True, "execution"))
    e.append(event(root, "M1-D", "3", "accepted real Q8_0 projection",
        "docs/architecture/reviews/evidence/f017-m1-d-real-projection-attempt-3-v1.json",
        ["blk.0.attn_kv_a_mqa.weight"], True, "execution"))
    e.append(event(root, "M1-E", "1", "rejected real expert decode gate", 
        "docs/architecture/reviews/evidence/f017-m1-e-real-expert-attempt-1-v1.json", EXPERT15, True, "execution"))
    e.append(event(root, "M1-E", "2", "schema rejection before payload access",
        "docs/architecture/reviews/evidence/f017-m1-e-real-expert-attempt-2-v1.json", [], True, "execution"))
    e.append(event(root, "M1-E", "3", "accepted real expert", 
        "docs/architecture/reviews/evidence/f017-m1-e-real-expert-attempt-3-v1.json", EXPERT15, True, "execution"))
    e.append(event(root, "M1-F0-Q5_K", "qualification-1", "real-byte Q5_K decoder qualification",
        "docs/architecture/reviews/evidence/f017-m1-f0-q5-k-real-byte-qualification-v1.json",
        ["blk.3.attn_output.weight"], False, "qualification_only"))
    e.append(event(root, "M1-F0", "1", "rejected real route discovery",
        "docs/architecture/reviews/evidence/f017-m1-f0-real-route-attempt-1-rejected-v1.json", M1F0, True, "execution"))
    e.append(event(root, "M1-F0", "2", "accepted real route discovery",
        "docs/architecture/reviews/evidence/f017-m1-f0-real-route-attempt-2-v1.json", M1F0, True, "execution"))
    e.append(event(root, "M1-F0", "analytical-recovery-1", "accepted-boundary evidence recovery",
        "docs/architecture/reviews/evidence/f017-m1-f0-router-analytical-recovery-v1.json", M1F0, False, "evidence_recovery"))
    e.append(event(root, "M1-F0-V2-ANTECEDENT-RECOVERY", "analytical-antecedent-recovery-1",
        "identity-gated analytical antecedent recovery for retrospective route-stability v2",
        "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-review-v1.json",
        M1F0, False, "evidence_recovery"))
    e.append(event(root, "Q4_K-REAL-BYTE-QUALIFICATION", "Q4K-REAL-1",
        "exact real-byte Q4_K decoder-format qualification",
        "docs/architecture/reviews/evidence/f017-q4-k-real-byte-qualification-attempt-1-v1.json",
        ["token_embd.weight"], True, "qualification_only"))
    e.append(event(root, "Q6_K-REAL-BYTE-QUALIFICATION", "Q6K-REAL-1",
        "exact real-byte Q6_K decoder-format qualification and F017-Q6K-LANE-ORDER-001 closure",
        "docs/architecture/reviews/evidence/f017-q6-k-real-byte-qualification-attempt-1-v1.json",
        ["blk.0.ffn_down.weight"], True, "qualification_only"))
    allowlist = json.loads((root / "docs/architecture/reviews/evidence/f017-dense-prefix-40-read-allowlist-v1.json").read_text())
    dense_prefix = [item["name"] for item in allowlist["entries"]]
    if len(dense_prefix) != 40:
        raise ValueError("dense-prefix allowlist must contain exactly 40 tensors")
    e.append(event(root, "M1-F(-1)-DENSE-PREFIX", "DPREFIX-REAL-1",
        "rejected real dense-prefix capture after all 40 authorized payload reads; exact candidate terminated NATIVE_RUNTIME / NATIVE_CANDIDATE_MATVEC_SHAPE before numerical evidence",
        "docs/architecture/reviews/evidence/f017-dense-prefix-real-attempt-1-rejected-native-runtime-v1.json",
        dense_prefix, True, "execution"))
    e.append(event(root, "M1-F(-1)-DENSE-PREFIX", "DPREFIX-REAL-2",
        "rejected terminal evidence validation after all 40 identity-gated payload reads; all eight real Tier-B surfaces qualified but the bound success path omitted required lifecycle and host-copy accounting",
        "docs/architecture/reviews/evidence/f017-dense-prefix-real-attempt-2-rejected-evidence-validation-v1.json",
        dense_prefix, True, "execution"))
    cumulative = 0
    seen: set[str] = set()
    for item in e:
        names = item["tensor_symbolic_names"]
        assert isinstance(names, list)
        item["repeated_payload_access"] = any(name in seen for name in names)
        seen.update(names)
        cumulative += int(item["tensor_payload_count"])
        item["cumulative_tensor_payloads_after_event"] = cumulative
    return {
        "schema": "pulsarmlx.f017.real-payload-access-ledger", "schema_version": "1.0.0",
        "accounting_rule": "each positional tensor payload read counts, including repeated reads and qualification/recovery reads",
        "metadata_header_reads_are_tensor_payloads": False,
        "checkpoint_identity_only": {"phase": "M1-B", "storage_read_count": 28444,
            "storage_read_bytes": 238485096032, "tensor_payload_count": 0,
            "classification": "checkpoint_identity_catalog_and_header_scans"},
        "events": e, "prior_m1f0_scoped_total": 37,
        "prior_scope_omissions": {"M1-C": 1, "M1-D": 1, "M1-E": 6},
        "prior_scope_omissions_total": 8, "cumulative_tensor_payloads": cumulative,
        "historical_evidence_rewritten": False, "real_checkpoint_access_during_ledger_reconstruction": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", type=Path)
    args = parser.parse_args()
    value = build_ledger(args.root)
    payload = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    target = args.output or args.check
    if args.check:
        if not target.is_file() or target.read_bytes() != payload:
            raise SystemExit("real-payload ledger differs from evidence-derived reconstruction")
    elif target:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    print(hashlib.sha256(payload).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
