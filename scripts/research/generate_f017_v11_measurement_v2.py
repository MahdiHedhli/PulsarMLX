#!/usr/bin/env python3
"""Active V11 implementation measurement (v9).

Two verifications that the v1 generator conflated into one:

* HISTORICAL — the frozen v8 record still describes its own head exactly.
  Every measured path's Git blob at ``implementation_head`` must carry the
  blob id and SHA-256 that v8 recorded, and the head's tree must be the tree
  v8 recorded. This keeps v8's meaning verifiable forever without pinning the
  working tree to a September 3 state.
* CURRENT — the checked-out working tree equals the Git objects at the head
  being measured, and the resulting v9 record inventories those bytes.

The measured path set is taken from the predecessor rather than restated
here, so the active measurement cannot silently widen its own scope; a set
digest is asserted against the constant below.

A v9 record inventories bytes. It does not ratify the behaviour of any body
that changed since v8: the reviewed change set is bound by ``review``.
No checkpoint is opened and no authority is minted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v9.json"
PREDECESSOR = ROOT / "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v8.json"
REVIEW = ROOT / "docs/architecture/reviews/f017-v11-active-measurement-repair-20260920.md"

SCHEMA = "pulsarmlx.f017.v11-result-envelope-implementation-measurement/9.0.0"
PREDECESSOR_SCHEMA = "pulsarmlx.f017.v11-result-envelope-implementation-measurement/8.0.0"
PREDECESSOR_SHA256 = "c529221a53a338dfe57d65f855f1b9d9b11e0b0251562f84067a65a0538a6414"
PREDECESSOR_HEAD = "f35d341110c67377200ad353ab56a3cf38615a73"
PREDECESSOR_TREE = "08864e7d529c91c0ec8f4bf9661006503e6d7dc9"
# sha256 of "\n".join(sorted(paths)) + "\n" over v8's 36 measured paths.
MEASURED_PATH_SET_SHA256 = "6ddd0dcc0f410e982525d84dc88bbf6c43a6ee5343f92bb65c5b34c553d8b951"
MEASURED_PATH_COUNT = 36
# The scientific numerical authority. These bodies must never drift under a
# measurement refresh; a v9 that reports them as changed is a stop, not a
# re-baseline.
NUMERICAL_CORE_PATHS = (
    "scripts/research/f017_corrected_oracle_primary_numerics_v3.py",
    "scripts/research/f017_corrected_oracle_secondary_numerics_v3.py",
)
BRANCH = "feat/017-rust-native-inference-runtime"


class MeasurementError(RuntimeError):
    """Raised after the complete report has been emitted."""


def path_set_sha256(paths) -> str:
    return hashlib.sha256(("\n".join(sorted(paths)) + "\n").encode()).hexdigest()


class GitReader:
    """The only process boundary; tests substitute a fake."""

    def __init__(self, root: Path = ROOT):
        self.root = root

    def text(self, *arguments: str) -> str:
        return subprocess.check_output(["git", *arguments], cwd=self.root, text=True).strip()

    def blob(self, head: str, path: str) -> bytes:
        return subprocess.check_output(["git", "show", f"{head}:{path}"], cwd=self.root)

    def blob_id(self, head: str, path: str) -> str:
        return self.text("rev-parse", f"{head}:{path}")

    def tree(self, head: str) -> str:
        return self.text("rev-parse", f"{head}^{{tree}}")

    def head(self) -> str:
        return self.text("rev-parse", "HEAD")

    def commits_touching(self, since: str, until: str, path: str):
        raw = subprocess.check_output(
            ["git", "log", "--reverse", "--format=%H%x00%s", f"{since}..{until}", "--", path],
            cwd=self.root, text=True,
        ).strip()
        out = []
        for line in raw.splitlines():
            if not line:
                continue
            commit, _, subject = line.partition("\x00")
            out.append({"commit": commit, "subject": subject})
        return out


def read_file(path: str) -> bytes:
    return (ROOT / path).read_bytes()


def load_predecessor(raw: bytes) -> dict:
    """Parse and structurally bind v8. Never mutated, never regenerated."""
    findings = []
    if hashlib.sha256(raw).hexdigest() != PREDECESSOR_SHA256:
        findings.append({"control": "PREDECESSOR_BYTES", "detail": "v8 sha256 does not match the bound constant"})
    record = json.loads(raw)
    if record.get("schema") != PREDECESSOR_SCHEMA:
        findings.append({"control": "PREDECESSOR_SCHEMA", "detail": f"schema {record.get('schema')!r}"})
    if record.get("implementation_head") != PREDECESSOR_HEAD:
        findings.append({"control": "PREDECESSOR_HEAD", "detail": f"head {record.get('implementation_head')!r}"})
    if record.get("implementation_tree") != PREDECESSOR_TREE:
        findings.append({"control": "PREDECESSOR_TREE", "detail": f"tree {record.get('implementation_tree')!r}"})
    paths = [item["path"] for item in record.get("measured_paths", [])]
    if len(paths) != MEASURED_PATH_COUNT or record.get("measured_path_count") != MEASURED_PATH_COUNT:
        findings.append({"control": "MEASURED_PATH_COUNT", "detail": f"{len(paths)} paths"})
    if len(set(paths)) != len(paths):
        findings.append({"control": "MEASURED_PATH_SET", "detail": "duplicate measured path"})
    if path_set_sha256(paths) != MEASURED_PATH_SET_SHA256:
        findings.append({"control": "SOURCE_SET_WIDENED_WITHOUT_APPROVAL",
                         "detail": f"path-set digest {path_set_sha256(paths)}"})
    if record.get("original_checkpoint_access") != 0:
        findings.append({"control": "PREDECESSOR_CHECKPOINT_ACCESS", "detail": "non-zero"})
    return {"record": record, "paths": paths, "findings": findings}


def measure(git: GitReader, reader, head: str, predecessor: dict) -> dict:
    """Produce the complete report. Assertions belong to verify()."""
    record = predecessor["record"]
    paths = predecessor["paths"]
    findings = list(predecessor["findings"])
    predecessor_by_path = {item["path"]: item for item in record["measured_paths"]}

    historical = []
    for path in paths:
        expected = predecessor_by_path[path]
        entry = {"path": path}
        try:
            blob_id = git.blob_id(PREDECESSOR_HEAD, path)
            raw = git.blob(PREDECESSOR_HEAD, path)
        except Exception as error:  # missing object at the frozen head
            entry.update(result="UNREADABLE", detail=str(error))
            findings.append({"control": "HISTORICAL_OBJECT_MISSING", "detail": path})
            historical.append(entry)
            continue
        digest = hashlib.sha256(raw).hexdigest()
        entry.update(git_blob_sha=blob_id, sha256=digest,
                     result="MATCH" if (blob_id == expected["git_blob_sha"] and digest == expected["sha256"]) else "MISMATCH")
        if entry["result"] == "MISMATCH":
            findings.append({"control": "HISTORICAL_DRIFT", "detail":
                             f"{path}: v8 recorded {expected['sha256'][:12]}, head {PREDECESSOR_HEAD[:8]} now carries {digest[:12]}"})
        historical.append(entry)
    historical_tree = None
    try:
        historical_tree = git.tree(PREDECESSOR_HEAD)
    except Exception as error:
        findings.append({"control": "HISTORICAL_HEAD_MISSING", "detail": str(error)})
    if historical_tree is not None and historical_tree != PREDECESSOR_TREE:
        findings.append({"control": "HISTORICAL_TREE", "detail": f"{PREDECESSOR_HEAD} tree is {historical_tree}"})

    current = []
    drift = []
    for path in paths:
        entry = {"path": path}
        try:
            blob_id = git.blob_id(head, path)
            raw = git.blob(head, path)
        except Exception as error:
            entry.update(result="MISSING_AT_HEAD", detail=str(error))
            findings.append({"control": "CURRENT_OBJECT_MISSING", "detail": path})
            current.append(entry)
            continue
        try:
            worktree = reader(path)
        except Exception as error:
            entry.update(result="MISSING_IN_WORKTREE", detail=str(error))
            findings.append({"control": "WORKTREE_FILE_MISSING", "detail": path})
            current.append(entry)
            continue
        digest = hashlib.sha256(raw).hexdigest()
        if worktree != raw:
            entry.update(git_blob_sha=blob_id, sha256=digest, result="WORKTREE_DIFFERS",
                         worktree_sha256=hashlib.sha256(worktree).hexdigest())
            findings.append({"control": "WORKTREE_DIFFERS_FROM_HEAD", "detail":
                             f"{path}: commit the change or check out {head[:8]}"})
            current.append(entry)
            continue
        entry.update(git_blob_sha=blob_id, sha256=digest, result="MATCH")
        current.append(entry)
        expected = predecessor_by_path[path]
        if digest != expected["sha256"]:
            drift.append({
                "path": path,
                "predecessor_git_blob_sha": expected["git_blob_sha"],
                "predecessor_sha256": expected["sha256"],
                "current_git_blob_sha": blob_id,
                "current_sha256": digest,
                "accepted_commits": git.commits_touching(PREDECESSOR_HEAD, head, path),
            })
    for item in drift:
        if not item["accepted_commits"]:
            findings.append({"control": "DRIFT_WITHOUT_LINEAGE", "detail":
                             f"{item['path']} differs from v8 but no commit between {PREDECESSOR_HEAD[:8]} and {head[:8]} touches it"})
        if item["path"] in NUMERICAL_CORE_PATHS:
            findings.append({"control": "NUMERICAL_AUTHORITY_DRIFT", "detail": item["path"]})

    return {
        "head": head,
        "historical": historical,
        "historical_tree": historical_tree,
        "current": current,
        "drift": drift,
        "findings": findings,
    }


def verify(report: dict, stream=None) -> None:
    """Emit the complete report, then fail."""
    if not report["findings"]:
        return
    stream = stream or sys.stderr
    print(json.dumps({
        "result": "FAIL",
        "schema": SCHEMA,
        "head": report["head"],
        "predecessor": str(PREDECESSOR.relative_to(ROOT)),
        "findings": report["findings"],
        "historical": [item for item in report["historical"] if item.get("result") != "MATCH"],
        "current": [item for item in report["current"] if item.get("result") != "MATCH"],
    }, indent=1, sort_keys=True), file=stream)
    controls = sorted({finding["control"] for finding in report["findings"]})
    raise MeasurementError("V11 active measurement failed: " + ", ".join(controls))


def build_record(report: dict, review_sha256: str, predecessor: dict) -> dict:
    record = predecessor["record"]
    drift_paths = {item["path"] for item in report["drift"]}
    return {
        "schema": SCHEMA,
        "purpose": "active-source verification of the measured V11 implementation set at the current head",
        "scope": "source-only byte inventory; it does not ratify the behaviour of any body that changed since the predecessor",
        "predecessor": {
            "path": str(PREDECESSOR.relative_to(ROOT)),
            "sha256": PREDECESSOR_SHA256,
            "schema": PREDECESSOR_SCHEMA,
            "implementation_head": PREDECESSOR_HEAD,
            "implementation_tree": PREDECESSOR_TREE,
            "status": "FROZEN_HISTORICAL_MEASUREMENT_NOT_REGENERATED",
        },
        "predecessor_historical_verification": {
            "verified_paths": len(report["historical"]),
            "blob_mismatches": 0,
            "tree": report["historical_tree"],
            "result": "PASS",
        },
        "branch": BRANCH,
        "head_binding": ("NONE_BY_DESIGN: the record pins each measured body by Git blob id and SHA-256, so it "
                         "verifies at any head that has not changed them and never has to name the commit that "
                         "carries it"),
        "measured_path_count": len(report["current"]),
        "measured_path_set_sha256": MEASURED_PATH_SET_SHA256,
        "measured_paths": [{"path": item["path"], "git_blob_sha": item["git_blob_sha"], "sha256": item["sha256"]}
                           for item in report["current"]],
        "unchanged_since_predecessor": len(report["current"]) - len(drift_paths),
        "drift_from_predecessor": report["drift"],
        "review": {"path": str(REVIEW.relative_to(ROOT)), "sha256": review_sha256},
        "numerical_authority_unchanged": sorted(NUMERICAL_CORE_PATHS),
        "historical_primary_v2_sha256": record["historical_primary_v2_sha256"],
        "historical_secondary_v2_sha256": record["historical_secondary_v2_sha256"],
        "event_04_retry": False,
        "event_05_executed": False,
        "live_event_05_authorization_created": False,
        "original_checkpoint_access": 0,
        "historical_master_ledger": record["historical_master_ledger"],
        "result": "PASS",
    }


def generate(git: GitReader | None = None, head: str | None = None) -> dict:
    git = git or GitReader()
    predecessor = load_predecessor(PREDECESSOR.read_bytes())
    head = head or git.head()
    report = measure(git, read_file, head, predecessor)
    verify(report)
    return build_record(report, hashlib.sha256(REVIEW.read_bytes()).hexdigest(), predecessor)


def serialize(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify the committed v9 record reproduces at the current head")
    arguments = parser.parse_args(argv)
    raw = serialize(generate())
    if arguments.check:
        if not OUTPUT.is_file():
            raise MeasurementError(f"missing active measurement {OUTPUT.relative_to(ROOT)}")
        if OUTPUT.read_text() != raw:
            print(json.dumps({"result": "FAIL", "control": "ACTIVE_MEASUREMENT_DRIFT",
                              "detail": "the committed v9 record does not reproduce at this head; regenerate it in the same commit as the source change"},
                             indent=1), file=sys.stderr)
            raise MeasurementError("V11 active measurement drift")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(raw)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
