#!/usr/bin/env python3
"""Prospective synthetic-only population. No model reads or native imports."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

D, H = 4096, 2048
TARGETS = {
    'A': ((1, 2), (4, -3), (12, 12), (2, -12)),
    'B': ((2, 1), (3, -4), (12, -12), (4, 12)),
}
ROLES = ('gate', 'up', 'down')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def input_bytes():
    return b''.join(struct.pack('<f', (2 + (1 if j.bit_count() % 2 == 0 else -1)) / 4096)
                    for j in range(D))


def bf16(value):
    packed = struct.pack('<f', value)
    if struct.unpack('<f', packed)[0] != value:
        raise ValueError('not exact F32 before BF16 conversion')
    bits = struct.unpack('<I', packed)[0]
    if bits & 65535 or bits & 0x7f800000 == 0x7f800000:
        raise ValueError('not exact finite BF16')
    return struct.pack('<H', bits >> 16)


def row_bytes(case, role, row):
    """Generate one packed row and its two metadata rows; no dense planes."""
    if case not in TARGETS or role not in ROLES:
        raise ValueError('population ID')
    n, k = (D, H) if role == 'down' else (H, D)
    if type(row) is not int or not 0 <= row < n:
        raise ValueError('row outside geometry')
    sign = 1 if case == 'A' else -1
    ri = ROLES.index(role)
    if role == 'down':
        s, b = sign / 4096, sign / 8192
    else:
        t = TARGETS[case][row % 4][ri]
        s, b = sign / 16, t / 2 - sign * 15 / 32
    weights = b''.join(struct.pack('<I', sum(((j + z + row + ri) % 16) << (4*z)
                                             for z in range(8)))
                       for j in range(0, k, 8))
    return weights, bf16(s) * (k // 64), bf16(b) * (k // 64)



def snapshot_case(out, case, entry):
    """Synthetic PLSEX001, same geometry/custody path; never original data."""
    prefix = 'language_model.model.layers.3.mlp.switch_mlp.'
    modules = [prefix+r+'_proj' for r in ROLES]
    components = [c for plane in entry['planes'] for c in plane['components']]
    lengths = [c['bytes'] for c in components]
    hashes = [c['sha256'] for c in components]
    metadata = sha(canonical({'synthetic_case': case, 'generator_schema': 2}))
    planes = []
    for i, role in enumerate(ROLES):
        planes.append({'role': role, 'module': modules[i], 'expert': 0, 'bits': 4,
            'group_size': 64, 'resolved_from': 'default', 'metadata_dtype': 'BF16',
            'logical_shape': [D,H] if role=='down' else [H,D],
            'ranges': [{'tensor': modules[i]+'.'+suffix, 'shard': 'synthetic-'+case+'.safetensors',
                'begin': 0, 'len': lengths[3*i+j]} for j,suffix in enumerate(('weight','scales','biases'))]})
    # These framing fields model captured metadata; they are synthetic schema
    # witnesses, not claims that original checkpoint reads occurred.
    plan = {'schema': 'pulsarmlx.bounded-expert-plan/1', 'checkpoint': 'synthetic-'+case,
        'metadata_snapshot_sha256': metadata, 'metadata_bytes_read': 790848,
        'request': {'modules': modules, 'expert': 0, 'experts': 288, 'd': D, 'h': H,
                    'bits': [4,4,4], 'group_size': 64},
        'planes': planes, 'selected_bytes': sum(lengths),
        'identity_scope': 'metadata snapshot and selected ranges only; no whole-checkpoint payload identity'}
    owned = {'schema': 'pulsarmlx.bounded-expert-owned/1', 'plan': plan,
        'selected_range_sha256': hashes, 'owned_bytes': sum(lengths),
        'packed_weights_unchanged': True, 'native_calls': 0, 'whole_shard_reads': 0,
        'whole_shard_hashes': 0, 'scope': 'host owned range bytes only; no numerical or full-checkpoint qualification'}
    header = canonical({'schema': 'pulsarmlx.selected-expert-snapshot/1',
                         'owned': owned, 'payload_lengths': lengths,
                         'scope': 'selected packed content only; no numerical qualification'})
    framing = b'PLSEX001'+struct.pack('<Q',len(header))+header
    digest = hashlib.sha256(framing)
    name = 'full-positive-'+case+'.snapshot'
    with (out/name).open('xb') as stream:
        stream.write(framing)
        for c in components:
            with (out/c['file']).open('rb') as source:
                while block := source.read(256*1024):
                    digest.update(block); stream.write(block)
    (out/name).chmod(0o400)
    entry['snapshot'] = name
    entry['binding'] = {'snapshot_sha256': digest.hexdigest(), 'snapshot_bytes': len(framing)+sum(lengths),
        'metadata_sha256': metadata, 'checkpoint': 'synthetic-'+case, 'ranges_sha256': hashes}


def control_population():
    """Concrete edits/predicates. No unsafe native refusal dispatch."""
    refusals = [
        {'id':'input-floor','kind':'r1-admission','edit':{'input_f32_index':0,'bits':0x2f000000},'expected':'R-DOMAIN-X-RANGE'},
        {'id':'metadata-floor','kind':'host-preflight','edit':{'role':'gate','component':'scales','bf16_index':0,'bits':0x2f00},'expected':'R-DOMAIN-META-RANGE'},
        {'id':'gate-margin','kind':'original-r1-admission','edit':{'role':'gate','row':0,'all_scales':0,'all_biases':8.5},'expected':'prospective activation margin'},
        {'id':'up-margin','kind':'original-r1-admission','edit':{'role':'up','row':0,'all_scales':0,'all_biases':8.5},'expected':'prospective activation margin'},
        {'id':'computed-hidden-margin','kind':'original-r1-admission','edit':{'gate_row0':{'s':0,'b':2**-21},'up_row0':{'s':0,'b':0.5}},'expected':'prospective down nonzero floor margin'},
        {'id':'down-floor-guard','kind':'r1-admission','edit':{'down_input_f32_index':0,'bits':0x2f000000},'expected':'R-DOMAIN-X-RANGE'},
    ]
    for name,pointer,value in [
        ('source','/owned/plan/metadata_snapshot_sha256','f'*64),
        ('layer','/owned/plan/planes/0/module','language_model.model.layers.4.mlp.switch_mlp.gate_proj'),
        ('expert','/owned/plan/request/expert',1),
        ('role','/owned/plan/planes/0/role','up'),
        ('recipe','/owned/plan/planes/0/bits',8),
        ('shape','/owned/plan/planes/0/logical_shape',[4096,2048])]:
        refusals.append({'id':'identity-'+name,'kind':'host-custody','pointer':pointer,'value':value,'expected':'identity/recipe/shape refusal before payload import'})
    for i in range(9):
        refusals.append({'id':f'range-digest-{i}','kind':'host-custody','edit':{'range':i,'byte_offset':0,'xor':255},'expected':'original range digest'})
    for name,operation in [('framing-missing-scope','remove top-level scope'),('framing-wrong-scope','replace top-level scope'),('framing-length','set first declared length to1'),('framing-trailing','append byte0'),('framing-duplicate','duplicate top-level schema key')]:
        refusals.append({'id':name,'kind':'host-custody','edit':operation,'expected':'framing/strict-schema refusal'})
    mutations=[]
    for name,kind,predicate in [
        ('omit-gate-bias','projection','gate separation exceeds Bg plus mutant QMM bound'),
        ('omit-up-bias','projection','up separation exceeds Bu plus mutant QMM bound'),
        ('nibble-order','native-packing-witness','full gate M1 N2048 K4096; every U32=0x76543210; s=1 b=0; basis x=e0; actual Plane/affine/code original0; native QMM original0; reversed original-byte decoder7 outside both local budgets'),
        ('gate-up-swap','activation','interval separation exceeds Bh plus swapped-input hidden bound'),
        ('lower-gate-clamp','clamp-stage','G=-15 U=1: clamp bits differ, balanced handles'),
        ('missing-upper-gate-clamp','clamp-stage','G=12 U=2: clamp bits differ, balanced handles'),
        ('missing-up-upper-clamp','clamp-stage','G=2 U=12: clamp bits differ, balanced handles'),
        ('missing-up-lower-clamp','clamp-stage','G=2 U=-12: clamp bits differ, balanced handles'),
        ('role-swap','host-custody','gate/down identity refused before import'),
        ('expert-swap','host-custody','expert1 refused before import'),
        ('reinterpret-8-bit','host-custody','bits8 refused before import'),
        ('skip-down-admission','report-audit','missing actual-down admission refuses acceptance'),
        ('candidate-fed-reference','authority-audit','reference input authority/hash mismatch refuses acceptance')]:
        mutations.append({'id':name,'kind':kind,'expected':predicate})
    ids=[c['id'] for c in refusals+mutations]
    if len(ids)!=len(set(ids)) or len(refusals)!=26 or len(mutations)!=13:
        raise ValueError('complete unique control population')
    return refusals,mutations


def generate(out):
    """Create-only files; component-at-a-time streaming; no overwritten attempts."""
    out.mkdir(parents=True, exist_ok=False)
    inp = input_bytes()
    (out / 'input-v2.f32').write_bytes(inp)
    manifest = {'schema': 'pulsarmlx.selected-synthetic-population/2',
                'license': 'MIT', 'provenance': 'closed-form synthetic only',
                'input': {'bytes': len(inp), 'sha256': sha(inp)}, 'cases': []}
    for case in TARGETS:
        entry = {'id': 'full-positive-' + case, 'M': 1, 'D': D, 'H': H, 'planes': []}
        for role in ROLES:
            n, k = (D, H) if role == 'down' else (H, D)
            plane = {'role': role, 'shape': [n, k], 'bits': 4, 'group_size': 64,
                     'metadata_dtype': 'BF16', 'components': []}
            for ci, component in enumerate(('weight', 'scales', 'biases')):
                name = f'{case}-{role}-{component}.raw'
                digest, length = hashlib.sha256(), 0
                with (out / name).open('xb') as stream:
                    for row in range(n):
                        raw = row_bytes(case, role, row)[ci]
                        stream.write(raw)
                        digest.update(raw)
                        length += len(raw)
                plane['components'].append({'file': name, 'bytes': length,
                                             'sha256': digest.hexdigest()})
            entry['planes'].append(plane)
        snapshot_case(out,case,entry)
        manifest['cases'].append(entry)
    refusals,mutations=control_population()
    manifest['refusals']=refusals;manifest['mutations']=mutations
    manifest['population']={'full_shape_positive':2,'host_refusal_and_guard':26,'mutation':13,'total':41}
    (out / 'manifest.json').write_bytes(canonical(manifest))
    receipt = {'schema': 'pulsarmlx.selected-input-freeze/2',
               'formula': '(2+(-1)^popcount(j))/4096; j=0..4095',
               'generator_sha256': sha(Path(__file__).read_bytes()),
               'interpreter_sha256': sha(Path(sys.executable).resolve().read_bytes()),
               'base_interpreter_sha256': sha(Path(sys._base_executable).resolve().read_bytes()),
               'interpreter_optimize': sys.flags.optimize,
               'interpreter_version': sys.version,
               'input_sha256': sha(inp), 'input_bytes': len(inp),
               'manifest_sha256': sha(canonical(manifest)),
               'numerical_native_calls': 0, 'real_payload_bytes_read': 0}
    (out / 'generation-receipt.json').write_bytes(canonical(receipt))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(generate(args.out), indent=2))
