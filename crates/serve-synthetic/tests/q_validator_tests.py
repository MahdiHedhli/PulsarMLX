#!/usr/bin/env python3
"""Canned records test only validation, never qualify a real mutation."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("q_result_validator", Path(__file__).with_name("q_result_validator.py"))
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def main():
    closed = {"status": "CLOSED", "code": 101, "native_signal": None, "timeout": False, "capture_error": None, "reaped": True}
    test = "intended_test"
    assertion = {"path": "tests/inert.rs", "line": 42, "message": "INDEPENDENT_ASSERTION"}
    fail = "test intended_test ... FAILED\nthread 'intended_test' panicked at tests/inert.rs:42:5:\nINDEPENDENT_ASSERTION\ntest result: FAILED. 0 passed; 1 failed;\n"
    passed = "test intended_test ... ok\ntest result: ok. 1 passed; 0 failed;\n"
    cases = [
        ("missing-result", closed, "", assertion, True, None),
        ("duplicate-result", closed, fail + fail, assertion, True, None),
        ("wrong-test", closed, fail.replace(test, "wrong_test"), assertion, True, None),
        ("wrong-assertion", closed, fail.replace("INDEPENDENT_ASSERTION", "UNRELATED"), assertion, True, None),
        ("wrong-site", closed, fail.replace(":42:", ":43:"), assertion, True, None),
        ("compile-failure", closed, "error: cannot compile", assertion, True, None),
        ("signal", {**closed, "code": None, "native_signal": 6}, fail, assertion, True, None),
        ("timeout", {**closed, "status": "TIMEOUT", "timeout": True}, fail, assertion, True, None),
        ("capture-failure", {**closed, "status": "EVIDENCE_INCOMPLETE", "capture_error": "write failed"}, fail, assertion, True, None),
        ("no-selected-test", closed, "test result: ok. 0 passed; 0 failed;", assertion, True, None),
        ("valid-semantic-kill", closed, fail, assertion, True, "SEMANTIC_KILL"),
        ("numeric-rust-thread-id", closed, fail.replace("' panicked", "' (46239811) panicked"), assertion, True, "SEMANTIC_KILL"),
        ("expected-inactive", {**closed, "code": 0}, passed, assertion, False, "EXPECTED_INACTIVE"),
        ("pristine-pass", {**closed, "code": 0}, passed, None, True, "PRISTINE_PASS"),
    ]
    outcomes = []
    for name, terminal, output, intended, active, expected in cases:
        try:
            actual = v.validate_rust(terminal, output, test, intended, active)
        except RuntimeError as exc:
            actual = None
            error = str(exc)
        else:
            error = None
        if actual != expected:
            raise RuntimeError(name + ": validator expectation failed")
        outcomes.append({"case": name, "input_terminal": terminal, "input_output": output, "actual": actual, "rejection": error})
    for name, output, intended, expected in [
        ("import-failure", "ModuleNotFoundError: no module", "INTENDED", None),
        ("wrong-python-assertion", "AssertionError: OTHER", "INTENDED", None),
        ("valid-python-assertion", "AssertionError: INTENDED", "INTENDED", "SEMANTIC_KILL"),
        ("python-pristine", "Q_SDK_GUARD_PRISTINE_PASS", None, "PRISTINE_PASS"),
    ]:
        terminal = {**closed, "code": 0 if intended is None else 1}
        try:
            actual = v.validate_python(terminal, output, intended)
        except RuntimeError as exc:
            actual, error = None, str(exc)
        else:
            error = None
        if actual != expected:
            raise RuntimeError(name + ": Python validation expectation failed")
        outcomes.append({"case": name, "input_terminal": terminal, "input_output": output, "actual": actual, "rejection": error})
    print(json.dumps({"status": "RESULT_VALIDATOR_SYNTHETIC_QUALIFIED", "cases": outcomes}, indent=2))


if __name__ == "__main__":
    main()
