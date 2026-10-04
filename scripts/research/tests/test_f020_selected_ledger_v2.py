"""Synthetic one-attempt ledger controls; no real capabilities or numerical calls."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import f020_selected_ledger_v2 as L


class Ledger(unittest.TestCase):
    def test_once_only_reference_and_out_cannot_bypass(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(L,'root',return_value=Path(tmp)/'fixed'):
            d={'commit':'a','contract_sha256':'b'};b={'snapshot_sha256':'c'}
            cap={'kind':'real','out':'original'}
            L.issue(cap,d,b);L.verify(cap,d,b)
            with self.assertRaises(FileExistsError):L.issue(cap,d,b)
            changed=dict(cap,out='fresh')
            with self.assertRaisesRegex(ValueError,'issued real capability'):L.verify(changed,d,b)
            L.begin_reference(cap,d,b)
            with self.assertRaises(FileExistsError):L.begin_reference(cap,d,b)
            augmented=dict(cap,pre_admission={'sha256':'later'})
            self.assertEqual(L.capability_sha(augmented),L.capability_sha(cap))
            L.verify(augmented,d,b)

    def test_private_ledger_and_fixed_key(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(L,'root',return_value=Path(tmp)/'fixed'):
            d={'commit':'a','contract_sha256':'b'};b={'snapshot_sha256':'c'};cap={'kind':'real'}
            L.issue(cap,d,b)
            key=L.directory(d,b)
            self.assertNotEqual(key,L.directory(dict(d,commit='other'),b))
            self.assertNotEqual(key,L.directory(d,{'snapshot_sha256':'other'}))
            key.chmod(0o755)
            with self.assertRaisesRegex(ValueError,'private ledger'):L.verify(cap,d,b)



if __name__=='__main__':unittest.main()
