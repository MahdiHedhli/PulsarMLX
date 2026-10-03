#!/usr/bin/env python3
"""Closed-form synthetic fixtures; no candidate, native library or RNG."""
import argparse, hashlib, json, struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
GATES=[-3,-1,-.5,0,.5,1,4,8,10,12,15]
UPS=[-15,-12,-10,-2,-1,-.5,0,.5,1,2,10,12,15]
ROLES=['gate','up','down']

def canonical(v): return (json.dumps(v,sort_keys=True,indent=2)+'\n').encode()
def sha(b): return hashlib.sha256(b).hexdigest()
def bf(v):
    word=struct.unpack('<I',struct.pack('<f',v))[0]
    if word & 65535: raise ValueError('formula is not exact BF16')
    return word>>16

def checkpoint(d,h,profile,refusal=None):
    arrays={}; specs={}; expected={}
    for ri,role in enumerate(ROLES):
        n,k=(d,h) if role=='down' else (h,d)
        bits=8 if profile=='mixed' and role!='up' else 4
        p=k*bits//32; groups=k//64
        all_words=[]; all_s=[]; all_b=[]
        for e in range(3):
            words=[]; scales=[]; biases=[]
            for row in range(n):
                if role=='down':
                    target=None; s=(e+1)/(4096 if bits==8 else 256); b=-1/32
                else:
                    base=(GATES if role=='gate' else UPS)[(row+ri*3)%len(GATES if role=='gate' else UPS)]
                    target=base+(e/16 if base else 0)
                    if refusal=='activation-gate' and role=='gate':target=-32
                    if refusal=='activation-up' and role=='up':target=32
                    s=1/16 if target else 0; b=target-.5 if target else 0
                rowcodes=[]
                for col in range(k):
                    code=8 if col==0 and role!='down' else (7*row+5*col+11*e+3*ri+1)% (1<<bits)
                    rowcodes.append(code)
                for col in range(0,k,32//bits):
                    words.append(sum(rowcodes[col+j]<<(j*bits) for j in range(32//bits)))
                for group in range(groups):
                    scales.append(bf(2**-33 if refusal=='metadata' and role=='gate' and e==1 and row==1 and group==0 else s))
                    biases.append(bf(b))
            components=[struct.pack('<'+'I'*len(words),*words),struct.pack('<'+'H'*len(scales),*scales),struct.pack('<'+'H'*len(biases),*biases)]
            expected[f'{role}/{e}']={'module':'synthetic.experts.'+role,'bits':bits,'group_size':64,'logical_shape':[n,k],'packed_shape':[n,p],'metadata_shape':[n,groups],'sha256':[sha(v) for v in components]}
            all_words+=words; all_s+=scales; all_b+=biases
        for suffix,dtype,shape,data in [('weight','U32',[3,n,p],struct.pack('<'+'I'*len(all_words),*all_words)),('scales','BF16',[3,n,groups],struct.pack('<'+'H'*len(all_s),*all_s)),('biases','BF16',[3,n,groups],struct.pack('<'+'H'*len(all_b),*all_b))]:
            name='synthetic.experts.'+role+'.'+suffix
            arrays[name]=data;specs[name]={'dtype':dtype,'shape':shape}
    header={'__metadata__':{'license':'MIT','provenance':'closed-form synthetic; no model data'}}; payload=b''
    for name in sorted(arrays):
        header[name]={**specs[name],'data_offsets':[len(payload),len(payload)+len(arrays[name])]}
        payload+=arrays[name]
    encoded=json.dumps(header,sort_keys=True,separators=(',',':')).encode()
    encoded+=b' '*((-len(encoded))%8)
    raw=struct.pack('<Q',len(encoded))+encoded+payload
    quant={'bits':4,'group_size':64}
    if profile=='mixed':
        for role in ['gate','down']:quant['synthetic.experts.'+role]={'bits':8,'group_size':64}
    config={'model_type':'synthetic-expert-mlp','quantization':quant}
    return raw,canonical(config),expected

def generate(out):
    files={}; cases=[]; cps={}
    def cp(d,h,profile,refusal=None):
        label=f'd{d}-h{h}-{profile}'+('-'+refusal if refusal else '')
        raw,config,expected=checkpoint(d,h,profile,refusal)
        path='checkpoints/'+label
        files[path+'/model.safetensors']=raw;files[path+'/config.json']=config
        cps[label]={'path':path,'expected_planes':expected}
        return label
    for d in [64,128]:
      for h in [64,128]:
       for profile in ['default','mixed']:
        label=cp(d,h,profile)
        for m in [1,32]:
         x=[(1,.5,0)[row%3] if col==0 else 0 for row in range(m) for col in range(d)]
         for e in range(3):
          ident=f'mlp-d{d}-h{h}-m{m}-e{e}-{profile}'
          xf='inputs/'+ident+'.f32';files[xf]=struct.pack('<'+'f'*len(x),*x)
          cases.append({'id':ident,'kind':'positive','checkpoint':label,'D':d,'H':h,'M':m,'expert':e,'profile':profile,'input':xf})
    base='d64-h64-default'
    for name,refusal,expert,probe,expected,phase in [
      ('input-floor',None,0,'input-floor','R-DOMAIN-X-RANGE','preflight'),
      ('metadata-floor','metadata',1,None,'R-DOMAIN-META-RANGE','preflight'),
      ('gate-range','activation-gate',0,None,'MLP-R-ACTIVATION','activation'),
      ('up-range','activation-up',0,None,'MLP-R-ACTIVATION','activation'),
      ('cross-expert',None,0,'cross-expert','MLP-R-TUPLE','tuple'),
      ('down-floor-guard',None,0,'down-floor-guard','R-DOMAIN-X-RANGE','down-guard')]:
        label=cp(64,64,'default',refusal) if refusal else base
        ident='refuse-'+name;xf='inputs/'+ident+'.f32'
        files[xf]=struct.pack('<'+'f'*64,2**-33 if probe=='input-floor' else 1,*([0]*63))
        cases.append({'id':ident,'kind':'guard-control' if probe=='down-floor-guard' else 'refusal','checkpoint':label,'D':64,'H':64,'M':1,'expert':expert,'profile':'default','input':xf,'probe':probe,'expected_refusal':expected,'phase':phase})
    controls=[{'id':name,'kind':'mutation','target':target} for name,target in [
      ('gate-up-argument-swap','stage-gate'),('gate-down-role-swap','tuple'),('down-expert-swap','tuple'),
      ('lower-gate-clamp','clamp-probe'),('missing-upper-gate-clamp','activation'),('missing-up-upper-clamp','activation'),
      ('missing-up-lower-clamp','activation'),('ignore-bit-override','recipe'),('skip-down-admission','guard-audit'),('candidate-fed-reference','authority-audit')]]
    predicates={
      'gate-up-argument-swap':'stage packed recipe',
      'gate-down-role-swap':'MLP-R-TUPLE at tuple phase with zero native counters',
      'down-expert-swap':'MLP-R-TUPLE at tuple phase with zero native counters',
      'lower-gate-clamp':'exact clamp stage rejects illicit lower clamp with unchanged handle census',
      'missing-upper-gate-clamp':'exact clamp semantics with unchanged handle census',
      'missing-up-upper-clamp':'exact clamp semantics with unchanged handle census',
      'missing-up-lower-clamp':'exact clamp semantics with unchanged handle census',
      'ignore-bit-override':'MLP-R-TUPLE at tuple phase with zero native counters',
      'skip-down-admission':'missing down_admission evidence',
      'candidate-fed-reference':'R1 authority binding'}
    for control in controls:control['expected_detection']=predicates[control['id']]
    manifest={'schema':'pulsarmlx.f020.expert-mlp-fixtures/1','license':'MIT','population':{'positives':48,'refusals':5,'guard_controls':1,'mutations':10,'total':64},'checkpoints':cps,'cases':cases,'controls':controls,'files':{k:{'bytes':len(v),'sha256':sha(v)} for k,v in sorted(files.items())}}
    files['manifest.json']=canonical(manifest)
    return files

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
    files=generate(a.out)
    if a.check:
        got={str(p.relative_to(a.out)):p.read_bytes() for p in a.out.rglob('*') if p.is_file()}
        if got!=files:raise SystemExit('fixture byte mismatch or extra file')
    else:
        a.out.mkdir(parents=True,exist_ok=True)
        for name,raw in files.items():
            p=a.out/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
    print(json.dumps({'status':'PASS','files':len(files),'bytes':sum(map(len,files.values())),'manifest_sha256':sha(files['manifest.json'])}))
