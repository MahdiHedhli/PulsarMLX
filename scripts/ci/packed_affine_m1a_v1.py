#!/usr/bin/env python3
"""Opt-in native-CI transport/controller; the compiled experiment stays frozen.

Importing this module is host-only. Only main's `run` command builds/runs native
code, after the CI route and persistent GitHub run-history checks. Never retry a
designated campaign to recover a missing artifact or an unknown probe outcome.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request

CANDIDATE = "190c64213135a756f5e3d61059036b9af2d78d7a"
TREE = "1bd6cf2f01d5a921fd9c402a109f36072721274f"
BRANCH = "codex/rust-expert-streaming-m0-m1"
REPOSITORY = "MahdiHedhli/PulsarMLX"
ARCHIVE_SHA = "8836fac6de10d2af682c21b3c1d9a1699e6a9121f120fd3f890de59d071662d2"
CONTROLLER = Path(__file__).resolve().parents[2]
STEM = "packed_affine_m1_inputs_v1"
RECONCILIATION = "scripts/ci/packed_affine_m1a_ci_reconciliation_v1.json"
RECONCILIATION_SHA = "ee0492eeeae56eca9e435bcb4649e21bd128cc7a2e6e816d260d9dc463ba756f"


def digest(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def write_new(path, value):
    with path.open("x") as f:
        json.dump(value, f, sort_keys=True, indent=2)
        f.write("\n")


def require_route(env, event):
    required = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_REF": "refs/heads/" + BRANCH,
                "GITHUB_RUN_ATTEMPT": "1", "PULSAR_ADOPTION_PHASE": "m1a"}
    if any(env.get(k) != v for k, v in required.items()):
        raise ValueError("designated native CI M1a route/attempt required")
    if event.get("inputs") != {"mode": "full", "packed_affine_m1a": "true"}:
        raise ValueError("explicit full/M1a inputs required")
    if not env.get("GITHUB_RUN_ID", "").isdigit():
        raise ValueError("actual run ID required")


def load_reconciliation():
    raw = (CONTROLLER / RECONCILIATION).read_bytes()
    if hashlib.sha256(raw).hexdigest() != RECONCILIATION_SHA:
        raise ValueError("missing or changed Rust009 reconciliation authority")
    record = json.loads(raw)
    if record["candidate"] != CANDIDATE or record["candidate_tree"] != TREE:
        raise ValueError("reconciliation candidate mismatch")
    return record


def exact_fields(value, expected):
    return all(type(value.get(k)) is type(v) and value[k] == v for k, v in expected.items())


def require_predecessor_run(run, predecessor):
    expected = {"id": predecessor["run_id"], "run_attempt": 1,
                "workflow_id": predecessor["workflow_id"], "path": predecessor["workflow_path"],
                "head_sha": predecessor["controller_commit"], "head_branch": BRANCH,
                "event": "workflow_dispatch", "status": "completed", "conclusion": "failure"}
    if not exact_fields(run, expected):
        raise ValueError("predecessor is not the exact completed attempt-1 failure")


def require_only_campaign(runs, run_id, controller_sha, reconciliation):
    predecessor = reconciliation["predecessor"]
    ids = [str(r["id"]) for r in runs]
    old_id = str(predecessor["run_id"])
    if run_id == old_id or len(runs) != 2 or set(ids) != {old_id, run_id}:
        raise ValueError("exact predecessor/current pair required; allowance not reset")
    require_predecessor_run(runs[ids.index(old_id)], predecessor)
    r = runs[ids.index(run_id)]
    if not exact_fields(r, {"id": int(run_id), "head_sha": controller_sha, "event": "workflow_dispatch",
                            "head_branch": BRANCH, "run_attempt": 1, "path": ".github/workflows/macos.yml",
                            "workflow_id": predecessor["workflow_id"]}):
        raise ValueError("actual workflow run identity mismatch")


def fetch_admission_json(path, evidence, private_dir):
    # Original responses may contain nonessential public actor/profile fields.
    # Retain them privately; the unchanged exporter uploads only root files and
    # campaign evidence. Published projections and raw-byte hashes are distinct.
    receipt = {"request_path": path, "status": "fetch_in_progress"}
    evidence["fetches"].append(receipt)
    request = urllib.request.Request(f"https://api.github.com/repos/{REPOSITORY}/{path}",
                                    headers={"Accept": "application/vnd.github+json",
                                             "User-Agent": "packed-affine-m1a"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(8 * 1024 * 1024 + 1)
        if len(body) > 8 * 1024 * 1024:
            raise ValueError("admission response exceeds capture bound")
        name = f"response-{len(evidence['fetches'])}.json"
        with (private_dir / name).open("xb") as f:
            f.write(body)
        receipt.update(status="received", bytes=len(body), raw_sha256=hashlib.sha256(body).hexdigest(),
                       retained_private=name, public_representation="selected admission fields only")
        return json.loads(body)
    except Exception as e:
        receipt.update(status="fetch_failed", error_type=type(e).__name__, error=str(e))
        raise


def read_complete_pages(path, key, evidence, private_dir):
    rows = []
    total = None
    for page in range(1, 1001):
        separator = "&" if "?" in path else "?"
        data = fetch_admission_json(f"{path}{separator}per_page=100&page={page}", evidence, private_dir)
        count = data["total_count"]
        if type(count) is not int or count < 0 or (total is not None and total != count):
            raise ValueError("invalid/changing API population")
        total = count
        batch = data[key]
        if not isinstance(batch, list) or (not batch and len(rows) < total):
            raise ValueError("incomplete API history")
        rows.extend(batch)
        if len(rows) > total or len({r["id"] for r in rows}) != len(rows):
            raise ValueError("duplicate/excess API rows")
        if len(rows) == total:
            return rows
    raise ValueError("incomplete API history")


def read_campaign_history(evidence, private_dir):
    query = urllib.parse.urlencode({"branch": BRANCH, "event": "workflow_dispatch"})
    return read_complete_pages(f"actions/workflows/macos.yml/runs?{query}", "workflow_runs", evidence, private_dir)


def reconcile_admission(root, run_id, controller_sha):
    evidence = {"fetches": [], "observations": {}, "admitted": False}
    try:
        record = load_reconciliation()
        evidence["reconciliation_sha256"] = RECONCILIATION_SHA
        private_dir = root / "admission-api.private"
        private_dir.mkdir()
        runs = read_campaign_history(evidence, private_dir)
        fields = ("id", "head_sha", "event", "head_branch", "run_attempt", "path", "workflow_id", "status", "conclusion")
        evidence["observations"]["history"] = [{k: r.get(k) for k in fields} for r in runs]
        require_only_campaign(runs, run_id, controller_sha, record)
        old = record["predecessor"]
        endpoint = f"actions/runs/{old['run_id']}"
        run = fetch_admission_json(endpoint, evidence, private_dir)
        evidence["observations"]["predecessor_run"] = {k: run.get(k) for k in fields}
        require_predecessor_run(run, old)
        jobs = read_complete_pages(endpoint + "/attempts/1/jobs", "jobs", evidence, private_dir)
        job_fields = ("id", "run_id", "run_attempt", "head_sha", "head_branch", "name", "status", "conclusion", "runner_id", "steps")
        evidence["observations"]["attempt_1_jobs"] = [{k: j.get(k) for k in job_fields} for j in jobs]
        native = [j for j in jobs if j["id"] == old["native_job_id"]]
        expected = {"id": old["native_job_id"], "run_id": old["run_id"], "run_attempt": 1,
                    "head_sha": old["controller_commit"], "head_branch": BRANCH,
                    "name": "Apple MLX small-fixture validation", "status": "completed",
                    "conclusion": "cancelled", "runner_id": 0, "steps": []}
        if len(native) != 1 or not exact_fields(native[0], expected):
            raise ValueError("predecessor native job has changed or may have executed")
        artifacts = read_complete_pages(endpoint + "/artifacts", "artifacts", evidence, private_dir)
        evidence["observations"]["artifact_ids"] = [a["id"] for a in artifacts]
        if artifacts:
            raise ValueError("unexpected predecessor artifacts")
        commit = fetch_admission_json("git/commits/" + old["controller_commit"], evidence, private_dir)
        evidence["observations"]["predecessor_controller"] = {"commit": commit["sha"], "tree": commit["tree"]["sha"]}
        if commit["sha"] != old["controller_commit"] or commit["tree"]["sha"] != old["controller_tree"]:
            raise ValueError("predecessor controller identity")
        # A rerun/extra dispatch during these reads must also close admission.
        final_runs = read_campaign_history(evidence, private_dir)
        require_only_campaign(final_runs, run_id, controller_sha, record)
        evidence["observations"]["final_history"] = [{k: r.get(k) for k in fields} for r in final_runs]
        evidence["admitted"] = True
        return {"reconciliation": record, "reconciliation_sha256": RECONCILIATION_SHA,
                "predecessor_run_id": old["run_id"], "current_run_id": run_id,
                "designated_dispatches_cumulative": 2, "additional_designated_dispatches": 1,
                "additional_raw_probe_allowances": 0, "predecessor_raw_probe_used": 0,
                "raw_probe_allowed": 1, "fetched_evidence": evidence}
    finally:
        write_new(root / "admission-evidence.json", evidence)


def extract_inputs(archive, manifest, destination):
    if digest(archive) != ARCHIVE_SHA or manifest["archive_sha256"] != ARCHIVE_SHA:
        raise ValueError("frozen input archive identity")
    if archive.stat().st_size != manifest["archive_bytes"]:
        raise ValueError("archive size")
    entries = {e["path"]: e for e in manifest["files"]}
    if len(entries) != len(manifest["files"]) or len(entries) != 46:
        raise ValueError("input population")
    destination.mkdir()  # Occupied paths are never reused or cleaned.
    seen = set()
    total = 0
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf:
            name = member.name
            parts = PurePosixPath(name)
            if (not member.isfile() or name not in entries or name in seen
                    or parts.is_absolute() or ".." in parts.parts or str(parts) != name):
                raise ValueError("unsafe/unknown/duplicate archive entry")
            row = entries[name]
            total += member.size
            if member.size != row["bytes"] or total > 100 * 1024 * 1024:
                raise ValueError("unpacked size bound")
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with tf.extractfile(member) as source, target.open("xb") as out:
                while chunk := source.read(1024 * 1024):
                    out.write(chunk)
            if digest(target) != row["sha256"]:
                raise ValueError("unpacked input identity")
            seen.add(name)
    if seen != entries.keys() or total != manifest["unpacked_bytes"]:
        raise ValueError("incomplete frozen inputs")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def executable(capture, target_name):
    found = set()
    for line in capture.read_text().splitlines():
        row = json.loads(line)
        if row.get("reason") == "compiler-artifact" and row["target"]["name"] == target_name and row.get("executable"):
            found.add(row["executable"])
    if len(found) != 1:
        raise ValueError("missing/ambiguous built executable: " + target_name)
    return Path(found.pop()).resolve(strict=True)


def capture(root, label, argv, cwd, env):
    with (root / (label + ".stdout")).open("xb") as out, (root / (label + ".stderr")).open("xb") as err:
        result = subprocess.run([str(a) for a in argv], cwd=cwd, env=env, stdout=out, stderr=err)
    write_new(root / (label + ".result.json"), {"argv": [str(a) for a in argv], "exit_code": result.returncode})
    if result.returncode:
        raise ValueError(label + " failed; captured outcome preserved; no retry")


def run_native_ci(root):
    env = os.environ.copy()
    event = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text())
    require_route(env, event)
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("required Apple native CI host")
    sha = git(CONTROLLER, "rev-parse", "HEAD")
    if sha != env["GITHUB_SHA"] or git(CONTROLLER, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("workflow checkout drift")
    root.mkdir()
    summary = {"candidate": CANDIDATE, "candidate_tree": TREE, "controller_commit": sha,
               "event": env["GITHUB_EVENT_NAME"], "ref": env["GITHUB_REF"], "inputs": event["inputs"],
               "run_id": env["GITHUB_RUN_ID"], "run_attempt": 1, "host_role": "native-ci",
               "M1a_ran": False, "M1a_passed": False, "raw_probe_used": 0,
               "shipping_default": "copied", "M1b_ran": False, "stage": "admission"}
    try:
        summary["admission"] = reconcile_admission(root, env["GITHUB_RUN_ID"], sha)
        write_new(root / "campaign-claim.json", summary)
        summary["stage"] = "prepare"
        source = root / "source"
        subprocess.run(["git", "-C", str(CONTROLLER), "worktree", "add", "--detach", str(source), CANDIDATE], check=True)
        if git(source, "rev-parse", "HEAD^{tree}") != TREE or git(source, "status", "--porcelain"):
            raise ValueError("compiled candidate tree/cleanliness")
        inputs = root / "inputs"
        manifest = json.loads((CONTROLLER / "scripts/ci" / (STEM + ".json")).read_text())
        extract_inputs(CONTROLLER / "scripts/ci" / (STEM + ".tar.gz"), manifest, inputs)
        prefix = Path(env["MLX_C_PREFIX"]).resolve(strict=True)
        if prefix != Path(env["MLX_PREFIX"]).resolve(strict=True):
            raise ValueError("one existing pinned prefix required")
        native_source = Path(env["RUNNER_TEMP"]) / "pulsar-native-mlx-source"
        pins = {"mlx": "68cf2fddd8de5edd8ab3d926391772b2e2cedad8", "mlx-c": "0726ca922fc902c4c61ef9c27d94132be418e945"}
        if any(git(native_source / name, "rev-parse", "HEAD") != pin for name, pin in pins.items()):
            raise ValueError("existing native source pins")
        receipt = root / "native-build-receipt.json"
        write_new(receipt, {"source_pins": pins, "installer_sha256": digest(source / "scripts/ci/install_native_mlx.sh"),
                           "installer_result": "preceding unchanged workflow installation step succeeded",
                           "native_source_diff_sha256": {n: hashlib.sha256(subprocess.check_output(["git", "-C", str(native_source / n), "diff", "--binary"])).hexdigest() for n in pins},
                           "patches": {p.name: digest(p) for p in native_source.glob("*.patch")},
                           "run_id": env["GITHUB_RUN_ID"], "workflow_commit": sha})
        env.update(CARGO_BUILD_JOBS="2", RUST_TEST_THREADS="1", CARGO_TARGET_DIR=str(root / "target-native"),
                   PYTHONDONTWRITEBYTECODE="1", PULSAR_ADOPTION_PHASE="m1a")
        # This separate workspace has five locked versions absent from the root
        # lockfile. Prepare those exact inputs on the authorized hosted installer
        # route, then build offline. This is never a Studio cache-repair command.
        summary["stage"] = "frozen-Cargo-inputs"
        capture(root, "dependency-fetch", ["cargo", "fetch", "--locked", "--manifest-path",
                "experiments/packed-affine-adoption/Cargo.toml"], source, env)
        cargo = ["cargo", "test", "--offline", "--locked", "--release", "--manifest-path",
                 "experiments/packed-affine-adoption/Cargo.toml", "--features", "native-adoption",
                 "--test", "adoption_parent", "--no-run", "--message-format=json"]
        summary["stage"] = "native-build"
        capture(root, "native-build", cargo, source, env)
        child = executable(root / "native-build.stdout", "adoption-probe")
        parent = executable(root / "native-build.stdout", "adoption_parent")
        env["CARGO_TARGET_DIR"] = str(root / "target-host")
        capture(root, "grader-build", ["cargo", "build", "--offline", "--locked", "--release", "--manifest-path",
                "experiments/packed-affine-adoption/Cargo.toml", "--bin", "grade-rust", "--message-format=json"], source, env)
        grader = executable(root / "grader-build.stdout", "grade-rust")
        for label, binary in (("child", child), ("parent", parent), ("grader", grader)):
            capture(root, label + "-linkage", ["/usr/bin/otool", "-L", binary], source, env)
        campaign = root / "campaign"
        summary["stage"] = "freeze"
        capture(root, "freeze", [sys.executable, "-B", "experiments/packed-affine-adoption/tools/freeze_host.py",
                "--host-role", "native-ci", "--source-commit", CANDIDATE, "--campaign", campaign,
                "--fixture-root", inputs / "fixtures", "--portable", inputs / "portable.json", "--reference", inputs / "reference.json",
                "--native-prefix", prefix, "--native-build-receipt", receipt, "--binary", child, "--parent", parent, "--rust-grader", grader], source, env)
        # Parent has an early M1b branch. Explicit selection is essential.
        env.update(PULSAR_ADOPTION_HOST_ROLE="native-ci", PULSAR_ADOPTION_CAMPAIGN=str(campaign))
        require_route(env, event)
        summary.update(stage="M1a", M1a_ran=True)
        capture(root, "M1a", [parent, "--exact", "required_native_m1a", "--test-threads=1", "--nocapture"], source, env)
        summary["stage"] = "original-byte-numerical-qualification"
        capture(root, "qualification", [sys.executable, "-B", "experiments/packed-affine-adoption/tools/qualify_reports.py", campaign, "--rust-grader", grader], source, env)
        acceptance = json.loads((campaign / "m1a-acceptance.json").read_text())
        if acceptance["correctness"] != "PASS" or acceptance["mechanism"] != "PASS" or len(acceptance["reports"]) != 52:
            raise ValueError("incomplete M1a acceptance")
        summary.update(stage="complete", M1a_passed=True, acceptance_sha256=digest(campaign / "m1a-acceptance.json"))
    except BaseException as e:
        summary["failure_type"] = type(e).__name__
        summary["failure"] = str(e)
        raise
    finally:
        if (root / "admission-evidence.json").exists():
            summary["admission_evidence_sha256"] = digest(root / "admission-evidence.json")
        summary["raw_probe_used"] = int((root / "campaign/raw-probe.intent.json").exists())
        summary["raw_probe_outcome_known"] = (root / "campaign/m1a/raw-probe-summary.json").exists()
        write_new(root / "result.json", summary)


def public_text(text, roots):
    for path, label in sorted(roots, key=lambda x: len(x[0]), reverse=True):
        text = text.replace(path, label)
    text = re.sub(r"/(?:Users|home)/[^/\s\"']+", "<HOME>", text)
    text = re.sub(r"/private/(?:var|tmp)/[^\s\"']+", "<HOST_TEMP_PATH>", text)
    # Retain all evidence privately; a public view cannot carry credential-like
    # material. Refusal is safer than guessing a redaction of an unknown secret.
    if re.search(r"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|sk-ant-|Bearer\s+\S+|https?://ntfy\.[^\s]+)", text, re.I):
        raise ValueError("credential/destination-like content; upload refused")
    return text


def export_public(root, destination):
    destination.mkdir()
    roots = [(str(root), "<CAMPAIGN_ROOT>"), (str(CONTROLLER), "<WORKFLOW_ROOT>")]
    for name, label in (("RUNNER_TEMP", "<RUNNER_TEMP>"), ("MLX_C_PREFIX", "<NATIVE_PREFIX>"), ("HOME", "<HOME>")):
        if os.environ.get(name):
            roots.append((os.environ[name], label))
    rows = []
    paths = sorted(p for p in root.glob("*") if p.is_file())
    paths += sorted(p for p in (root / "campaign").rglob("*") if p.is_file())
    for p in paths:
        if p.is_symlink():
            raise ValueError("evidence symlink")
        relative = p.relative_to(root)
        data = p.read_bytes()
        if p.suffix != ".f32":
            # Campaign outputs use .bin for saved f32 tensors.
            if p.suffix != ".bin":
                data = public_text(data.decode("utf-8"), roots).encode()
        out = destination / relative
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("xb") as f:
            f.write(data)
        rows.append({"path": str(relative), "original_sha256": digest(p), "public_sha256": digest(out), "changed": data != p.read_bytes()})
    result = json.loads((root / "result.json").read_text()) if (root / "result.json").exists() else {"M1a_ran": False, "M1a_passed": False, "reason": "controller not entered; inspect required preceding steps"}
    write_new(destination / "public-view-manifest.json", {"files": rows, "note": "Original-byte qualification precedes path sanitization. Changed views do not satisfy original-byte hashes."})
    summary = public_text(json.dumps(result, sort_keys=True), roots)
    with open(os.environ.get("GITHUB_STEP_SUMMARY", os.devnull), "a") as f:
        f.write("\nPacked-affine M1a: `" + summary + "`\n")
    print(summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("run", "export"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--public", type=Path)
    args = parser.parse_args()
    if args.command == "run":
        run_native_ci(args.root)
    else:
        if args.public is None:
            parser.error("--public required")
        export_public(args.root, args.public)
