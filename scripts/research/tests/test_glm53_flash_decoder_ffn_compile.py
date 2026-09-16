"""Compile-gate equivalence for the admitted dense-FFN caller (Flash AN, Graph 7).

Glm5NextDecoderLayer.__call__ routes B=1, L=1 decode steps through
mx.compile(self._ffn_block). This test consumes the admitted closed graph via
source.load() without altering it, and checks the compiled function against
the eager one on the frozen dense-FFN fixtures, on CPU and on Metal.

Predeclared rule (run-card-graph7, frozen before observation): per fixture and
device, max_absolute_error(compiled, eager) <= tolerances.output; bitwise
equality is recorded, not required. A missing Metal device is NOT_EXECUTED,
never a pass. A compiled mutant with the residual omitted must exceed the
allowance on every fixture, proving the assertion discriminates.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))

REQUIRED_MLX='0.32.0'
def _precondition():
    from importlib.metadata import version, PackageNotFoundError
    try:
        installed=version('mlx')
    except PackageNotFoundError:
        return 'mlx unavailable'
    if installed!=REQUIRED_MLX:
        return f'mlx {installed} != required {REQUIRED_MLX}'
    return None
_UNMET=_precondition()
if _UNMET:
    raise unittest.SkipTest('DENSE_FFN_COMPILE_ENV_REQUIRED ('+_UNMET+'); NOT_EXECUTED')
from scripts.research.glm53_flash.decoder_ffn import source, controls
import mlx.core as mx
import mlx.nn as nn

FIXTURE='fixtures/research/glm53-flash-decoder-ffn-v1/fixtures.json'
EVENTS=[]


def event(kind,**data):
    value={'event':kind,**data}
    EVENTS.append(value)
    print(json.dumps(value,allow_nan=False),flush=True)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def max_error(a,b):
    if type(a) is list:
        if len(a)!=len(b):
            return float('inf')
        return max(max_error(a[i],b[i]) for i in range(len(a)))
    return abs(a-b)


class CompileGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        mx.set_memory_limit(512*1024**2)
        mx.set_cache_limit(16*1024**2)
        cls.matrix=json.loads((ROOT/FIXTURE).read_bytes())
        cls.cases=cls.matrix['cases']
        cls.tolerance=cls.matrix['tolerances']['output']
        cls.devices=[('cpu',mx.Device(mx.cpu))]
        try:
            gpu=mx.Device(mx.gpu)
            mx.eval(mx.zeros((1,),stream=gpu))
            cls.devices.append(('metal',gpu))
            cls.metal='EXECUTED'
        except Exception as exc:  # recorded, never silently passed
            cls.metal='NOT_EXECUTED:'+type(exc).__name__
        event('build_identity',python=sys.version,optimized=sys.flags.optimize,isolated=sys.flags.isolated,
              mlx=mx.__version__,metal=cls.metal,test_sha256=digest(Path(__file__).read_bytes()),
              tolerance=cls.tolerance)

    def _bound(self):
        return source.load(ROOT,mx,nn).namespace

    def _inputs(self,f):
        # Full fixture input and the L=1 slice that matches the upstream compile gate.
        full=mx.array(f['x'],dtype=mx.float32)
        return [('full',full),('decode-step',full[:, :1])]

    def _compare(self,n,label,name,device,f,block):
        owner=controls._owner(n,f)
        compiled=mx.compile(lambda x: block(owner,x))
        rows=[]
        for shape_label,x in self._inputs(f):
            with mx.stream(device):
                eager=block(owner,x); mx.eval(eager)
                fast=compiled(x); mx.eval(fast)
            e,c=eager.tolist(),fast.tolist()
            err=max_error(c,e)
            rows.append({'input':shape_label,'shape':list(x.shape),'max_absolute_error':err,
                         'bitwise_equal':e==c,'within_allowance':err<=self.tolerance,
                         'dtype':str(fast.dtype)})
        event('compile_equivalence',label=label,device=name,fixture_id=f['fixture_id'],rows=rows)
        return rows

    def test_compiled_ffn_block_matches_eager(self):
        n=self._bound()
        block=n['source_ffn_block']
        for name,device in self.devices:
            for f in self.cases:
                for r in self._compare(n,'admitted',name,device,f,block):
                    self.assertTrue(r['within_allowance'],f"{name}/{f['fixture_id']}/{r['input']}: {r['max_absolute_error']}")
                    self.assertEqual(r['dtype'],'mlx.core.float32')

    def test_metal_was_executed_or_explicitly_not(self):
        # A missing device is a recorded limitation, not a pass; on hosted CI
        # macos-15 arm64 provides Metal, so absence there is a failure.
        event('metal_status',status=self.metal,hosted_ci=bool(os.environ.get('GITHUB_ACTIONS')))
        if os.environ.get('GITHUB_ACTIONS'):
            self.assertEqual(self.metal,'EXECUTED')

    def test_compiled_mutant_is_distinguishable(self):
        # Test-only mutant compiled through the same gate must exceed the
        # allowance on every fixture; the admitted graph is untouched.
        n=self._bound()
        capsule=(ROOT/source.CAPSULE).read_text()
        before,after='residual = x','residual = mx.zeros_like(x)'
        self.assertEqual(capsule.count(before),1)
        mutated=capsule.replace(before,after)
        node=next(v for v in ast.parse(mutated).body if getattr(v,'name',None)=='source_ffn_block')
        ns=dict(n)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'test-only:compile-mutant','exec'),ns)
        mutant=ns['source_ffn_block']
        for name,device in self.devices:
            for f in self.cases:
                owner=controls._owner(n,f)
                x=mx.array(f['x'],dtype=mx.float32)
                with mx.stream(device):
                    good=n['source_ffn_block'](owner,x); mx.eval(good)
                    bad=mx.compile(lambda x: mutant(owner,x))(x); mx.eval(bad)
                err=max_error(bad.tolist(),good.tolist())
                event('compile_mutant',device=name,fixture_id=f['fixture_id'],max_absolute_error=err,
                      exceeds_allowance=err>self.tolerance,mutant_sha256=digest(mutated.encode()))
                self.assertGreater(err,self.tolerance,f"{name}/{f['fixture_id']}")


if __name__=='__main__':
    result=unittest.main(exit=False).result
    print(json.dumps({'event':'result','status':'PASS' if result.wasSuccessful() else 'FAIL',
                      'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
                      'skipped':len(result.skipped)}),flush=True)
    sys.exit(0 if result.wasSuccessful() else 1)
