from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from scripts.ci.run_research_tests import discover_filtered, main


PASSING = """
import unittest


class Passing(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(True)
"""

FAILING = """
import unittest


class Failing(unittest.TestCase):
    def test_not_ok(self):
        self.fail("deliberate failure")
"""


class RunResearchTests(unittest.TestCase):
    """The runner discovers like `unittest discover` and excludes whole modules."""

    def _tree(self, modules: dict[str, str]) -> Path:
        directory = Path(
            self.enterContext(tempfile.TemporaryDirectory(prefix="run-research-tests-"))
        )
        # A unique suffix keeps each case's modules out of another case's sys.modules.
        self.suffix = uuid.uuid4().hex[:8]
        for stem, body in modules.items():
            (directory / f"{stem}_{self.suffix}.py").write_text(body, encoding="utf-8")
        return directory

    def _run(self, *argv) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            code = main(list(argv))
        return code, stream.getvalue()

    def test_excluded_prefix_removes_only_matching_modules(self):
        directory = self._tree({
            "test_alpha_keep": PASSING,
            "test_glm53_flash_drop": FAILING,
            "test_glm53_flash_drop_two": FAILING,
        })
        code, output = self._run(
            "-s", str(directory), "-p", "test*.py",
            "--exclude-module-prefix", "test_glm53_flash",
        )
        # The excluded modules fail when run; the pass is green only if they were dropped.
        self.assertEqual(code, 0, output)
        self.assertIn("loaded modules: 1", output)
        self.assertIn("excluded modules: 2", output)
        self.assertIn(f"excluded: test_glm53_flash_drop_{self.suffix}", output)
        self.assertNotIn(f"excluded: test_alpha_keep_{self.suffix}", output)

    def test_non_matching_prefix_excludes_nothing(self):
        directory = self._tree({"test_alpha_keep": PASSING})
        code, output = self._run(
            "-s", str(directory), "-p", "test*.py",
            "--exclude-module-prefix", "test_glm53_flash",
        )
        self.assertEqual(code, 0, output)
        self.assertIn("loaded modules: 1", output)
        self.assertIn("excluded modules: 0", output)

    def test_zero_tests_is_refused(self):
        directory = self._tree({"test_glm53_flash_only": PASSING})
        code, output = self._run(
            "-s", str(directory), "-p", "test*.py",
            "--exclude-module-prefix", "test_glm53_flash",
        )
        self.assertEqual(code, 2, output)
        self.assertIn("REFUSED", output)

    def test_zero_tests_is_refused_when_nothing_matches_the_pattern(self):
        directory = self._tree({"test_alpha_keep": PASSING})
        code, output = self._run("-s", str(directory), "-p", "nomatch*.py")
        self.assertEqual(code, 2, output)
        self.assertIn("REFUSED", output)

    def test_failure_propagates(self):
        directory = self._tree({"test_alpha_fails": FAILING})
        code, output = self._run("-s", str(directory), "-p", "test*.py")
        self.assertEqual(code, 1, output)
        self.assertIn("deliberate failure", output)

    def test_failure_propagates_even_alongside_a_passing_module(self):
        directory = self._tree({"test_alpha_fails": FAILING, "test_beta_passes": PASSING})
        code, output = self._run("-s", str(directory), "-p", "test*.py")
        self.assertEqual(code, 1, output)
        self.assertIn("loaded modules: 2", output)

    def test_an_unimportable_module_is_attributed_to_its_prefix(self):
        # A module that raises on import becomes unittest.loader._FailedTest; the
        # runner must still attribute it to its own name so a prefix exclusion
        # covers it rather than leaving an unattributable error.
        directory = self._tree({
            "test_alpha_keep": PASSING,
            "test_glm53_flash_broken": "raise ImportError('no mlx here')\n",
        })
        code, output = self._run(
            "-s", str(directory), "-p", "test*.py",
            "--exclude-module-prefix", "test_glm53_flash",
        )
        self.assertEqual(code, 0, output)
        self.assertIn("excluded modules: 1", output)
        self.assertIn(f"excluded: test_glm53_flash_broken_{self.suffix}", output)

    def test_an_unimportable_module_still_fails_when_not_excluded(self):
        directory = self._tree({"test_gamma_broken": "raise ImportError('boom')\n"})
        code, output = self._run("-s", str(directory), "-p", "test*.py")
        self.assertEqual(code, 1, output)

    def test_an_excluded_module_is_never_imported(self):
        # The whole point of the split: filtering the suite after discovery would
        # already have executed the excluded module's imports. A module that would
        # blow up the interpreter on import must therefore not be imported at all.
        directory = self._tree({
            "test_alpha_keep": PASSING,
            "test_glm53_flash_marker": "import sys\nsys.modules['run_research_tests_marker'] = object()\n",
        })
        sys.modules.pop("run_research_tests_marker", None)
        code, output = self._run(
            "-s", str(directory), "-p", "test*.py",
            "--exclude-module-prefix", "test_glm53_flash",
        )
        self.assertEqual(code, 0, output)
        self.assertNotIn("run_research_tests_marker", sys.modules,
                         "the excluded module was imported")

    def test_a_kept_module_is_imported(self):
        directory = self._tree({
            "test_alpha_marker": "import sys\nsys.modules['run_research_tests_kept'] = object()\n"
                                 + PASSING,
        })
        sys.modules.pop("run_research_tests_kept", None)
        code, output = self._run("-s", str(directory), "-p", "test*.py")
        self.assertEqual(code, 0, output)
        self.assertIn("run_research_tests_kept", sys.modules)

    def test_discover_filtered_reports_names(self):
        directory = self._tree({"test_alpha_keep": PASSING, "test_glm53_flash_drop": PASSING})
        suite, kept, excluded = discover_filtered(
            str(directory), "test*.py", None, ("test_glm53_flash",)
        )
        self.assertEqual(kept, {f"test_alpha_keep_{self.suffix}"})
        self.assertEqual(excluded, {f"test_glm53_flash_drop_{self.suffix}"})
        self.assertEqual(suite.countTestCases(), 1)


if __name__ == "__main__":
    unittest.main()
