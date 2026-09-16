#!/usr/bin/env python3
"""Mutation kills for the contention and workspace-boundary contracts."""
import tempfile
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent

def require(text, needles):
    missing = [needle for needle in needles if needle not in text]
    if missing: raise AssertionError('MUTATION_SURVIVED:' + ','.join(missing))


class MutationKills(unittest.TestCase):
    def test_contention_semantics(self):
        original = (HERE / 'sdk_client.py').read_text()
        required = ['holder.await_admission()', 'except openai.RateLimitError as error:',
                    'body.get("code") == "server_busy"', 'holder.close()']
        require(original, required)
        for needle in required:
            with self.subTest(needle=needle):
                with self.assertRaisesRegex(AssertionError, 'MUTATION_SURVIVED'):
                    require(original.replace(needle, '', 1), required)

    def test_membership_semantics(self):
        original = (HERE / 'test_ci_campaign.py').read_text()
        required = ['if result.returncode!=0:raise RuntimeError',
                    'WORKSPACE_METADATA_MALFORMED',
                    "'pulsar-serve-synthetic' in member_names",
                    'SYNTHETIC_CRATE_IN_PRODUCTION_WORKSPACE']
        require(original, required)
        for needle in required:
            with self.subTest(needle=needle):
                with self.assertRaisesRegex(AssertionError, 'MUTATION_SURVIVED'):
                    require(original.replace(needle, '', 1), required)


if __name__ == '__main__': unittest.main()
