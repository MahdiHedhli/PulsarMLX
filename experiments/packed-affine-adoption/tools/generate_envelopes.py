#!/usr/bin/env python3
"""Create-only synthetic packaging; original bytes and authorities stay intact."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'scripts/research'))
import f020_selected_fixtures_v2 as original

def sha(b): return hashlib.sha256(b).hexdigest()
def encoded(x): return (json.dumps(x, sort_keys=True, indent=2)+'\n').encode()
def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f: f.write(data)
def verified(path, record):
    b=path.read_bytes()
    if len(b)!=record['bytes'] or sha(b)!=record['sha256']: raise ValueError('original byte identity: '+str(path))
    return b

def generate(out):
    out.mkdir(parents=True, exist_ok=False)
    dependency=json.loads((Path(__file__).parents[1]/'dependency-manifest.json').read_text())
    for row in dependency['files']:
        if row['path'].startswith(('scripts/', 'fixtures/')):
            verified(REPO/row['path'],row)
    fixture=REPO/'fixtures/expert-mlp-composition'
    inherited=json.loads((fixture/'manifest.json').read_text())
    cases=[]
    for profile in ('default','mixed'):
        name='d128-h64-'+profile; source=fixture/'checkpoints'/name; dest=out/name
        for filename in ('config.json','model.safetensors'):
            rel='checkpoints/'+name+'/'+filename
            write(dest/filename,verified(fixture/rel,inherited['files'][rel]))
        raw=(dest/'model.safetensors').read_bytes();hlen=struct.unpack_from('<Q',raw)[0]
        header=json.loads(raw[8:8+hlen]);names=[n for n in header if n!='__metadata__']
        if len(names)!=9: raise ValueError('original nine names')
        write(dest/'model.safetensors.index.json',encoded({'weight_map':{n:'model.safetensors' for n in names}}))
        for c in inherited['cases']:
            if c.get('checkpoint')!=name or c.get('kind')!='positive' or c.get('expert') not in (0,1):continue
            input_raw=verified(fixture/c['input'],inherited['files'][c['input']]);write(out/c['input'],input_raw)
            for role in ('gate','up'):
                plane=inherited['checkpoints'][name]['expected_planes'][role+'/'+str(c['expert'])]
                cases.append({'id':c['id']+'-'+role,'original_id':c['id'],'population_id':'small-tuple-read-into-v1','source':name,'input':c['input'],'input_sha256':sha(input_raw),'role':role,'expert':c['expert'],'experts':3,'D':128,'H':64,'M':c['M'],'bits':[8,4,8] if profile=='mixed' else [4,4,4],'expected_hashes':plane['sha256'],'source_kind':'indexed-tuple'})
    # Generate original raw arrays first. Never use PLSEX001 framing as the
    # metadata identity of the new indexed Safetensors envelope.
    original.generate(out/'original-full')
    full=json.loads((out/'original-full/manifest.json').read_text())
    inp=verified(out/'original-full/input-v2.f32',full['input'])
    if sha(inp)!='746ed37cdd4a6a1792ec512ada02f9a2bd2cfa9c5a88d2eae2758ccbd9b2d799':raise ValueError('frozen representative input')
    for c in full['cases']:
        dest=out/c['id'];header={};offset=0;parts=[]
        for plane in c['planes']:
            n,k=plane['shape']
            for ci,component in enumerate(plane['components']):
                name='synthetic.experts.'+plane['role']+'.'+('weight','scales','biases')[ci]
                length=component['bytes'];header[name]={'dtype':'U32' if ci==0 else 'BF16','shape':[1,n,k//8 if ci==0 else k//64],'data_offsets':[offset,offset+length]};offset+=length;parts.append(component)
        if offset!=14155776:raise ValueError('tuple cap/shape')
        dest.mkdir();h=encoded(header)
        with (dest/'model.safetensors').open('xb') as f:
            f.write(struct.pack('<Q',len(h)));f.write(h)
            for part in parts:f.write(verified(out/'original-full'/part['file'],part))
        write(dest/'config.json',encoded({'quantization':{'bits':4,'group_size':64}}))
        write(dest/'model.safetensors.index.json',encoded({'weight_map':{n:'model.safetensors' for n in header}}))
        for plane in c['planes'][:2]:
            cases.append({'id':c['id']+'-'+plane['role'],'original_id':c['id'],'population_id':'representative-read-into-v1','source':c['id'],'input':'original-full/input-v2.f32','input_sha256':sha(inp),'role':plane['role'],'expert':0,'experts':1,'D':4096,'H':2048,'M':1,'bits':[4,4,4],'expected_hashes':[x['sha256'] for x in plane['components']],'source_kind':'indexed-tuple'})
    files={str(p.relative_to(out)):{'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(out.rglob('*')) if p.is_file()}
    manifest={'schema':'pulsarmlx.adoption-fixtures/1','generator_sha256':sha(Path(__file__).read_bytes()),'original_full_generator_sha256':sha(Path(original.__file__).read_bytes()),'cases':cases,'files':files,'small_sequences':[[f'mlp-d128-h64-m{m}-e{e}-{profile}-{role}' for e in (0,1,0)] for profile in ('default','mixed') for role in ('gate','up') for m in (1,32)],'inherited_slice2c_manifest_sha256':sha((REPO/'fixtures/native-composition/manifest.json').read_bytes()),'inherited_population_unchanged':32,'inherited_positive_changed_import_required':14}
    if len(cases)!=20 or len(manifest['small_sequences'])!=8:raise ValueError('population')
    write(out/'manifest.json',encoded(manifest))
    return {'manifest_sha256':sha(encoded(manifest)),'cases':len(cases),'files':len(files),'native_calls':0,'real_payload_bytes':0}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    print(json.dumps(generate(parser.parse_args().out),indent=2))
