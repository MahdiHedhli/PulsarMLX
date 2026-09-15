"""Evidence-first result classification, independent of process exit truthiness."""
import hashlib
import json
from pathlib import Path
import re


def read_capture(path):
    path = Path(path)
    terminal = json.loads((path / "terminal.json").read_bytes())
    events = [json.loads(line) for line in (path / "lifecycle.jsonl").read_text().splitlines()]
    if not events or events[-1].get("event") != "CLOSE" or any(events[-1].get(key) != value for key, value in terminal.items()):
        raise RuntimeError("EVIDENCE_INCOMPLETE: terminal/lifecycle mismatch")
    streams = {}
    rows = []
    for name in ("stdout", "stderr"):
        file = path / (name + ".raw")
        body = file.read_bytes()
        if len(body) != terminal["stream_bytes"][name]:
            raise RuntimeError("EVIDENCE_INCOMPLETE: stream byte mismatch")
        streams[name] = body.decode("utf-8", errors="strict")
        rows.append({"path": str(file), "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
    if terminal["status"] != "CLOSED" or terminal["capture_error"] or terminal["timeout"] or terminal["native_signal"] or terminal["spawn_error"] or not terminal["reaped"]:
        raise RuntimeError("NON_SEMANTIC_TERMINAL: " + terminal["status"])
    return terminal, streams["stdout"] + "\n" + streams["stderr"], rows


def validate_rust(terminal, output, test, assertion=None, active=True):
    if terminal.get("status") != "CLOSED" or terminal.get("native_signal") or terminal.get("timeout") or terminal.get("capture_error") or not terminal.get("reaped"):
        raise RuntimeError("NON_SEMANTIC_TERMINAL")
    selected = re.findall(r"^test ([A-Za-z0-9_:]+) \.\.\. (ok|FAILED)$", output, flags=re.M)
    results = re.findall(r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed;", output, flags=re.M)
    if len(selected) != 1 or selected[0][0] != test or len(results) != 1:
        raise RuntimeError("MISSING_DUPLICATE_OR_WRONG_TEST_RESULT")
    if assertion is None:
        if selected[0][1] != "ok" or results[0] != ("ok", "1", "0") or terminal["code"] != 0:
            raise RuntimeError("PRISTINE_NAMED_TEST_NOT_PASS")
        return "PRISTINE_PASS"
    if selected[0][1] == "ok" and results[0] == ("ok", "1", "0") and terminal["code"] == 0:
        return "SURVIVED" if active else "EXPECTED_INACTIVE"
    if terminal["code"] != 101 or selected[0][1] != "FAILED" or results[0] != ("FAILED", "0", "1"):
        raise RuntimeError("NON_SEMANTIC_TEST_FAILURE")
    sites = re.findall(r"thread '([^']+)' panicked at ([^\n]+):", output)
    site = assertion["path"] + ":" + str(assertion["line"]) + ":"
    if len(sites) != 1 or sites[0][0] != test or not sites[0][1].startswith(site) or assertion["message"] not in output:
        raise RuntimeError("WRONG_ASSERTION_FAILURE")
    return "SEMANTIC_KILL" if active else "UNEXPECTED_ACTIVE_FAILURE"


def validate_python(terminal, output, assertion=None):
    if terminal.get("status") != "CLOSED" or terminal.get("native_signal") or terminal.get("timeout") or terminal.get("capture_error") or not terminal.get("reaped"):
        raise RuntimeError("NON_SEMANTIC_TERMINAL")
    if any(kind in output for kind in ("SyntaxError", "ImportError", "ModuleNotFoundError", "NameError", "IndentationError")):
        raise RuntimeError("PYTHON_LOAD_FAILURE")
    if assertion is None:
        if terminal["code"] != 0 or output.count("Q_SDK_GUARD_PRISTINE_PASS") != 1:
            raise RuntimeError("SDK_PRISTINE_NOT_PASS")
        return "PRISTINE_PASS"
    if terminal["code"] == 0:
        return "SURVIVED"
    exceptions = re.findall(r"^AssertionError: (.*)$", output, flags=re.M)
    permitted = [assertion]
    chained = ["fake cloud destination was accepted", assertion] if assertion == "Q_CLOUD_DESTINATION_ACCEPTED" else permitted
    if terminal["code"] != 1 or exceptions not in (permitted, chained):
        raise RuntimeError("WRONG_SDK_ASSERTION_FAILURE")
    return "SEMANTIC_KILL"
