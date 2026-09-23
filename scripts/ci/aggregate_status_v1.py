#!/usr/bin/env python3
"""The CI aggregate's decision, factored out of the workflow so it is testable.

The mode rules are the ones the workflow's inline shell applied before this
file existed, case for case. One rule is added: when the classifier reports
that the committed range touched evidence, the evidence-integrity job must have
succeeded, whatever the mode. A skipped, cancelled, failed or absent integrity
result is then a failure. When evidence was not touched, the integrity result
is not consulted outside EVIDENCE_ONLY, exactly as before.

Standard library only; reads the job results from the environment.
"""

from __future__ import annotations

import os
import sys
from typing import Mapping


class AggregateFailure(RuntimeError):
    pass


def _expect(results: Mapping[str, str], key: str, expected: str) -> None:
    actual = results.get(key, "")
    if actual != expected:
        raise AggregateFailure(f"{key}={actual!r}, required {expected!r}")


def decide(results: Mapping[str, str]) -> str:
    """Return the success line, or raise AggregateFailure."""
    _expect(results, "CLASSIFY_RESULT", "success")
    mode = results.get("MODE", "")
    touched = results.get("EVIDENCE_TOUCHED", "")
    if touched not in {"true", "false"}:
        raise AggregateFailure(f"EVIDENCE_TOUCHED={touched!r}, required 'true' or 'false'")
    if mode in {"FULL_NATIVE", "UNKNOWN_DEFAULT_FULL"}:
        _expect(results, "BASELINE_RESULT", "success")
        _expect(results, "NATIVE_RESULT", "success")
    elif mode == "EVIDENCE_ONLY":
        _expect(results, "EVIDENCE_RESULT", "success")
        _expect(results, "BASELINE_RESULT", "skipped")
        _expect(results, "NATIVE_RESULT", "skipped")
    elif mode == "DOCS_ONLY":
        _expect(results, "DOCS_RESULT", "success")
        _expect(results, "BASELINE_RESULT", "skipped")
        _expect(results, "NATIVE_RESULT", "skipped")
    elif mode == "NO_CHANGES":
        _expect(results, "BASELINE_RESULT", "skipped")
        _expect(results, "NATIVE_RESULT", "skipped")
    elif mode == "CLOSED_BRANCH_GUARD":
        _expect(results, "GUARD_RESULT", "failure")
        raise AggregateFailure(
            "Closed-branch guard correctly refused automatic implementation qualification.")
    else:
        raise AggregateFailure(f"Unknown CI mode: {mode}")
    if touched == "true":
        # Mixed code+evidence ranges: native success does not qualify evidence.
        _expect(results, "EVIDENCE_RESULT", "success")
    return f"selected_mode={mode}\nevidence_touched={touched}"


KEYS = ("MODE", "EVIDENCE_TOUCHED", "CLASSIFY_RESULT", "EVIDENCE_RESULT", "DOCS_RESULT",
        "GUARD_RESULT", "BASELINE_RESULT", "NATIVE_RESULT")


def main(environ: Mapping[str, str] | None = None) -> int:
    environ = os.environ if environ is None else environ
    try:
        line = decide({key: environ.get(key, "") for key in KEYS})
    except AggregateFailure as error:
        print(f"CI aggregate failed: {error}", file=sys.stderr)
        return 1
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
