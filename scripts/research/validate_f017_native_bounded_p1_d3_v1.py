#!/usr/bin/env python3
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-execution-architecture-v1.json"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    data = json.loads(CONTRACT.read_text())
    if data["schema"] != "pulsarmlx.f017.native-bounded-p1-execution-architecture" or data["schema_version"] != "1.0.0":
        raise SystemExit("schema")
    if data["authority"]["historical_master_terminal_count"] != 175:
        raise SystemExit("ledger")
    for section in (data["bound_contracts"],):
        for item in section.values():
            if sha(ROOT / item["path"]) != item["sha256"]:
                raise SystemExit(f"bound hash: {item['path']}")
    for item in [data["retained_qualification"]["runner_source"], data["retained_qualification"]["grant_enforcer"], data["retained_qualification"]["canonical_graph"], *data["load_bearing_sources"]]:
        if sha(ROOT / item["path"]) != item["sha256"]:
            raise SystemExit(f"source hash: {item['path']}")
    own = data["ownership_domain"]
    if own["cross_runtime_counter_stitching"] or own["mock_boundary"] != "TENSOR_MATH_ONLY" or not own["mandatory_stop"]:
        raise SystemExit("ownership")
    retained = data["retained_qualification"]
    if retained["tensor_count"] != 40 or retained["checkpoint_fallback"] or not retained["per_read_receipts"]:
        raise SystemExit("retained")
    if data["instantiability"]["real_full_checkpoint_bounded_p1_math"] != "NOT_YET_INSTANTIABLE_BLOCKS_FINAL_DOMAIN_ACCEPTANCE":
        raise SystemExit("scope honesty")
    if any(data["phase_invariants"].values()):
        raise SystemExit("execution invariant")
    print("PASS: D3 architecture source bindings and scope")

if __name__ == "__main__":
    main()
