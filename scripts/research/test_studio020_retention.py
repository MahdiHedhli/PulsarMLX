"""Partial evidence can be compared only after an unambiguous positive reap."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import studio020_supervise as s


class Retention(unittest.TestCase):
    def test_seal_population_is_exclusive_and_partial_contents_retained(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            out = root / 'output'
            out.mkdir(mode=0o700)
            (out / '00.hidden.f32').write_bytes(b'\x00' * 4)
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                s.native_seal(root)
            records = s.output_seal(out, 1024, True, False)
            s.put(root / 'partial-sealed.json', dict(complete=False, files=records))
            self.assertFalse(s.native_seal(root)[2])
            self.assertEqual(s.output_seal(out, 1024, require_complete=False), records)
            with self.assertRaisesRegex(ValueError, 'full logits'):
                s.output_seal(out, 1024)
            s.put(root / 'sealed.json', {})
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                s.native_seal(root)
            # Temporary fixture cleanup only; no campaign evidence is touched.
            out.chmod(0o700)

    def test_uncertain_reap_refuses_before_comparison(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name).resolve()
            seal = dict(operation='op', claim_sha256='hash', exit_sha256='hash', complete=False)
            claim = dict(stage='native', run='run', source='head', operation='op')
            exit_record = dict(operation='op', clean_reap=False, exit=None)
            config = dict(run='run', source={'head': 'head'})
            def record(path):
                return exit_record if Path(path).name == 'numeric-exit.json' else claim
            with patch.object(s, 'original_reference'), patch.object(s, 'layout', return_value=(root,root/'output',root/'cap')), \
                 patch.object(s, 'native_seal', return_value=(root/'partial-sealed.json',seal,False)), \
                 patch.object(s, 'doc', side_effect=record), patch.object(s, 'digest', return_value='hash'), \
                 patch.object(s, 'output_seal') as read_outputs:
                with self.assertRaisesRegex(ValueError, 'original native process/claim'):
                    s.grading_inputs(config, 'native')
                read_outputs.assert_not_called()


if __name__ == '__main__': unittest.main()
