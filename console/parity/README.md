# Parity ledger

**Status (2026-11-14):** 913 rows, all `pending`. No row is resolved yet.

[`ledger.json`](ledger.json) is how PulsarMLX Console measures "full parity" with the
serving layer of project-maya, the donor. It has one row per donor test method in
`serve/test_*.py` at the pinned donor commit `7e68a30f2f208056195352129188661fb6b94445`
(release v1.1.63). By the end of the increment (milestone M10), each row must resolve to
exactly one disposition from the closed set `rust-test`, `scenario`, `web-test`, `shim`,
`vendor-render`, `deviation` or `not-applicable` (with a reason from a closed list);
`pending` is allowed only until close-out. `shim` and `vendor-render` rows run only in the
manual reference job, and blocking CI checks their committed record. A checker will fail
the build on a dangling row. Until then a `pending` row means only that the work is
not done; it is not a claim about the donor or about PulsarMLX Console.

## What a row holds

| Field | Meaning |
| --- | --- |
| `id` | `file::Class::method`, or `file::function` for a module-level test function |
| `file` | Donor test file, relative to the donor repository root |
| `class` | Test class, or `null` for a module-level function |
| `method` | Test method or function name |
| `subsystem` | Console crate or area expected to own the evidence, assigned per donor file when the ledger was first generated (see the last section) |
| `disposition` | One of the dispositions above; `pending` today |

The top-level object also records the donor project, repository URL, commit and scope,
the listing tool, and the row count. The full schema, the closed list of dispositions and
"not applicable" reasons, and the rules for resolving a row are part of the feature
contracts in
[`../../specs/022-console-serving-parity/contracts/`](../../specs/022-console-serving-parity/contracts/).
Approved deviations live in the deviation register,
[`contracts/deviations.md`](../../specs/022-console-serving-parity/contracts/deviations.md).
Where this README and the contracts disagree, the contracts win.

## How the rows were counted

The rows come from [`../tools/list_donor_tests.py`](../tools/list_donor_tests.py). It
reads each `serve/test_*.py` file as text and parses it with Python's `ast` module. It
never imports or executes donor code and never runs `git` inside the donor checkout; the
commit is read from the checkout's `.git` directory as text.

A test is a `def test*` (or `async def test*`) written directly in the body of a
module-level class, or directly at module level. Inherited methods are not repeated under
a subclass, and functions nested inside other functions are not listed.

The 2026-11-14 run found 913 methods in 44 files, all of them in classes, with no
module-level test functions. That matches the count stated in the feature
[`plan.md`](../../specs/022-console-serving-parity/plan.md) (913 methods in 44 files), and
the per-file counts match, file by file, the inventory of the conformance planning record
described in the last section.

## Regenerating the ledger

From the repository root, with a checkout of project-maya at the pinned commit kept
outside this repository, using an isolated interpreter:

```sh
python3 -I console/tools/list_donor_tests.py PATH/TO/project-maya --summary \
    --expect-commit 7e68a30f2f208056195352129188661fb6b94445
python3 -I console/tools/list_donor_tests.py PATH/TO/project-maya \
    --expect-commit 7e68a30f2f208056195352129188661fb6b94445 \
    --write-ledger console/parity/ledger.json
```

Regeneration is safe to repeat. A row that already exists keeps its `subsystem`,
`disposition` and any other fields it has gained; a new row starts as `pending` with the
subsystem of other rows from the same donor file, or from a `--subsystems` JSON map. The
tool refuses to drop a row and refuses a donor at a different commit than the ledger's,
because re-pinning the donor is a separate, owner-approved decision. The output is
deterministic: the same donor commit gives the same bytes.

The first run took the subsystems from the conformance planning record, which is not
part of the repository, with `--subsystems PATH/TO/conformance-strategy.json`. Later runs
do not need it.
