#!/usr/bin/env python3
"""Exclusive, durable subprocess capture for the graph-owned Q lane."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

STREAM_LIMIT = 64 * 1024 * 1024


class CaptureInterrupted(BaseException):
    """Distinct from InterruptedError, which selectors may suppress."""
    pass


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exclusive(path):
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)


def write_all(fd, data):
    view = memoryview(data)
    while view:
        count = os.write(fd, view)
        if count <= 0:
            raise OSError("capture persistence failed")
        view = view[count:]
    os.fsync(fd)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def capture(argv, cwd, env, output, timeout=120, limit=STREAM_LIMIT, inject_failure=False, termination_grace=0.5):
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    start = time.monotonic()
    child = None
    fds = {}
    counts = {"stdout": 0, "stderr": 0}
    failure = None
    spawn_error = None
    timed_out = False
    terminal = None
    selector = selectors.DefaultSelector()
    lifecycle = None
    previous_signals = {}

    def interrupted(signum, _frame):
        raise CaptureInterrupted("supervisor interrupted by signal " + str(signum))

    def event(kind, **extra):
        write_all(lifecycle, (json.dumps({"event": kind, "wall": utc(), "monotonic": time.monotonic(), **extra}, sort_keys=True) + "\n").encode())

    def stop_owned():
        if child is None:
            return
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=termination_grace)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_signals[signum] = signal.signal(signum, interrupted)
        for name in ("stdout", "stderr"):
            fds[name] = exclusive(output / (name + ".raw"))
        lifecycle = os.open(output / "lifecycle.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        executable = Path(argv[0]).resolve()
        script_identities = []
        for argument in argv[1:]:
            candidate = Path(argument)
            if not candidate.is_absolute():
                candidate = Path(cwd) / candidate
            if candidate.suffix in {".py", ".sh", ".rs"} and candidate.is_file():
                script_identities.append({"path": str(candidate.resolve()), "sha256": digest(candidate)})
        launch = {"argv": argv, "cwd": str(cwd), "environment_keys": sorted(env), "executable": str(executable), "executable_sha256": digest(executable) if executable.is_file() else None, "script_identities": script_identities, "supervisor_pid": os.getpid(), "supervisor_sha256": digest(__file__), "timeout_seconds": timeout, "termination_grace_seconds": termination_grace, "stream_limit_bytes": limit, "started_wall": utc(), "started_monotonic": start}
        fd = exclusive(output / "launch.json")
        try:
            write_all(fd, (json.dumps(launch, indent=2) + "\n").encode())
        finally:
            os.close(fd)
        event("PRECREATED")
        try:
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        except OSError as exc:
            spawn_error = type(exc).__name__ + ": " + str(exc)
            event("SPAWN_ERROR", error=spawn_error)
        if child is not None:
            event("SPAWN", child_pid=child.pid, process_group=child.pid)
            for name in ("stdout", "stderr"):
                stream = getattr(child, name)
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, name)
            while selector.get_map():
                if time.monotonic() - start >= timeout:
                    timed_out = True
                    event("TIMEOUT")
                    stop_owned()
                    break
                for key, _ in selector.select(timeout=0.05):
                    data = os.read(key.fileobj.fileno(), 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    name = key.data
                    if inject_failure and sum(counts.values()) > 0:
                        raise OSError("injected persistence failure")
                    if counts[name] + len(data) > limit:
                        available = max(0, limit - counts[name])
                        write_all(fds[name], data[:available])
                        counts[name] += available
                        raise OSError("capture stream limit exceeded")
                    write_all(fds[name], data)
                    counts[name] += len(data)
            if not timed_out:
                child.wait(timeout=max(0.01, timeout - (time.monotonic() - start)))
            # Kill any remaining members even when the leader exited normally.
            stop_owned()
    except BaseException as exc:
        failure = type(exc).__name__ + ": " + str(exc)
        stop_owned()
    finally:
        if child is not None:
            stop_owned()
        code = child.returncode if child is not None else None
        terminal = {"status": "EVIDENCE_INCOMPLETE" if failure else "TIMEOUT" if timed_out else "SPAWN_ERROR" if spawn_error else "CLOSED", "code": code if code is None or code >= 0 else None, "native_signal": -code if code is not None and code < 0 else None, "spawn_error": spawn_error, "capture_error": failure, "timeout": timed_out, "child_pid": child.pid if child else None, "reaped": child is None or child.poll() is not None, "closed_wall": utc(), "closed_monotonic": time.monotonic(), "stream_bytes": counts}
        try:
            terminal["stream_sha256"] = {name: digest(output / (name + ".raw")) for name in counts if (output / (name + ".raw")).is_file()}
            if lifecycle is not None:
                event("CLOSE", **terminal)
            fd = exclusive(output / "terminal.json")
            try:
                write_all(fd, (json.dumps(terminal, indent=2) + "\n").encode())
            finally:
                os.close(fd)
        except BaseException:
            terminal["status"] = "EVIDENCE_INCOMPLETE"
        for key in list(selector.get_map().values()):
            key.fileobj.close()
        selector.close()
        for fd in fds.values():
            os.close(fd)
        if lifecycle is not None:
            os.close(lifecycle)
        for signum, previous in previous_signals.items():
            signal.signal(signum, previous)
    return terminal


def clean_env(root):
    env = {key: os.environ[key] for key in ("HOME", "USER", "LOGNAME", "LANG") if key in os.environ}
    env.update({"PATH": "/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin", "TMPDIR": str(Path(root) / "tmp"), "PIP_CONFIG_FILE": os.devnull, "XDG_CACHE_HOME": str(Path(root) / "cache" / "xdg"), "CLANG_MODULE_CACHE_PATH": str(Path(root) / "cache" / "module"), "LLVM_CACHE_DIR": str(Path(root) / "cache" / "lto"), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"})
    if "CODEX_HOME" in os.environ:
        env["CODEX_HOME"] = os.environ["CODEX_HOME"]
    return env


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.argv[1:] if args.argv and args.argv[0] == "--" else args.argv
    result = capture(argv, args.cwd, clean_env(args.root), args.output, args.timeout, termination_grace=5)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(0 if result["status"] == "CLOSED" and result["code"] == 0 else 1)
