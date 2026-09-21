"""MIT. Bounded stdlib-only GLM53-Flash research runner.

The parent validates the external workspace and creates an exclusive run.  The
internal child accepts an admission digest and nonce only over a parent pipe.
This is a misuse guard and evidence binding, not an operating-system security
boundary against another process running as the same user.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import resource
import secrets
import select
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest


MAX_RSS = 256 * 1024 * 1024
MAX_WALL = 120.0
NORMAL_CHILD_DEADLINE = 118.0
PROBE_CHILD_DEADLINE = 0.25
TERM_GRACE = 0.35
KILL_GRACE = 0.50
MAX_FILE_SIZE = 64 * 1024 * 1024
MAX_TEMP_LOGICAL_BYTES = 64 * 1024 * 1024
MAX_PHASE_LOGICAL_BYTES = 1024 * 1024 * 1024
MAX_PUBLIC_FIXTURE_BYTES = 256 * 1024
HISTORICAL_STORE_RUN_AGENT_ACCOUNTING_NOT_MEASURED_BYTES = 15_333
PATTERN_RE = re.compile(r"test_glm53_flash_[a-z0-9_*]+\.py")


def json_bytes(obj):
    return (json.dumps(obj, indent=2, allow_nan=False) + "\n").encode("utf-8")


def write_json(path, obj):
    path = Path(path)
    data = json_bytes(obj)
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def confined(root, path):
    root = Path(root).absolute()
    path = Path(path)
    if not path.is_absolute():
        path = root / path
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError("path escapes workspace")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("symlink path rejected")
        if part == root:
            break
    return path


def require_directory(root, path, label, *, writable=False):
    path = confined(root, path)
    if not path.exists() or not path.is_dir() or path.is_symlink():
        raise ValueError(f"{label} must be an existing real directory")
    if writable and not os.access(path, os.W_OK | os.X_OK):
        raise ValueError(f"{label} must be writable")
    return path


def verify_workspace(root, *, query_volume):
    root = Path(root).absolute()
    require_directory(root, root, "workspace", writable=True)
    binding_path = confined(root, root / "machine-binding.local.json")
    if not binding_path.is_file() or binding_path.is_symlink():
        raise ValueError("machine binding missing or unsafe")
    if stat.S_IMODE(binding_path.stat().st_mode) & 0o077:
        raise ValueError("machine binding must be owner-only")
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    if Path(binding["workspace"]) != root:
        raise ValueError("workspace binding mismatch")
    volume = binding["volume"]
    mount = Path(volume["MountPoint"]).resolve()
    if not root.resolve().is_relative_to(mount):
        raise ValueError("workspace is not beneath the bound external mount")
    if root.stat().st_dev != mount.stat().st_dev:
        raise ValueError("workspace and bound mount are on different devices")
    if query_volume:
        info = plistlib.loads(
            subprocess.check_output(
                ["diskutil", "info", "-plist", str(mount)], timeout=10
            )
        )
        if info.get("VolumeUUID") != volume["VolumeUUID"]:
            raise ValueError("volume identity changed")
        if info.get("MountPoint") != volume["MountPoint"]:
            raise ValueError("volume mount point changed")
        if info.get("Internal") is not False:
            raise ValueError("external mount not established")
        if info.get("ReadOnlyVolume") or info.get("ReadOnlyMedia"):
            raise ValueError("read-only volume")
        if info.get("FilesystemType") != volume.get("FilesystemType"):
            raise ValueError("filesystem identity changed")

    roles = {}
    for name, value in binding["roles"].items():
        role = confined(root, value)
        roles[name] = role
        if role.exists() and role.stat().st_dev != root.stat().st_dev:
            raise ValueError(f"role {name} is on a different device")
    required = ("source_repo", "planning_repo", "cache", "temporary", "runs", "evidence")
    if any(name not in roles for name in required):
        raise ValueError("binding lacks a required role")
    source_repo = require_directory(root, roles["source_repo"], "source repo")
    planning_repo = require_directory(root, roles["planning_repo"], "planning repo")
    cache = require_directory(root, roles["cache"], "cache", writable=True)
    temporary = require_directory(root, roles["temporary"], "temporary", writable=True)
    runs = require_directory(root, roles["runs"], "runs", writable=True)
    evidence = require_directory(root, roles["evidence"], "evidence", writable=True)
    if temporary.resolve() != (cache / "tmp").resolve():
        raise ValueError("temporary role is not the admitted cache/tmp")

    expected_script = source_repo / "scripts/research/glm53_flash/supervise.py"
    script = Path(__file__).resolve()
    if script != expected_script.resolve():
        raise ValueError("supervisor is not the bound public source file")
    confined(root, script)
    if script.stat().st_dev != root.stat().st_dev:
        raise ValueError("supervisor is not on the bound device")
    tests = require_directory(
        root, source_repo / "scripts/research/tests", "Flash tests"
    )
    return {
        "root": root,
        "binding": binding,
        "mount": mount,
        "roles": roles,
        "source_repo": source_repo,
        "planning_repo": planning_repo,
        "cache": cache,
        "temporary": temporary,
        "runs": runs,
        "evidence": evidence,
        "script": script,
        "tests": tests,
    }


def validate_pattern(pattern):
    if not isinstance(pattern, str) or not PATTERN_RE.fullmatch(pattern):
        raise ValueError("only bounded Flash unittest file patterns are allowed")
    return pattern


def regular_files(root, path, *, required=False):
    """Return sorted regular files without following any symlink."""
    path = confined(root, path)
    if not path.exists():
        if required:
            raise ValueError(f"required path missing: {path.name}")
        return []
    if path.is_symlink():
        raise ValueError("symlink in owned phase path")
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise ValueError("non-file object in owned phase path")
    found = []
    stack = [path]
    while stack:
        directory = stack.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                entry_path = Path(entry.path)
                if entry.is_symlink():
                    raise ValueError("symlink in owned phase tree")
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry_path)
                elif entry.is_file(follow_symlinks=False):
                    found.append(entry_path)
                else:
                    raise ValueError("unsupported object in owned phase tree")
    return sorted(found, key=lambda item: str(item))


def manifest_records(context, pattern):
    root = context["root"]
    source_repo = context["source_repo"]
    source_dir = source_repo / "scripts/research/glm53_flash"
    docs_dir = source_repo / "docs/glm53-flash/tiny-reference-v1"
    fixture_dir = source_repo / "fixtures/research/glm53-flash-tiny-v1"
    tests = sorted(context["tests"].glob(pattern), key=lambda item: item.name)
    if not tests:
        raise ValueError("test pattern matched no files")
    groups = (
        ("source", regular_files(root, source_dir, required=True)),
        ("contract", regular_files(root, docs_dir, required=True)),
        ("fixture", regular_files(root, fixture_dir, required=True)),
        ("test", tests),
    )
    records = []
    seen = set()
    for role, paths in groups:
        for path in paths:
            path = confined(root, path)
            if path.is_symlink() or not path.is_file():
                raise ValueError("manifest input is not a regular file")
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            records.append(
                {
                    "role": role,
                    "path": str(resolved.relative_to(source_repo.resolve())),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    records.sort(key=lambda item: (item["role"], item["path"]))
    return records


def manifest_digest(records):
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def phase_roots(context):
    source = context["source_repo"]
    planning = context["planning_repo"]
    root = context["root"]
    return (
        ("public_docs", source / "docs/glm53-flash/tiny-reference-v1"),
        ("public_scripts", source / "scripts/research/glm53_flash"),
        ("public_tests", source / "scripts/research/tests"),
        ("public_fixtures", source / "fixtures/research/glm53-flash-tiny-v1"),
        ("private_phase", planning / "GLM53-Flash/tiny-reference-v1"),
        ("external_evidence", root / "evidence/tiny-reference-v1"),
        ("external_runs", root / "runs/tiny-reference-v1"),
        ("external_temporary", context["temporary"]),
    )


def phase_inventory(context):
    summaries = []
    total = 0
    fixture_total = 0
    temporary_total = 0
    for role, path in phase_roots(context):
        if role == "public_tests":
            paths = sorted(path.glob("test_glm53_flash_*.py"), key=lambda item: item.name) if path.exists() else []
            for candidate in paths:
                confined(context["root"], candidate)
                if candidate.is_symlink() or not candidate.is_file():
                    raise ValueError("unsafe Flash test inventory entry")
        else:
            paths = regular_files(context["root"], path)
        logical = 0
        for candidate in paths:
            size = candidate.stat().st_size
            logical += size
            if role == "public_fixtures" and size > MAX_PUBLIC_FIXTURE_BYTES:
                raise ValueError("committed public fixture exceeds 256 KiB")
        total += logical
        if role == "public_fixtures":
            fixture_total = logical
        if role == "external_temporary":
            temporary_total = logical
        summaries.append(
            {
                "role": role,
                "exists": path.exists(),
                "files": len(paths),
                "logical_bytes": logical,
            }
        )
    if fixture_total > MAX_TEMP_LOGICAL_BYTES:
        raise ValueError("generated fixture aggregate exceeds 64 MiB")
    if temporary_total > MAX_TEMP_LOGICAL_BYTES:
        raise ValueError("temporary aggregate exceeds 64 MiB")
    if total > MAX_PHASE_LOGICAL_BYTES:
        raise ValueError("owned phase aggregate exceeds 1 GiB")
    return {
        "roots": summaries,
        "total_phase_logical_bytes": total,
        "public_fixture_logical_bytes": fixture_total,
        "temporary_current_logical_bytes": temporary_total,
        "limits": {
            "phase_logical_bytes": MAX_PHASE_LOGICAL_BYTES,
            "generated_fixture_logical_bytes": MAX_TEMP_LOGICAL_BYTES,
            "temporary_logical_bytes": MAX_TEMP_LOGICAL_BYTES,
            "public_fixture_each_bytes": MAX_PUBLIC_FIXTURE_BYTES,
            "run_artifacts": "NO_SEPARATE_CEILING_INCLUDED_IN_PHASE_TOTAL",
        },
        "historical_store_run_agent_accounting_not_measured_bytes": (
            HISTORICAL_STORE_RUN_AGENT_ACCOUNTING_NOT_MEASURED_BYTES
        ),
    }


def tree_logical_bytes(root, path):
    return sum(candidate.stat().st_size for candidate in regular_files(root, path))


def child_admission(args):
    """Validate that this child was admitted by the external parent run."""
    if sys.stdin.isatty() or not stat.S_ISFIFO(os.fstat(sys.stdin.fileno()).st_mode):
        raise ValueError("internal child requires a parent pipe admission")
    ready, _, _ = select.select([sys.stdin], [], [], 1.0)
    if not ready:
        raise ValueError("parent pipe admission timed out")
    line = sys.stdin.buffer.readline(1025)
    if len(line) > 1024 or not line.endswith(b"\n"):
        raise ValueError("invalid parent admission frame")
    frame = json.loads(line.decode("utf-8"))
    nonce = frame.get("nonce")
    admission_sha256 = frame.get("admission_sha256")
    if not isinstance(nonce, str) or not re.fullmatch(r"[0-9a-f]{64}", nonce):
        raise ValueError("invalid parent nonce")
    if not isinstance(admission_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", admission_sha256):
        raise ValueError("invalid admission digest")
    context = verify_workspace(args.workspace, query_volume=False)
    validate_pattern(args.pattern)
    run_dir = confined(
        context["root"], context["runs"] / "tiny-reference-v1" / args.run_name
    )
    if not run_dir.is_dir() or run_dir.is_symlink():
        raise ValueError("admitted run directory missing or unsafe")
    admission_path = run_dir / "admission.json"
    prefix_path = run_dir / "prefix.json"
    if sha256_file(admission_path) != admission_sha256:
        raise ValueError("admission bytes changed")
    admission = json.loads(admission_path.read_text(encoding="utf-8"))
    if hashlib.sha256(nonce.encode("ascii")).hexdigest() != admission["nonce_sha256"]:
        raise ValueError("parent nonce mismatch")
    if admission["parent_pid"] != os.getppid():
        raise ValueError("admitting parent changed")
    if admission["run_name"] != args.run_name or admission["mode"] != args.mode:
        raise ValueError("child mode/run differs from admission")
    if admission["pattern"] != args.pattern:
        raise ValueError("child pattern differs from admission")
    if sha256_file(prefix_path) != admission["prefix_sha256"]:
        raise ValueError("admitted prefix bytes changed")
    if sha256_file(context["script"]) != admission["script_sha256"]:
        raise ValueError("supervisor bytes changed before child start")
    if Path.cwd().resolve() != context["source_repo"].resolve():
        raise ValueError("child cwd is not the bound source repo")
    expected_temp = context["temporary"].resolve()
    for name in ("TMPDIR", "TMP", "TEMP"):
        if Path(os.environ.get(name, "")).resolve() != expected_temp:
            raise ValueError(f"{name} is not the admitted external temporary path")
    tempfile.tempdir = None
    if Path(tempfile.gettempdir()).resolve() != expected_temp:
        raise ValueError("tempfile selected a fallback directory")
    manifest = manifest_records(context, args.pattern)
    digest = manifest_digest(manifest)
    if digest != admission["input_manifest_sha256"]:
        raise ValueError("input manifest changed before child start")
    write_json(
        run_dir / "started.json",
        {
            "schema": "flash-supervision-child-start-v2",
            "started_utc": utc_now(),
            "pid": os.getpid(),
            "parent_pid": os.getppid(),
            "nonce_sha256": admission["nonce_sha256"],
            "admission_sha256": admission_sha256,
            "input_manifest_sha256": digest,
            "temp_role_verified": "external_temporary",
            "cwd_role_verified": "source_repo",
        },
    )
    return context, run_dir, admission, digest


def child(args):
    resource.setrlimit(resource.RLIMIT_CPU, (120, 120))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_SIZE, MAX_FILE_SIZE))
    context, run_dir, admission, pre_digest = child_admission(args)
    exit_code = 1
    result = {}
    try:
        if args.mode in ("timeout-probe", "cancel-probe"):
            time.sleep(10)
        elif args.mode == "preflight":
            if 17 + 25 != 42:
                raise AssertionError("source-free arithmetic preflight failed")
            if sum([0.125, 0.25, 0.625]) != 1.0:
                raise AssertionError("exact arithmetic preflight failed")
            payload = b"Flash synthetic file roundtrip\x00\x01\x7f\xff"
            with tempfile.TemporaryDirectory(
                prefix="flash-preflight-", dir=context["temporary"]
            ) as directory:
                fixture = Path(directory) / "fixture.bin"
                with fixture.open("xb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                if fixture.read_bytes() != payload:
                    raise AssertionError("external file roundtrip failed")
            result = {
                "arithmetic": "PASS",
                "roundtrip": "PASS",
                "fixture_bytes": len(payload),
                "fixture_sha256": hashlib.sha256(payload).hexdigest(),
            }
            exit_code = 0
        else:
            suite = unittest.defaultTestLoader.discover(
                str(context["tests"]), pattern=args.pattern
            )
            run = unittest.TextTestRunner(verbosity=2).run(suite)
            result = {
                "tests_run": run.testsRun,
                "failures": len(run.failures),
                "errors": len(run.errors),
                "skips": len(run.skipped),
            }
            exit_code = 0 if run.wasSuccessful() and run.testsRun else 1
    finally:
        try:
            post_digest = manifest_digest(manifest_records(context, args.pattern))
            drift = post_digest != pre_digest
        except BaseException as exc:
            post_digest = None
            drift = True
            result["manifest_post_error"] = type(exc).__name__
        if drift:
            exit_code = 1
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            peak *= 1024
        result.update(
            {
                "peak_rss_bytes": peak,
                "rss_scope": "DIRECT_CHILD_ONLY",
                "descendants": "FORBIDDEN_NOT_MEASURED",
                "exit_code": exit_code,
                "input_manifest_pre_sha256": pre_digest,
                "input_manifest_post_sha256": post_digest,
                "input_manifest_drift": drift,
                "admitted_deadline_seconds": admission["effective_child_deadline_seconds"],
            }
        )
        write_json(run_dir / "child.json", result)
    return exit_code


def sample_direct_rss(pid, timeout):
    try:
        completed = subprocess.run(
            ["/bin/ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            timeout=max(0.01, timeout),
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None
    value = completed.stdout.strip()
    return int(value) * 1024 if value else None


def terminate_group(proc, child_start):
    evidence = {
        "term_sent_seconds": None,
        "kill_sent_seconds": None,
        "stopped_seconds": None,
        "kill_escalated": False,
        "kill_wait_timeout": False,
        "stop_confirmed": False,
        "term_process_missing": False,
        "kill_process_missing": False,
    }
    if proc.poll() is not None:
        evidence["stopped_seconds"] = time.monotonic() - child_start
        evidence["stop_confirmed"] = True
        return evidence
    evidence["term_sent_seconds"] = time.monotonic() - child_start
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        evidence["term_process_missing"] = True
    try:
        proc.wait(timeout=TERM_GRACE)
    except subprocess.TimeoutExpired:
        evidence["kill_escalated"] = True
        evidence["kill_sent_seconds"] = time.monotonic() - child_start
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            evidence["kill_process_missing"] = True
        try:
            proc.wait(timeout=KILL_GRACE)
        except subprocess.TimeoutExpired:
            evidence["kill_wait_timeout"] = True
            return evidence
    if proc.poll() is not None:
        evidence["stopped_seconds"] = time.monotonic() - child_start
        evidence["stop_confirmed"] = True
    return evidence


def build_environment(context):
    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith("PYTHON") or name.startswith("DYLD_") or name.startswith("LD_"):
            environment.pop(name, None)
    temporary = str(context["temporary"].resolve())
    environment.update(
        {
            "TMPDIR": temporary,
            "TMP": temporary,
            "TEMP": temporary,
            "XDG_CACHE_HOME": str(context["cache"].resolve()),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return environment


def stabilize_projected_sizes(context, run_dir, receipt, phase_bytes):
    """Include the not-yet-written receipt without hiding its own fields."""
    current_run = tree_logical_bytes(context["root"], run_dir)
    receipt.setdefault("declared_receipt_bytes", 0)
    receipt.setdefault("projected_run_logical_bytes_with_receipt", current_run)
    receipt.setdefault("projected_phase_logical_bytes_with_receipt", phase_bytes)
    for _ in range(12):
        encoded_size = len(json_bytes(receipt))
        projected_run = current_run + encoded_size
        projected_phase = phase_bytes + encoded_size
        values = (encoded_size, projected_run, projected_phase)
        old = (
            receipt["declared_receipt_bytes"],
            receipt["projected_run_logical_bytes_with_receipt"],
            receipt["projected_phase_logical_bytes_with_receipt"],
        )
        receipt["declared_receipt_bytes"] = encoded_size
        receipt["projected_run_logical_bytes_with_receipt"] = projected_run
        receipt["projected_phase_logical_bytes_with_receipt"] = projected_phase
        if values == old:
            return
    raise ValueError("receipt size projection did not stabilize")


def parent(args):
    validate_pattern(args.pattern)
    context = verify_workspace(args.workspace, query_volume=True)
    run_dir = confined(
        context["root"], context["runs"] / "tiny-reference-v1" / args.run_name
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    if run_dir.is_symlink() or run_dir.stat().st_dev != context["root"].stat().st_dev:
        raise ValueError("run directory is not a real directory on the bound device")

    pre_budget = phase_inventory(context)
    input_manifest = manifest_records(context, args.pattern)
    input_digest = manifest_digest(input_manifest)
    script_sha256 = sha256_file(context["script"])
    executable = Path(sys.executable).resolve()
    executable_sha256 = sha256_file(executable)
    effective_deadline = (
        PROBE_CHILD_DEADLINE
        if args.mode in ("timeout-probe", "cancel-probe")
        else NORMAL_CHILD_DEADLINE
    )
    portable_argv = [
        "{python}",
        "-B",
        "{source_repo}/scripts/research/glm53_flash/supervise.py",
        "--workspace",
        "{workspace}",
        "--run-name",
        args.run_name,
        "--mode",
        args.mode,
        "--pattern",
        args.pattern,
        "--internal-child",
    ]
    nonce = secrets.token_hex(32)
    prefix = {
        "schema": "flash-supervision-v2",
        "mode": args.mode,
        "pattern": args.pattern,
        "wall_limit_seconds": MAX_WALL,
        "effective_child_deadline_seconds": effective_deadline,
        "termination_grace_seconds": TERM_GRACE,
        "kill_grace_seconds": KILL_GRACE,
        "rss_limit_bytes": MAX_RSS,
        "rss_scope": "DIRECT_CHILD_ONLY",
        "descendants": "FORBIDDEN_NOT_MEASURED",
        "script_sha256": script_sha256,
        "python_version": sys.version,
        "python_executable": str(executable),
        "python_executable_role": "existing_interpreter",
        "python_executable_sha256": executable_sha256,
        "cwd_role": "source_repo",
        "portable_argv": portable_argv,
        "input_manifest": input_manifest,
        "input_manifest_sha256": input_digest,
        "budget_pre": pre_budget,
        "fixture_limit_scope": "FIXTURE_BYTES_ONLY_NOT_RECEIPTS_OR_TEST_OUTPUT",
        "volume_binding_verified": True,
        "workspace_under_bound_mount_verified": True,
        "same_device_verified": True,
        "ownership_enforcement": context["binding"]["volume"].get("GlobalPermissionsEnabled"),
        "encryption": context["binding"]["volume"].get("Encryption"),
        "started_utc": utc_now(),
    }
    prefix_path = run_dir / "prefix.json"
    write_json(prefix_path, prefix)
    prefix_sha256 = sha256_file(prefix_path)
    admission = {
        "schema": "flash-supervision-admission-v2",
        "parent_pid": os.getpid(),
        "run_name": args.run_name,
        "mode": args.mode,
        "pattern": args.pattern,
        "effective_child_deadline_seconds": effective_deadline,
        "nonce_sha256": hashlib.sha256(nonce.encode("ascii")).hexdigest(),
        "prefix_sha256": prefix_sha256,
        "script_sha256": script_sha256,
        "input_manifest_sha256": input_digest,
        "cwd_role": "source_repo",
        "temporary_role": "external_temporary",
    }
    admission_path = run_dir / "admission.json"
    write_json(admission_path, admission)
    admission_sha256 = sha256_file(admission_path)

    command = [
        sys.executable,
        "-B",
        str(context["script"]),
        "--workspace",
        str(context["root"]),
        "--run-name",
        args.run_name,
        "--mode",
        args.mode,
        "--pattern",
        args.pattern,
        "--internal-child",
    ]
    environment = build_environment(context)
    sampled_peak = 0
    sampled_temp_peak = pre_budget["temporary_current_logical_bytes"]
    reason = None
    termination = None
    supervisor_start = time.monotonic()
    stdout_path = run_dir / "stdout.txt"
    stderr_path = run_dir / "stderr.txt"
    with stdout_path.open("xb") as out, stderr_path.open("xb") as err:
        proc = subprocess.Popen(
            command,
            cwd=context["source_repo"],
            env=environment,
            stdin=subprocess.PIPE,
            stdout=out,
            stderr=err,
            start_new_session=True,
        )
        child_start = time.monotonic()
        try:
            frame = json.dumps(
                {"nonce": nonce, "admission_sha256": admission_sha256},
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            proc.stdin.write(frame)
            proc.stdin.flush()
            proc.stdin.close()
            while proc.poll() is None:
                elapsed = time.monotonic() - child_start
                if elapsed >= effective_deadline:
                    reason = (
                        "CANCEL_INJECTED" if args.mode == "cancel-probe" else "TIMEOUT"
                    )
                    termination = terminate_group(proc, child_start)
                    break
                remaining = effective_deadline - elapsed
                rss = sample_direct_rss(proc.pid, min(0.10, remaining))
                if rss is not None:
                    sampled_peak = max(sampled_peak, rss)
                sampled_temp_peak = max(
                    sampled_temp_peak,
                    tree_logical_bytes(context["root"], context["temporary"]),
                )
                if sampled_temp_peak > MAX_TEMP_LOGICAL_BYTES:
                    reason = "TEMP_LIMIT"
                    termination = terminate_group(proc, child_start)
                    break
                if sampled_peak > MAX_RSS:
                    reason = "RSS_LIMIT"
                    termination = terminate_group(proc, child_start)
                    break
                if time.monotonic() - child_start >= effective_deadline:
                    reason = (
                        "CANCEL_INJECTED" if args.mode == "cancel-probe" else "TIMEOUT"
                    )
                    termination = terminate_group(proc, child_start)
                    break
                time.sleep(min(0.02, max(0.0, effective_deadline - (time.monotonic() - child_start))))
        except BaseException:
            if proc.poll() is None:
                termination = terminate_group(proc, child_start)
            if not (run_dir / "supervisor-interruption.json").exists():
                write_json(
                    run_dir / "supervisor-interruption.json",
                    {
                        "child_returncode": proc.returncode,
                        "termination": termination,
                        "observed_utc": utc_now(),
                    },
                )
            raise
    child_elapsed = time.monotonic() - child_start
    supervisor_elapsed = time.monotonic() - supervisor_start
    stop_unknown = bool(termination and not termination.get("stop_confirmed"))
    child_path = run_dir / "child.json"
    child_result = (
        json.loads(child_path.read_text(encoding="utf-8")) if child_path.exists() else None
    )
    started_path = run_dir / "started.json"
    started = (
        json.loads(started_path.read_text(encoding="utf-8"))
        if started_path.exists()
        else None
    )
    peak = max(sampled_peak, child_result["peak_rss_bytes"] if child_result else 0)
    post_manifest = manifest_records(context, args.pattern)
    post_digest = manifest_digest(post_manifest)
    manifest_drift = post_digest != input_digest
    prefix_post_sha256 = sha256_file(prefix_path)
    admission_post_sha256 = sha256_file(admission_path)
    control_drift = (
        prefix_post_sha256 != prefix_sha256
        or admission_post_sha256 != admission_sha256
    )
    post_budget = phase_inventory(context)
    outputs = {
        "stdout": {
            "bytes": stdout_path.stat().st_size,
            "sha256": sha256_file(stdout_path),
            "stability": (
                "SNAPSHOT_CHILD_STOP_UNCONFIRMED"
                if stop_unknown
                else "FINAL_AFTER_CONFIRMED_CHILD_STOP"
            ),
        },
        "stderr": {
            "bytes": stderr_path.stat().st_size,
            "sha256": sha256_file(stderr_path),
            "stability": (
                "SNAPSHOT_CHILD_STOP_UNCONFIRMED"
                if stop_unknown
                else "FINAL_AFTER_CONFIRMED_CHILD_STOP"
            ),
        },
    }
    expected_reason = (
        "CANCEL_INJECTED" if args.mode == "cancel-probe" else "TIMEOUT"
    )
    signal_return = proc.returncode in (-signal.SIGTERM, -signal.SIGKILL)
    bounded_stop = bool(
        termination
        and termination.get("stop_confirmed") is True
        and termination["term_sent_seconds"] is not None
        and termination["stopped_seconds"] is not None
        and termination["stopped_seconds"] - termination["term_sent_seconds"]
        <= TERM_GRACE + KILL_GRACE + 0.10
    )
    started_valid = bool(
        started
        and started.get("admission_sha256") == admission_sha256
        and started.get("nonce_sha256") == admission["nonce_sha256"]
        and started.get("input_manifest_sha256") == input_digest
    )
    expected_cancel = bool(
        args.mode in ("timeout-probe", "cancel-probe")
        and reason == expected_reason
        and started_valid
        and signal_return
        and bounded_stop
        and child_elapsed <= effective_deadline + TERM_GRACE + KILL_GRACE + 0.10
    )
    ok = bool(
        args.mode not in ("timeout-probe", "cancel-probe")
        and proc.returncode == 0
        and child_result is not None
        and child_result.get("exit_code") == 0
        and child_result.get("input_manifest_drift") is False
        and not manifest_drift
        and not control_drift
        and peak <= MAX_RSS
        and sampled_temp_peak <= MAX_TEMP_LOGICAL_BYTES
        and child_elapsed <= MAX_WALL
        and not stop_unknown
        and post_budget["total_phase_logical_bytes"] <= MAX_PHASE_LOGICAL_BYTES
    )
    receipt = {
        "schema": "flash-supervision-receipt-v2",
        "status": "PASS" if ok else "EXPECTED_CANCELLATION" if expected_cancel else "FAIL",
        "returncode": proc.returncode,
        "reason": reason,
        "child_wall_seconds": None if stop_unknown else child_elapsed,
        "child_observation_seconds": child_elapsed,
        "child_stop_confirmed": not stop_unknown,
        "supervisor_wall_seconds": supervisor_elapsed,
        "wall_limit_seconds": MAX_WALL,
        "effective_child_deadline_seconds": effective_deadline,
        "termination": termination,
        "cancellation_evidence": {
            "child_started": started_valid,
            "signal_returncode": signal_return,
            "bounded_stop": bounded_stop,
            "expected_reason": expected_reason if args.mode in ("timeout-probe", "cancel-probe") else None,
        },
        "peak_rss_bytes": peak,
        "peak_kind": (
            "direct_child_getrusage_and_sampled"
            if child_result
            else "direct_child_sampled_lower_bound"
        ),
        "rss_scope": "DIRECT_CHILD_ONLY",
        "descendants": "FORBIDDEN_NOT_MEASURED",
        "temporary_sampled_peak_logical_bytes": sampled_temp_peak,
        "temporary_peak_kind": "SAMPLED_CURRENT_LOGICAL_BYTES_NOT_CUMULATIVE",
        "child": child_result,
        "input_manifest_pre_sha256": input_digest,
        "input_manifest_post_sha256": post_digest,
        "input_manifest_drift": manifest_drift,
        "prefix_sha256": prefix_sha256,
        "prefix_post_sha256": prefix_post_sha256,
        "admission_sha256": admission_sha256,
        "admission_post_sha256": admission_post_sha256,
        "control_file_drift": control_drift,
        "outputs": outputs,
        "budget_post_before_receipt": post_budget,
        "fixture_limit_scope": "FIXTURE_BYTES_ONLY_NOT_RECEIPTS_OR_TEST_OUTPUT",
        "portable_argv": portable_argv,
        "cwd_role": "source_repo",
        "python_executable_sha256": executable_sha256,
        "physical_io": "NOT_MEASURABLE",
        "map_unmap": "NOT_EXERCISED",
        "completed_utc": utc_now(),
    }
    stabilize_projected_sizes(
        context,
        run_dir,
        receipt,
        post_budget["total_phase_logical_bytes"],
    )
    if receipt["projected_phase_logical_bytes_with_receipt"] > MAX_PHASE_LOGICAL_BYTES:
        receipt["status"] = "FAIL"
        receipt["reason"] = receipt["reason"] or "PHASE_SIZE_LIMIT"
    # Status/reason changes can alter receipt length by a few bytes.
    stabilize_projected_sizes(
        context,
        run_dir,
        receipt,
        post_budget["total_phase_logical_bytes"],
    )
    write_json(run_dir / "receipt.json", receipt)
    print(json.dumps(receipt, allow_nan=False))
    return 0 if receipt["status"] in ("PASS", "EXPECTED_CANCELLATION") else 1


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace")
    parser.add_argument("--run-name")
    parser.add_argument(
        "--mode",
        choices=("preflight", "tests", "timeout-probe", "cancel-probe"),
        default="tests",
    )
    parser.add_argument("--pattern", default="test_glm53_flash_*.py")
    parser.add_argument("--internal-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (
        not args.workspace
        or not args.run_name
        or not re.fullmatch(r"[a-z0-9-]{1,60}", args.run_name)
    ):
        parser.error("workspace and a unique bounded run-name required")
    try:
        validate_pattern(args.pattern)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def main():
    args = parse_args()
    if args.internal_child:
        return child(args)
    return parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
