#!/usr/bin/env python3
"""Independent reread qualification; no synthetic record is a mutation kill."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import sys

spec = importlib.util.spec_from_file_location("q_capture", Path(__file__).with_name("q_capture.py"))
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = q.clean_env(args.root)
    cases = [
        ("exit0", "print('ordinary success')", "CLOSED", 0, None, {}),
        ("exit134", "raise SystemExit(134)", "CLOSED", 134, None, {}),
        ("native-signal", "import os,signal; os.kill(os.getpid(),signal.SIGTERM)", "CLOSED", None, signal.SIGTERM, {}),
        ("separation", "import os; os.write(1,b'stdout-only\\n'); os.write(2,b'stderr-only\\n')", "CLOSED", 0, None, {}),
        ("missing-executable", None, "SPAWN_ERROR", None, None, {}),
        ("timeout-cleanup", "import subprocess,sys,signal,time; child=subprocess.Popen([sys.executable,'-I','-B','-c','import time;time.sleep(30)']); print(child.pid,flush=True); signal.signal(signal.SIGTERM,lambda *_:(child.terminate(),child.wait(),sys.exit(0))); time.sleep(30)", "TIMEOUT", 0, None, {"timeout": 0.5}),
        ("persistence-failure", "import os,time; os.write(1,b'prefix\\n'); time.sleep(.1); os.write(1,b'failure\\n'); time.sleep(30)", "EVIDENCE_INCOMPLETE", None, signal.SIGTERM, {"inject_failure": True}),
        ("limit-failure", "import os; os.write(1,b'x'*128)", "EVIDENCE_INCOMPLETE", None, None, {"limit": 16}),
    ]
    manifests = []
    for name, code, status, expected_code, expected_signal, options in cases:
        case = output / name
        argv = [sys.executable, "-I", "-B", "-c", code] if code is not None else [str(output / "does-not-exist")]
        result = q.capture(argv, args.root, env, case, **options)
        terminal = json.loads((case / "terminal.json").read_bytes())
        require(terminal == result, name + ": terminal differs from returned result")
        require(terminal["status"] == status and terminal["reaped"], name + ": status/reaping mismatch")
        if name != "limit-failure":
            require(terminal["code"] == expected_code and terminal["native_signal"] == expected_signal, name + ": exit vs signal mismatch")
        lifecycle = [json.loads(line) for line in (case / "lifecycle.jsonl").read_text().splitlines()]
        require(lifecycle[-1]["event"] == "CLOSE", name + ": missing close")
        for key in terminal:
            require(lifecycle[-1][key] == terminal[key], name + ": lifecycle terminal mismatch")
        for stream in ("stdout", "stderr"):
            require((case / (stream + ".raw")).stat().st_size == terminal["stream_bytes"][stream], name + ": byte count mismatch")
        if name == "separation":
            require((case / "stdout.raw").read_bytes() == b"stdout-only\n" and (case / "stderr.raw").read_bytes() == b"stderr-only\n", "stream separation failed")
        if name == "persistence-failure":
            require((case / "stdout.raw").read_bytes() == b"prefix\n", "incomplete prefix was not preserved")
        if name == "timeout-cleanup":
            descendant = int((case / "stdout.raw").read_bytes().strip())
            for pid, group in ((terminal["child_pid"], False), (terminal["child_pid"], True), (descendant, False)):
                try:
                    (os.killpg if group else os.kill)(pid, 0)
                except ProcessLookupError:
                    pass
                else:
                    raise RuntimeError("owned timeout process/group remains")
        rows = []
        for path in sorted(case.iterdir()):
            require(path.is_file() and not path.is_symlink() and path.stat().st_mode & 0o777 == 0o600, "capture file protection failed")
            rows.append({"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        require(len(rows) == 5, name + ": actual inventory mismatch")
        manifests.append({"case": name, "terminal": terminal, "actual_files": rows})
        print("CAPTURE_SYNTHETIC_PASS " + name, flush=True)
    # Open failure must prevent spawning, preserve any already-created prefix,
    # and remain explicitly incomplete. This does not overwrite earlier cases.
    original = q.exclusive
    def fail_stderr(path):
        if str(path).endswith("stderr.raw"):
            raise OSError("injected capture open failure")
        return original(path)
    q.exclusive = fail_stderr
    try:
        case = output / "open-failure"
        result = q.capture([sys.executable, "-I", "-B", "-c", "print('must not spawn')"], args.root, env, case)
    finally:
        q.exclusive = original
    terminal = json.loads((case / "terminal.json").read_bytes())
    require(terminal == result and terminal["status"] == "EVIDENCE_INCOMPLETE" and terminal["child_pid"] is None, "open failure was not closed without spawn")
    rows = [{"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(case.iterdir())]
    require({row["path"].split("/")[-1] for row in rows} == {"stdout.raw", "terminal.json"}, "open failure inventory was fabricated")
    manifests.append({"case": "open-failure", "terminal": terminal, "actual_files": rows})
    # Interrupt an actual nested supervisor. It must preserve an incomplete
    # terminal and reap its separately owned child group before returning.
    nested = output / "interrupted-inner"
    helper = "import sys,threading,time,os,signal; sys.path.insert(0," + repr(str(Path(__file__).parent)) + "); import q_capture; threading.Thread(target=lambda:(time.sleep(.2),os.kill(os.getpid(),signal.SIGTERM)),daemon=True).start(); result=q_capture.capture([sys.executable,'-I','-B','-c','import time;print(\\\"prefix\\\",flush=True);time.sleep(30)']," + repr(args.root) + ",q_capture.clean_env(" + repr(args.root) + ")," + repr(str(nested)) + "); print(result); raise SystemExit(3)"
    outer = output / "interrupted-outer"
    result = q.capture([sys.executable, "-I", "-B", "-c", helper], args.root, env, outer, termination_grace=5)
    inner = json.loads((nested / "terminal.json").read_bytes())
    require(result["status"] == "CLOSED" and result["code"] == 3 and inner["status"] == "EVIDENCE_INCOMPLETE" and inner["reaped"], "supervisor interruption was not truthfully closed")
    require("CaptureInterrupted" in inner["capture_error"] and (nested / "stdout.raw").read_bytes() == b"prefix\n", "interrupted prefix/error missing")
    try:
        os.killpg(inner["child_pid"], 0)
    except ProcessLookupError:
        pass
    else:
        raise RuntimeError("interrupted owned child group remains")
    for name, case, terminal in (("interrupted-inner", nested, inner), ("interrupted-outer", outer, result)):
        rows = [{"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(case.iterdir())]
        require(len(rows) == 5, "interruption actual inventory incomplete")
        manifests.append({"case": name, "terminal": terminal, "actual_files": rows})
    fd = q.exclusive(output / "qualification-manifest.json")
    try:
        q.write_all(fd, (json.dumps({"mode": "optimized" if sys.flags.optimize else "normal", "status": "CAPTURE_SYNTHETIC_QUALIFIED", "cases": manifests}, indent=2) + "\n").encode())
    finally:
        os.close(fd)
    print("CAPTURE_SYNTHETIC_QUALIFIED count=" + str(len(manifests)))


if __name__ == "__main__":
    main()
