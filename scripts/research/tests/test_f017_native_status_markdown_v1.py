"""The status document's figures must come from the generator, not from prose.

Adversarial review showed a substring-based check passing after nine separate
mutations, five of them inside the generated block and four adding contradicting
figures outside it. Each of those nine is a case here.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts" / "research"))

import generate_f017_native_status_v1 as status  # noqa: E402


class StatusMarkdownVerification(unittest.TestCase):
    def setUp(self):
        self.original = status.STATUS_DOC.read_text()
        self.addCleanup(status.STATUS_DOC.write_text, self.original)

    def _check(self) -> int:
        return status.main(["--check"])

    def _mutate(self, old: str, new: str) -> None:
        self.assertIn(old, self.original)
        status.STATUS_DOC.write_text(self.original.replace(old, new, 1))

    def _append(self, text: str) -> None:
        status.STATUS_DOC.write_text(self.original.rstrip("\n") + "\n\n" + text + "\n")

    def test_unmutated_document_passes(self):
        self.assertEqual(self._check(), 0)

    # --- mutations inside the generated block ---
    def test_ulp_count_mutation_fails(self):
        self._mutate("0 ULP over", "9 ULP over")
        self.assertEqual(self._check(), 1)

    def test_prompt_token_count_mutation_fails(self):
        self._mutate("21 prompt tokens over", "99 prompt tokens over")
        self.assertEqual(self._check(), 1)

    def test_position_count_mutation_fails(self):
        self._mutate("over 24 positions", "over 99 positions")
        self.assertEqual(self._check(), 1)

    def test_generated_token_count_mutation_fails(self):
        self._mutate("4 generated tokens", "9 generated tokens")
        self.assertEqual(self._check(), 1)

    def test_decode_rate_mutation_fails(self):
        self._mutate("0.0116 tok/s", "116 tok/s")
        self.assertEqual(self._check(), 1)

    def test_produced_token_mutation_fails(self):
        self._mutate("154820", "999999")
        self.assertEqual(self._check(), 1)

    # --- figures added outside the generated block ---
    def test_inline_code_token_outside_the_block_fails(self):
        self._append("The run produced `999999` as its token.")
        self.assertEqual(self._check(), 1)

    def test_number_words_outside_the_block_fail(self):
        self._append("Twenty-nine of thirty-six measured bodies are unchanged.")
        self.assertEqual(self._check(), 1)

    def test_prose_figures_outside_the_block_fail(self):
        self._append("Stage B2 executed 99 positions and generated nine tokens.")
        self.assertEqual(self._check(), 1)

    def test_a_second_generated_block_fails(self):
        self._append(status.BEGIN + "\n| Stage B1 | 99 tokens |\n" + status.END)
        self.assertEqual(self._check(), 1)

    def test_a_missing_generated_block_fails(self):
        start = self.original.find(status.BEGIN)
        stop = self.original.find(status.END) + len(status.END)
        status.STATUS_DOC.write_text(self.original[:start] + self.original[stop:])
        self.assertEqual(self._check(), 1)


if __name__ == "__main__":
    unittest.main()
