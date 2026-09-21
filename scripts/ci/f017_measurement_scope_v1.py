#!/usr/bin/env python3
"""Historical measurement integrity, not current execution authorization.

The frozen generator's PATHS and return expression are evaluated as data using
a closed interpreter. Git supplies actual historical object bytes. No research
module is imported or executed and no authority file is written. Current source
gates and behavioral tests remain separate mandatory workflow invocations.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[2]
MEASUREMENT = "docs/architecture/reviews/evidence/f017-v11-result-envelope-implementation-measurement-v8.json"
GENERATOR = "scripts/research/generate_f017_v11_measurement_v1.py"
HISTORICAL_HEAD = "f35d341110c67377200ad353ab56a3cf38615a73"
HISTORICAL_TREE = "08864e7d529c91c0ec8f4bf9661006503e6d7dc9"
RECORD_COMMIT = "5939dd4588738666279da37408264b6b8b0ad4f2"
RECORD_SHA = "c529221a53a338dfe57d65f855f1b9d9b11e0b0251562f84067a65a0538a6414"
GENERATOR_SHA = "ead39c8a8e1f8be4e0dbcd42121beaf58470dbf7dbcb4d93bcc83ef0f8527ef0"
SOURCE_BASE = "6f59d9db93e92afed142b543a0e2fc19e0362bb4"
WORKFLOW_BASE_SHA = "3b18be9762f19a8115f311080f6ebfa906a697e889a9c4b7c3fb9c0c790ee68a"
# The second frozen lineage. A required F017 step in the consolidated tree may
# only contain lines that one of the two historical workflows already contained:
# the qualify line above, and the native line here. Both are historical commits
# already in this history and neither will ever change; advancing either is a
# deliberate edit to these constants, which is exactly the review point that a
# change to a mandatory step should require.
NATIVE_BASE = "44c1b34eaec4768933f807ea6406d9dcb97f00e9"
NATIVE_WORKFLOW_SHA256 = "72cb1cfe1b5563a12bc9691ce28914c1391d0f67952a73e5eb5426acbdb49c0d"
OLD_COMMAND = ".venv/bin/python scripts/research/generate_f017_v11_measurement_v1.py --check"
NEW_COMMANDS = (
    ".venv/bin/python scripts/ci/f017_measurement_scope_v1.py --check",
    ".venv/bin/python -I -S -B scripts/research/tests/f017_primary_confined_ci_v1.py",
)


def require(ok, label):
    if not ok:
        raise ValueError(label)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def blob_id(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "DUPLICATE_RECORD_KEY")
        result[key] = value
    return result


def _return_value(node, names):
    """Only the pinned generator's non-executable output construction grammar."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.Dict):
        keys = [_return_value(k, names) for k in node.keys]
        require(len(set(keys)) == len(keys), "GENERATOR_DUPLICATE_KEY")
        return dict(zip(keys, (_return_value(v, names) for v in node.values), strict=True))
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "len" and len(node.args) == 1 and not node.keywords
            and isinstance(node.args[0], ast.Name) and node.args[0].id == "records"):
        return len(names["records"])
    raise ValueError("GENERATOR_OUTPUT_GRAMMAR")


def generator_description(raw):
    require(digest(raw) == GENERATOR_SHA, "GENERATOR_IDENTITY")
    tree = ast.parse(raw)
    assignments = [n for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "PATHS" for t in n.targets)]
    require(len(assignments) == 1, "GENERATOR_PATH_CENSUS")
    paths = ast.literal_eval(assignments[0].value)
    require(type(paths) is tuple and len(paths) == len(set(paths)) == 36, "GENERATOR_PATH_CENSUS")
    for path in paths:
        require(type(path) is str and path.startswith("scripts/research/")
                and str(PurePosixPath(path)) == path and ".." not in PurePosixPath(path).parts,
                "GENERATOR_PATH")
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "generate")
    returns = [n for n in function.body if isinstance(n, ast.Return)]
    require(len(returns) == 1, "GENERATOR_RETURN_CENSUS")
    return paths, returns[0].value


def verify_historical(record_raw, generator_raw, head, tree, objects):
    """objects: exact declared path -> (Git blob identity, actual Git body)."""
    require(digest(record_raw) == RECORD_SHA, "RECORD_IDENTITY")
    record = json.loads(record_raw, object_pairs_hook=unique)
    require(head == record["implementation_head"] == HISTORICAL_HEAD, "HISTORICAL_HEAD")
    require(tree == record["implementation_tree"] == HISTORICAL_TREE, "HISTORICAL_TREE")
    paths, output_node = generator_description(generator_raw)
    require(set(objects) == set(paths), "HISTORICAL_COMPLETE_CLOSURE")
    require([r["path"] for r in record["measured_paths"]] == list(paths), "RECORD_PATH_ORDER")
    rows = []
    for path, expected in zip(paths, record["measured_paths"], strict=True):
        git_blob, body = objects[path]
        require(type(body) is bytes and len(body) <= 1048576, "HISTORICAL_BODY_BOUND")
        require(git_blob == blob_id(body) == expected["git_blob_sha"], "HISTORICAL_BLOB:" + path)
        require(digest(body) == expected["sha256"], "HISTORICAL_HASH:" + path)
        rows.append(dict(path=path, git_blob_sha=git_blob, sha256=digest(body)))
    recomputed = _return_value(output_node, dict(head=head, tree=tree, records=rows))
    require(canonical(recomputed) == record_raw, "HISTORICAL_RECORD_RECOMPUTATION")
    return dict(result="PASS", scope="HISTORICAL_RECORD_INTEGRITY_ONLY",
                historical_head=head, historical_tree=tree, source_rows=len(rows),
                measurement_sha256=digest(record_raw), generator_sha256=digest(generator_raw),
                record_commit=RECORD_COMMIT, research_module_executions=0,
                current_execution_authorization=False)


_SCRIPT_REFERENCE = re.compile(r"scripts/(?:research|ci)/[\w./-]+\.py")
_JOB_KEY = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
_STEP_START = re.compile(r"^      - ")
_STEP_NAME = re.compile(r"^      - name:\s*(.*?)\s*$")
_GATING_KEYS = ("if:", "continue-on-error:", "timeout-minutes:", "shell:", "env:")


def _normalise(line):
    """A workflow line's identity.

    Whitespace and a trailing backslash are punctuation: the backslash joins
    lines, so appending an argument to a multi-line command changes the joined
    line without changing the command that was already there. Everything else --
    the interpreter, flags, arguments, redirects and any trailing shell -- is
    identity-bearing, so `|| true` or a rewritten assertion is a different line.
    """
    stripped = line.strip()
    return stripped[:-1].rstrip() if stripped.endswith("\\") else stripped


def _steps(text):
    """Every step block in the workflow, with the job it sits under."""
    lines = text.split("\n")
    steps = []
    job = None
    index = 0
    while index < len(lines):
        key = _JOB_KEY.match(lines[index])
        if key:
            job = key.group(1)
        if _STEP_START.match(lines[index]):
            end = index + 1
            while end < len(lines) and not _STEP_START.match(lines[end]) and not (
                lines[end].strip() and not lines[end].startswith("       ")
            ):
                end += 1
            block = lines[index:end]
            name = _STEP_NAME.match(block[0])
            steps.append({"job": job, "name": name.group(1) if name else None,
                          "lines": block})
            index = end
            continue
        index += 1
    return steps


def _gating(block):
    """The step's execution-gating keys, verbatim, in file order.

    `if:`, `continue-on-error:`, `timeout-minutes:`, `shell:` and a step-level
    `env:` block decide whether and how the step runs at all, so a required step
    may neither change them nor acquire one it did not have.
    """
    captured = []
    inside_env = False
    for line in block[1:]:
        if line.startswith("        ") and not line.startswith("         "):
            inside_env = False
            key = line.strip()
            if any(key.startswith(name) for name in _GATING_KEYS):
                captured.append(line)
                inside_env = key.startswith("env:")
        elif inside_env:
            captured.append(line)
    return "\n".join(captured)


def _job_context(text, job):
    """The job's `runs-on:` line and job-level `env:` block, verbatim."""
    lines = text.split("\n")
    captured = []
    active = False
    inside_env = False
    for line in lines:
        key = _JOB_KEY.match(line)
        if key:
            active = key.group(1) == job
            inside_env = False
            continue
        if not active:
            continue
        if line.startswith("    ") and not line.startswith("     "):
            inside_env = False
            entry = line.strip()
            if entry.startswith("runs-on:") or entry.startswith("env:"):
                captured.append(line)
                inside_env = entry.startswith("env:")
        elif inside_env:
            captured.append(line)
    return "\n".join(captured)


def _ordered_subset(expected_lines, current_lines):
    cursor = 0
    for line in expected_lines:
        while cursor < len(current_lines) and current_lines[cursor] != line:
            cursor += 1
        if cursor == len(current_lines):
            return False
        cursor += 1
    return True


def _is_required(block_text):
    for path in _SCRIPT_REFERENCE.findall(block_text):
        if "f017" in path.rsplit("/", 1)[-1].lower():
            return True
    return any(command in block_text for command in NEW_COMMANDS)


def verify_workflow_inventory(original, current, native):
    """Bound every required F017 step to its two frozen lineages.

    The guarantee is that each mandatory F017 check remains a separate,
    unaltered invocation in its existing context. Whole-file byte equality
    enforced that but forbade any unrelated addition, so it could not survive
    integration with another track's CI. A line inventory survived integration
    but could not see step-level gating: `if: false`, `continue-on-error: true`,
    a deleted or weakened assertion, an inserted `set +e` or `exit 0`, or
    `|| true` on a continuation line all passed it.

    A required step is therefore bounded from both sides. Every line the qualify
    lineage expects must still be there, byte-identical and in order; and every
    line actually present must come from one of the two frozen lineages, so
    nothing invented can live inside a mandatory step. Gating keys and the
    enclosing job's execution context must match the qualify lineage exactly.
    Additive steps, and any change to a non-required step, remain unconstrained.
    """
    require(digest(original) == WORKFLOW_BASE_SHA, "WORKFLOW_ORIGINAL_IDENTITY")
    require(digest(native) == NATIVE_WORKFLOW_SHA256, "WORKFLOW_NATIVE_IDENTITY")
    before = original.decode()
    require(before.count(OLD_COMMAND) == 1, "WORKFLOW_OLD_CHECK_CENSUS")
    replacement = ("\n          ").join(NEW_COMMANDS)
    expected = before.replace(OLD_COMMAND, replacement)

    native_text = native.decode()
    native_substituted = native_text.count(OLD_COMMAND) == 1
    if native_substituted:
        native_text = native_text.replace(OLD_COMMAND, replacement)

    current_text = current.decode()
    expected_steps = _steps(expected)
    current_steps = _steps(current_text)
    native_steps = {s["name"]: s for s in _steps(native_text) if s["name"]}
    current_by_name = {}
    for step in current_steps:
        current_by_name.setdefault(step["name"], step)

    required = [s for s in expected_steps if _is_required("\n".join(s["lines"]))]
    require(required, "F017_REQUIRED_STEP_CENSUS")

    positions = []
    for step in required:
        name = step["name"]
        current_step = current_by_name.get(name)
        require(current_step is not None, "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")

        expected_lines = [_normalise(line) for line in step["lines"]]
        current_lines = [_normalise(line) for line in current_step["lines"]]
        # (a) nothing the qualify lineage requires may be dropped, altered or reordered.
        require(_ordered_subset(expected_lines, current_lines),
                "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")
        # (b) nothing from outside the two frozen lineages may appear inside the step.
        native_step = native_steps.get(name)
        permitted = set(expected_lines)
        if native_step is not None:
            permitted |= {_normalise(line) for line in native_step["lines"]}
        require(all(line in permitted for line in current_lines),
                "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")
        # (c) execution gating may not change or be acquired.
        require(_gating(current_step["lines"]) == _gating(step["lines"]),
                "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")
        # (d) same job, same execution context, same relative order.
        require(current_step["job"] == step["job"], "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")
        require(_job_context(current_text, current_step["job"])
                == _job_context(expected, step["job"]),
                "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")
        positions.append(current_steps.index(current_step))
    require(positions == sorted(positions), "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")

    checks = re.findall(_SCRIPT_REFERENCE, before)
    f017_checks = [p for p in checks if 'f017' in PurePosixPath(p).name.lower()]
    require(GENERATOR in f017_checks, "F017_ORIGINAL_CHECK_PRESENT")
    return dict(result="PASS", original_script_references=len(checks), f017_script_references=len(f017_checks), relocated_checks=1,
                unchanged_other_f017_checks=len(f017_checks)-1, historical_context="EXACT_F35D_OBJECTS",
                current_context="CURRENT_CHECKOUT", both_legs_required=True,
                required_steps=len(required),
                native_lineage_substituted=native_substituted,
                additive_steps=len(current_steps)-len(_steps(expected)))


def read_current(relative):
    path = ROOT / relative
    require(path.is_file() and not path.is_symlink(), "CURRENT_REGULAR_SOURCE")
    raw = path.read_bytes()
    require(len(raw) <= 12 * 1024 * 1024, "CURRENT_SOURCE_BOUND")
    return raw


def git(*args):
    import subprocess
    p = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=ROOT,
                       capture_output=True, timeout=30)
    require(p.returncode == 0, "HISTORICAL_GIT_OBJECT_UNAVAILABLE")
    require(len(p.stdout) <= 12 * 1024 * 1024, "GIT_OUTPUT_BOUND")
    return p.stdout


def check():
    record = read_current(MEASUREMENT)
    generator = read_current(GENERATOR)
    require(git("show", RECORD_COMMIT + ":" + MEASUREMENT) == record, "RECORD_GIT_CUSTODY")
    require(git("show", HISTORICAL_HEAD + ":" + GENERATOR) == generator, "GENERATOR_GIT_CUSTODY")
    paths, _ = generator_description(generator)
    tree = git("rev-parse", HISTORICAL_HEAD + "^{tree}").decode().strip()
    objects = {p: (git("rev-parse", HISTORICAL_HEAD + ":" + p).decode().strip(),
                   git("show", HISTORICAL_HEAD + ":" + p)) for p in paths}
    historical = verify_historical(record, generator, HISTORICAL_HEAD, tree, objects)
    inventory = verify_workflow_inventory(git("show", SOURCE_BASE + ":.github/workflows/macos.yml"),
                                          read_current(".github/workflows/macos.yml"),
                                          git("show", NATIVE_BASE + ":.github/workflows/macos.yml"))
    return dict(historical=historical, invocation_inventory=inventory,
                current_behavior="SEPARATE_MANDATORY_CONFINED_PRIMARY_AND_EXISTING_CURRENT_WORKFLOW_CHECKS",
                live_authority_created=False, result="PASS")


if __name__ == "__main__":
    import sys
    require(sys.argv[1:] == ["--check"] and sys.flags.optimize == 0, "CHECK_ONLY_INVOCATION")
    print(json.dumps(check(), sort_keys=True))
