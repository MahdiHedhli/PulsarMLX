#!/usr/bin/env python3
"""List the donor test methods that the PulsarMLX Console parity ledger tracks.

The donor is project-maya (https://github.com/mw00/project-maya). Its checkout
is untrusted third-party data, so this tool never imports, executes or
evaluates anything from it. Each ``serve/test_*.py`` file is read as text and
parsed with :mod:`ast`; Git metadata is read as text, and no ``git`` command is
run inside the donor checkout.

What counts as a test:

* a ``def test*`` or ``async def test*`` written directly in the body of a
  module-level class (``file::Class::method``);
* a ``def test*`` or ``async def test*`` written directly at module level
  (``file::function``).

Methods a class inherits from another class are not repeated under the
subclass, and functions nested inside other functions are not listed, because
neither is a separately written test method.

Run it with an isolated interpreter and with the donor path as an argument,
from outside the donor checkout::

    python3 -I console/tools/list_donor_tests.py PATH/TO/project-maya
    python3 -I console/tools/list_donor_tests.py PATH/TO/project-maya \\
        --write-ledger console/parity/ledger.json

The second form writes the parity ledger. Each row keeps the subsystem and
disposition it already has in an existing ledger; new rows take their
subsystem from ``--subsystems`` (a JSON file) or from other rows of the same
donor file, and start with the disposition ``pending``. Rows that would
disappear are an error, because re-pinning the donor is a separate decision.

Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path, PurePosixPath

LISTING_TOOL = "console/tools/list_donor_tests.py"
DONOR_PROJECT = "project-maya"
DONOR_REPOSITORY = "https://github.com/mw00/project-maya"
DONOR_GLOB = "serve/test_*.py"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_SOURCE_BYTES = 8 * 1024 * 1024


class ListingError(RuntimeError):
    """The donor checkout or an input file cannot be listed safely."""


def is_test_name(name: str) -> bool:
    return name.startswith("test")


def list_file(root: Path, path: Path) -> list[dict]:
    """Return one row per test method or module-level test function."""

    relative = path.relative_to(root).as_posix()
    data = path.read_bytes()
    if len(data) > MAX_SOURCE_BYTES:
        raise ListingError(f"{relative}: file is larger than the listing limit")
    try:
        tree = ast.parse(data, filename=relative)
    except SyntaxError as error:
        raise ListingError(f"{relative}: cannot be parsed: {error.msg}") from error

    rows = []
    functions = (ast.FunctionDef, ast.AsyncFunctionDef)
    for node in tree.body:
        if isinstance(node, functions) and is_test_name(node.name):
            rows.append({"file": relative, "class": None, "method": node.name})
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, functions) and is_test_name(item.name):
                    rows.append({"file": relative, "class": node.name, "method": item.name})
    for row in rows:
        parts = [row["file"]] + ([row["class"]] if row["class"] else []) + [row["method"]]
        row["id"] = "::".join(parts)
    return rows


def list_donor(root: Path) -> list[dict]:
    serve = root / "serve"
    if not serve.is_dir():
        raise ListingError("the donor checkout has no serve/ directory")
    files = sorted(p for p in serve.glob("test_*.py") if p.is_file() and not p.is_symlink())
    if not files:
        raise ListingError("the donor checkout has no serve/test_*.py files")
    rows = [row for path in files for row in list_file(root, path)]
    ids = [row["id"] for row in rows]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        # A class or function defined twice in one file: Python keeps only the
        # last definition, so a listing with duplicates would overcount.
        raise ListingError("duplicate test ids: " + ", ".join(duplicates))
    return sorted(rows, key=lambda row: row["id"])


def read_head_commit(root: Path) -> str | None:
    """Read the checked-out commit from .git as text, without running git."""

    git_dir = root / ".git"
    if git_dir.is_file():
        text = git_dir.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir: "):
            return None
        git_dir = (root / text[len("gitdir: "):]).resolve()
    head_file = git_dir / "HEAD"
    if not head_file.is_file():
        return None
    head = head_file.read_text(encoding="utf-8").strip()
    if SHA_RE.match(head):
        return head
    if not head.startswith("ref: "):
        return None
    ref = head[len("ref: "):]
    if ".." in PurePosixPath(ref).parts:
        return None
    loose = git_dir / ref
    if loose.is_file():
        value = loose.read_text(encoding="utf-8").strip()
        return value if SHA_RE.match(value) else None
    packed = git_dir / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            fields = line.split(" ")
            if len(fields) == 2 and fields[1] == ref and SHA_RE.match(fields[0]):
                return fields[0]
    return None


def load_subsystems(path: Path) -> dict[str, str]:
    """Accept a {file: subsystem} map, or a JSON record with a test_inventory list."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("test_inventory"), list):
        mapping = {}
        for entry in data["test_inventory"]:
            mapping[str(entry["maya_test_file"])] = str(entry["subsystem"])
        return mapping
    if isinstance(data, dict) and all(isinstance(v, str) for v in data.values()):
        return dict(data)
    raise ListingError(f"{path}: not a subsystem map")


def build_ledger(rows: list[dict], commit: str, existing: dict | None,
                 subsystems: dict[str, str]) -> dict:
    old_rows = {row["id"]: row for row in (existing or {}).get("rows", [])}
    by_file = {}
    for row in old_rows.values():
        by_file.setdefault(row["file"], row.get("subsystem"))

    removed = sorted(set(old_rows) - {row["id"] for row in rows})
    if removed:
        raise ListingError(
            f"{len(removed)} existing ledger rows are no longer in the donor listing "
            f"(first: {removed[0]}); re-pinning the donor is a separate decision"
        )

    out_rows = []
    missing = set()
    for row in rows:
        old = old_rows.get(row["id"])
        if old is not None:
            merged = dict(old)
            merged.update({k: row[k] for k in ("id", "file", "class", "method")})
        else:
            subsystem = subsystems.get(row["file"]) or by_file.get(row["file"])
            if subsystem is None:
                missing.add(row["file"])
            merged = {
                "id": row["id"],
                "file": row["file"],
                "class": row["class"],
                "method": row["method"],
                "subsystem": subsystem,
                "disposition": "pending",
            }
        out_rows.append(merged)
    if missing:
        raise ListingError("no subsystem known for: " + ", ".join(sorted(missing)))

    return {
        "ledger": "PulsarMLX Console parity ledger",
        "donor": {
            "project": DONOR_PROJECT,
            "repository": DONOR_REPOSITORY,
            "commit": commit,
            "scope": DONOR_GLOB,
        },
        "listing_tool": LISTING_TOOL,
        "count": len(out_rows),
        "rows": out_rows,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("donor", type=Path, help="path of a project-maya checkout")
    parser.add_argument("--expect-commit", help="fail unless the checkout is at this commit")
    parser.add_argument("--write-ledger", type=Path, help="write or update this ledger file")
    parser.add_argument("--subsystems", type=Path,
                        help="JSON map of donor file to subsystem for new rows")
    parser.add_argument("--summary", action="store_true",
                        help="print per-file counts instead of the listing")
    args = parser.parse_args(argv)

    try:
        root = args.donor.resolve(strict=True)
        rows = list_donor(root)
        commit = read_head_commit(root)
        if args.expect_commit:
            if commit is None:
                raise ListingError("cannot read the donor commit to check it")
            if commit != args.expect_commit:
                raise ListingError(f"donor is at {commit}, expected {args.expect_commit}")

        if args.write_ledger:
            if commit is None:
                raise ListingError("cannot read the donor commit for the ledger")
            existing = None
            if args.write_ledger.is_file():
                existing = json.loads(args.write_ledger.read_text(encoding="utf-8"))
                old_commit = existing.get("donor", {}).get("commit")
                if old_commit and old_commit != commit:
                    raise ListingError(
                        f"ledger is pinned to {old_commit}, donor is at {commit}; "
                        "re-pinning the donor is a separate decision"
                    )
            subsystems = load_subsystems(args.subsystems) if args.subsystems else {}
            ledger = build_ledger(rows, commit, existing, subsystems)
            text = json.dumps(ledger, indent=2, ensure_ascii=True) + "\n"
            args.write_ledger.write_text(text, encoding="utf-8")
            files = len({row["file"] for row in rows})
            print(f"wrote {args.write_ledger}: {ledger['count']} rows from {files} files")
            return 0

        if args.summary:
            counts = {}
            for row in rows:
                counts[row["file"]] = counts.get(row["file"], 0) + 1
            for name in sorted(counts):
                print(f"{counts[name]:5d}  {name}")
            print(f"{len(rows):5d}  total in {len(counts)} files")
            return 0

        for row in rows:
            print(row["id"])
        return 0
    except (ListingError, OSError, ValueError, KeyError) as error:
        print(f"list_donor_tests: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
