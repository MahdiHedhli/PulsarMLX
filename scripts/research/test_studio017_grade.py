"""Synthetic small full-population source/receipt/grader controls. No MLX."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np
from studio017_ref_grade import _inspect,_grade,layout,REAL,STATE_ABS
from studio017_ref_store import Refusal,bf


TINY=(5,8,32,10,8,2,4,4,4)


def encode(d):
    return (json.dumps(d,sort_keys=True,separators=(',',':'))+'\n').encode()


def dataset(path,role,changes=None):
    path.mkdir(mode=0o700)
    files={};routes=[];changes=changes or {}
    for name,(i,l,n,kind) in layout(TINY).items():
        a=np.zeros(n,dtype='<f4')
        if kind=='one' or kind=='embedding':a+=1
        if kind=='indexer':a[-1]=1
        if kind=='corrected':
            a[:]=np.arange(n,dtype='<f4')*.125
            if changes.get('tie') and i==3:a[1]=a[2]
            if changes.get('bad_route') and i==3:a[1:3]=a[1:3][::-1]
            ids=sorted(range(n),key=lambda x:(-a[x],x))[:8]
            routes.append(dict(layer=i,ids=ids,weights=[.3125]*8,cutoff_gap=float(min(a[j] for j in ids))-
                               float(max(a[j] for j in range(n) if j not in ids))))
        if kind=='logits':
            a[1]=3;a[2]=2
            if changes.get('margin'):a[2]=3
            if changes.get('wrong_nonwinner'):a[3]=.25
        if changes.get('state') and kind=='state' and i==1:a[7]=2*STATE_ABS
        data=a.tobytes()
        f=path/name;f.write_bytes(data)
        if not(changes.get('mutable') and kind=='conv' and i==0):f.chmod(0o400)
        files[name]=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
    rep=dict(schema='studio017-'+role+'/1',input_id=154820,token_id=1,position=0,
             layer_count=5,generated_token_count=1,routes=routes,runner_up=2,margin=0 if changes.get('margin') else 1)
    rep['files']=files
    if role=='native':
        rep['libraries']=['libjaccl.dylib','libmlx.dylib','libmlxc.dylib']
        rep['native']=dict(logical_bytes=32,reads=4,native_allocator_peak=32,affine_handles_freed=4,affine_live=0)
        if changes.get('leak'):rep['native']['affine_live']=1
    if changes.get('wrong_id'):rep['token_id']=3
    f=path/'report.json';f.write_bytes(encode(rep));f.chmod(0o400)
    if changes.get('missing'):(path/'00.state.offset.f32').unlink()
    if changes.get('extra'):(path/'unused').write_bytes(b'')
    path.chmod(0o500)


class Checks(unittest.TestCase):
    def test_exact_census(self):
        p=layout(REAL)
        self.assertEqual(len(p),399)
        self.assertEqual(sum(i[2] for i in p.values()),
                         154880+4096*2+45*(4096*6+1)+
                         34*(64*128*128+9*64*128)+11*(512+257)+42*(288+2*4096))

    def run_case(self,ref={},native=None):
        # All writes confined to a freshly created test-private tree.
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'ref';b=Path(tmp)/'native'
            try:
                dataset(a,'reference',ref)
                if native is None:return _inspect(a,TINY)
                dataset(b,'native',native)
                return _grade(a,b,TINY)
            finally:
                for p in (a,b):
                    if p.exists():p.chmod(0o700)

    def test_reference_only_gates(self):
        self.assertTrue(self.run_case()['eligible'])
        self.assertFalse(self.run_case({'tie':True})['eligible'])
        self.assertFalse(self.run_case({'margin':True})['eligible'])
        for problem in ('mutable','missing','extra','wrong_id'):
            with self.assertRaises(Refusal,msg=problem):self.run_case({problem:True})

    def test_pair_with_same_token_and_different_content(self):
        self.assertTrue(self.run_case(native={})['qualified'])
        r=self.run_case(native={'wrong_nonwinner':True})
        self.assertEqual(r['outside'],1);self.assertFalse(r['qualified']);self.assertEqual(r['native_token']['winner'],1)
        r=self.run_case(native={'state':True})
        self.assertEqual(r['outside'],1);self.assertFalse(r['qualified'])
        with self.assertRaises(Refusal):self.run_case(native={'leak':True})
        r=self.run_case(native={'bad_route':True})
        self.assertFalse(r['routes'][3]['membership_match']);self.assertFalse(r['qualified'])


if __name__=='__main__':unittest.main()
