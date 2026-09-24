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
# The resolution. It began as the merge commit where the qualify and native
# lineages were reconciled (9e145b09, workflow sha256 4e132d2c...); it is now
# advanced, deliberately and in the commit immediately after the one that added
# the two F020 required steps, to that commit's tree (4f0ed191, 185c2183...). It
# is advanced once more, to the commit that made evidence-integrity also run
# for mixed code+evidence ranges; that commit changed two residual lines (a
# classify output and the integrity job's `if:`) and no required step. It is
# advanced again, to the commit that added the required F020 Slice 2B native
# qualification step (99677210); that commit added one required block and
# changed no existing one. It is advanced once more, to 7f28bc5c, whose only
# change is that step's post-check (the runner architecture is recorded
# rather than predicted, and E1/E6 counts are asserted). The
# earlier resolution's required blocks are contained in this one byte for
# byte -- advancing the base never rewrites or drops one. Required steps are
# frozen at these exact bytes. Line-level
# rules were shown insufficient -- allowed lines can be composed into a function
# definition that swallows the body, and execution can be redirected from above
# the step by `defaults.run.shell`, job `if:` or job `continue-on-error:` -- so
# the whole step block, its job's execution keys and the workflow's own defaults
# are compared byte for byte instead.
RESOLUTION_BASE = "7f28bc5cd6727d2d80952ecd19347d6e224d8f6d"
RESOLUTION_WORKFLOW_SHA256 = "c759c5d1df2aae04f123853674775667b4b2bec2fd604b58a587797a12133551"
# Everything that decides whether, where and how a step runs.
JOB_EXECUTION_KEYS = ("runs-on", "env", "if", "continue-on-error", "defaults",
                      "timeout-minutes", "strategy", "container", "services")
WORKFLOW_EXECUTION_KEYS = ("defaults", "env")
OLD_COMMAND = ".venv/bin/python scripts/research/generate_f017_v11_measurement_v1.py --check"
NEW_COMMANDS = (
    ".venv/bin/python scripts/ci/f017_measurement_scope_v1.py --check",
    ".venv/bin/python -I -S -B scripts/research/tests/f017_primary_confined_ci_v1.py",
)
# Steps that are required although no script they name has `f017` in its
# basename. The basename rule was a proxy for "this step is mandatory", and it
# stops being one as soon as a successor feature owns a mandatory gate: F020's
# native affine qualification must run, and naming its script `f017_...` to get
# that would be a lie about what the script is. So the selector is extended
# with an explicit, reviewable list of step NAMES. Adding a name here makes
# that step frozen at the resolution exactly like an F017 step, which is why
# the list is short, spelled in full, and moves only together with a deliberate
# advance of RESOLUTION_BASE and RESOLUTION_WORKFLOW_SHA256.
REQUIRED_EXTRA_STEP_NAMES = (
    "Qualify MLX affine compatibility (synthetic, pinned MLX wheel)",
    "Test MLX affine representation",
    # F020 Slice 2B (owner GO 2026-09-23): the native qualification that runs
    # the qualify child on the runner GPU over the frozen population.
    "Qualify F020 Slice 2B native primitives (frozen synthetic population, runner GPU)",
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
    first = block_text.split("\n", 1)[0]
    name = _STEP_NAME.match(first)
    if name and name.group(1) in REQUIRED_EXTRA_STEP_NAMES:
        return True
    for path in _SCRIPT_REFERENCE.findall(block_text):
        if "f017" in path.rsplit("/", 1)[-1].lower():
            return True
    return any(command in block_text for command in NEW_COMMANDS)


# A block-scalar header may carry an indentation indicator, a chomping
# indicator and a trailing comment; all three forms open a scalar body.
_BLOCK_SCALAR = re.compile(r"^(\s*)[^\s#][^:]*:\s*[|>][-+0-9]*\s*(?:#.*)?$")
_STEP_ITEM = re.compile(r"^(\s*)- (name|uses|id):")
_QUOTED_KEY = re.compile(r"""^\s*(?:-\s+)?["'][^"']+["']\s*:""")
_COMPLEX_KEY = re.compile(r"^\s*\?\s")
_MERGE_KEY = re.compile(r"^\s*<<\s*:")
# YAML anchor and alias names are any non-space, non-flow-indicator run, and an
# alias may be followed by a comment, so the earlier `[A-Za-z0-9_-]` and
# end-of-line forms were both too narrow. Tags include the verbatim `!<...>`
# form as well as shorthand.
_ANCHOR_NAME = r"[^\s\[\]{},]+"
_ANCHOR = re.compile(r"(?:^|\s)&" + _ANCHOR_NAME)
_ALIAS = re.compile(r"(?:^|[\s:\-])\*" + _ANCHOR_NAME)
_TAG = re.compile(r"(?:^|\s)!(?:<[^>]*>|!?[A-Za-z0-9_/%.-]*)")
_FLOW = re.compile(r":\s*[\[{]")
_MAP_KEY = re.compile(r"^(\s*)(?:- )?([A-Za-z0-9_.-]+):(\s|$)")
# `key : value` is the same key to YAML and a different string to a comparison.
_SPACED_KEY = re.compile(r"^\s*(?:- )?[A-Za-z0-9_.-]+[ \t]+:(?:\s|$)")


def _structural(text):
    """Every line that is YAML structure rather than block-scalar content.

    `run: |` bodies are shell and Python. They legitimately contain `!=`, `&&`,
    `*` and `{`, none of which are YAML constructs there, so the canonical-form
    gate must not read them as such.
    """
    lines = text.split("\n")
    block_indent = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if block_indent is not None:
            if stripped and indent <= block_indent:
                block_indent = None
            else:
                continue
        if stripped:
            block = _BLOCK_SCALAR.match(line)
            if block:
                yield index, line
                block_indent = len(block.group(1))
                continue
        yield index, line


def decode_workflow(raw, label):
    """Decode a workflow only if its bytes admit exactly one line structure.

    Every scanner here splits on "\n". YAML also recognises a bare CR, NEL,
    U+2028 and U+2029 as line breaks, so a file containing one of those has a
    line structure the scanners cannot see: CR-separated structural lines would
    sit inside what this code treats as one removable non-required step while
    the YAML parser reads them as enclosing job structure, and the residual
    could then omit context it claims to freeze. Rather than teach every scanner
    YAML's full break set, the ambiguity is rejected outright, before any scan.

    Non-ASCII is refused in structural lines for the same reason in a different
    dimension: a Cyrillic look-alike is a different key to a byte comparison and
    the same key to a reader. `run:` bodies are exempt -- they are program text,
    not structure.
    """
    require(isinstance(raw, (bytes, bytearray)), "WORKFLOW_NONCANONICAL")
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("WORKFLOW_NONCANONICAL")
    for forbidden in (b"\r", b"\xc2\x85", b"\xe2\x80\xa8", b"\xe2\x80\xa9"):
        if forbidden in raw:
            raise ValueError("WORKFLOW_NONCANONICAL")
    for byte in raw:
        # C0 controls other than the one line break we accept; tab is rejected
        # separately by the canonical gate so its diagnostic stays specific.
        if byte < 0x20 and byte not in (0x09, 0x0A):
            raise ValueError("WORKFLOW_NONCANONICAL")
        if byte == 0x7F:
            raise ValueError("WORKFLOW_NONCANONICAL")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        raise ValueError("WORKFLOW_NONCANONICAL") from None
    if "\x85" in text or "\u2028" in text or "\u2029" in text:
        raise ValueError("WORKFLOW_NONCANONICAL")
    for index, line in _structural(text):
        if not line.isascii():
            raise ValueError("WORKFLOW_NONCANONICAL")
    return text


def canonical_form(text):
    """Reject any YAML spelling that hides meaning from a textual comparison.

    A freeze that compares text only protects what the attacker spells the way
    the freeze expects. Quoting a key, aliasing an anchored mapping, using an
    explicit `? key`, a merge key or a tab all preserve YAML meaning while
    changing the bytes, so the file is first required to be written in one
    canonical form. The constructs the resolution itself uses -- `- name:`,
    `- uses:` and `- id:` step items -- are allowed explicitly; it contains no
    quoted keys, no flow collections, no anchors, aliases, tags or tabs.
    """
    problems = []
    structural = list(_structural(text))
    seen_keys = {}
    jobs = []
    step_names = {}
    current_job = None
    in_steps = False
    for index, line in structural:
        if "\t" in line:
            problems.append(f"line {index + 1}: tab in workflow structure")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        for pattern, label in ((_QUOTED_KEY, "quoted mapping key"),
                               (_COMPLEX_KEY, "explicit complex key"),
                               (_MERGE_KEY, "merge key"),
                               (_ANCHOR, "anchor"),
                               (_ALIAS, "alias"),
                               (_TAG, "tag"),
                               (_FLOW, "flow collection"),
                               (_SPACED_KEY, "whitespace before a mapping key's colon")):
            if pattern.search(line):
                problems.append(f"line {index + 1}: {label}")
        four_space = re.match(r"^    ([A-Za-z0-9_.-]+):", line)
        if four_space:
            in_steps = four_space.group(1) == "steps"
        item = re.match(r"^(\s*)- (\S+)", line)
        if item and item.group(1) == "      " and in_steps and not _STEP_ITEM.match(line):
            problems.append(f"line {index + 1}: step item is not - name:/- uses:/- id:")
        job = _JOB_KEY.match(line)
        if job:
            if job.group(1) in jobs:
                problems.append(f"line {index + 1}: duplicate job id {job.group(1)}")
            jobs.append(job.group(1))
            current_job = job.group(1)
            step_names.setdefault(current_job, [])
        # A step's name is its identity wherever it appears in the step and
        # however it is quoted, so `- uses:` first or a quoted name is the same
        # step to GitHub and must be the same step here.
        inline = re.match(r"^\s{6,}(?:- )?name:\s*(.*?)\s*$", line)
        name = inline if (inline and in_steps) else None
        if name and current_job is not None:
            value = name.group(1)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            name = re.match(r"(?s)(.*)", value)
        if name and current_job is not None:
            if name.group(1) in step_names[current_job]:
                problems.append(f"line {index + 1}: duplicate step name in {current_job}")
            step_names[current_job].append(name.group(1))
        key = _MAP_KEY.match(line)
        if key:
            indent = len(key.group(1)) + (2 if line.lstrip().startswith("- ") else 0)
            for level in [k for k in seen_keys if k > indent]:
                del seen_keys[level]
            if line.lstrip().startswith("- "):
                seen_keys[indent] = set()
            bucket = seen_keys.setdefault(indent, set())
            if key.group(2) in bucket:
                problems.append(f"line {index + 1}: duplicate key {key.group(2)}")
            bucket.add(key.group(2))
    return problems


def _step_spans(text):
    """(start, end, block) for every step, including the comments above it.

    A comment immediately above a step documents that step, so it travels with
    it: otherwise removing a non-required step would strand its comment in the
    residual and make an unrelated CI edit look like a frozen-region change.
    """
    lines = text.split("\n")
    spans = []
    index = 0
    while index < len(lines):
        if _STEP_START.match(lines[index]):
            start = index
            while start > 0:
                previous = lines[start - 1]
                if previous.strip().startswith("#") and previous.startswith("      "):
                    start -= 1
                else:
                    break
            end = index + 1
            while end < len(lines) and not _STEP_START.match(lines[end]) and not (
                lines[end].strip() and not lines[end].startswith("       ")
            ):
                end += 1
            # A trailing comment block belongs to the next step, not this one.
            while end - 1 > index and lines[end - 1].strip().startswith("#"):
                end -= 1
            spans.append((start, end, "\n".join(lines[index:end])))
            index = end
            continue
        index += 1
    return spans


def residual(text):
    """The workflow with every non-required step block removed.

    What remains is everything this doctor freezes: the workflow header, its
    `on`, `concurrency`, `permissions`, `defaults` and `env`, every job header
    and job-level key, every job that carries no required step, and every
    required step block. Non-required steps -- the Flash steps, the Feature 002
    discovery step, anything added later -- are removed before comparison and are
    therefore free to change.
    """
    lines = text.split("\n")
    keep = [True] * len(lines)
    for start, end, block in _step_spans(text):
        if not _is_required(block):
            for position in range(start, end):
                keep[position] = False
    return "\n".join(line for line, flag in zip(lines, keep) if flag)


def verify_workflow_inventory(original, current, native, resolution):
    """Freeze the qualification workflow everywhere except non-required steps.

    Enumerating key spellings does not work: a quoted `"defaults"`, an anchored
    mapping reused through an alias, an explicit `? defaults` or a tab all keep
    their YAML meaning while escaping a textual key comparison, and any one of
    them can install `run.shell: /usr/bin/true {0}` so that every required step
    becomes a no-op. So the file is first required to be in one canonical form,
    and then everything except non-required step blocks is compared byte for byte
    against the resolution. There is no key list left to miss.
    """
    require(digest(original) == WORKFLOW_BASE_SHA, "WORKFLOW_ORIGINAL_IDENTITY")
    require(digest(native) == NATIVE_WORKFLOW_SHA256, "WORKFLOW_NATIVE_IDENTITY")
    require(digest(resolution) == RESOLUTION_WORKFLOW_SHA256, "WORKFLOW_RESOLUTION_IDENTITY")
    before = decode_workflow(original, "qualify")
    require(before.count(OLD_COMMAND) == 1, "WORKFLOW_OLD_CHECK_CENSUS")

    decode_workflow(native, "native")
    resolution_text = decode_workflow(resolution, "resolution")
    current_text = decode_workflow(current, "current")
    require(not canonical_form(current_text), "WORKFLOW_NONCANONICAL")
    require(residual(current_text) == residual(resolution_text),
            "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")

    resolution_steps = _steps(resolution_text)
    current_steps = _steps(current_text)
    required = [s for s in resolution_steps if _is_required("\n".join(s["lines"]))]
    require(required, "F017_REQUIRED_STEP_CENSUS")
    by_name = {}
    for step in current_steps:
        by_name.setdefault(step["name"], []).append(step)
    positions = []
    for step in required:
        matches = by_name.get(step["name"], [])
        require(len(matches) == 1, "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")
        require(matches[0]["lines"] == step["lines"], "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")
        require(matches[0]["job"] == step["job"], "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")
        positions.append(current_steps.index(matches[0]))
    require(positions == sorted(positions), "WORKFLOW_CHECK_INVENTORY_OR_CONTEXT")

    checks = re.findall(_SCRIPT_REFERENCE, before)
    f017_checks = [p for p in checks if 'f017' in PurePosixPath(p).name.lower()]
    require(GENERATOR in f017_checks, "F017_ORIGINAL_CHECK_PRESENT")
    return dict(result="PASS", original_script_references=len(checks), f017_script_references=len(f017_checks), relocated_checks=1,
                unchanged_other_f017_checks=len(f017_checks)-1, historical_context="EXACT_F35D_OBJECTS",
                current_context="CURRENT_CHECKOUT", both_legs_required=True,
                required_steps=len(required), frozen_at=RESOLUTION_BASE,
                canonical_form="PASS", residual_frozen=True,
                free_steps=len([s for s in _step_spans(current_text) if not _is_required(s[2])]))


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
                                          git("show", NATIVE_BASE + ":.github/workflows/macos.yml"),
                                          git("show", RESOLUTION_BASE + ":.github/workflows/macos.yml"))
    return dict(historical=historical, invocation_inventory=inventory,
                current_behavior="SEPARATE_MANDATORY_CONFINED_PRIMARY_AND_EXISTING_CURRENT_WORKFLOW_CHECKS",
                live_authority_created=False, result="PASS")


if __name__ == "__main__":
    import sys
    require(sys.argv[1:] == ["--check"] and sys.flags.optimize == 0, "CHECK_ONLY_INVOCATION")
    print(json.dumps(check(), sort_keys=True))
