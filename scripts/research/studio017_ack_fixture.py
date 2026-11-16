"""Synthetic process roles for the Studio017 pre-payload admission control."""
import os
from pathlib import Path
import sys

import studio017_py_gate as pyg
from studio017_ref_entry import query_helper
import studio017_supervise as sup

STAGE = "synthetic-ack"
ROLES = ("fixture-bootstrap", "fixture-worker", "fixture-helper")


def arguments(cap, role, extra=()):
    p = sup.doc(cap)
    b = p["python_gate"]
    return pyg.cli(sys.executable, cap.parent / ("cache-" + role), pyg.SELF, role,
                   b["policy"], b["sha256"], pyg.rolepath(cap.parent, role),
                   p["operation"], [cap, *extra])


def enter(role, args, operation, policy, digest, receipt):
    cap = pyg.real(args[0])
    d = cap.parent
    sup.hexid(operation, 32)
    sup.need(role in ROLES and d.name == "synthetic-admission-" + operation and
             d.is_relative_to(sup.STATE) and
             cap == d / "fixture-cap.json" and Path(receipt) == pyg.rolepath(d, role),
             "synthetic control path")
    data = sup.doc(cap)
    sup.need(set(data) == {"schema", "stage", "operation", "run", "supervisor",
                           "supervisor_image", "expected_image", "python_gate", "grant_sha256"} and
             data["schema"] == "studio017-fixture-cap/1" and data["stage"] == STAGE and
             data["operation"] == operation and data["run"] == operation and
             data["python_gate"] == {"interpreter": str(Path(sys.executable).resolve()),
                                     "policy": policy, "sha256": digest}, "fixture binding")
    grant = d / "fixture-grant.json"
    sup.need(sup.digest(grant) == data["grant_sha256"] and sup.doc(grant) ==
             dict(schema="studio017-synthetic-ack-only/1", stage=STAGE, operation=operation),
             "synthetic grant")
    if role == "fixture-bootstrap":
        sup.need(len(args) == 2, "fixture bootstrap arguments")
        sup.startup_barrier(cap, int(args[1]))
        return None, arguments(cap, "fixture-worker")
    sup.need(len(args) == 1, "fixture worker/helper arguments")
    if role == "fixture-worker":
        # Demonstrate the active sandbox using a populated sibling file outside all read roots.
        try:
            (d / "denied-marker").read_bytes()
        except PermissionError:
            pass
        else:
            raise ValueError("sandbox permitted denied-marker")
        fd = int(os.environ["STUDIO017_ADMIT_CHANNEL"])
        response = query_helper(arguments(cap, "fixture-helper"), fd)
        expected = dict(stage=STAGE, operation=operation, helper_acknowledged=True)
        sup.need(response == expected, "helper output")
        return dict(**expected, sandbox_denied_marker=True), None
    claim = d / "fixture-spend.json"
    spent = sup.doc(claim)
    sup.need(spent.get("stage") == STAGE and spent.get("grant_sha256") == data["grant_sha256"]
             and spent.get("cap_sha256") == sup.digest(cap), "fixture spend")
    sup.acknowledge_child(cap, data, claim)
    return dict(stage=STAGE, operation=operation, helper_acknowledged=True), None
