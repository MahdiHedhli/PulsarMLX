"""Finite synthetic controls only. No model directory discovery or real weights."""
import hashlib
import os
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

import studio017_ref_graph as g
import studio017_ref_criteria as c
from studio017_ref_store import Store,Refusal,bf


def matrix(key,shape,scale=.18):
    seed=int.from_bytes(hashlib.sha256(key.encode('ascii')).digest()[:4],'little')
    rng=np.random.Generator(np.random.PCG64(seed))
    return bf(rng.uniform(-scale,scale,size=shape))


class MockStore:
    def __init__(self,no_shared=False):
        self.no_shared=no_shared

    def dense(self,name,shape,dtype='BF16'):
        if name.endswith('norm.weight'):
            return np.ones(shape,np.float32)
        if name.endswith('e_score_correction_bias'):
            return (np.arange(shape[0],dtype=np.float32)-4)*.018
        if name.endswith('.scale'):
            return np.array([.8,.75,.53],dtype=np.float32)
        return matrix(name,shape)

    def projection(self,prefix,x,outputs,group=None,bits=8):
        if self.no_shared and '.mlp.shared_experts.' in prefix:
            return np.zeros(outputs,dtype=np.float32)
        key=prefix+repr(group)+str(bits)
        return bf(matrix(key,(outputs,x.size),.57).astype('f8')@x.astype('f8'))

    def embedding(self,prefix,token,width,vocab):
        return matrix('embed_'+str(token),(width,),1)


class Tests(unittest.TestCase):
    def test_full_small_graph_and_changed_expert(self):
        observed=[]
        def save(kind,meta,row):
            observed.append((kind,meta,row))
        logits,win,runner,margin=g.synthetic_forward(MockStore(),10,save)
        self.assertEqual([m['layer'] for k,m,a in observed if k=='layer'],list(range(5)))
        self.assertEqual([m['layer'] for k,m,a in observed if k=='route'],[3,4])
        self.assertEqual([m['layer'] for k,m,a in observed if k=='mla'],[3])
        for key,m,a in observed:
            if key=='kda':
                self.assertEqual(a['state'].shape,(2,4,4))
                self.assertFalse(a['suffix'][:2].any()); self.assertTrue(a['suffix'][-1].any())
            if key=='mla':
                self.assertEqual(a['indexer_cache'].shape,(9,))
                self.assertEqual(float(a['indexer_cache'][-1]),1)
                self.assertTrue(np.array_equal(a['latent_k'],a['latent_v']))
            if key=='route':
                self.assertTrue(c.route_margin(a['corrected'],m['selected'])['eligible'])
                self.assertTrue(np.any(a['shared']))
        self.assertEqual(len(logits),32);self.assertEqual(np.argmax(logits),win)
        self.assertGreaterEqual(margin,0);self.assertNotEqual(win,runner)
        altered=g.synthetic_forward(MockStore(no_shared=True),10,lambda *args:None)[0]
        self.assertTrue(np.any(logits!=altered))

    def test_rounding_packing_and_recipe(self):
        self.assertEqual(float(g.silu_bf(np.float32(0.06640625))),0.0341796875)
        self.assertEqual(float(bf(.06640625*g.sigmoid(.06640625))),.034423828125)  # rejects lost BF16 sigmoid edge
        one_even=1+1/256
        self.assertEqual(float(bf([one_even])[0]),1)
        self.assertEqual(float(bf([1+3/256])[0]),1+2/128)
        # Two rows of 4-bit codes. Integer scalar code-packing oracle, rather
        # than our NumPy unpacking routine, constructs bytes. Nonidentity bias.
        codes=[[int((r+3*j)%16) for j in range(64)] for r in range(2)]
        words=b''.join(struct.pack('<I',sum(row[i+t]<<(4*t) for t in range(8)))
                       for row in codes for i in range(0,64,8))
        scales=bytes.fromhex('803f0040');bias=bytes.fromhex('803f80bf')
        def setup(path):
            path.write_bytes(b'0'*8+words+scales+bias)
            fd=os.open(path,os.O_RDONLY);st=os.fstat(fd)
            ww=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
            tensors={'q.weight':('s',8,'U32',(2,8)),'q.scales':('s',8+len(words),'BF16',(2,1)),
                     'q.biases':('s',12+len(words),'BF16',(2,1))}
            return fd,Store({'s':fd},tensors,{'s':ww})
        with tempfile.TemporaryDirectory() as tmp:
            fd,store=setup(Path(tmp)/'synth')
            try:
                x=np.arange(64,dtype='f4')/64
                expected=bf([sum((c*scale+b)*float(z) for c,z in zip(row,x)) for row,scale,b in
                            zip(codes,[1,2],[1,-1])])
                np.testing.assert_array_equal(store.projection('q',x,2,None,4),expected)
                with self.assertRaises(Refusal):store.projection('q',x,2,None,8)
                with self.assertRaises(Refusal):store.projection('q',x,2,(2,0),4)
                with self.assertRaises(Refusal):store.raw('q.weight',(2,8),'U32',15,2)
            finally:
                os.close(fd)

    def test_mhc_activation_and_state_orientation(self):
        s=np.array([[1,2],[3,5]],dtype='f4');b=np.array([.5,1],'f4')
        post=np.array([1,2],'f4');comb=np.array([[.25,.75],[.625,.375]],'f4')
        y=g.expand(s,b,post,comb)
        np.testing.assert_array_equal(y,bf([[2.625,4.625],[2.875,5.375]]))
        # Negative gate is not clamped from below; up is clamped on both sides.
        hot=g.gate_activation(np.array([15.,10.,-15.,-10.]),np.array([13.,10.,-22.,-10.]))
        self.assertEqual(hot[0],hot[1]);self.assertNotEqual(hot[2],hot[3]);self.assertGreater(hot[2],0)
        q=np.array([[.5,-.25]],'f4');k=np.array([[.75,.5]],'f4');v=np.array([[1,2,-3]],'f4')
        y,st=g.cold_delta(q,k,v,np.ones_like(k),np.array([.5],'f4'))
        np.testing.assert_array_equal(st[0],np.array([[.375,.25],[.75,.5],[-1.125,-.75]]))
        np.testing.assert_array_equal(y,bf([[.125,.25,-.375]]))

    def test_route_and_grading_negative_controls(self):
        logits=np.array([2,1,0,-1],'f4');bias=np.array([0,-1,.7,0],'f4')
        ids,weights,u,gap=g.choose(logits,bias,2)
        self.assertEqual(set(ids),{0,2});self.assertGreater(gap,0)
        orig={id_:float(w) for id_,w in zip(ids,weights)}
        self.assertAlmostEqual(orig[0]/orig[2],(1/(1+np.exp(-2)))/.5,places=6)
        r={'selected':[int(i) for i in ids],'weights':weights,'corrected':u}
        bad={**r,'weights':weights[::-1]}
        self.assertFalse(c.route_result(r,bad)['pass_all'])
        self.assertFalse(c.route_margin(np.array([.5,.5,.1],'f4'),[0])['eligible'])
        good=bf([1.1,1.,-.5,0])
        self.assertTrue(c.logits_result(good,good,0)['pass_all'])
        bad=good.copy();bad[2]=bf(-.48)
        self.assertFalse(c.logits_result(good,bad,0)['pass_all'])  # winner still exact
        self.assertFalse(c.logits_result(good,good,1)['pass_all'])
        self.assertFalse(c.golden_margin(bf([1,1-2**-8,0]))['eligible'])
        with self.assertRaises(Refusal):c.interval_bf16(np.array([.1],'f4'))


if __name__=='__main__':
    unittest.main()
