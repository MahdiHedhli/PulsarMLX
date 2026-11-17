"""One read-only Route B comparison against the sealed ineligible reference.

The original scientific calculations and thresholds are imported unchanged.
This adapter reports empirical metrics alongside their original failed grades.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

import numpy as np
import studio017_ref_grade as original
from studio017_ref_criteria import interval_bf16, route_eps


def observed_routes(directory, geometry):
    population = original.layout(geometry)
    with original.sealed(directory, population, "native", geometry) as native:
        # This read is solely for labels and normalized weights already in the
        # sealed report. The original grader verifies their score consistency.
        return {str(i): row for i, row in native.routes.items()}


def _compare(reference, native, geometry):
    result = original._grade(reference, native, geometry)
    native_routes = observed_routes(native, geometry)
    population = original.layout(geometry)
    with original.sealed(reference, population, "reference", geometry) as ref:
        reference_routes = {str(i): row for i, row in ref.routes.items()}
    for i, row in result["routes"].items():
        row["reference_selected_ids"] = reference_routes[str(i)]["ids"]
        row["native_selected_ids"] = native_routes[str(i)]["ids"]
        row["reference_weights"] = reference_routes[str(i)]["weights"]
        row["native_weights"] = native_routes[str(i)]["weights"]
    result["schema"] = "studio019-route-b-grade/1"
    result["original_frozen_qualification"] = result.pop("qualified")
    result["qualified"] = False
    result["reference_eligible"] = False
    result["reference_failed_route_layers"] = [
        i for i, row in result["routes"].items() if row["ref_robust_gap"] <= 0
    ]
    result["empirical_agreement"] = bool(
        result["outside"] == 0
        and all(row["membership_match"] and row["weights_match"] for row in result["routes"].values())
        and result["reference_token"]["winner"] == result["native_token"]["winner"]
    )
    route_disagreements = {
        f"{i:02}.moe.corrected.f32" for i, row in result["routes"].items()
        if not row["membership_match"] or not row["weights_match"]
    }
    result["first_observed_divergence"] = next(
        (name for name, row in result["stages"].items()
         if row["outside"] or name in route_disagreements), None
    )
    result["complete"] = True
    result["observed_cause"] = None
    result["prior_reference_known_to_author"] = True
    return result


def bounded_partial(directory, geometry):
    """Read available private output without accepting an incomplete population."""
    fd = original.open_dir(directory)
    arrays = {}
    records = {}
    errors = {}
    expected = original.layout(geometry)
    try:
        before = os.fstat(fd)
        original.require(not before.st_mode & 0o222, "partial directory must be sealed")
        names = os.listdir(fd)
        original.require(len(names) <= len(expected) + 1, "partial output population")
        total = 0
        for name in names:
            original.require(name in expected or name == "report.json", "unexpected partial file")
            item = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:
                st = os.fstat(item)
                original.require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and
                                 not st.st_mode & 0o222 and st.st_uid == os.geteuid() and
                                 0 < st.st_size <= 8 << 20, "partial file type/size")
                total += st.st_size
                original.require(total <= 256 << 20, "partial output byte budget")
                with os.fdopen(item, "rb", closefd=False) as stream:
                    raw = stream.read(st.st_size + 1)
                original.require(len(raw) == st.st_size and original.pair(st) ==
                                 original.pair(os.fstat(item)) ==
                                 original.pair(os.stat(name, dir_fd=fd, follow_symlinks=False)),
                                 "partial file changed")
                records[name] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                if name in expected:
                    count = expected[name][2]
                    if len(raw) == count * 4:
                        array = np.frombuffer(raw, dtype="<f4")
                        if np.all(np.isfinite(array)):
                            arrays[name] = array
                        else:
                            errors[name] = "nonfinite stored values"
                    else:
                        errors[name] = "wrong stored vector size"
            finally:
                os.close(item)
        original.require(original.pair(before) == original.pair(os.fstat(fd)) and
                         set(names) == set(os.listdir(fd)), "partial directory changed")
    finally:
        os.close(fd)
    return arrays, records, errors


def partial_comparison(reference, native, geometry, refusal):
    """Retain every available scalar comparison after an incomplete native result."""
    arrays, records, errors = bounded_partial(native, geometry)
    population = original.layout(geometry)
    stages = {}
    routes = {i: None for i in range(3, geometry[0])}
    native_token = None
    reference_token = None
    with original.sealed(reference, population, "reference", geometry) as ref:
        for name, (i, label, count, kind) in population.items():
            x = ref.arr(name, count)
            original.representation(x, kind)
            if kind == "logits":
                reference_token = original.token_fields(ref, x)
            y = arrays.get(name)
            if y is None:
                stages[name] = None
                continue
            delta = np.abs(x.astype("f8") - y.astype("f8"))
            metric = dict(values=count, max_abs=float(delta.max()), outside=None)
            stages[name] = metric
            try:
                original.representation(y, kind)
                if kind in ("one", "embedding"):
                    bad = x.view("<u4") != y.view("<u4")
                elif kind in ("mhc", "decay", "corrected"):
                    bad = delta > route_eps(x)
                elif kind == "state":
                    bad = delta > original.STATE_ABS + original.STATE_REL * np.abs(x.astype("f8"))
                else:
                    low, high = interval_bf16(x)
                    bad = (y < low) | (y > high)
                metric["outside"] = int(np.count_nonzero(bad))
                if metric["outside"]:
                    metric["first_outside"] = int(np.flatnonzero(bad)[0])
                if kind == "logits":
                    native_token = original.golden_margin(y)
            except original.Refusal as error:
                metric["representation_error"] = str(error)
        ref_content = ref.finish()
    return dict(schema="studio019-route-b-grade/1", complete=False, qualified=False,
                original_frozen_qualification=False, empirical_agreement=None,
                reference_eligible=False, reference_failed_route_layers=[23, 33, 34],
                original_complete_grade_refusal=str(refusal), reference=ref_content,
                native=dict(files=len(records), bytes=sum(row["bytes"] for row in records.values()),
                            manifest_sha256=hashlib.sha256(
                                (json.dumps(records, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest(),
                            report_sha256=records.get("report.json", {}).get("sha256")),
                partial_files=records, partial_errors=errors, stages=stages, routes=routes,
                reference_token=reference_token, native_token=native_token,
                first_observed_divergence=next((name for name, row in stages.items()
                    if row and (row["outside"] or row.get("representation_error"))), None),
                observed_cause=None, prior_reference_known_to_author=True,
                witness_scope=original.witness_scope(geometry[0]))


def grade_pair(reference, native):
    try:
        result = _compare(reference, native, original.REAL)
    except (original.Refusal, FileNotFoundError) as error:
        return partial_comparison(reference, native, original.REAL, error)
    original.require(result["reference_failed_route_layers"] == [23, 33, 34] and
                     result["original_frozen_qualification"] is False,
                     "unexpected frozen reference classification")
    return result
