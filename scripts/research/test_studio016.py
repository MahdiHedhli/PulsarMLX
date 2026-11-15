"""Offline negative controls, including actual reference wire grammar. No model payload."""
import copy
import json
import os
import struct
import tempfile
import unittest
import sys
from fractions import Fraction as F
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from studio016_source import whole_identity,geometry, parse, read, opened, vector, sha
from studio016_compare import serialize, deserialize, affine_gate, compare
from studio016_reference import affine, units, X_EXP, W_EXP, hidden_admission
from studio016_campaign import record, sealed, file_receipt, enc, validate_binding

class Tests(unittest.TestCase):
    def test_wire(self):
        # Actual serializers, schema, and full coordinate counts; no test-only codec.
        vals=[F(0),F(7),F(-2),F(3,4)]*512
        obj=dict(g=vals,u=vals,bg=list(map(abs,vals)),bu=list(map(abs,vals)),
                 h=[(v,v) for v in vals],bh=list(map(abs,vals)),y=[(v,v) for v in vals]*2,propagated=list(map(abs,vals))*2)
        wire=parse(json.dumps(serialize(obj)).encode())
        self.assertEqual(wire['g'][:4],['0/1','7/1','-2/1','3/4'])
        self.assertEqual(deserialize(wire),obj)
        for invalid in ('0','-2','2/2','-0/1'):
            wire['g'][0]=invalid
            with self.assertRaises(ValueError):deserialize(wire)

    def test_changed_nibble_and_bias_rejected(self):
        class Tiny:
            k,n=2048,1
            def groups(self,row):
                yield 0,b'\x21'+bytes(31),1<<W_EXP,1<<W_EXP
        p=Tiny();x=[1<<X_EXP]+[0]*2047
        y,b=affine(p,x)
        self.assertEqual(y,[2]);affine_gate(F(2),y[0],b[0])
        for wrong in (3,1): # swapped nibble; omitted bias
            with self.assertRaises(ValueError):affine_gate(wrong,y[0],b[0])
    def test_full_report_consumer(self):
        # Synthetic all-zero planes; production codec and real local-down decoder.
        zero=F(0);h=[(zero,zero)]*2048
        ref=dict(g=[zero]*2048,u=[zero]*2048,bg=[zero]*2048,bu=[zero]*2048,bh=[zero]*2048,h=h,y=h*2,propagated=[zero]*4096)
        parts={r:(bytes(4194304),bytes(262144),bytes(262144)) for r in ('gate','up','down')}
        outputs=lambda n:dict(shape=[1,n],dtype='F32',sha256=sha(bytes(4*n)),f32_bits=[0]*n)
        ident={'input_sha256':sha(vector())};report=dict(outcome='executed',identity=ident,source=dict(logical_bytes=14155776,logical_calls=9),
            cleanup=dict(live=0,double_frees=0,handler_messages=0,cleanup_errors=0),staging=[])
        for r,n,N in [('gate',2048,273),('up',2048,273),('down',4096,145)]:
            rss=dict(active_bytes=0,allocator_peak_bytes=0,process_peak_rss_bytes=0)
            report[r]=dict(output=outputs(n),bound_exponent=N,preflight_calls=0,calls_before=[0,0],calls_after=[5,4],
                packed_sha256=sha(parts[r][0]),input_sha256=(ident['input_sha256'] if r!='down' else sha(bytes(8192))),
                resources_before=rss,resources_after=rss)
            report['staging'].append(dict(reader=dict(published=True,setup=dict(policy='BufferedRequested',live=1)),logical=dict(role=r,actual_sha256=[sha(a) for a in parts[r]]),retired=dict(live=0,released=1)))
        report['activation']=dict(status=0,elements=2048,stats=[2,0,9,4,13,1,9,0],gate_clamp_bits=[0]*2048,up_clamp_bits=[0]*2048,output=outputs(2048))
        report['down_admission']=dict(decision='admitted',before=[10,8],after=[10,8],input_sha256=sha(bytes(8192)))
        self.assertEqual(compare(report,deserialize(serialize(ref)),parts,ident)['status'],'PASS')
        # Change the reported final word with a self-consistent digest. The
        # independent ideal/local contracts must reject it despite valid framing.
        report['down']['output']['f32_bits'][-1]=0x3f800000
        report['down']['output']['sha256']=sha(bytes(4095*4)+struct.pack('<f',1.))
        with self.assertRaisesRegex(ValueError,'down local'):compare(report,ref,parts,ident)

    def test_output_replacement(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t).resolve();p=root/'native.json';p.write_bytes(enc({'n':1}))
            with p.open('rb') as f:expected=file_receipt(f)
            record(root/'native-seal.json',expected)
            self.assertEqual(sealed(root,'native',{'native':expected}),{'n':1})
            q=root/'replacement';q.write_bytes(p.read_bytes());os.replace(q,p)
            with self.assertRaises(ValueError):sealed(root,'native',{'native':expected})

    def test_admission(self):
        self.assertEqual(len(vector()),16384)
        self.assertEqual(sha(vector()),'0cf0ff9cfc811e69f72f31bf7279d66b03720a63f136d71a2d81ab3e6aff6a38')
        with self.assertRaises(ValueError):parse(b'{"a":0,"a":0}')
        for word in (1,0x7fc00000,0x00800000):
            with self.assertRaises(ValueError):units(word)
        with self.assertRaises(ValueError):hidden_admission([17],[0],[0],[0])
        for offsets in ([0,12],[-1,2],[1,2],[0,1]):
            with self.assertRaises(ValueError):geometry({'x':{'data_offsets':offsets}},8,10)
    def test_mutation_short_read_and_claim_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();p=root/'data';p.write_bytes(b'abc')
            # Even an unchanged selected prefix cannot hide an out-of-range flip.
            p.write_bytes(b'abc1')
            with p.open('rb') as f:self.assertEqual(whole_identity(f.fileno(),4,sha(b'abc1')),sha(b'abc1'))
            p.write_bytes(b'abc2')
            with p.open('rb') as f,self.assertRaisesRegex(ValueError,'publisher'):whole_identity(f.fileno(),4,sha(b'abc1'))
            with self.assertRaises(FileNotFoundError):validate_binding(root,{}, {})
            p.write_bytes(b'abc')
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
            try:
                with self.assertRaises(ValueError):
                    with opened(fd,'data') as (f,_):read(f,0,4)
                with self.assertRaises(ValueError):
                    with opened(fd,'data') as (f,_):p.write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    with opened(fd,'data') as (f,_):read(f,0,(16<<20)+1)
                (root/'link').symlink_to(p)
                with self.assertRaises(OSError):
                    with opened(fd,'link'):pass
                claim=root/'claim';record(claim,{'ordinal':1})
                with self.assertRaises(FileExistsError):record(claim,{'ordinal':2})
                self.assertEqual(parse(claim.read_bytes()),{'ordinal':1})
            finally:os.close(fd)
if __name__=='__main__':unittest.main()
