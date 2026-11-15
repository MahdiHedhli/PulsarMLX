"""Offline negative controls, including actual reference wire grammar. No model payload."""
import copy
import json
import os
import struct
import tempfile
import unittest
from fractions import Fraction as F
from pathlib import Path
from studio016_source import geometry, parse, read, opened, vector, sha
from studio016_compare import serialize, deserialize, affine_gate
from studio016_reference import affine, units, X_EXP, W_EXP, hidden_admission
from studio016_campaign import record

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
