"""paged_reference.py argument surface (stdlib only, no mlx): the admitted expert-cache ceiling is the explicit
--max-expert-cache-bytes flag rather than a hard-coded constant, it defaults to 60000000000 so existing invocations
keep their behaviour, an explicit value is parsed as an int, and the flag reaches the recorded run config. The module
imports mlx only inside main(), so importing it and building its parser is safe in the offline discover run; the
--help path is exercised in a separate interpreter (-I -B) to prove the flag is documented on the command line."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOGFOOD = ROOT / 'scripts/research/glm53_flash/dogfood'
SCRIPT = DOGFOOD / 'paged_reference.py'
sys.path.insert(0, str(DOGFOOD))
import paged_reference as pr  # noqa: E402  (after the sys.path insert; imports no mlx at module level)

BASE = ['--offload', '/tmp/repack', '--expert-cache-bytes', '60000000000', '--coalesce-gap', '0',
        '--write-mode', 'per-expert', '--wire', '--messages', '/tmp/req.json', '--log', '/tmp/out.json']


class CeilingFlag(unittest.TestCase):
    def test_default_is_the_previously_hard_coded_ceiling(self):
        args = pr.build_parser().parse_args(BASE)
        self.assertEqual(args.max_expert_cache_bytes, 60_000_000_000)
        self.assertIsInstance(args.max_expert_cache_bytes, int)

    def test_explicit_value_is_parsed(self):
        args = pr.build_parser().parse_args(BASE + ['--max-expert-cache-bytes', '70000000000'])
        self.assertEqual(args.max_expert_cache_bytes, 70_000_000_000)
        self.assertEqual(args.expert_cache_bytes, 60_000_000_000)

    def test_budget_and_ceiling_are_independent(self):
        args = pr.build_parser().parse_args(
            ['--offload', '/tmp/repack', '--expert-cache-bytes', '70000000000',
             '--max-expert-cache-bytes', '70000000000', '--coalesce-gap', '0',
             '--write-mode', 'per-expert', '--no-wire', '--messages', '/tmp/req.json', '--log', '/tmp/out.json'])
        self.assertEqual((args.expert_cache_bytes, args.max_expert_cache_bytes), (70_000_000_000, 70_000_000_000))
        self.assertFalse(args.wire)

    def test_no_hard_coded_ceiling_left_in_the_verify_call(self):
        src = SCRIPT.read_text()
        self.assertIn('verify_artifact(args.offload, args.max_expert_cache_bytes, args.expert_cache_bytes)', src)
        self.assertNotIn('verify_artifact(args.offload, 60_000_000_000', src)

    def test_the_flag_is_recorded_in_the_run_config(self):
        self.assertIn("'max_expert_cache_bytes': args.max_expert_cache_bytes", SCRIPT.read_text())

    def test_docstring_mirrors_the_flag(self):
        self.assertIn('--max-expert-cache-bytes', pr.__doc__)

    def test_help_documents_the_flag_in_a_clean_interpreter(self):
        out = subprocess.run([sys.executable, '-I', '-B', str(SCRIPT), '--help'],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('--max-expert-cache-bytes', out.stdout)
        self.assertIn('60000000000', out.stdout)


if __name__ == '__main__':
    unittest.main()
