"""Whole-node binding, independent expectations and safe metadata admission."""
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'scripts/research/glm53_flash'


def module(folder,name):
    spec=importlib.util.spec_from_file_location('linear_contract_'+folder+'_'+name,BASE/folder/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


class LinearAttentionContract(unittest.TestCase):
    def setUp(self):
        self.oracle=module('linear_attention','oracle');self.source=module('linear_attention','source')
        self.reference=module('recurrent_dispatch','oracle')
        self.fixture=json.loads((ROOT/'fixtures/research/glm53-flash-linear-attention-v1/fixtures.json').read_bytes())
        self.raw=(BASE/'linear_attention/capsule.py').read_bytes()
        self.origin=(BASE/'recurrent_dispatch/upstream-language.txt').read_bytes()
        self.provenance=json.loads((BASE/'linear_attention/provenance.json').read_bytes())

    def test_full_original_definitions_and_no_mask_forwarding(self):
        nodes=self.source.verify_module(self.raw,self.origin,self.provenance)
        self.assertEqual(len(nodes),4)
        self.assertEqual(nodes[-1].name,'Glm5NextLinearAttention')

    def test_repinned_algorithm_change_is_refused(self):
        changed=self.raw.replace(b'cache.advance(S)',b'cache.advance(S + 1)')
        p=copy.deepcopy(self.provenance);p['capsule_sha256']=hashlib.sha256(changed).hexdigest()
        with self.assertRaisesRegex(ValueError,'^MODULE_WHOLE_NODE_OR_SPAN$'):
            self.source.verify_module(changed,self.origin,p)

    def test_frozen_independent_results_and_budgets(self):
        for case in self.fixture['cases']:
            actual=self.oracle.module_reference(case,self.reference)
            self.assertEqual(actual,self.fixture['expected'][case['name']])
            self.assertLess(max(actual['maximum_radii'].values()),1e-4)
        self.assertEqual(self.fixture['scientific_case_count_including_interleaving'],8)

    def test_sparse_dyadic_projection_and_convolution_anchor(self):
        projection=Fraction(1,2)*Fraction(1,4)
        convolution=Fraction(1,2)*projection
        self.assertEqual(projection,Fraction(1,8));self.assertEqual(convolution,Fraction(1,16))
        self.assertEqual(self.fixture['expected']['dyadic-anchor']['events'][0]['anchor'],
                         {'mixed_b0_c0':float(projection),'convolution_b0_c0':float(convolution)})

    def test_new_square_geometry_and_refusals_are_metadata_only(self):
        self.source.mx=types.SimpleNamespace(float32='FP32')
        def array(dims):
            size=1
            for n in dims:size*=n
            return types.SimpleNamespace(shape=dims,size=size,dtype='FP32')
        args={'inputs':[array(s) for s in [(2,5,2,32)]*4+[(2,5,2),(2,2,32,32)]]+[5],
              'grid':(32,32,4),'threadgroup':(32,4,1),'output_shapes':[(2,5,2,32),(2,2,32,32)],
              'output_dtypes':['FP32','FP32'],'template':[('InT','FP32'),('StT','FP32'),('Dk',32),('Dv',32),('Hk',2),('Hv',2)]}
        names=['q','k','v','g','beta','state_in','T']
        result=self.source.kernel_buffers(args,names)
        self.assertEqual(result['max_state_float32_elements'],4096)
        self.assertIn('NOT_PROVED_BY_METADATA',result['packing_assumption'])
        args['grid']=(64,32,4)
        with self.assertRaisesRegex(ValueError,'^MODULE_KERNEL_GEOMETRY$'):self.source.kernel_buffers(args,names)
        case=copy.deepcopy(self.fixture['cases'][0]);case['config']['linear_head_dim']=31
        with self.assertRaisesRegex(self.oracle.InputError,'^FINITE_DOMAIN$'):self.oracle.validate(case)

    def test_initial_metadata_refusals_precede_source_loading(self):
        controls=module('linear_attention','controls')
        controls.oracle=self.oracle
        calls=[]
        controls.source=types.SimpleNamespace(load=lambda *args: calls.append(args))
        for original in (self.fixture['cases'][0],self.fixture['cases'][4]):
            B,S=original['B'],original['S']
            field_cases={
                'initial_lengths': [
                    ('MISSING',None),('TYPE',None),('TYPE',()),('TYPE',0),('SHAPE',[]),
                    ('SHAPE',[S]*max(B-1,0)),('TYPE',[True]*B),('TYPE',[float(S)]*B),
                    ('TYPE',[float('inf')]*B),('RANGE',[S-1]*B),('OK',[S]*B),('OK',[S+1]*B)],
                'initial_padding': [
                    ('MISSING',None),('TYPE',None),('TYPE',()),('TYPE',0),('SHAPE',[]),
                    ('SHAPE',[0]*max(B-1,0)),('TYPE',[True]*B),('TYPE',[0.5]*B),
                    ('TYPE',[float('nan')]*B),('RANGE',[-1]*B),('OK',[0]*B),
                    ('OK',[max(S-1,0)]*B),('OK',[S]*B),('OK',[S+1]*B)],
            }
            for field,variants in field_cases.items():
                prefix='ORACLE_' + field.upper()
                for kind,value in variants:
                    with self.subTest(B=B,S=S,field=field,kind=kind,value=value):
                        case=copy.deepcopy(original)
                        if kind=='MISSING':
                            del case[field]
                        else:
                            case[field]=value
                        before=copy.deepcopy(case)
                        if kind=='OK':
                            self.oracle.validate(case)
                        else:
                            with self.assertRaisesRegex(self.oracle.InputError,'^'+prefix+'_'+kind+'$'):
                                controls.Engine(None,None,case,None,'cpu',1)
                            self.assertEqual(case, before)
                            self.assertEqual(calls,[])

    def test_recurrence_crosschecks_have_exact_reasons_in_normal_and_optimized_python(self):
        case=copy.deepcopy(self.fixture['cases'][0])
        class Recurrence:
            def ops_transition(self, request, initial):
                B,H=request['B'],request['Hk']
                return {'output':[[[[0.0]*8 for _ in range(H)]] for _ in range(B)],
                        'state':[[[0.0]*8 for _ in range(H)] for _ in range(B)]}
        original=self.oracle.close
        for expected,fail_on in [('ORACLE_RECURRENCE_CROSSCHECK_OUTPUT',1),
                                 ('ORACLE_RECURRENCE_CROSSCHECK_STATE',2)]:
            calls=[]
            def injected(*args):
                calls.append(args)
                return len(calls)!=fail_on
            self.oracle.close=injected
            with self.subTest(expected=expected):
                with self.assertRaisesRegex(self.oracle.InputError,'^'+expected+'$'):
                    self.oracle.module_reference(copy.deepcopy(case),Recurrence())
        self.oracle.close=original
        root=str(ROOT)
        child="""import importlib.util
import json
import pathlib
import sys
root = pathlib.Path(%r)
spec = importlib.util.spec_from_file_location('o', root / 'scripts/research/glm53_flash/linear_attention/oracle.py')
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)
case = json.loads((root / 'fixtures/research/glm53-flash-linear-attention-v1/fixtures.json').read_text())['cases'][0]
o.close = lambda *args: False
class R:
    def ops_transition(self, request, initial):
        return {'output': [[[[0.0] * 8 for _ in range(request['Hk'])]] for _ in range(request['B'])],
                'state': [[[0.0] * 8 for _ in range(request['Hk'])] for _ in range(request['B'])]}
try:
    o.module_reference(case, R())
except o.InputError as error:
    print(error)
    sys.exit(0 if str(error) == 'ORACLE_RECURRENCE_CROSSCHECK_OUTPUT' else 2)
sys.exit(3)
""" % root
        optimized=subprocess.run([sys.executable,'-O','-c',child],text=True,capture_output=True)
        self.assertEqual(optimized.returncode,0,optimized.stdout+optimized.stderr)
        canary=subprocess.run([sys.executable,'-O','-c',"import unittest;unittest.TestCase().fail('OPTIMIZED_CANARY')"],text=True,capture_output=True)
        self.assertNotEqual(canary.returncode,0)
        self.assertIn('OPTIMIZED_CANARY',canary.stderr)

    def test_temporary_oracle_mutants_are_exposed_by_the_bounded_contract(self):
        path=BASE/'linear_attention/oracle.py'
        raw=path.read_text()
        def mutant(before,after):
            self.assertEqual(raw.count(before),1)
            with tempfile.TemporaryDirectory() as directory:
                target=Path(directory)/'oracle.py'
                target.write_text(raw.replace(before,after))
                spec=importlib.util.spec_from_file_location('linear_mutant',target)
                value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
                return value
        invalid=copy.deepcopy(self.fixture['cases'][0]);invalid['initial_lengths']=[0]
        value=mutant('value < minimum','False')
        self.assertEqual(value.validate(invalid),(1,1,4,1,32,2))
        bool_case=copy.deepcopy(self.fixture['cases'][0]);bool_case['initial_lengths']=[True]
        value=mutant('type(value) is not int','not isinstance(value,int)')
        self.assertEqual(value.validate(bool_case),(1,1,4,1,32,2))
        padding_case=copy.deepcopy(self.fixture['cases'][1]);padding_case['initial_padding']=[2]
        value=mutant("('initial_padding', 0, 'ORACLE_INITIAL_PADDING')","('initial_padding', S, 'ORACLE_INITIAL_PADDING')")
        with self.assertRaisesRegex(value.InputError,'^ORACLE_INITIAL_PADDING_RANGE$'):
            value.validate(padding_case)
        missing=copy.deepcopy(self.fixture['cases'][0]);del missing['initial_lengths']
        value=mutant("('initial_lengths', S, 'ORACLE_INITIAL_LENGTHS')","('initial_padding', S, 'ORACLE_INITIAL_LENGTHS')")
        self.assertEqual(value.validate(missing),(1,1,4,1,32,2))
        class Recurrence:
            def ops_transition(self, request, initial):
                B,H=request['B'],request['Hk']
                return {'output':[[[[0.0]*8 for _ in range(H)]] for _ in range(B)],
                        'state':[[[0.0]*8 for _ in range(H)] for _ in range(B)]}
        value=mutant('if not close(mapping(recur_y, lambda x:x.v), accepted_y, 1e-14, 1e-13):',
                     'if False and not close(mapping(recur_y, lambda x:x.v), accepted_y, 1e-14, 1e-13):')
        value.close=lambda *args: True
        self.assertEqual(value.module_reference(copy.deepcopy(self.fixture['cases'][0]),Recurrence())['accepted_recurrence_block_crosscheck'],
                         'PASS; unchanged Dv8 interface, four independent value-row blocks')


if __name__=='__main__':unittest.main()
