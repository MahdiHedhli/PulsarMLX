#!/usr/bin/env python3
"""Run a `unittest discover` pass that can omit whole test modules by name prefix.

This exists because the consolidated tree carries two research test corpora that
were qualified under *different* interpreters:

* the GLM-5.3-Flash modules (`test_glm53_flash_*.py`) were qualified on their own
  branch under a system `python3` with no MLX installed, which is what makes their
  `test_mlx_not_imported` purity assertions meaningful;
* the Feature 002 / F017 modules were qualified under the pinned `uv` virtualenv,
  which does have MLX, and under a `DYLD_LIBRARY_PATH` that points at the pinned
  source-built MLX.

Running both corpora in one interpreter satisfies neither: the venv interpreter
imports MLX through the Flash modules and breaks the purity invariant, and the
pinned `DYLD_LIBRARY_PATH` makes the wheel's `mlx.core` fail to load at all. The
two passes are therefore split, and this runner is what lets the second pass omit
the modules the first pass already owns.

**Exclusion has to happen before import, not after.** `TestLoader.discover()`
imports every module matching the pattern and only then hands back a suite, so
filtering the returned suite would still have imported MLX through an excluded
module. This runner instead enumerates the top-level files that the pattern
matches — the same `fnmatch` test `discover()` applies — drops the excluded ones,
and then calls `TestLoader().discover(start_dir, pattern=<that exact filename>)`
for each survivor. Discovery of every module that does run is therefore performed
by `unittest` itself, exactly as `python -m unittest discover -s <dir> -p <pat>`
would, and an excluded module is never imported.

Exclusion removes whole top-level test modules by name prefix, never individual
assertions, and the runner refuses to report success if it loaded nothing.

Standard library only; no third-party imports.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import unittest


def discover_filtered(start_directory, pattern, top_level_directory, prefixes):
    """Discover `pattern` under `start_directory`, never importing excluded modules.

    Returns (suite, kept_module_names, excluded_module_names).
    """
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    kept: set[str] = set()
    excluded: set[str] = set()

    for name in sorted(os.listdir(start_directory)):
        path = os.path.join(start_directory, name)
        if not os.path.isfile(path) or not fnmatch.fnmatch(name, pattern):
            continue
        module = name[:-3] if name.endswith(".py") else name
        if any(module.startswith(prefix) for prefix in prefixes):
            excluded.add(module)
            continue
        kept.add(module)
        suite.addTests(
            loader.discover(
                start_directory, pattern=name, top_level_dir=top_level_directory
            )
        )
    return suite, kept, excluded


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-s", "--start-directory", required=True,
                        help="directory to start discovery from (unittest -s)")
    parser.add_argument("-p", "--pattern", default="test*.py",
                        help="test file pattern (unittest -p)")
    parser.add_argument("-t", "--top-level-directory", default=None,
                        help="top level directory of project (unittest -t)")
    parser.add_argument("--exclude-module-prefix", action="append", default=[],
                        metavar="PREFIX",
                        help="drop discovered top-level test modules whose name starts "
                             "with PREFIX, without importing them; repeatable")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="accepted for symmetry with `unittest discover -v`; this "
                             "runner always reports at verbosity 2")
    arguments = parser.parse_args(list(argv) if argv is not None else None)

    # `python -m unittest ...` puts the current working directory on sys.path;
    # running this file as a script puts *its own* directory there instead. Test
    # modules in this repository import their siblings as `scripts.research.tests.*`,
    # which only resolves from the repository root, so restore the `-m` behaviour
    # rather than making callers set PYTHONPATH.
    working_directory = os.getcwd()
    if working_directory not in sys.path:
        sys.path.insert(0, working_directory)

    suite, kept, excluded = discover_filtered(
        arguments.start_directory,
        arguments.pattern,
        arguments.top_level_directory,
        tuple(arguments.exclude_module_prefix),
    )

    print(f"loaded modules: {len(kept)}", flush=True)
    print(f"excluded modules: {len(excluded)}", flush=True)
    for name in sorted(excluded):
        print(f"  excluded: {name}", flush=True)

    if suite.countTestCases() == 0:
        print("REFUSED: discovery loaded zero tests; refusing to report success",
              file=sys.stderr, flush=True)
        return 2

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
