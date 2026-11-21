"""Synthetic admission bindings only. No model, original reference, or real claims."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import studio020_guard as g
import studio020_operator as operator
import studio020_py_gate as gate
import studio020_supervise as sup

class Bindings(unittest.TestCase):
    def test_reserved_operations_and_namespaces(self):
        c=dict(run=g.RUN,operations=dict(g.OPERATIONS))
        b=g.operation_bindings(c)
        self.assertNotEqual(b['claims']['native'],b['claims']['grade'])
        self.assertEqual(b['outputs']['grade'],str(g.STATE/'pairwise-grade'))
        for mutation in ({'native':g.OPERATIONS['grade'],'grade':g.OPERATIONS['grade']},
                         dict(g.OPERATIONS,native='e407d5354a445be64811725c4320e656'),
                         dict(g.OPERATIONS,grade='2716258e1e096dbcda22f898828fdbe4'),
                         dict(g.OPERATIONS,grade='84bca402c0066d03b211cf24f6259ef3'),
                         dict(g.OPERATIONS,grade='g'*32)):
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):
                g.operation_bindings(dict(c,operations=mutation))
        with self.assertRaises(ValueError):g.operation_bindings(dict(c,run='0'*64))

    def test_native_refuses_either_spent_anchor_or_ambiguous_grade_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);anchors={k:root/(k+'.claim') for k in ('native','grade')};gd=root/'pairwise-grade'
            with patch.object(sup,'ANCHORS',anchors),patch.object(sup,'GRADE_STATE',gd),patch.object(sup,'local_mode',return_value=True),patch.object(sup,'bound_envelope',return_value='approved') as bound:
                self.assertEqual(sup.envelope({},'native'),'approved');bound.reset_mock()
                for path in (*anchors.values(),gd):
                    if path==gd:path.mkdir()
                    else:path.write_text('synthetic-spent')
                    try:
                        with self.assertRaisesRegex(ValueError,'spent claim'):sup.envelope({},'native')
                        bound.assert_not_called()
                    finally:
                        if path==gd:path.rmdir()
                        else:path.unlink()

    def test_comparison_bytes_and_exact_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp).resolve()/'comparison.json';g.put(p,g.COMPARISON_LIMITS)
            c=dict(artifacts={'comparison-resource':dict(path=str(p),sha256=g.digest(p))})
            self.assertEqual(g.comparison_limits(c),g.COMPARISON_LIMITS)
            p.chmod(0o600);p.write_text('{}')
            with self.assertRaises(ValueError):g.comparison_limits(c)

    def test_grade_binding_paths_operations_arguments_source_policy(self):
        base=g.STATE;d=base/'pairwise-grade';source=dict(head='1'*40,tree='2'*40)
        policy=dict(source=source,interpreter='/python')
        args=[str(g.REFERENCE_STATE/'campaign-reference/output'),str(base/'campaign-native/output')]
        intent=dict(operation=g.OPERATIONS['grade'],numeric_operation=g.OPERATIONS['native'],run=g.RUN,
                    source=source,python_policy='/policy',python_policy_sha256='a'*64,
                    python_interpreter='/python',arguments=args)
        def invoke(i,op=None,av=None,receipt=None):
            raw=gate.wire(i);claim=dict(schema='studio020-grade-claim/1',**i,intent_sha256=gate.h(raw))
            def read(path,*a):
                if Path(path)==d/'grade-intent.json':return raw
                if Path(path)==g.ANCHORS['grade']:return gate.wire(claim)
                raise AssertionError('unexpected fixture read '+str(path))
            with patch.object(gate,'raw',side_effect=read),patch.object(gate,'real',side_effect=Path),patch.object(gate.sys,'pycache_prefix',str(d/'cache-grade')):
                return gate.grade_binding('/policy','a'*64,receipt or str(d/'python-grade.json'),op or g.OPERATIONS['grade'],args if av is None else av,policy)
        self.assertEqual(invoke(intent)['schema'],'studio020-grade-claim/1')
        for key,value in (('operation','0'*32),('numeric_operation','0'*32),('run','0'*64),
                          ('source',dict(source,tree='3'*40)),('python_policy','/other'),
                          ('python_policy_sha256','0'*64),('python_interpreter','/other')):
            with self.subTest(key=key),self.assertRaises(ValueError):invoke(dict(intent,**{key:value}))
        with self.assertRaises(ValueError):invoke(intent,av=args[::-1])
        with self.assertRaises(ValueError):invoke(intent,receipt=str(base/'campaign-native/python-grade.json'))

    def test_fixture_grade_requires_private_cap_and_private_inputs(self):
        op='a'*32;d=g.STATE/('synthetic-grade-'+op);source=dict(head='1'*40,tree='2'*40)
        policy=dict(source=source,interpreter='/python')
        args=[str(d/'reference/output'),str(d/'native/output')]
        intent=dict(operation=op,numeric_operation=g.OPERATIONS['native'],run=g.RUN,source=source,
                    python_policy='/policy',python_policy_sha256='b'*64,python_interpreter='/python',arguments=args)
        raw=gate.wire(intent);claim=dict(schema='studio020-fixture-grade-claim/1',**intent,intent_sha256=gate.h(raw))
        claimraw=gate.wire(claim)
        cap=dict(schema='studio020-fixture-grade-cap/1',synthetic=True,task=g.TASK,source=source,
                 operation=op,intent_sha256=gate.h(raw),claim_sha256=gate.h(claimraw))
        def read(p,*a):
            return {str(d/'grade-intent.json'):raw,str(d/'fixture-grade-claim.json'):claimraw,
                    str(d/'fixture-grade-cap.json'):gate.wire(cap)}[str(p)]
        with patch.object(gate,'raw',side_effect=read),patch.object(gate,'real',side_effect=Path) as canonical,patch.object(gate.sys,'pycache_prefix',str(d/'cache-fixture-grade')):
            gate.grade_binding('/policy','b'*64,str(d/'python-fixture-grade.json'),op,args,policy,True)
            with self.assertRaises(ValueError):
                gate.grade_binding('/policy','b'*64,str(d/'python-fixture-grade.json'),op,
                    [str(g.REFERENCE_STATE/'campaign-reference/output'),args[1]],policy,True)
            canonical.side_effect=ValueError('noncanonical synthetic input')
            with self.assertRaisesRegex(ValueError,'noncanonical'):
                gate.grade_binding('/policy','b'*64,str(d/'python-fixture-grade.json'),op,args,policy,True)
            canonical.side_effect=Path
            cap['synthetic']=False
            with self.assertRaises(ValueError):
                gate.grade_binding('/policy','b'*64,str(d/'python-fixture-grade.json'),op,args,policy,True)

    def test_historical_receipt_positive_and_mutations(self):
        rows={'native':dict(run='887d9f85fadaebb634af04039815dabc8fb5b91a05febab2b398d13393d294d1',source='a1343f3532bbbe0153de0a553ede960309ebe98b',operation='e407d5354a445be64811725c4320e656'),
              'grade-intent.json':dict(operation='2716258e1e096dbcda22f898828fdbe4',numeric_operation='e407d5354a445be64811725c4320e656'),
              'grade-exit.json':dict(operation='2716258e1e096dbcda22f898828fdbe4',exit=0,guardian_exit=0,clean_reap=True,residual_group_killed=False)}
        def doc(p):return rows[Path(p).name] if Path(p).name.startswith('grade-') else rows['native']
        with patch.object(g,'checked') as checks,patch.object(g,'doc',side_effect=doc):
            g.historical_diagnostic();self.assertEqual(checks.call_count,3)
            for row,key,value in [('native','operation','0'*32),('grade-intent.json','numeric_operation','0'*32),('grade-exit.json','clean_reap',False),('grade-exit.json','guardian_exit',7)]:
                old=rows[row][key];rows[row][key]=value
                try:
                    with self.assertRaises(ValueError):g.historical_diagnostic()
                finally:rows[row][key]=old

    def test_no_payload_import_before_grade_binding(self):
        source=Path(gate.__file__).read_text()
        self.assertLess(source.index('if role in ("grade","fixture-grade"):grade_binding'),source.index('finder=install(p)'))
        self.assertLess(source.index('if role in ("grade","fixture-grade"):grade_binding'),source.index('import studio019_grade as gr'))
        rust=(Path(__file__).resolve().parents[2]/'crates/mlx-expert-mlp/src/full_flash/child.rs').read_bytes()
        self.assertEqual(g.sha(rust[:rust.index(b'pub fn run()')]),'f605080c89e489513523669ca8575a62a6cca29e9cab3187796887a3f7ad5b94')
        self.assertEqual(g.sha(rust[rust.index(b'    ffi::verify_abi()?;'):]),'ef949bd35b34b3971cd7f191356f5f64a7bf6104346f2e126ea9512333dd582c')

if __name__=='__main__':unittest.main()
