"""Negative controls for the active V11 implementation measurement (v9).

The module's only process boundary is its GitReader, so every control here
drives the real verification logic with a fake repository: no temporary clone
and no dependence on the checkout's own state.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/research/generate_f017_v11_measurement_v2.py"
SPEC = importlib.util.spec_from_file_location("f017_v11_measurement_v2", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

HEAD = "1" * 40
CHANGED = "scripts/research/f017_corrected_oracle_primary_wrapper_v11.py"
UNCHANGED = "scripts/research/f017_corrected_oracle_primary_numerics_v3.py"


def blob_id(raw: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(raw) + raw).hexdigest()


class FakeGit:
    """Two-head repository: the frozen predecessor head and a current head."""

    def __init__(self, historical: dict, current: dict, trees: dict | None = None):
        self.objects = {MODULE.PREDECESSOR_HEAD: historical, HEAD: current}
        self.trees = trees or {MODULE.PREDECESSOR_HEAD: MODULE.PREDECESSOR_TREE, HEAD: "2" * 40}

    def blob(self, head: str, path: str) -> bytes:
        try:
            return self.objects[head][path]
        except KeyError:
            raise RuntimeError(f"no object {head}:{path}")

    def blob_id(self, head: str, path: str) -> str:
        return blob_id(self.blob(head, path))

    def tree(self, head: str) -> str:
        return self.trees[head]

    def head(self) -> str:
        return HEAD

    def commits_touching(self, since: str, until: str, path: str):
        return [{"commit": "5b39a21aa8369ea2e53ea8e406002cc74250cec3",
                 "subject": "feat: simplify Event 06 to minimum gate path"}] if path == CHANGED else []


def world(**overrides):
    """A consistent fake: 36 paths, one of them legitimately drifted."""
    paths = [f"scripts/research/module_{index:02d}.py" for index in range(34)] + [CHANGED, UNCHANGED]
    historical = {path: f"# {path} at v8\n".encode() for path in paths}
    current = dict(historical)
    current[CHANGED] = b"# minimum-gate rewrite\n"
    record = {
        "schema": MODULE.PREDECESSOR_SCHEMA,
        "implementation_head": MODULE.PREDECESSOR_HEAD,
        "implementation_tree": MODULE.PREDECESSOR_TREE,
        "measured_path_count": len(paths),
        "measured_paths": [{"path": path, "git_blob_sha": blob_id(historical[path]),
                            "sha256": hashlib.sha256(historical[path]).hexdigest()} for path in paths],
        "historical_primary_v2_sha256": "a" * 64,
        "historical_secondary_v2_sha256": "b" * 64,
        "original_checkpoint_access": 0,
        "historical_master_ledger": 175,
        "result": "PASS",
    }
    record.update(overrides.pop("record", {}))
    historical.update(overrides.pop("historical", {}))
    current.update(overrides.pop("current", {}))
    for path in overrides.pop("drop_current", ()):
        current.pop(path)
    for path in overrides.pop("drop_historical", ()):
        historical.pop(path)
    assert not overrides, overrides
    return record, FakeGit(historical, current), current


def run(record, git, worktree, *, set_digest=None):
    raw = json.dumps(record, sort_keys=True).encode()
    monkey = MODULE.MEASURED_PATH_SET_SHA256
    MODULE.MEASURED_PATH_SET_SHA256 = set_digest or MODULE.path_set_sha256(
        [item["path"] for item in record["measured_paths"]])
    monkey_sha = MODULE.PREDECESSOR_SHA256
    MODULE.PREDECESSOR_SHA256 = hashlib.sha256(raw).hexdigest()
    monkey_count = MODULE.MEASURED_PATH_COUNT
    MODULE.MEASURED_PATH_COUNT = record["measured_path_count"]
    try:
        predecessor = MODULE.load_predecessor(raw)
        report = MODULE.measure(git, lambda path: worktree[path], HEAD, predecessor)
        MODULE.verify(report)
        return report
    finally:
        MODULE.MEASURED_PATH_SET_SHA256 = monkey
        MODULE.PREDECESSOR_SHA256 = monkey_sha
        MODULE.MEASURED_PATH_COUNT = monkey_count


def controls(excinfo) -> set[str]:
    return set(str(excinfo.value).split(": ", 1)[1].split(", "))


def test_accepted_drift_passes_and_is_reported_with_its_lineage() -> None:
    report = run(*world())
    assert report["findings"] == []
    assert [item["path"] for item in report["drift"]] == [CHANGED]
    assert report["drift"][0]["accepted_commits"][0]["commit"].startswith("5b39a21a")
    assert all(item["result"] == "MATCH" for item in report["historical"])
    assert all(item["result"] == "MATCH" for item in report["current"])


def test_mutated_working_tree_source_fails() -> None:
    record, git, worktree = world()
    worktree = dict(worktree, **{UNCHANGED: b"# local edit\n"})
    with pytest.raises(MODULE.MeasurementError) as excinfo:
        run(record, git, worktree)
    assert "WORKTREE_DIFFERS_FROM_HEAD" in controls(excinfo)


def test_missing_working_tree_file_fails() -> None:
    record, git, worktree = world()
    worktree = {path: raw for path, raw in worktree.items() if path != UNCHANGED}
    with pytest.raises(MODULE.MeasurementError) as excinfo:
        run(record, git, worktree)
    assert "WORKTREE_FILE_MISSING" in controls(excinfo)


def test_path_missing_at_head_fails() -> None:
    record, git, worktree = world(drop_current=[UNCHANGED])
    with pytest.raises(MODULE.MeasurementError) as excinfo:
        run(record, git, worktree)
    assert "CURRENT_OBJECT_MISSING" in controls(excinfo)


def test_tampered_predecessor_blob_id_fails() -> None:
    record, git, worktree = world()
    record = copy.deepcopy(record)
    record["measured_paths"][0]["git_blob_sha"] = "0" * 40
    with pytest.raises(MODULE.MeasurementError) as excinfo:
        run(record, git, worktree)
    assert "HISTORICAL_DRIFT" in controls(excinfo)


def test_historical_drift_at_the_frozen_head_fails() -> None:
    record, git, worktree = world(historical={UNCHANGED: b"# rewritten history\n"})
    with pytest.raises(MODULE.MeasurementError) as excinfo:
        run(record, git, worktree)
    assert "HISTORICAL_DRIFT" in controls(excinfo)


def test_missing_historical_object_fails() -> None:
    record, git, worktree = world(drop_historical=[UNCHANGED])
    with pytest.raises(MODULE.MeasurementError) as excinfo:
        run(record, git, worktree)
    assert "HISTORICAL_OBJECT_MISSING" in controls(excinfo)


@pytest.mark.parametrize("field,value,control", [
    ("schema", "pulsarmlx.f017.v11-result-envelope-implementation-measurement/7.0.0", "PREDECESSOR_SCHEMA"),
    ("implementation_head", "9" * 40, "PREDECESSOR_HEAD"),
    ("implementation_tree", "9" * 40, "PREDECESSOR_TREE"),
    ("original_checkpoint_access", 1, "PREDECESSOR_CHECKPOINT_ACCESS"),
])
def test_wrong_predecessor_binding_fails(field, value, control) -> None:
    record, git, worktree = world()
    record = copy.deepcopy(record)
    record[field] = value
    with pytest.raises(MODULE.MeasurementError) as excinfo:
        run(record, git, worktree)
    assert control in controls(excinfo)


def test_predecessor_bytes_must_match_the_bound_digest() -> None:
    record, git, worktree = world()
    raw = json.dumps(record, sort_keys=True).encode()
    predecessor = MODULE.load_predecessor(raw)  # real PREDECESSOR_SHA256 constant
    assert any(finding["control"] == "PREDECESSOR_BYTES" for finding in predecessor["findings"])


def test_widening_the_source_set_fails() -> None:
    record, git, worktree = world()
    record = copy.deepcopy(record)
    extra = "scripts/research/newly_added_module.py"
    record["measured_paths"].append({"path": extra, "git_blob_sha": "0" * 40, "sha256": "0" * 64})
    record["measured_path_count"] += 1
    git.objects[MODULE.PREDECESSOR_HEAD][extra] = b""
    git.objects[HEAD][extra] = b""
    worktree = dict(worktree, **{extra: b""})
    with pytest.raises(MODULE.MeasurementError) as excinfo:
        run(record, git, worktree, set_digest=MODULE.path_set_sha256(
            [item["path"] for item in record["measured_paths"][:-1]]))
    assert "SOURCE_SET_WIDENED_WITHOUT_APPROVAL" in controls(excinfo)


def test_drift_without_commit_lineage_fails() -> None:
    record, git, worktree = world(current={UNCHANGED: b"# appeared from nowhere\n"})
    worktree = dict(worktree, **{UNCHANGED: b"# appeared from nowhere\n"})
    with pytest.raises(MODULE.MeasurementError) as excinfo:
        run(record, git, worktree)
    assert {"DRIFT_WITHOUT_LINEAGE", "NUMERICAL_AUTHORITY_DRIFT"} <= controls(excinfo)


def test_numerical_core_drift_is_a_hard_failure() -> None:
    record, git, worktree = world(current={UNCHANGED: b"# numerics changed\n"})
    worktree = dict(worktree, **{UNCHANGED: b"# numerics changed\n"})

    class Lineage(FakeGit):
        def commits_touching(self, since, until, path):
            return [{"commit": "c" * 40, "subject": "some accepted commit"}]

    lineage = Lineage(git.objects[MODULE.PREDECESSOR_HEAD], git.objects[HEAD])
    with pytest.raises(MODULE.MeasurementError) as excinfo:
        run(record, lineage, worktree)
    assert "NUMERICAL_AUTHORITY_DRIFT" in controls(excinfo)


def test_the_complete_report_is_emitted_before_the_exception(capsys) -> None:
    record, git, worktree = world()
    worktree = dict(worktree, **{UNCHANGED: b"# local edit\n"})
    with pytest.raises(MODULE.MeasurementError):
        run(record, git, worktree)
    emitted = json.loads(capsys.readouterr().err)
    assert emitted["result"] == "FAIL"
    assert emitted["head"] == HEAD
    assert any(item["path"] == UNCHANGED for item in emitted["current"])


def test_real_predecessor_is_bound_byte_for_byte() -> None:
    raw = MODULE.PREDECESSOR.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == MODULE.PREDECESSOR_SHA256
    predecessor = MODULE.load_predecessor(raw)
    assert predecessor["findings"] == []
    assert len(predecessor["paths"]) == MODULE.MEASURED_PATH_COUNT


def test_the_event06_bridge_pins_agree_with_the_active_measurement() -> None:
    """Two places pin the same bytes; they must not be able to disagree."""
    bridge = importlib.util.spec_from_file_location(
        "f017_event06_numerical_bridge",
        ROOT / "scripts/research/qualify_f017_event06_numerical_bridge_v1.py")
    source = (ROOT / "scripts/research/qualify_f017_event06_numerical_bridge_v1.py").read_text()
    pinned = {}
    inside = False
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("IMMUTABLE = {"):
            inside = True
            continue
        if inside:
            if stripped.startswith("}"):
                break
            if stripped.startswith('"'):
                path, _, digest = stripped.partition(":")
                pinned[path.strip().strip('",')] = digest.strip().strip('",')
    assert pinned, "could not read the bridge's immutable pins"
    assert bridge is not None
    measurement = json.loads(
        (ROOT / "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v9.json").read_text())
    measured = {item["path"]: item["sha256"] for item in measurement["measured_paths"]}
    for path, digest in pinned.items():
        if path in measured:
            assert measured[path] == digest, f"{path}: the bridge pin and the active measurement disagree"
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, f"{path}: pin does not match the working tree"
