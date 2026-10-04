"""Synthetic-only independent parser tests. Files retained for audit."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import f020_selected_snapshot_v2 as reader


def document():
    lens=reader.LENGTHS
    hashes=[hashlib.sha256(bytes([i+1])*n).hexdigest() for i,n in enumerate(lens)]
    planes=[]
    for i,role in enumerate(('gate','up','down')):
        module=reader.MODULES[i]
        planes.append(dict(role=role,module=module,expert=0,bits=4,group_size=64,
            resolved_from='default',metadata_dtype='BF16',
            logical_shape=[4096,2048] if i==2 else [2048,4096],
            ranges=[dict(tensor=module+'.'+suffix,shard='synthetic.safetensors',begin=0,len=lens[3*i+j])
                    for j,suffix in enumerate(('weight','scales','biases'))]))
    plan=dict(schema='pulsarmlx.bounded-expert-plan/1',checkpoint='synthetic',
        metadata_snapshot_sha256='a'*64,metadata_bytes_read=790848,
        request=dict(modules=list(reader.MODULES),expert=0,experts=288,d=4096,h=2048,bits=[4]*3,group_size=64),
        planes=planes,selected_bytes=reader.PAYLOAD,
        identity_scope='metadata snapshot and selected ranges only; no whole-checkpoint payload identity')
    owned=dict(schema='pulsarmlx.bounded-expert-owned/1',plan=plan,selected_range_sha256=hashes,
        owned_bytes=reader.PAYLOAD,packed_weights_unchanged=True,native_calls=0,whole_shard_reads=0,whole_shard_hashes=0,
        scope='host owned range bytes only; no numerical or full-checkpoint qualification')
    h=dict(schema='pulsarmlx.selected-expert-snapshot/1',owned=owned,payload_lengths=list(lens),scope='selected packed content only; no numerical qualification')
    expected=dict(snapshot_sha256='b'*64,snapshot_bytes=0,metadata_sha256='a'*64,checkpoint='synthetic',ranges_sha256=hashes)
    return h,expected


class Snapshot(unittest.TestCase):
    def test_strict_header_and_boolean_not_integer(self):
        h,e=document();raw=json.dumps(h).encode()
        reader.decode_header(raw,e)
        for key,val in [('expert',False),('experts',287),('d',2048),('group_size',32)]:
            bad=copy.deepcopy(h);bad['owned']['plan']['request'][key]=val
            with self.assertRaises(ValueError):reader.decode_header(json.dumps(bad).encode(),e)
        with self.assertRaises(ValueError):reader.decode_header(b'{"schema":0,'+raw[1:],e)
        h['unknown']=1
        with self.assertRaises(ValueError):reader.decode_header(json.dumps(h).encode(),e)

    def test_capture_scope_is_required_and_exact(self):
        h,e=document()
        bad=copy.deepcopy(h);del bad['scope']
        with self.assertRaisesRegex(ValueError,'strict keys'):
            reader.decode_header(json.dumps(bad).encode(),e)
        h['scope']='numerically qualified'
        with self.assertRaisesRegex(ValueError,'snapshot scope'):
            reader.decode_header(json.dumps(h).encode(),e)

    def test_full_synthetic_framing_and_corruption(self):
        h,e=document();raw=json.dumps(h).encode()
        prefix=b'PLSEX001'+struct.pack('<Q',len(raw))
        # Retain rather than deleting attempts. No private original bytes.
        directory=Path(tempfile.mkdtemp(prefix='f020-python-snapshot-host-'))
        path=directory/'synthetic.snapshot'
        digest=hashlib.sha256(prefix+raw)
        with path.open('xb') as stream:
            stream.write(prefix+raw)
            for i,n in enumerate(reader.LENGTHS):
                block=bytes([i+1])*n;stream.write(block);digest.update(block)
        path.chmod(0o400)
        e['snapshot_sha256']=digest.hexdigest();e['snapshot_bytes']=path.stat().st_size
        parts=reader.read_snapshot(path,e)
        self.assertEqual(sum(len(b) for p in parts.values() for b in p),14155776)
        for i in range(9):
            wrong=copy.deepcopy(e);wrong['ranges_sha256'][i]='c'*64
            with self.assertRaisesRegex(ValueError,'nine hashes'):reader.read_snapshot(path,wrong)
        def patch(offset, data):
            path.chmod(0o600)
            with path.open('r+b') as stream:
                stream.seek(offset);stream.write(data)
            path.chmod(0o400)
        start=len(prefix)+len(raw)
        for i,n in enumerate(reader.LENGTHS):
            offset=start+sum(reader.LENGTHS[:i])
            patch(offset,bytes([255]))
            with self.assertRaisesRegex(ValueError,'range digest'):
                reader.read_snapshot(path,e)
            patch(offset,bytes([i+1]))
        gate=start;up=start+sum(reader.LENGTHS[:3])
        patch(gate,parts['up'][0]);patch(up,parts['gate'][0])
        with self.assertRaisesRegex(ValueError,'range digest'):
            reader.read_snapshot(path,e)
        patch(gate,parts['gate'][0]);patch(up,parts['up'][0])
        wrong=dict(e,snapshot_sha256='c'*64)
        with self.assertRaisesRegex(ValueError,'whole snapshot'):reader.read_snapshot(path,wrong)
        link=directory/'link';os.symlink(path,link)
        with self.assertRaises(OSError):reader.read_snapshot(link,e)
        path.chmod(0o600)
        with self.assertRaisesRegex(ValueError,'immutable'):reader.read_snapshot(path,e)

    def test_depth_and_nonfinite(self):
        _,e=document()
        for raw in (b'['*17+b'0'+b']'*17,b'{"x":NaN}'):
            with self.assertRaises(ValueError):reader.decode_header(raw,e)


if __name__=='__main__':unittest.main()
