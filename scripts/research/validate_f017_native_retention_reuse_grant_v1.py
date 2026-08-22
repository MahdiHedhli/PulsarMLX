#!/usr/bin/env python3
import argparse, hashlib, json, pathlib, subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
GRANT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-representative-retention-reuse-grant-v1.json"
PACKAGE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-retained-qualification-package-v1.json"
REPAIR = ROOT / "docs/architecture/reviews/evidence/f017-native-retained-router-authority-repair-v1.json"

def unique(path):
    def pairs(values):
        out = {}
        for key, value in values:
            if key in out: raise ValueError(f"duplicate key {key}")
            out[key] = value
        return out
    return json.loads(path.read_text(), object_pairs_hook=pairs)

def sha_bytes(value): return hashlib.sha256(value).hexdigest()
def sha(path): return sha_bytes(path.read_bytes())

def package_root(reads):
    fields = ("ordinal","canonical_tensor_id","role","destination_relative_path","sha256","byte_count","encoding","shape","quantization","decoder_binding","source_authority_path","source_authority_sha256","source_result_event")
    value = {"schema":"pulsarmlx.f017.apple-production-serial-f32-retained-package-root","schema_version":"1.0.0","package_version":"F017-APPLE-SERIAL-F32-RETAINED-40-V1","tensor_count":40,"ordered_tensor_descriptors":[{key: row[key] for key in fields} for row in reads]}
    return sha_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n")

def historical(commit, path):
    return subprocess.check_output(
        ["git", "show", f"{commit}:{path}"], cwd=ROOT, stderr=subprocess.DEVNULL
    )

def validate(grant_path=GRANT, package_path=PACKAGE):
    grant, package = unique(grant_path), unique(package_path)
    if grant["schema"] != "pulsarmlx.f017.native-retained-reuse-grant/1.0.0": raise ValueError("schema")
    if grant["consumer_id"] != "F017-NATIVE-REPRESENTATIVE-LAYER3-QUALIFICATION-1": raise ValueError("consumer")
    if sha(ROOT / grant["consumer_source_path"]) != grant["consumer_source_sha256"]: raise ValueError("consumer hash")
    if grant["d0_sha256"] != sha(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v2.json"): raise ValueError("D0")
    if grant["historical_master_ledger_sha256"] != "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e": raise ValueError("ledger")
    if grant["tensor_count"] != 40 or len(grant["allowed_reads"]) != 40 or len(package["tensors"]) != 40: raise ValueError("census")
    if grant["historical_package_root_sha256"] != "564a33aee801b4a44e23f3a9b370e1a2ce040dda521dadc4ac54dbfd29045be6": raise ValueError("historical package root")
    if package_root(grant["allowed_reads"]) != grant["package_root_sha256"] or grant["package_root_sha256"] != "03ccbb1be96073bfe051ba8950ec4e16a3824b998c041dfcac7e209ede66151c": raise ValueError("native consumer package root")
    if grant["total_bytes"] != 257305600 or sum(x["byte_count"] for x in grant["allowed_reads"]) != 257305600: raise ValueError("bytes")
    if [grant[k] for k in ["attempts","qualification_runs","same_process_runs","fresh_process_runs","stages_per_run","retained_reads_per_run","expected_retained_read_receipts"]] != [1,20,10,10,34,40,800] or grant["checkpoint_fallback"] or any(grant[k] for k in ["original_checkpoint_reads","original_checkpoint_shard_opens","historical_payload_ledger_delta"]): raise ValueError("execution policy")
    seen = set()
    for ordinal, item in enumerate(grant["allowed_reads"]):
        if item["ordinal"] != ordinal or item["role"] in seen: raise ValueError("order/duplicate")
        seen.add(item["role"])
        spec = package["tensors"].get(item["role"])
        if spec is None: raise ValueError("role")
        for key in ["path","sha256","encoding","shape"]:
            if spec[key] != item[key]: raise ValueError(f"package mismatch {item['role']} {key}")
        if item["byte_count"] <= 0 or len(item["sha256"]) != 64: raise ValueError("read identity")
        if item["source_branch"] != "feat/017-real-checkpoint-runner" or len(item["source_commit"]) != 40: raise ValueError("source authority")
        if subprocess.run(["git", "merge-base", "--is-ancestor", item["source_commit"], "origin/feat/017-real-checkpoint-runner"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode: raise ValueError("source commit not on claimed branch")
        if sha_bytes(historical(item["source_commit"], item["source_authority_path"])) != item["source_authority_sha256"]: raise ValueError(f"source hash {item['role']}")
    if package["checkpoint_paths"] != [] or package["runtime"]["mlx_version"] != "0.31.2" or package["runtime"]["mlx_c_version"] != "0.6.0": raise ValueError("package runtime")
    repair = unique(REPAIR)
    if repair["defect"]["affected_ordinals"] != [10,11,12] or repair["replacement_authority"]["sha256"] != "c46b00cb263347e1a345b1766fd1e36d3758c6e21ae15674bfe8dfc8841f21a1" or repair["native_consumer_result"]["grant_sha256"] != sha(grant_path): raise ValueError("authority repair evidence")
    return grant

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--grant", type=pathlib.Path, default=GRANT); parser.add_argument("--package", type=pathlib.Path, default=PACKAGE)
    args = parser.parse_args(); validate(args.grant, args.package)
    print("PASS: native consumer-scoped grant 40/40 exact reads; no checkpoint fallback")

if __name__ == "__main__": main()
