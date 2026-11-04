#!/usr/bin/env python3
"""Build/run only the fake ABI plus real bridge core. Never build a native target.

Requires existing pinned MLX C headers. No dependency or native installation.
Each case is one serial fresh process so production error latches are never reset.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[3]
BASE = '190c64213135a756f5e3d61059036b9af2d78d7a'
OLD_HASH = '32f650ec6583bf0d8cd99533657348cbcfa9abd3bdf0869f60197705de695e08'
CASES = ['copied', 'adopted', 'reuse', 'duplicate', 'error-bound', 'evidence']
CASES += [f'{op}:{kind}' for op in ('slice', 'reshape', 'cast', 'cast-bias', 'qmm')
          for kind in ('before', 'partial', 'empty', 'callback', 'throw')]
CASES += [f'{op}:{kind}' for op in ('import','import-scales','import-biases','input') for kind in ('before','partial')]
CASES += ['eval:before','sync:before','retire:before','free-output:before']

def execute(argv, log):
    r = subprocess.run(argv, capture_output=True, timeout=60)
    log.with_suffix('.stdout').write_bytes(r.stdout)
    log.with_suffix('.stderr').write_bytes(r.stderr)
    log.with_suffix('.command.json').write_text(json.dumps({'argv':argv,'exit_code':r.returncode},indent=2)+'\n')
    return r

def main():
    p=argparse.ArgumentParser();p.add_argument('--headers',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    out=a.out.resolve();out.mkdir() # preserve every attempt
    header=a.headers.resolve(strict=True)
    if not (header/'mlx/c/array.h').is_file():raise ValueError('pinned header directory required')
    core=REPO/'experiments/packed-affine-adoption/native'
    old=subprocess.check_output(['git','-C',str(REPO),'show',BASE+':experiments/packed-affine-adoption/native/adoption_bridge.mm'])
    if hashlib.sha256(old).hexdigest()!=OLD_HASH:raise ValueError('immutable regression source drift')
    # Remove only the platform wrapper, leaving old production bridge logic intact.
    lines=old.decode().splitlines();removed=[s for s in lines if s.startswith(('#import <Metal/Metal.h>', 'extern "C" size_t pa_page()', 'extern "C" size_t pa_max_buffer()'))]
    if len(removed)!=3:raise ValueError('old platform separation drift')
    (out/'old_core.h').write_text('extern "C" size_t pa_page();\nextern "C" size_t pa_max_buffer();\n'+'\n'.join(s for s in lines if s not in removed)+'\n')
    rows=[]
    for variant in ('old','repaired'):
        binary=out/('host-'+variant)
        cmd=['/usr/bin/clang++','-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-unused-parameter','-I'+str(header),'-I'+str(core),str(core/'bridge_host_test.cpp'),'-o',str(binary)]
        if variant=='old':cmd[1:1]=['-DPA_OLD_CORE','-DPA_CORE_INCLUDE="'+str(out/'old_core.h')+'"']
        r=execute(cmd,out/(variant+'-build'));assert r.returncode==0,r.stderr.decode()
        link=execute(['/usr/bin/otool','-L',str(binary)],out/(variant+'-linkage'));assert link.returncode==0
        if any(word in link.stdout.decode().lower() for word in ('libmlx','metal.framework','foundation.framework')):raise ValueError('forbidden host linkage')
        for name in (['copied'] if variant=='old' else CASES):
            label=variant+'-'+name.replace(':','-')
            r=execute([str(binary),name,str(out/(label+'.events.jsonl'))],out/label)
            expected=42 if variant=='old' else 0
            rows.append({'variant':variant,'case':name,'exit_code':r.returncode,'expected':expected})
            assert r.returncode==expected,(name,r.stdout.decode(),r.stderr.decode())
    (out/'result.json').write_text(json.dumps({'host_only':True,'native_linkage':False,'repaired_cases':len(CASES),'old_regression_exit':42,'rows':rows},indent=2)+'\n')
    print(json.dumps({'host_only':True,'passed':len(CASES),'old_regression_exit':42}))
if __name__=='__main__':main()
