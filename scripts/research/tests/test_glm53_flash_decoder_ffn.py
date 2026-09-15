"""Bounded, prospective K qualification. Mutants live only in test scratch."""
import ast
import copy
import difflib
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from scripts.research.glm53_flash.decoder_ffn import source, oracle, controls
import mlx.core as mx
import mlx.nn as nn

FIXTURE='fixtures/research/glm53-flash-decoder-ffn-v1/fixtures.json'
INPUTS=(source.LANGUAGE,source.HC,source.PROVENANCE,
        source.ROOT+'decoder_ffn/source.py')+source.GRAPH_FILES
EVENTS=[]


def event(kind,**data):
    value={'event':kind,**data}
    EVENTS.append(value)
    print(json.dumps(value,allow_nan=False),flush=True)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def tensor_error(a,b):
    if type(a) is list:
        return max(tensor_error(a[i],b[i]) for i in range(len(a)))
    return abs(a-b)


class Qualification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mx.set_memory_limit(512*1024**2)
        mx.set_cache_limit(16*1024**2)
        mx.set_default_device(mx.cpu)
        cls.matrix=json.loads((ROOT/FIXTURE).read_bytes())
        cls.cases=cls.matrix['cases']
        event('build_identity',python=sys.version,optimized=sys.flags.optimize,
              bytecode_disabled=sys.dont_write_bytecode,isolated=sys.flags.isolated,
              mlx=mx.__version__,files=[{'path':p,'bytes':len((ROOT/p).read_bytes()),
                'sha256':digest((ROOT/p).read_bytes())} for p in INPUTS])

    def scratch(self):
        temp=tempfile.TemporaryDirectory(prefix='flash-k-')
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        self.assertEqual(root.resolve(strict=True),root)
        self.assertTrue(root.is_relative_to(Path(os.environ['TMPDIR']).resolve()))
        self.assertFalse(any(p.is_symlink() for p in (root,*root.parents)))
        for name in INPUTS:
            path=root/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes((ROOT/name).read_bytes())
        return root

    def refuse(self,name,raw,label):
        root=self.scratch()
        (root/name).write_bytes(raw)
        calls=[]
        original=source._exec
        def spy(node,namespace,filename):
            calls.append(node.name)
            return original(node,namespace,filename)
        source._exec=spy
        observed=None
        try:
            source.load(root,mx,nn)
        except ValueError as exc:
            observed=str(exc)
        finally:
            source._exec=original
        event('tamper_refusal',label=label,path=name,input_sha256=digest(raw),
              observed=observed,adaptation_executions=len(calls),executed_nodes=calls,
              decision=observed is not None and not calls)
        self.assertIsNotNone(observed)
        self.assertTrue(observed.startswith('DENSE_FFN_'))
        self.assertEqual(calls,[])

    def test_shape_decisions(self):
        # Expected decisions are literal, independent of either comparator.
        decisions=[
            ('scalar',1,1.0,True,[]),
            ('scalar-different',1,2,False,[]),
            ('vector',[1,2],[1.0,2.0],True,[2]),
            ('matrix',[[1,2],[3,4]],[[1,2],[3,4]],True,[2,2]),
            ('truncated',[1],[1,2],False,[2]),
            ('rank',[1],[[1]],False,[1]),
            ('unexpected-shape',[1],[1],False,[2]),
            ('empty',[],[],False,[0]),
            ('empty-nested',[[]],[[]],False,[1,0]),
            ('ragged',[[1],[2,3]],[[1],[2,3]],False,[2,2]),
            ('tuple',(1,),[1],False,[1]),
            ('string','1',1,False,[]),
            ('bool',True,1,False,[]),
            ('none',None,1,False,[]),
            ('nan',float('nan'),1,False,[]),
            ('positive-inf',float('inf'),1,False,[]),
            ('negative-inf',float('-inf'),1,False,[]),
            ('nested-nan',[float('nan')],[1],False,[1]),
            ('nested-inf',[[float('inf')]],[[1]],False,[1,1]),
            ('same-inf',float('inf'),float('inf'),False,[])]
        for name,a,b,expected,shape in decisions:
            for direction,left,right in [('forward',a,b),('reverse',b,a)]:
                observed=controls._close(left,right,1e-4,shape)
                event('shape_decision',name=name,direction=direction,
                      input_a=repr(left),input_b=repr(right),expected_shape=shape,
                      expected=expected,observed=observed)
                self.assertIs(observed,expected)
        self.assertFalse(controls._close(1,1,float('nan')))
        self.assertFalse(controls._close(1,1,-1))

    def test_actual_loader_tampering(self):
        for path in INPUTS:
            self.refuse(path,(ROOT/path).read_bytes()+b'\n# graph-owned tamper\n',path)

    def test_complete_caller_contract(self):
        bound=source.load(ROOT,mx,nn)
        p=bound.provenance
        tree=ast.parse((ROOT/source.LANGUAGE).read_bytes())
        owner=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Glm5NextDecoderLayer')
        original=next(n for n in owner.body if isinstance(n,ast.FunctionDef) and n.name=='_ffn_block')
        transformed=copy.deepcopy(original)
        transformed.name='source_ffn_block'
        candidate=ast.parse((ROOT/source.CAPSULE).read_bytes()).body[0]
        self.assertEqual(ast.dump(transformed),ast.dump(candidate))
        self.assertEqual(p['caller_contract']['original_ast_sha256'],source.ast_sha(original))
        self.assertIsInstance(candidate.returns,ast.Attribute)
        self.assertIsInstance(candidate.args.args[1].annotation,ast.Attribute)
        event('caller_contract',contract=p['caller_contract'],closure=p['closure_globals'],
              whole_ast_equal=True,annotations_retained=True)
        # Direct closure check has no adaptation path, independent expected rejection.
        bad=ast.parse('def source_ffn_block(self,x):\n    return unauthorized(x)').body
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_CLOSURE'):
            source._closure(bad)
        with self.assertRaisesRegex(RuntimeError,'FUSED_HC_FORBIDDEN'):
            bound.namespace['_hc_kernel']()
        event('closure_and_fused_refusal',unsupported_closure_refused=True,fused_refused=True)

    def test_paired_finite_matrix(self):
        self.assertEqual([c['fixture_id'] for c in self.cases],
            ['sinkhorn-1-clamp-active','sinkhorn-1-clamp-inactive',
             'sinkhorn-3-clamp-active','sinkhorn-3-clamp-inactive'])
        for f in self.cases:
            result=controls.run(ROOT,f,self.matrix)
            event('numerical_case',**result)
            self.assertEqual(result['status'],'PASS')
            self.assertEqual(set(result['candidate']),set(self.matrix['boundary_shapes']))
            self.assertTrue(result['observation_output_equivalent'])

    def test_actual_numerical_mutants(self):
        recipes=[
            ('caller-wrong-wiring',source.CAPSULE,
             'hc_expand(m, residual, post, comb)','hc_expand(m, residual, post, comb.swapaxes(-1, -2))','source_ffn_block'),
            ('omitted-normalization',source.CAPSULE,
             'self.post_attention_layernorm(xc)','xc','source_ffn_block'),
            ('omitted-residual',source.CAPSULE,
             'residual = x','residual = mx.zeros_like(x)','source_ffn_block'),
            ('hc-axis',source.HC,
             'comb.sum(axis=-2, keepdims=True)','comb.sum(axis=-1, keepdims=True)','_hc_split_sinkhorn_ops'),
            ('sinkhorn-count',source.HC,
             'range(max(sinkhorn_iters - 1, 0))','range(0)','_hc_split_sinkhorn_ops'),
            ('clamp-omitted',source.LANGUAGE,
             'gate = mx.minimum(gate, self.limit)','gate = gate','ClampedSwiGLU')]
        for label,path,before,after,node_name in recipes:
            original=(ROOT/path).read_text()
            self.assertIn(before,original)
            mutated=original.replace(before,after)
            raw=mutated.encode()
            diff=''.join(difflib.unified_diff(original.splitlines(True),
                mutated.splitlines(True),fromfile=path,tofile=label+'/'+path))
            event('mutant_body',label=label,path=path,sha256=digest(raw),
                  body=mutated,diff=diff)
            self.refuse(path,raw,label)
            bound=source.load(ROOT,mx,nn)
            n=bound.namespace
            node=next(v for v in ast.parse(raw).body if getattr(v,'name',None)==node_name)
            # Explicit TEST-ONLY direct harness. Production loader refused these
            # same bytes above; trust anchors and loader never admit the mutant.
            compiled=compile(ast.Module(body=[node],type_ignores=[]),'test-only:'+label,'exec')
            exec(compiled,n)
            results=[]
            for f in self.cases:
                output=n['source_ffn_block'](controls._owner(n,f),
                    mx.array(f['x'],dtype=mx.float32))
                mx.eval(output)
                value=output.tolist()
                reference=oracle.run(f)['output']
                valid=(controls._shape(value)==tuple(f['shape']))
                mismatch=valid and not controls._close(value,reference,1e-4,f['shape'])
                results.append({'fixture_id':f['fixture_id'],'runnable':True,
                    'reached_semantic_assertion':True,'shape_valid':valid,
                    'actual':value,'expected':reference,'killed':mismatch,
                    'max_absolute_error':tensor_error(value,reference)})
            killed=any(r['killed'] for r in results)
            event('semantic_mutant',label=label,input_sha256=digest(raw),
                node_ast_sha256=source.ast_sha(node),compiled=True,runnable=True,
                candidate_evaluations=len(results),oracle_evaluations=len(results),
                killed=killed,results=results)
            self.assertTrue(killed,label)

    def test_shape_and_late_integrity_mutants(self):
        path=source.ROOT+'decoder_ffn/controls.py'
        original=(ROOT/path).read_text()
        tree=ast.parse(original)
        close=next(n for n in tree.body if getattr(n,'name',None)=='_close')
        body="""def _close(a,b,tol,expected_shape=None):
    if type(a) is list:
        return all(_close(x,y,tol) for x,y in zip(a,b))
    return abs(a-b)<=tol
"""
        lines=original.splitlines(True)
        mutant=''.join(lines[:close.lineno-1])+body+''.join(lines[close.end_lineno:])
        self.refuse(path,mutant.encode(),'shape-truncation-acceptance')
        ns={}
        exec(compile(body,'test-only:shape-mutant','exec'),ns)
        malformed=[([1],[1,2],[2]),([1,2],[1],[2]),([],[],[0])]
        results=[]
        for a,b,shape in malformed:
            observed=ns['_close'](a,b,1e-4,shape)
            results.append({'input_a':a,'input_b':b,'expected':False,
                'observed':observed,'reached_semantic_assertion':True})
        event('semantic_mutant',label='shape-truncation-acceptance',body=mutant,
            diff=''.join(difflib.unified_diff(original.splitlines(True),
                 mutant.splitlines(True),fromfile=path,tofile='shape-mutant')),
            compiled=True,runnable=True,results=results,
            killed=any(r['observed'] for r in results))
        self.assertTrue(any(r['observed'] for r in results))
        path=source.ROOT+'decoder_ffn/source.py'
        original=(ROOT/path).read_text()
        needle="    loader = (root/(ROOT+'decoder_ffn/source.py')).read_bytes()"
        self.assertIn(needle,original)
        early="    _exec(_node(ast.parse(language),'ClampedSwiGLU'), {'mx':mx,'nn':nn,'__name__':'late_mutant'}, 'test-only:early')\n"
        mutant=original.replace(needle,early+needle)
        self.refuse(path,mutant.encode(),'late-loader-body-refusal')
        root=self.scratch()
        (root/source.CAPSULE).write_bytes((ROOT/source.CAPSULE).read_bytes()+b'\n# late tamper\n')
        ns={'__name__':'test_only_late_loader'}
        exec(compile(mutant,'test-only:late-loader','exec'),ns)
        executions=[]
        actual_exec=source._exec
        def spy(node,namespace,filename):
            executions.append(node.name)
            return actual_exec(node,namespace,filename)
        ns['_exec']=spy
        observed=None
        try:
            ns['load'](root,mx,nn)
        except ValueError as exc:
            observed=str(exc)
        event('semantic_mutant',label='late-integrity-check',body=mutant,
            diff=''.join(difflib.unified_diff(original.splitlines(True),
                mutant.splitlines(True),fromfile=path,tofile='late-mutant')),
            compiled=True,runnable=True,refusal=observed,executed_nodes=executions,
            adaptation_executions=len(executions),reached_semantic_assertion=True,
            killed=len(executions)>0 and observed is not None)
        self.assertEqual(executions,['ClampedSwiGLU'])
        self.assertIsNotNone(observed)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Qualification)
    ids=[t._testMethodName for t in suite]
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    event('result',status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL',
          test_ids=ids,tests_run=result.testsRun,failures=len(result.failures),
          errors=len(result.errors),skips=len(result.skipped),
          observed_event_counts={kind:sum(e['event']==kind for e in EVENTS)
            for kind in sorted({e['event'] for e in EVENTS})})
    sys.exit(0 if result.wasSuccessful() and not result.skipped else 1)
