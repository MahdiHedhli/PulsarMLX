"""Preregistered discriminating host-only controls, no model tensor access."""
from decimal import Decimal, localcontext
import copy
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np
from studio017_ref_store import bf, Store, Refusal
from studio017_ref_graph import rms, sinkhorn, normalized_index_key, cold_cache
from studio017_ref_criteria import bf_stage, logits_result
from studio017_text_config import validate_document


class ScientificControls(unittest.TestCase):
    def test_exact_public_config_and_mutants(self):
        p=Path(__file__).resolve().parents[2]/'crates/mlx-expert-ranges/src/studio017-text-profile.json'
        a=json.loads(p.read_bytes())
        validate_document(a)
        for key,mut in [('rms_norm_eps',1e-6),('hc_sinkhorn_iters',19),('hc_eps',None),('attention_bias',0),
                        ('norm_topk_prob',1),('swiglu_limit',10),('layer_types',['linear_attention']*45)]:
            d=copy.deepcopy(a);d['text_config'][key]=mut
            with self.assertRaises(ValueError,msg=key):validate_document(d)
        d=copy.deepcopy(a);d['text_config']['linear_attn_config']['gate_lower_bound']=-4.0
        with self.assertRaises(ValueError):validate_document(d)

    def test_norm_epsilon_and_weight(self):
        # Binary-exact 1/512 amplitude makes epsilon and learned weight matter.
        h=1/512; x=bf([h,-h,h,-h]);weights=bf([1,2,3,4])
        expect=bf(np.array([h,-2*h,3*h,-4*h])/math.sqrt(h*h+1e-5))
        good=bf(rms(x,weights,1e-5))
        np.testing.assert_array_equal(good,expect)
        for bad in [bf(rms(x,weights,1e-6)),bf(rms(x,1,1e-5))]:
            self.assertGreater(bf_stage(expect,bad)['outside'],0)
        # LayerNorm subtracts 1 before applying variance, gamma and beta.
        z=1/128; k=bf([1.,1+z,1-z,1.]);b=bf([.5,.25,-.25,.125])
        e=bf(b+np.array([0.,2*z,-3*z,0.])/math.sqrt(z*z/2+1e-6))
        np.testing.assert_array_equal(normalized_index_key(k,weights,b),e)
        self.assertGreater(bf_stage(e,normalized_index_key(k,weights,b,1e-5))['outside'],0)
        self.assertGreater(bf_stage(e,bf(rms(k,weights,1e-6)+b))['outside'],0)

    def test_sinkhorn_iteration_mutant(self):
        L=[[0,-12,-12,-12],[0,0,-12,-12],[-12,0,0,-12],[-12,-12,0,0]]
        # Decimal scalar with matrix entries explicitly indexed. The NumPy
        # transform is under test, never reused to generate the expected values.
        with localcontext() as ctx:
            ctx.prec=60;ep=Decimal('0.000001')
            a=[[Decimal(x).exp() for x in row] for row in L]
            def normrows(a):return [[x/(sum(row)+ep) for x in row] for row in a]
            def normcols(a):return [[a[i][j]/(sum(r[j] for r in a)+ep) for j in range(4)] for i in range(4)]
            a=normcols([[x+ep for x in row] for row in normrows(a)])
            for _ in range(19):a=normcols(normrows(a))
            e=np.array([[float(x) for x in row] for row in a])
        g=sinkhorn(L,1e-6,20);m=sinkhorn(L,1e-6,19)
        np.testing.assert_allclose(g,e,rtol=2e-7,atol=3e-8)
        self.assertTrue(np.any(abs(e-m)>4e-5+4e-6*abs(e)))

    def test_cache_append_and_zero_sign(self):
        row=bf([[.5,-1.,1.]])
        a,p=cold_cache(row,3,3)
        np.testing.assert_array_equal(a[-1],row[0]);self.assertEqual(p,1)
        self.assertTrue(np.all(a[:-1].view('<u4')==0))
        with self.assertRaises(Refusal):cold_cache(row[:0],3,3)
        plus=np.array([0.],'<f4');minus=np.array([-0.],'<f4')
        self.assertEqual(bf_stage(plus,minus)['outside'],0)  # numerical equality only
        self.assertNotEqual(plus.view('<u4')[0],minus.view('<u4')[0])  # custody equality

    def test_untied_head_axis(self):
        # Same square physical dimensions and byte count: transposing does
        # NOT trigger a shape check; full logits/greedy must catch the error.
        n=64;rows=np.zeros((n,n),dtype='u1');rows[2,1]=11;rows[1,5]=3;rows[4,1]=5
        x=np.zeros(n,'f4');x[1]=1
        def project(matrix,p):
            raw=np.ascontiguousarray(matrix).tobytes()
            scale=struct.pack('<H',0x3f80)*n;bias=bytes(2*n)
            p.write_bytes(b'x'*8+raw+scale+bias)
            fd=os.open(p,os.O_RDONLY)
            try:
                st=os.fstat(fd);w=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
                src=Store({'s':fd},{'h.weight':('s',8,'U32',(n,n//4)),
                    'h.scales':('s',8+n*n,'BF16',(n,1)),'h.biases':('s',8+n*n+2*n,'BF16',(n,1))},{'s':w})
                return src.projection('h',x,n)
            finally:os.close(fd)
        with tempfile.TemporaryDirectory() as t:
            a=project(rows,Path(t)/'a');b=project(rows.T,Path(t)/'b')
        e=np.zeros(n,'f4');e[2]=11;e[4]=5
        self.assertTrue(logits_result(e,a,2)['pass_all'])
        self.assertEqual(int(np.argmax(b)),5)
        self.assertFalse(logits_result(e,b,5)['pass_all'])
