#!/usr/bin/env python3
"""Additive original-byte wrapper. Never reads candidate data to form R1."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import reference_budget
REPO=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(REPO/'scripts/research'),str(REPO/'crates/mlx-native-affine/acceptance')]
from mlx_affine_qmm_reference_v1 import exact_quantized_matmul
from exact_gates_v1 import binary64, decide_qmm
from f020_selected_r1_v2 import original_input, Plane, affine, gamma

def sha(raw):return hashlib.sha256(raw).hexdigest()
def canonical(j):return (json.dumps(j,sort_keys=True,indent=2)+'\n').encode()
def original(root,c):
    if c['role'] not in ('gate','up'):raise ValueError('projection scope')
    path=root/c['source']/'model.safetensors'
    with path.open('rb') as f:
        hlen=struct.unpack('<Q',f.read(8))[0]
        if hlen>2*1024*1024:raise ValueError('header cap')
        h=json.loads(f.read(hlen));parts=[];n,k=c['H'],c['D'];bits=c['bits'][('gate','up').index(c['role'])]
        for i,suffix in enumerate(('weight','scales','biases')):
            record=h['synthetic.experts.'+c['role']+'.'+suffix]
            width=4 if i==0 else 2;cols=k*bits//32 if i==0 else k//64;length=n*cols*width
            if record['shape']!=[c['experts'],n,cols] or record['dtype']!=('U32' if i==0 else 'BF16'):raise ValueError('original header')
            f.seek(8+hlen+record['data_offsets'][0]+c['expert']*length);raw=f.read(length)
            if len(raw)!=length or sha(raw)!=c['expected_hashes'][i]:raise ValueError('original component binding')
            parts.append(raw)
    x=(root/c['input']).read_bytes()
    if len(x)!=c['M']*k*4 or sha(x)!=c['input_sha256']:raise ValueError('original input binding')
    return x,parts

def freeze(root,manifest_hash,portable,out):
    start=time.monotonic();raw=(root/'manifest.json').read_bytes()
    if sha(raw)!=manifest_hash:raise ValueError('manifest identity')
    manifest=json.loads(raw);p=json.loads(portable.read_text())
    if p['fixture_manifest_sha256']!=manifest_hash:raise ValueError('portable evidence binding')
    pre={r['id']:r for r in p['cases']};rows={}
    for c in manifest['cases']:
        reference_budget.check()
        if time.monotonic()-start>900:raise ValueError('reference deadline')
        x,parts=original(root,c);n,k=c['H'],c['D'];bits=c['bits'][('gate','up').index(c['role'])]
        exponent=pre[c['id']]['bound_exponent']
        if k==4096:
            if sha(x)!='746ed37cdd4a6a1792ec512ada02f9a2bd2cfa9c5a88d2eae2758ccbd9b2d799':raise ValueError('full input')
            ys,bounds=affine(Plane(c['role'],parts),original_input(x,k));ph=[b/gamma(k) for b in bounds]
            exact={'k':k,'y_exact':[str(v) for v in ys],'phi_exact':[str(v) for v in ph]};rust=None
        else:
            case={'id':c['id'],'params':{'bits':bits,'group_size':64,'N':n,'K':k,'M_eff':c['M'],'transpose':True,'metadata_dtype':'BF16'}}
            tensors={}
            for name,dtype,shape,b in [('x','F32',[c['M'],k],x),('w','U32',[n,k*bits//32],parts[0]),('scales','BF16',[n,k//64],parts[1]),('biases','BF16',[n,k//64],parts[2])]:
                fmt='I' if dtype in ('F32','U32') else 'H';tensors[name]=(dtype,shape,b,[v[0] for v in struct.iter_unpack('<'+fmt,b)])
            exact=exact_quantized_matmul(case,tensors);rust=p['rust_r1'][c['id']]
            g=Fraction(k+1,2**53-(k+1))
            if any(abs(binary64(y)-Fraction(e))>g*Fraction(ph) for y,e,ph in zip(rust['y'],exact['y_exact'],exact['phi_exact'],strict=True)):raise ValueError('frozen Rust R1 self-check')
        rows[c['id']]={'original_id':c['original_id'],'input_sha256':c['input_sha256'],'component_sha256':c['expected_hashes'],'exact':exact,'rust':rust,'gamma_n':exponent}
    result={'schema':'pulsarmlx.adoption-original-reference/1','fixture_manifest_sha256':manifest_hash,'portable_sha256':sha(portable.read_bytes()),'wrapper_sha256':sha(Path(__file__).read_bytes()),'cases':rows,'reference_envelope':reference_budget.check(),'native_calls':0,'candidate_outputs_read':0,'elapsed_seconds':time.monotonic()-start}
    with out.open('xb') as f:f.write(canonical(result))
    return {'cases':len(rows),'reference_sha256':sha(out.read_bytes()),'rust_self_checks':16,'native_acceptance':'PENDING'}

def grade(reference,report):
    refs=json.loads(reference.read_text());run=json.loads(report.read_text());results=[]
    if run['identity']['fixture_manifest_sha256']!=refs['fixture_manifest_sha256']:raise ValueError('reference/report identity')
    for output in run['outputs']:
        r=refs['cases'][output['id']];case={'id':output['id'],'expected':{'families_0_31_2':[{'gamma_n':r['gamma_n']}]}}
        verdict=decide_qmm(case,r['exact'],r['rust'],{'id':output['id'],'output':output},report.parent)
        if any(v is not None and not v['pass'] for v in verdict.values()):raise ValueError('independent numerical failure')
        results.append({'id':output['id'],'gates':verdict})
    if not results:raise ValueError('missing numerical outputs')
    return results

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--manifest-sha256',required=True);p.add_argument('--portable',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();reference_budget.start();print(json.dumps(freeze(a.root,a.manifest_sha256,a.portable,a.out),indent=2))
