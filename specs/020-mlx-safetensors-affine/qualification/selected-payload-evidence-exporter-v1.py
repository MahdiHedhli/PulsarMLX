#!/usr/bin/env python3
"""Export bounded capture receipts only; never opens model or snapshot payloads."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    a, repo = args.audit, args.repo
    freeze = read(a / "source-freeze-v1.json")
    review = a / "review-02"
    verdict = read(review / "parsed-review.json")
    rr = read(review / "process-receipt.json")
    capsule = read(review / "review-capsule.json")
    assert verdict["decision"] == "ACCEPT" and not verdict["blocking_findings"]
    assert verdict["actual_models"] == ["claude-opus-5-5"]
    assert rr["exit_code"] == 0 and rr["commit"] == freeze["commit"]
    assert rr["tree"] == freeze["tree"] and rr["package_sha256"] == freeze["package_sha256"]
    assert sha(review / "review-capsule.json") == rr["capsule_sha256"]
    assert sha(review / "claude-review.json") == rr["raw_review_sha256"]
    for name, expected in freeze["source_files"].items():
        assert sha(repo / name) == expected
        assert (repo / name).read_text() == capsule["files"][name]
    repair = read(a / "host-repair-checks-02.json")
    workspace = read(a / "workspace-host-checks.json")
    assert all(r["exit_code"] == 0 for r in repair + workspace)
    targeted = (a / "targeted-tests-02.log").read_text()
    assert "21 passed; 0 failed" in targeted and "SKIP" not in targeted
    assert "synthetic real storage geometry: selected=14155776 bytes, calls=9, native=0" in targeted
    sums = re.findall(r"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;", (a / "workspace-tests.log").read_text())
    assert [sum(int(r[i]) for r in sums) for i in range(3)] == [658, 0, 3]
    process = read(a / "capture-01/process-receipt.json")
    capture = read(a / "capture-01/stdout.json")
    assert sha(a / "capture-01/stdout.json") == process["raw_stdout_sha256"]
    assert process["commit"] == freeze["commit"] and process["tree"] == freeze["tree"]
    assert process["source_package_sha256"] == freeze["package_sha256"]
    assert process["review_capsule_sha256"] == rr["capsule_sha256"]
    assert process["raw_review_sha256"] == rr["raw_review_sha256"]
    assert process["review_decision"] == "ACCEPT" and process["blocking_findings"] == 0
    assert process["actual_review_model"] == "claude-opus-5-5"
    assert process["exit_code"] == 0 and process["source_unchanged_after"] is True
    assert process["real_payload_observations"] == 1
    assert all(process[k] == 0 for k in ("native_calls", "whole_checkpoint_reads", "whole_original_shard_hashes", "model_downloads"))
    assert not re.search(r"libmlx|libmlxc|metallib", process["native_linkage"], re.I)
    assert sha(repo / "target/release/examples/glm_selected_freeze") == process["binary_sha256"]
    prior = read(a.parent / "20261003-expert-range-admission/real-metadata-plan-01-stdout.json")
    assert sha(a.parent / "20261003-expert-range-admission/real-metadata-plan-01-stdout.json") == process["prior_metadata_stdout_sha256"]
    plan = capture["owned"]["plan"]
    assert plan == prior["plan"]
    assert plan["metadata_snapshot_sha256"] == process["expected_metadata_snapshot_sha256"]
    assert capture["requested_payload_bytes"] == capture["snapshot_payload_bytes_written"] == plan["selected_bytes"] == 14155776
    assert capture["payload_read_calls"] == 9 and capture["native_calls"] == 0
    assert capture["owned"]["owned_bytes"] == 14155776
    assert plan["request"]["expert"] == 0 and plan["request"]["experts"] == 288
    assert plan["request"]["d"] == 4096 and plan["request"]["h"] == 2048
    assert plan["request"]["bits"] == [4, 4, 4] and plan["request"]["group_size"] == 64
    prefix = "language_model.model.layers.3.mlp.switch_mlp."
    assert plan["request"]["modules"] == [prefix + r for r in ("gate_proj", "up_proj", "down_proj")]
    assert [p["logical_shape"] for p in plan["planes"]] == [[2048,4096],[2048,4096],[4096,2048]]
    assert [p["metadata_dtype"] for p in plan["planes"]] == ["BF16"] * 3
    hashes = capture["owned"]["selected_range_sha256"]
    assert len(hashes) == 9 and all(re.fullmatch(r"[0-9a-f]{64}", h) for h in hashes)
    proof = read(a / "capture-01/independent-snapshot-verification.json")
    vc = read(a / "snapshot-verifier-receipt.json")
    q = repo / "specs/020-mlx-safetensors-affine/qualification"
    assert sha(q / "selected-snapshot-verifier-v1.py") == vc["verifier_source_sha256"]
    assert sha(q / "test_selected_snapshot_verifier_v1.py") == vc["verifier_tests_sha256"]
    assert sha(a / "capture-01/independent-snapshot-verification.json") == vc["proof_sha256"]
    assert "Ran 6 tests" in (a / "snapshot-verifier-tests.log").read_text()
    assert "\nOK\n" in (a / "snapshot-verifier-tests.log").read_text()
    assert proof["status"] == "PASS" and proof["selected_payload_bytes_verified"] == 14155776
    assert proof["selected_range_sha256"] == hashes
    assert proof["metadata_snapshot_sha256"] == plan["metadata_snapshot_sha256"]
    assert proof["snapshot_sha256"] == capture["snapshot_sha256"]
    assert proof["snapshot_bytes_read"] == capture["snapshot_bytes"] == 14159388
    assert proof["original_checkpoint_bytes_read"] == proof["native_calls"] == 0
    summary = {
        "schema": "pulsarmlx.selected-expert-capture-evidence/1",
        "source": {k:freeze[k] for k in ("commit","tree","package_sha256","base")},
        "source_review": {"decision":"ACCEPT","blockers":0,"actual_model":"claude-opus-5-5",
                          "capsule_sha256":rr["capsule_sha256"],"raw_review_sha256":rr["raw_review_sha256"],
                          "invalid_provider_attempt_preserved":True},
        "host": freeze["host_tests"],
        "capture": {"status":"PASS","layer":3,"expert":0,"E":288,"D":4096,"H":2048,
                    "bits":[4,4,4],"group_size":64,"metadata_dtype":"BF16",
                    "metadata_bytes_read":plan["metadata_bytes_read"],
                    "metadata_snapshot_sha256":plan["metadata_snapshot_sha256"],
                    "original_selected_payload_bytes_read":14155776,"range_read_attempts":9,
                    "snapshot_payload_bytes_written":14155776,"snapshot_bytes":capture["snapshot_bytes"],
                    "snapshot_sha256":capture["snapshot_sha256"],"selected_range_sha256":hashes,
                    "native_calls":0,"whole_checkpoint_reads":0,"whole_original_shard_hashes":0,"model_downloads":0,
                    "raw_stdout_sha256":process["raw_stdout_sha256"],"binary_sha256":process["binary_sha256"],
                    "snapshot_location":"private Studio audit only","physical_SSD_bytes":"unknown"},
        "independent_byte_verification": {"status":"PASS","synthetic_tests":6,
                                         "snapshot_bytes_read":proof["snapshot_bytes_read"],
                                         "original_checkpoint_bytes_read":0,"native_calls":0,**vc},
        "exporter_sha256":sha(Path(__file__)),
        "scope":"one bounded packed host capture and selected-byte custody; no R1/native/full-shape numerical qualification",
        "next_gate":"Separately review original-byte R1, frozen F32 input and exact native adapter; prospectively qualify 4096/2048 geometry and 8388608 MACs per projection or label a bounded block. Preserve E_act=1/128, beta_B=5201/4194304 and the down admission floor.",
    }
    (q / "selected-payload-studio-evidence-v1.json").write_text(json.dumps(summary, indent=2) + "\n")
    (q / "selected-payload-source-freeze-v1.json").write_text(json.dumps(freeze, indent=2) + "\n")
    receipt = {"schema":"pulsarmlx.selected-payload-source-review/1","decision":"ACCEPT","blocking_findings":0,
               "actual_model":"claude-opus-5-5","source_commit":freeze["commit"],**rr,
               "scope":"host selected-content capture only","verification_limits_carried_forward":verdict.get("verification_limits",[])}
    (q / "selected-payload-source-review-v1.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status":"SANITIZED_EVIDENCE_EXPORTED","snapshot_sha256":capture["snapshot_sha256"]}))


if __name__ == "__main__":
    main()
