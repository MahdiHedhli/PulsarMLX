"""Whole-node binding, independent expectations and safe metadata admission."""
import copy
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
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


if __name__=='__main__':unittest.main()
