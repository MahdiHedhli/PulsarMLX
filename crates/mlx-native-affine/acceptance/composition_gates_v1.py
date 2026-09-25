#!/usr/bin/env python3
"""F020 Slice 2C -- the inherited exact-rational gates, applied to sides A and B.

Standard library only. This file adds NO arithmetic of its own. It imports,
after verifying their sha256, the two unchanged modules that already decide
the inherited gates:

* ``crates/mlx-native-affine/acceptance/exact_gates_v1.py`` --
  ``decide_qmm`` (G-QMM-EXACT, and G-R1-SELF-QMM when a Rust R1 is given),
  exactly as the Slice 2B parent uses it;
* ``scripts/research/mlx_affine_qmm_reference_v1.py`` -- ``exact_case``, the
  exact Python R1 on the oracle's expected logical data (the standalone file).

and applies ``decide_qmm`` to A (the composed path) and to B (the standalone
plane) separately, each against C (slice2c-plan.md section 4 step 5;
contract comparisons.gates). ``exact_gates_v1.py`` is not edited: its
hard-coded Slice 2B manifest hash sits only in its ``run()``, which is not
called here.

Inputs:

* ``--manifest``    the frozen Slice 2C manifest (sha256 checked);
* ``--fixture-dir`` ``fixtures/native-composition`` (standalone files are
  hash-checked by ``exact_case`` against the manifest);
* ``--rust-r1``     the Rust binary64 R1 document of the parent;
* ``--report`` and ``--report-dir``  the compose child's report and its
  output files (each output checked against the report's sha256).

Exit status: 0 when the document was produced (the decisions are inside it),
2 when an input was refused.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

SCHEMA = "pulsarmlx.f020.slice2c-composition-gates/1.0.0"
CHILD_SCHEMA = "pulsarmlx.f020.slice2c-child-report/1.0.0"
RUST_SCHEMA = "pulsarmlx.f020.r1-rust-binary64/1.0.0"
MANIFEST_SHA256 = "6f0e39e6d2c705603f3f897133d42c31837c53348aba0f4b0389dca18018fc14"

HERE = Path(__file__).resolve().parent
REPOSITORY_ROOT = HERE.parents[2]
EXACT_GATES = (HERE / "exact_gates_v1.py",
               "23b6c46e1d2e986d5027c0eea9d902c88a54f623a07d6ab42264fc410f23e887")
EXACT_R1 = (REPOSITORY_ROOT / "scripts" / "research" / "mlx_affine_qmm_reference_v1.py",
            "b9ef145e2bdce533aa733b70866d39364e2e61ee4642746b650e705f8a40ef15")


class InputError(ValueError):
    pass


def load_pinned(name: str, pinned):
    path, sha = pinned
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha:
        raise InputError("%s sha256 differs from the pinned value" % path.name)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--fixture-dir", required=True, type=Path)
    ap.add_argument("--rust-r1", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--report-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    try:
        gates = load_pinned("f020_exact_gates_v1", EXACT_GATES)
        reference = load_pinned("f020_mlx_affine_qmm_reference_v1", EXACT_R1)
        raw = a.manifest.read_bytes()
        if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
            raise InputError("manifest sha256 differs from the frozen value")
        manifest = json.loads(raw)
        rust = json.loads(a.rust_r1.read_bytes())
        if rust.get("schema") != RUST_SCHEMA:
            raise InputError("Rust R1 document schema differs")
        report = json.loads(a.report.read_bytes())
        if report.get("schema") != CHILD_SCHEMA or report.get("manifest_sha256") != MANIFEST_SHA256:
            raise InputError("child report schema or manifest binding differs")
        records = {}
        for rec in report["cases"]:
            if rec["id"] in records:
                raise InputError("duplicate case %s in the child report" % rec["id"])
            records[rec["id"]] = rec
        cases = {}
        for case in manifest["cases"]:
            if "python_exact_r1" not in case.get("references", []):
                continue
            cid = case["id"]
            exact = reference.exact_case(case, a.fixture_dir)
            if exact["op"] != "quantized_matmul":
                raise InputError("case %s: not a quantized_matmul R1" % cid)
            rust_rec = rust["cases"].get(cid) if "rust_binary64_r1" in case["references"] else None
            rec = records.get(cid)
            decided = {"executed": False}
            if rec is not None and rec.get("outcome") == "executed":
                decided = {"executed": True, "k": exact["k"]}
                self_gates = []
                for side in ("A", "B"):
                    side_record = {"id": "%s/%s" % (cid, side), "output": rec[side]["output"]}
                    d = gates.decide_qmm(case, exact, rust_rec, side_record, a.report_dir)
                    decided[side] = {"G-QMM-EXACT": d["G-QMM-EXACT"]}
                    self_gates.append(d["G-R1-SELF-QMM"])
                # G-R1-SELF-QMM depends on R1 and C only; both sides must agree.
                if self_gates[0] != self_gates[1]:
                    raise InputError("case %s: G-R1-SELF-QMM differs between sides" % cid)
                decided["C"] = {"G-R1-SELF-QMM": self_gates[0]}
            cases[cid] = decided
    except (InputError, OSError, KeyError, ValueError, TypeError) as error:
        print("refused: %s" % error, file=sys.stderr)
        return 2
    summary = {}
    for label, pick in (("G-QMM-EXACT(A)", lambda c: c.get("A", {}).get("G-QMM-EXACT")),
                        ("G-QMM-EXACT(B)", lambda c: c.get("B", {}).get("G-QMM-EXACT")),
                        ("G-R1-SELF-QMM(C)", lambda c: c.get("C", {}).get("G-R1-SELF-QMM"))):
        decided = [pick(c) for c in cases.values() if pick(c) is not None]
        summary[label] = {"cases": len(decided), "passed_cases": sum(1 for g in decided if g["pass"]),
                          "elements": sum(g["elements"] for g in decided),
                          "failed_elements": sum(g["failed_elements"] for g in decided)}
    summary["not_executed"] = sorted(cid for cid, c in cases.items() if not c["executed"])
    document = {"schema": SCHEMA, "manifest_sha256": MANIFEST_SHA256,
                "imported": {"exact_gates_v1.py": EXACT_GATES[1],
                             "mlx_affine_qmm_reference_v1.py": EXACT_R1[1]},
                "cases": cases, "summary": summary}
    a.out.write_text(json.dumps(document, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(run())
