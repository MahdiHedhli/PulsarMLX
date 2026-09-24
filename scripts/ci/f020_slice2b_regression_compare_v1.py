#!/usr/bin/env python3
"""F020 Slice 2C: proof that the Slice 2B invocation is unchanged (slice2c-plan.md 6.2).

Standard library only. It compares, and never tolerates:

(b) PRIMARY, same run: the base (12b06367) and candidate Slice 2B child
    reports (``qualification/child/report.json``). Before anything is removed,
    every case's ``stats.e5_peak_memory`` in BOTH reports must have exactly the
    four keys and the deterministic key/type/null pattern derived from the
    Slice 2B source. Then exactly the four prospectively enumerated volatile
    fields V1-V4 are deleted, both documents are serialized as
    ``json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)``
    encoded as UTF-8, and the two byte strings must be equal. Any difference
    is listed by JSON path and fails. In the same run the two parent summaries
    must both be PASS with no failure and identical gate counts equal to the
    attempt-3 counts, and the Slice 2B step's test-name lists (``--list`` and
    ``--doc --list``) must be identical line for line, with the composition
    target in neither and listed by ``--test composition_qualification``.

(a) SECONDARY, cross run: the candidate report against the preserved
    attempt-3 report (CI run 36006063937), whose sha256 and size are verified
    first: per case id ``outcome``, ``refusal_id``, ``output.sha256/nbytes/
    dtype/shape`` and ``structural``, and both canaries' ``output_sha256``.
    It relies on an identical runner native build, toolchain and device, so
    both runs' provenance is recorded with it. A mismatch here while (b)
    passes is RECORDED (result MISMATCH) and reported; it is never converted
    into a pass and it does not change the exit status of (b).

Exit status: 0 when (b) holds, 1 when (b) fails, 2 when an input is refused.
Adding a field to VOLATILE after an observation is a contract change
(correction_policy rule_2).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCHEMA = "pulsarmlx.f020.slice2b-regression-proof/1.0.0"
BASE_COMMIT = "12b063675c2227c59d2157458e051d73647b7045"
CHILD_SCHEMA = "pulsarmlx.f020.slice2b-child-report/1.0.0"
ATTEMPT3_SHA256 = "e3b596bc6d3c3af3eca33d8084c1a9cb3b0c6bbd2b8910d3bbe7c4e32cac5640"
ATTEMPT3_BYTES = 519872
ATTEMPT3_RUN = 36006063937
# V1-V4, exactly (contract execution.slice_2b_regression.primary_b_same_run_differential).
VOLATILE = (
    "provenance.build.qualify_executable_sha256",
    "cases[*].stats.e5_peak_memory.active_before",
    "cases[*].stats.e5_peak_memory.peak_after",
    "cases[*].stats.e5_peak_memory.peak_delta_ge_output_nbytes",
)
E5_KEYS = {"active_before", "peak_after", "output_nbytes", "peak_delta_ge_output_nbytes"}
ATTEMPT3_GATE_COUNTS = {
    "B6-REFUSAL": 37, "E1-DEVICE": 362, "E6-CPU-REFUSED": 1, "G-IMPORT": 8, "G-CAST": 2,
    "G-DQ-CODES": 18, "G-DQ-RUST": 59, "G-DQ-EXACT": 59, "G-R1-SELF-DQ": 59,
    "G-QMM-RUST": 239, "G-QMM-EXACT": 237, "G-R1-SELF-QMM": 237, "N-QMM-ZERO": 1,
    "SHAPE-DTYPE": 326,
}
COMPOSITION_TEST = "composition_qualification_of_the_frozen_population: test"


class InputError(ValueError):
    pass


def is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_e5(report: dict, label: str) -> list:
    """The deterministic key/type/null pattern of every case, before removal."""
    errors = []
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        return ["%s: no cases" % label]
    for case in cases:
        cid = case.get("id")
        stats = case.get("stats")
        e5 = stats.get("e5_peak_memory") if isinstance(stats, dict) else None
        if not isinstance(e5, dict) or set(e5) != E5_KEYS:
            errors.append("%s:%s: e5_peak_memory key set %r" % (label, cid, sorted(e5) if isinstance(e5, dict) else e5))
            continue
        op, outcome = case.get("op"), case.get("outcome")
        a, p, o, d = (e5["active_before"], e5["peak_after"], e5["output_nbytes"],
                      e5["peak_delta_ge_output_nbytes"])
        if outcome == "executed" and op in ("dequantize", "quantized_matmul"):
            ok = is_int(a) and a >= 0 and is_int(p) and p >= 0 and is_int(o) and isinstance(d, bool)
        elif outcome == "executed" and op in ("import_u32", "import_meta", "astype_f32"):
            ok = a is None and p is None and is_int(o) and d is None
        elif outcome == "refused":
            ok = a is None and p is None and o is None and d is None
        else:
            ok = False
        if not ok:
            errors.append("%s:%s: e5 pattern for op=%s outcome=%s is %r" % (label, cid, op, outcome, e5))
    return errors


def remove_volatile(report: dict) -> dict:
    doc = json.loads(json.dumps(report))
    del doc["provenance"]["build"]["qualify_executable_sha256"]
    for case in doc["cases"]:
        e5 = case["stats"]["e5_peak_memory"]
        for key in ("active_before", "peak_after", "peak_delta_ge_output_nbytes"):
            del e5[key]
    return doc


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def diff_paths(a, b, path="$", out=None, limit=200):
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append("%s.%s (present in %s only)" % (path, k, "base" if k in a else "candidate"))
            else:
                diff_paths(a[k], b[k], "%s.%s" % (path, k), out, limit)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append("%s (length %d vs %d)" % (path, len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            label = x.get("id") if isinstance(x, dict) and "id" in x else i
            diff_paths(x, y, "%s[%s]" % (path, label), out, limit)
    elif type(a) is not type(b) or a != b:
        out.append(path)
    return out


def load_json(path: Path, what: str):
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError) as error:
        raise InputError("%s: %s" % (what, error)) from None


def lines(path: Path) -> list:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise InputError("%s: %s" % (path, error)) from None


def gate_counts(summary: dict) -> dict:
    return {g: v for g, v in summary.get("gate_counts", {}).items()}


def primary(base_dir: Path, cand_dir: Path, lists: Path) -> dict:
    base = load_json(base_dir / "qualification/child/report.json", "base report")
    cand = load_json(cand_dir / "qualification/child/report.json", "candidate report")
    for label, r in (("base", base), ("candidate", cand)):
        if r.get("schema") != CHILD_SCHEMA or r.get("completed") is not True:
            raise InputError("%s report schema/completed" % label)
    failures = []
    e5_errors = validate_e5(base, "base") + validate_e5(cand, "candidate")
    failures += e5_errors
    report_equal = False
    differing = []
    if not e5_errors:
        cb, cc = canonical(remove_volatile(base)), canonical(remove_volatile(cand))
        report_equal = cb == cc
        if not report_equal:
            differing = diff_paths(remove_volatile(base), remove_volatile(cand))
            failures.append("canonical reports differ outside V1-V4 at %d path(s)" % len(differing))
    # Summaries: PASS, no failure, identical gate counts equal to attempt 3.
    sb = load_json(base_dir / "qualification/summary.json", "base summary")
    sc = load_json(cand_dir / "qualification/summary.json", "candidate summary")
    want = {g: {"cases": n, "passed": n} for g, n in ATTEMPT3_GATE_COUNTS.items()}
    for label, s in (("base", sb), ("candidate", sc)):
        if s.get("result") != "PASS" or s.get("failures") != []:
            failures.append("%s summary result %r failures %r" % (label, s.get("result"), s.get("failures")))
        if gate_counts(s) != want:
            failures.append("%s gate counts differ from attempt 3: %r" % (label, gate_counts(s)))
    if gate_counts(sb) != gate_counts(sc):
        failures.append("base and candidate gate counts differ")
    # Test-name lists, line for line.
    lists_result = {}
    for kind in ("list", "doc-list"):
        lb, lc = lines(lists / ("base-%s.txt" % kind)), lines(lists / ("candidate-%s.txt" % kind))
        same = lb == lc
        lists_result[kind] = {"base_lines": len(lb), "candidate_lines": len(lc), "identical": same,
                              "tests": sum(1 for x in lc if x.endswith(": test"))}
        if not same:
            failures.append("Slice 2B %s differs between base and candidate" % kind)
    composition = lines(lists / "composition-list.txt")
    composition_tests = [x for x in composition if x.endswith(": test")]
    slice2b_lines = set(lines(lists / "candidate-list.txt")) | set(lines(lists / "base-list.txt"))
    absent = not any(t in slice2b_lines for t in composition_tests)
    listed = COMPOSITION_TEST in composition
    if not absent or not listed:
        failures.append("composition target listing: absent from Slice 2B lists=%s, listed by --test=%s" % (absent, listed))
    return {
        "result": "PASS" if not failures else "FAIL",
        "base_commit": BASE_COMMIT,
        "volatile_fields_removed": list(VOLATILE),
        "e5_pre_removal_validation": {"cases_per_report": len(base.get("cases", [])), "errors": e5_errors},
        "canonical_reports_equal": report_equal,
        "differing_paths": differing,
        "base_report_sha256": hashlib.sha256((base_dir / "qualification/child/report.json").read_bytes()).hexdigest(),
        "candidate_report_sha256": hashlib.sha256((cand_dir / "qualification/child/report.json").read_bytes()).hexdigest(),
        "v1_values": {"base": base["provenance"]["build"].get("qualify_executable_sha256"),
                      "candidate": cand["provenance"]["build"].get("qualify_executable_sha256")},
        "gate_counts": {"base": gate_counts(sb), "candidate": gate_counts(sc), "equal_attempt3": gate_counts(sb) == want == gate_counts(sc)},
        "test_lists": lists_result,
        "composition_target": {"tests_listed_by_test_flag": composition_tests, "absent_from_slice2b_lists": absent},
        "failures": failures,
    }


def provenance_of(report: dict) -> dict:
    p = report.get("provenance", {})
    return {"native_prefix_identity_sha256": p.get("native_prefix", {}).get("identity_sha256"),
            "libmlx_sha256": p.get("libmlx", {}).get("sha256"),
            "libmlxc_sha256": p.get("libmlxc", {}).get("sha256"),
            "metallib_sha256": p.get("metallib", {}).get("sha256"),
            "rustc": p.get("build", {}).get("rustc"),
            "os_product_version": p.get("os_product_version"),
            "device_info": p.get("device_info")}


def secondary(attempt3: Path, cand_dir: Path) -> dict:
    raw = attempt3.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ATTEMPT3_SHA256 or len(raw) != ATTEMPT3_BYTES:
        raise InputError("attempt-3 report copy fails its sha256/size verification")
    ref = json.loads(raw)
    cand = load_json(cand_dir / "qualification/child/report.json", "candidate report")
    by_id = {c["id"]: c for c in ref["cases"]}
    mismatches = []
    compared = 0
    for c in cand["cases"]:
        r = by_id.get(c["id"])
        if r is None:
            mismatches.append("%s: not in attempt 3" % c["id"])
            continue
        compared += 1
        for key in ("outcome", "refusal_id", "structural"):
            if c.get(key) != r.get(key):
                mismatches.append("%s.%s" % (c["id"], key))
        co, ro = c.get("output") or {}, r.get("output") or {}
        for key in ("sha256", "nbytes", "dtype", "shape"):
            if co.get(key) != ro.get(key):
                mismatches.append("%s.output.%s" % (c["id"], key))
    if len(cand["cases"]) != len(ref["cases"]) or compared != len(ref["cases"]):
        mismatches.append("case count %d vs attempt-3 %d" % (len(cand["cases"]), len(ref["cases"])))
    for canary in ("canary_start", "canary_end"):
        if cand.get(canary, {}).get("output_sha256") != ref.get(canary, {}).get("output_sha256"):
            mismatches.append("%s.output_sha256" % canary)
    return {"result": "MATCH" if not mismatches else "MISMATCH",
            "reference": {"ci_run": ATTEMPT3_RUN, "sha256": ATTEMPT3_SHA256, "bytes": ATTEMPT3_BYTES, "verified": True},
            "cases_compared": compared, "mismatches": mismatches[:500], "mismatch_count": len(mismatches),
            "provenance": {"attempt3": provenance_of(ref), "candidate": provenance_of(cand)},
            "policy": "recorded and reported to the planner on mismatch; never converted into a pass"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--base", required=True, type=Path, help="base PULSAR_F020_QUALIFICATION_OUT")
    ap.add_argument("--candidate", required=True, type=Path, help="candidate PULSAR_F020_QUALIFICATION_OUT")
    ap.add_argument("--lists", required=True, type=Path, help="directory with the five --list files")
    ap.add_argument("--attempt3", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        b = primary(a.base, a.candidate, a.lists)
        s = secondary(a.attempt3, a.candidate)
    except (InputError, OSError, KeyError, ValueError, TypeError) as error:
        print("refused: %s" % error, file=sys.stderr)
        return 2
    document = {"schema": SCHEMA, "primary_b_same_run_differential": b, "secondary_a_cross_run": s}
    a.out.write_text(json.dumps(document, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"primary_b": b["result"], "canonical_reports_equal": b["canonical_reports_equal"],
                      "differing_paths": b["differing_paths"][:20], "failures": b["failures"],
                      "secondary_a": s["result"], "secondary_mismatch_count": s["mismatch_count"]}, sort_keys=True))
    return 0 if b["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
