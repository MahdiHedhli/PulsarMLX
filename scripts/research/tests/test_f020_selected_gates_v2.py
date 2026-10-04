"""Host-only authority/report controls; no full-shape numerical observation."""
import copy
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import f020_selected_compare_v2 as C
import f020_selected_qualify_v2 as Q
import f020_selected_authority_v2 as A


def reference():
    counts={'g':2048,'u':2048,'bg':2048,'bu':2048,'h':2048,'bh':2048,'y':4096,'propagated':4096}
    return {k:[(F(0),F(0)) if k in ('h','y') else F(0)]*n for k,n in counts.items()}


class Gates(unittest.TestCase):
    def test_reference_roundtrip_and_malformed(self):
        r=reference();doc=C.serialize(r)
        self.assertEqual(C.deserialize(doc),r)
        for key,value in [('h',['1','0']),('h',['0','1/1024']),('bh','-1')]:
            d=copy.deepcopy(doc);d[key][0]=value
            with self.assertRaises(ValueError):C.deserialize(d)
        d=copy.deepcopy(doc);d['y'].pop()
        with self.assertRaisesRegex(ValueError,'shape'):C.deserialize(d)

    def test_output_digest_shape_and_nonfinite(self):
        raw=struct.pack('<f',1)
        output={'shape':[1,1],'dtype':'F32','f32_bits':[0x3f800000],'sha256':hashlib.sha256(raw).hexdigest()}
        self.assertEqual(C.decode(output,1),([F(1)],raw))
        for key,value in [('shape',[1,2]),('f32_bits',[True]),('sha256','0'*64)]:
            d=dict(output);d[key]=value
            with self.assertRaises(ValueError):C.decode(d,1)
        d=dict(output,f32_bits=[0x7f800000],sha256=hashlib.sha256(struct.pack('<I',0x7f800000)).hexdigest())
        with self.assertRaises(ValueError):C.decode(d,1)

    def test_down_guard_record_required_before_comparison(self):
        with self.assertRaisesRegex(ValueError,'down admission'):
            C.compare({'outcome':'executed'},None,None,None)

    def test_inherited_summary_formats_and_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);records={}
            for key,count in [('primitives',363),('planes',32)]:
                child=root/(key+'-child.json');child.write_bytes(b'{}')
                summary={'result':'PASS','candidate_commit':'a'*40,'worktree_dirty':False,
                         'gate_counts':{'gate':{'cases':count,'passed':count}},'failures':[],
                         'child':{'report_sha256':A.sha(b'{}')}}
                if key=='primitives':summary.update(cases=[{}]*count,frozen={'case_count':count})
                else:summary['case_accounting']={'case_ids':count}
                path=root/(key+'.json');path.write_bytes(A.canonical(summary))
                records[key]={'summary_path':str(path),'summary_sha256':A.sha(path.read_bytes()),'report_path':str(child)}
            cap={'regressions':records};descriptor={'commit':'a'*40}
            self.assertEqual(Q.regression_summaries(cap,descriptor)['primitives']['count'],363)
            Path(records['planes']['report_path']).write_bytes(b'{"changed":true}')
            with self.assertRaisesRegex(ValueError,'child digest'):Q.regression_summaries(cap,descriptor)

    def test_inherited_gate_precedes_population_execution(self):
        with patch.object(Q,'verified',return_value=({},None,None,None,None)), patch.object(Q,'run_positive') as native:
            with self.assertRaises(KeyError):Q.full_synthetic({'kind':'synthetic'})
            native.assert_not_called()


if __name__=='__main__':unittest.main()
