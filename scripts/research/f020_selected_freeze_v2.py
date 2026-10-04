#!/usr/bin/env python3
"""Freeze source/synthetic review package; never read real selected data.

Neither freeze nor issue executes any numerical worker. A valid raw final review
is required to issue even a synthetic capability. No pass flag is accepted.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import f020_selected_authority_v2 as A
from f020_selected_process_v2 import private_json

ROOT=Path(__file__).resolve().parents[2]
SPEC='specs/020-mlx-safetensors-affine/'
CONTRACT=SPEC+'selected-numerical-v2/contracts/selected-numerical-v3.json'
CRATES=('mlx-expert-ranges','mlx-expert-mlp','mlx-native-affine','safetensors-catalog','mlx-affine','backend')


def source_paths():
    tracked=A.git(ROOT,'ls-files').splitlines()
    selected=[]
    for name in tracked:
        p=Path(name)
        include=name in ('Cargo.toml','Cargo.lock','CONTRIBUTING.md','.specify/memory/constitution.md')
        include |= any(name.startswith('crates/'+c+'/') and p.suffix in ('.rs','.cpp','.c','.h','.py','.toml') for c in CRATES)
        include |= name.startswith(SPEC+'selected-numerical-v2/')
        include |= name.startswith('scripts/ci/') and ('mlx' in p.name or 'f020' in p.name)
        include |= name.startswith('scripts/research/') and (p.name.startswith('f020_selected_') or p.name.startswith('test_f020_selected_'))
        include |= p.name in ('f020_expert_mlp_r1_v1.py','f020_expert_mlp_qualify_v1.py','f020_expert_mlp_fixtures_v1.py',
            'f020_native_primitives_fixtures_v1.py','f020_native_composition_fixtures_v1.py',
            'test_f020_native_composition_fixtures_v1.py','mlx_affine_qmm_reference_v1.py',
            'f020_fused_swiglu_cpu_guard_v2_4.h')
        include |= name in [SPEC+x for x in ('slice2b-plan.md','slice2c-plan.md','source-pins-slice2.json',
            'contracts/native-primitives-v1.json','contracts/native-composition-v1.json',
            'contracts/expert-mlp-composition-v1.json','contracts/numerics-v1.json')]
        if include:selected.append(name)
    A.require(any(n.endswith('f020_selected_freeze_v2.py') for n in selected),'freezer committed')
    return sorted(selected)


def freeze(args):
    A.require(A.git(ROOT,'status','--porcelain')=='','clean source before freeze')
    build=A.strict(A.bounded(args.build,private=True))
    for key in ('commands','rustc','cargo','clang','environment','regression_executables','native_libraries'):
        A.require(key in build,'build record '+key)
    for entry in build['regression_executables'].values():
        A.require(A.file_sha(Path(entry['path']).resolve(),256*1024*1024)==entry['sha256'],'regression executable hash')
    for entry in build['native_libraries'].values():
        A.require(A.file_sha(Path(entry['path']).resolve(),256*1024*1024)==entry['sha256'],'native library hash')
    # Review source/build identities, not private host filesystem locations.
    for entry in build['regression_executables'].values():
        entry['path']=str(Path(entry['path']).resolve().relative_to(ROOT))
    for name,entry in build['native_libraries'].items():
        entry['path']={'libmlx':'lib/libmlx.dylib','libmlxc':'lib/libmlxc.dylib','metallib':'lib/mlx.metallib'}[name]
    for key in ('MLX_PREFIX','MLX_C_PREFIX'):build['environment'][key]='PINNED_NATIVE_PREFIX'
    build.update(interpreter_optimize=sys.flags.optimize,interpreter_version=sys.version,
                 interpreter_sha256=A.file_sha(Path(sys._base_executable).resolve(),128*1024*1024))
    A.require(sys.flags.optimize==0,'unoptimized reference interpreter')
    files={name:{'text':A.bounded(ROOT/name).decode()} for name in source_paths()}
    for r in files.values():r['sha256']=A.sha(r['text'].encode())
    hashes={name:r['sha256'] for name,r in files.items()}
    population_raw=A.bounded(args.population);manifest=A.strict(population_raw)
    A.require(manifest['population']=={'full_shape_positive':2,'host_refusal_and_guard':26,'mutation':13,'total':41},'synthetic population')
    input_raw=A.bounded(args.input,16384)
    d={'commit':A.git(ROOT,'rev-parse','HEAD'),'tree':A.git(ROOT,'rev-parse','HEAD^{tree}'),
       'source_sha256':hashes,'package_sha256':A.sha(A.canonical(hashes)),
       'contract_path':CONTRACT,'contract_sha256':A.sha(A.bounded(ROOT/CONTRACT)),
       'executable_sha256':A.file_sha(args.executable.resolve(),256*1024*1024),
       'population_sha256':A.sha(population_raw),'input_sha256':A.sha(input_raw),'build':build,
       'pre_review_selected_numerical_observations':0}
    capsule={'schema':A.SCHEMA,'purpose':'FINAL_EXECUTION_REVIEW','descriptor':d,'source_files':files,
             'synthetic_population':{'text':population_raw.decode(),'sha256':A.sha(population_raw)},
             'request':"Independent adversarial final exact-version review. Source/proof/test/synthetic definitions only; no real values or raw private capture receipts. Check prospective input affine-bias observability, full-shape positive/control completeness, original-byte R1 independence and exact intervals, unchanged fixed budgets/domains, scoped geometry, owned adapter/custody, resource claims/enforcement, raw review/capability authority, regression evidence and one real probe ordering. Source tests and generation are not numerical qualification. No numerical observations have occurred under this new exact version. Prior source33b6e450 passed its synthetic population but its real attempt refused the accepted capture header before reading packed payload or computing R1/native values; this version repairs that framing incompatibility without changing input or numerical budgets. Build and source hashes identify the intended executable; reviewer has no tools. Return JSON only with schema pulsarmlx.selected-execution-review/2, decision ACCEPT or BLOCKED, blockers integer, findings array (severity/path/reason/fix), and assessed equal to the COMPLETE descriptor object verbatim as JSON. ACCEPT requires zero blockers. Do not omit assessed fields or source hashes. Any correctness/resource/authority gap is blocking. Established inherited source boundaries are preserved; review the bounded extension, without treating existing passing evidence as new numerical qualification."}
    private_json(args.out,capsule)
    print(A.sha(A.bounded(args.out)))


def issue(args):
    capsule=A.bounded(args.capsule,private=True);review=A.bounded(args.review,private=True)
    d=A.verify_current(ROOT,args.capsule,args.review,A.sha(capsule),A.sha(review),args.executable,
                     ROOT/CONTRACT,args.population,args.input)
    manifest=A.strict(A.bounded(args.population));case=manifest['cases'][0]
    cap={'schema':'pulsarmlx.selected-capability/2','repo':str(ROOT),'capsule_path':str(args.capsule.resolve()),
         'review_path':str(args.review.resolve()),'capsule_sha256':A.sha(capsule),'review_sha256':A.sha(review),
         'executable':str(args.executable.resolve()),'population_path':str(args.population.resolve()),
         'input_path':str(args.input.resolve()),'kind':'synthetic','case_id':case['id'],
         'snapshot_path':str(args.population.resolve().parent/case['snapshot']),'out':str(args.out.resolve()),
         'regressions':A.strict(A.bounded(args.regressions,private=True)) if args.mode=='issue-synthetic' else {}}
    if args.mode=='issue-real':
        import f020_selected_qualify_v2 as Q
        import f020_selected_ledger_v2 as L
        raw=A.bounded(args.synthetic_qualification,private=True)
        cap.update(kind='real',case_id='selected-layer3-expert0',snapshot_path=str(args.snapshot.resolve()),
            real_binding=A.strict(A.bounded(args.real_binding,private=True)),
            synthetic_qualification={'path':str(args.synthetic_qualification.resolve()),'sha256':A.sha(raw)})
        binding=Q.qualified_real(cap,d,A.strict(A.bounded(ROOT/CONTRACT)),manifest)
        # No snapshot access here. Once-only ledger is outside the output dir.
        L.issue(cap,d,binding)
    args.out.mkdir(mode=0o700,exist_ok=False)
    private_json(args.out/'capability.json',cap)
    print('Issued '+cap['kind']+' capability; no numerical execution.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=('freeze','issue-synthetic','issue-real'))
    for arg in ('executable','population','input','out'):parser.add_argument('--'+arg,type=Path,required=True)
    for arg in ('build','capsule','review','regressions','real-binding','synthetic-qualification','snapshot'):parser.add_argument('--'+arg,type=Path)
    args=parser.parse_args()
    if args.mode=='freeze':
        A.require(args.build is not None,'build record required');freeze(args)
    else:
        A.require(all((args.capsule,args.review)),'review records required')
        required=(args.regressions,) if args.mode=='issue-synthetic' else (args.real_binding,args.synthetic_qualification,args.snapshot)
        A.require(all(required),'scope evidence required');issue(args)


if __name__=='__main__':main()
