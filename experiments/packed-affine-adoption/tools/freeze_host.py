#!/usr/bin/env python3
"""Create one prospective native campaign manifest. No native artifact is run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
from report_checks import CONTRACT, sha
REPO=Path(__file__).resolve().parents[3]
def run(*args):return subprocess.check_output(args,cwd=REPO,text=True).strip()
def file_sha(path):
    with path.open("rb") as f:return hashlib.file_digest(f,"sha256").hexdigest()
def prepare(a):
    if run('git','status','--porcelain'):raise ValueError('freeze requires clean source; preserve newer work')
    source=run('git','rev-parse','HEAD');tree=run('git','rev-parse','HEAD^{tree}')
    if source!=a.source_commit:raise ValueError('source drift')
    machine=run('/usr/sbin/sysctl','-n','machdep.cpu.brand_string')
    if a.host_role=='native-ci':
        if os.environ.get('GITHUB_ACTIONS')!='true':raise ValueError('approved native CI required')
    elif machine!='Apple M1 Ultra':raise ValueError('physical M1 Ultra required')
    if platform.system()!='Darwin':raise ValueError('macOS native route required')
    prefix=a.native_prefix.resolve(strict=True)
    libraries={}
    for name in ('libmlx.dylib','libmlxc.dylib','mlx.metallib'):
        path=(prefix/'lib'/name).resolve(strict=True)
        if not path.is_relative_to(prefix/'lib'):raise ValueError('native input outside prefix')
        libraries[name]=file_sha(path)
    # Link inspection is read-only; the parent and grader must be MLX-free.
    for path in (a.parent,a.rust_grader):
        linked=run('/usr/bin/otool','-L',str(path))
        if any('libmlx' in line.lower() for line in linked.splitlines()[1:]):raise ValueError('host executable linked to MLX')
    manifest=json.loads((a.fixture_root/'manifest.json').read_bytes())
    portable=json.loads(a.portable.read_bytes());reference=json.loads(a.reference.read_bytes())
    mh=sha((a.fixture_root/'manifest.json').read_bytes())
    if portable['fixture_manifest_sha256']!=mh or reference['fixture_manifest_sha256']!=mh or reference['portable_sha256']!=sha(a.portable.read_bytes()):raise ValueError('crossed fixture/reference')
    for name,entry in manifest['files'].items():
        from report_checks import confined
        path=confined(a.fixture_root,name)
        if file_sha(path)!=entry['sha256']:raise ValueError('fixture file drift')
    from report_checks import expected_population
    inherited=REPO/'fixtures/native-composition';original=json.loads((inherited/'manifest.json').read_bytes())
    if sha((inherited/'manifest.json').read_bytes())!='6f0e39e6d2c705603f3f897133d42c31837c53348aba0f4b0389dca18018fc14':raise ValueError('frozen inherited manifest')
    expected_population(manifest,original)
    # This checks bytes and source pins, not provenance of an installation. The
    # named host owner must verify the existing pinned build receipt separately.
    record={'schema':'pulsarmlx.adoption-host-freeze/1','contract_sha256':CONTRACT,'source_commit':source,'source_tree':tree,'host_role':a.host_role,'binary_sha256':file_sha(a.binary),'parent_sha256':file_sha(a.parent),'rust_grader_sha256':file_sha(a.rust_grader),'native_libraries':libraries,'mlx_commit':'68cf2fddd8de5edd8ab3d926391772b2e2cedad8','mlx_c_commit':'0726ca922fc902c4c61ef9c27d94132be418e945','native_build_receipt_sha256':file_sha(a.native_build_receipt),'native_build_receipt':str(a.native_build_receipt.resolve()),'fixture_root':str(a.fixture_root.resolve()),'fixture_manifest_sha256':mh,'portable_report':str(a.portable.resolve()),'portable_report_sha256':sha(a.portable.read_bytes()),'reference':str(a.reference.resolve()),'reference_sha256':sha(a.reference.read_bytes()),'inherited_root':str(inherited),'inherited_manifest_sha256':sha((inherited/'manifest.json').read_bytes()),'generator_hashes':{k:manifest[k] for k in ('generator_sha256','original_full_generator_sha256')},'dependency_manifest_sha256':sha((REPO/'experiments/packed-affine-adoption/dependency-manifest.json').read_bytes()),'host':{'machine':machine,'os':platform.mac_ver()[0],'source_volume':'generated local synthetic files; no cache flush','cache_state_labels':['uncontrolled OS page cache','native allocator cleared at child startup'],'native_limits':{'live_working_bytes':33554432,'mlx_memory_requested':33554432,'mlx_cache_requested':33554432,'combined_logical_reservation':100663296}},'raw_probe_budget':{'allowed':1,'used':0},'shipping_default':'copied'}
    if a.native_ci_acceptance:
        acceptance=json.loads(a.native_ci_acceptance.read_bytes())
        if a.host_role!='m1-ultra-studio' or acceptance['host_role']!='native-ci' or acceptance['source_commit']!=source or acceptance['source_tree']!=tree or acceptance['fixture_manifest_sha256']!=mh or acceptance['correctness']!='PASS' or acceptance['mechanism']!='PASS':raise ValueError('CI acceptance identity')
        record['native_ci_acceptance']=str(a.native_ci_acceptance.resolve());record['native_ci_acceptance_sha256']=sha(a.native_ci_acceptance.read_bytes())
    return record
def freeze(a):
    record=prepare(a)
    source=record['source_commit'];tree=record['source_tree']
    a.campaign.mkdir() # never replace a spent/unknown campaign
    with (a.campaign/'freeze.json').open('x') as f:json.dump(record,f,sort_keys=True,indent=2);f.write('\n')
    print(json.dumps({'source_commit':source,'source_tree':tree,'freeze_sha256':sha((a.campaign/'freeze.json').read_bytes()),'host_role':a.host_role}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host-role',choices=['native-ci','m1-ultra-studio'],required=True);p.add_argument('--source-commit',required=True)
    for name in ('campaign','fixture-root','portable','reference','native-prefix','native-build-receipt','binary','parent','rust-grader'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--native-ci-acceptance',type=Path);freeze(p.parse_args())
