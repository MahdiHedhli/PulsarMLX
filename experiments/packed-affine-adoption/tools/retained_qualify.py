#!/usr/bin/env python3
"""One CPU-only supplement over admitted retained outputs; never a live campaign."""
import argparse
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
import traceback

from retained_admission import admit, read, bounded, digest, equal, require, git, C, C_TREE, H, H_TREE
from retained_rational import frozen_view, grade_compatible, NumericalFailure

PROMPT = {'commit': '3df48aece25e51e5d7f3af99dbc9b108d767c552',
          'sha256': '26e64ed366eae4fba5b5be851fb8ef4761ed555c6dc6c9f89385dc79657834d2'}
ROOT = Path(__file__).resolve().parents[3]
FORBIDDEN_ENV = ('MLX_PREFIX', 'MLX_C_PREFIX', 'PULSAR_REQUIRE_NATIVE_MLX', 'PULSAR_ADOPTION_PHASE',
                 'PULSAR_ADOPTION_HOST_ROLE', 'PULSAR_ADOPTION_CAMPAIGN', 'PULSARMLX_MODEL_GGUF')


def environment():
    require(not any(k in os.environ for k in FORBIDDEN_ENV), 'native/experiment/model environment forbidden')


def guard(grader=None):
    """Execution safety boundary; arbitrary/archive/native subprocesses are refused."""
    def check(event, args):
        if event.startswith(('ctypes.dlopen', 'socket.')):
            raise RuntimeError('native load/network forbidden')
        if event == 'import' and str(args[0]).split('.')[0] in ('mlx', 'torch', 'tensorflow'):
            raise RuntimeError('native/model import forbidden')
        if event == 'subprocess.Popen':
            exe, argv = str(args[0]), args[1]
            require(isinstance(argv, (list, tuple)), 'shell forbidden')
            allowed = exe == 'git' or exe == '/usr/bin/otool'
            if grader is not None and exe == grader['path']:
                require(digest(exe) == grader['sha256'], 'CPU grader binary changed')
                allowed = True
            require(allowed, 'unapproved child executable')
    sys.addaudithook(check)


def create(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n'); f.flush(); os.fsync(f.fileno())


def arguments(a):
    return {k: str(getattr(a, k).resolve(strict=True)) for k in
            ('archive', 'artifact', 'source', 'controller', 'inputs', 'input_manifest')}


def admission(paths):
    return admit(*(paths[k] for k in ('archive', 'artifact', 'source', 'controller', 'inputs', 'input_manifest')))


def checker_identity():
    equal(git(ROOT, 'status', '--porcelain'), '', 'Q must be committed and clean')
    equal(git(ROOT, 'merge-base', C, 'HEAD'), C, 'Q ancestry')
    changes = git(ROOT, 'diff', '--name-status', C, 'HEAD').splitlines()
    require(bool(changes), 'Q additive source missing')
    delta = []
    for line in changes:
        status, name = line.split('\t')
        require(status == 'A' and name.startswith('experiments/packed-affine-adoption/'), 'previously tracked C file changed')
        require('/tools/' in name or name.endswith('.md'), 'checker scope')
        delta.append({'path': name, 'sha256': digest(ROOT / name)})
    return {'commit': git(ROOT, 'rev-parse', 'HEAD'), 'tree': git(ROOT, 'rev-parse', 'HEAD^{tree}'), 'delta': delta}


def freeze(a):
    environment(); guard()
    q = checker_identity(); paths = arguments(a)
    evidence = admission(paths)
    _, census = frozen_view(bounded(a.inputs / 'reference.json'), read(a.inputs / 'fixtures/manifest.json'))
    grader = a.grader.resolve(strict=True)
    build = read(a.build_identity)
    equal(build['source_commit'], C, 'CPU build source')
    equal(str(grader), build['executable'], 'CPU build executable')
    equal(digest(grader), build['sha256'], 'CPU build identity')
    linked = subprocess.check_output(['/usr/bin/otool', '-L', str(grader)], text=True)
    require(not any(s in linked.lower() for s in ('libmlx', 'libmlxc', 'metal.framework')), 'native-linked grader forbidden')
    equal(linked, build['linkage'], 'fresh CPU linkage')
    output = a.output.resolve()
    require(not os.path.lexists(output), 'occupied grading output')
    for root in (a.artifact, a.inputs, a.source, a.controller, ROOT):
        require(not output.is_relative_to(root.resolve()), 'output overlaps protected root')
        require(not a.receipt.resolve().is_relative_to(root.resolve()), 'receipt overlaps protected root')
    receipt = {'schema': 'pulsarmlx.retained-requalification-freeze/1', 'authority': PROMPT, 'Q': q,
               'executed_C': C, 'executed_C_tree': C_TREE, 'controller_H': H, 'controller_H_tree': H_TREE,
               'paths': paths, 'output': str(output), 'grader': {'path': str(grader), 'sha256': digest(grader),
               'build_identity_sha256': digest(a.build_identity), 'linkage': linked},
               'python': {'path': str(Path(sys.executable).resolve()), 'sha256': digest(Path(sys.executable).resolve())},
               'normalization': census, 'admission': evidence,
               'attempts_allowed': 1, 'native_launches_allowed': 0, 'raw_calls_allowed': 0,
               'deadline_seconds': 900, 'working_data_budget': 268435456,
               'selected_environment': {'native_variables_absent': True, 'RUST_TEST_THREADS': '1', 'CARGO_BUILD_JOBS': '2'}}
    create(a.receipt, receipt)
    return {'receipt_sha256': digest(a.receipt), 'Q': q, 'numerical_attempt_consumed': False}


def claim(receipt_path, receipt):
    output = Path(receipt['output'])
    require(not os.path.lexists(output), 'occupied grading root')
    # Stable authority anchor; a different output root does not reset the claim.
    intent = Path(receipt_path).parent / 'rust011-retained-grading.intent.json'
    create(intent, {'authority': PROMPT, 'receipt_sha256': digest(receipt_path),
                    'Q': receipt['Q'], 'output': str(output), 'attempt': 1,
                    'allowance_consumed': True, 'started_unix': time.time()})
    output.mkdir()
    return intent, output


def cpu_child(grader, argv, directory, remaining):
    require(remaining > 0, 'grading deadline expired')
    create(directory / 'rust-gates.attempt.json', {'grader_sha256': grader['sha256'], 'argv': argv})
    started = time.monotonic(); proc = None; status = {'started_monotonic': started}
    try:
        with (directory / 'rust-gates.stdout').open('xb') as out, (directory / 'rust-gates.stderr').open('xb') as err:
            proc = subprocess.Popen(argv, stdout=out, stderr=err)
            status['owned_pid'] = proc.pid
            status['exit_code'] = proc.wait(timeout=remaining)
            require(status['exit_code'] == 0, 'Rust reference gate failed')
    finally:
        if proc is not None and proc.poll() is None:
            proc.kill(); proc.wait(); status['owned_child_killed_and_reaped'] = True
        status['elapsed_seconds'] = time.monotonic() - started
        create(directory / 'rust-gates.outcome.json', status)


def grade(a):
    environment()
    receipt = read(a.receipt)
    equal(receipt['schema'], 'pulsarmlx.retained-requalification-freeze/1', 'receipt schema')
    equal(receipt['authority'], PROMPT, 'receipt authority')
    equal(checker_identity(), receipt['Q'], 'frozen Q')
    equal(receipt['python'], {'path': str(Path(sys.executable).resolve()), 'sha256': digest(Path(sys.executable).resolve())}, 'actual interpreter')
    equal([receipt['attempts_allowed'], receipt['native_launches_allowed'], receipt['raw_calls_allowed'],
           receipt['deadline_seconds'], receipt['working_data_budget']], [1, 0, 0, 900, 268435456], 'closed attempt bounds')
    guard(receipt['grader'])
    # Last read-only admission before the exclusive, allowance-consuming intent.
    evidence = admission(receipt['paths'])
    equal(evidence, receipt['admission'], 'admission changed after freeze')
    equal(digest(receipt['grader']['path']), receipt['grader']['sha256'], 'host grader identity')
    intent, output = claim(a.receipt, receipt)
    rows = []; counts = {'rust_invocations': 0, 'exact_projections': 0, 'rust_checks': 0, 'rust_deferrals': 0}
    failure = None; label = None; begin = time.monotonic(); envelope = None
    try:
        import reference_budget
        from reference import decide_qmm
        from mlx_affine_qmm_reference_v1 import exact_case
        reference_budget.start()
        deadline = begin + 900
        signal.setitimer(signal.ITIMER_REAL, max(0.001, deadline - time.monotonic()))
        paths = {k: Path(v) for k, v in receipt['paths'].items()}
        view, census = frozen_view(bounded(paths['inputs'] / 'reference.json'), read(paths['inputs'] / 'fixtures/manifest.json'))
        equal(census, receipt['normalization'], 'normalization changed')
        original_root = paths['source'] / 'fixtures/native-composition'
        inherited = {c['id']: c for c in read(original_root / 'manifest.json')['cases'] if c['expected']['outcome'] == 'accept'}
        for item in evidence['reports']:
            envelope = reference_budget.check(); label = item['label']
            directory = output / label; directory.mkdir()
            report = paths['artifact'] / item['path']; run = read(report)
            result_path = directory / 'rust-gates.json'
            argv = [receipt['grader']['path'], str(paths['inputs'] / 'portable.json'), str(original_root), str(report), str(result_path)]
            counts['rust_invocations'] += 1
            cpu_child(receipt['grader'], argv, directory, deadline - time.monotonic())
            rust = read(result_path)
            equal(rust['report_sha256'], digest(report), 'new Rust report binding')
            ids = [o['id'] for o in run['outputs']] if 'outputs' in run else [run['id']]
            equal([c['id'] for c in rust['cases']], ids, 'Rust case order')
            for case in rust['cases']:
                full = case['id'] in view['cases'] and view['cases'][case['id']]['rust'] is None
                if full:
                    equal(case, {'id': case['id'], 'gate': 'selected exact original-input R1 required separately', 'rust': None}, 'full-K explicit Rust deferral')
                    counts['rust_deferrals'] += 1
                else:
                    equal(case['G-QMM-RUST'], 'PASS', 'applicable Rust gate')
                    require(case['rust'] is not None, 'missing applicable Rust reference')
                    counts['rust_checks'] += 1
            if run.get('population') == 'inherited_slice2c_changed_import':
                c = inherited[run['id']]
                exact = exact_case(c, original_root)
                gates = decide_qmm(c, exact, rust['cases'][0]['rust'], run, report.parent)
                if any(v is not None and not v['pass'] for v in gates.values()):
                    raise NumericalFailure(run['id'], gates)
                gates = [{'id': run['id'], 'gates': gates}]
            else:
                gates = grade_compatible(view, report)
            counts['exact_projections'] += len(gates)
            row = {'label': label, 'report_sha256': digest(report), 'rust_gates_sha256': digest(result_path),
                   'rust_cases': rust['cases'], 'exact_gates': gates}
            create(directory / 'exact-gates.json', gates); rows.append(row)
            print(json.dumps({'completed': len(rows), 'label': label, 'elapsed_seconds': time.monotonic() - begin}), flush=True)
        equal(counts, {'rust_invocations': 52, 'exact_projections': 84, 'rust_checks': 76, 'rust_deferrals': 8}, 'complete retained numerical population')
        equal(admission(receipt['paths']), evidence, 'inputs/evidence changed during grading')
        equal(checker_identity(), receipt['Q'], 'Q changed during grading')
        require(time.monotonic() <= deadline, 'retained pass exceeded deadline')
        envelope = reference_budget.check()
    except BaseException as e:
        failure = {'type': type(e).__name__, 'error': str(e), 'label': label, 'traceback': traceback.format_exc(),
                   'case': getattr(e, 'case', None), 'gates': getattr(e, 'gates', None)}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    result = {'schema': 'pulsarmlx.retained-numerical-requalification/1', 'authority': PROMPT,
              'receipt_sha256': digest(a.receipt), 'intent_sha256': digest(intent), 'Q': receipt['Q'],
              'native_execution': {'C': C, 'C_tree': C_TREE, 'H': H, 'H_tree': H_TREE, 'run': 41933197121, 'attempt': 1, 'CI_conclusion': 'failure'},
              'verdict': 'PASS' if failure is None else 'FAILED_NO_RETRY', 'failure': failure,
              'admission': evidence, 'normalization': receipt['normalization'], 'python': receipt['python'],
              'grader': receipt['grader'], 'counts': counts, 'reports': rows, 'reference_envelope': envelope,
              'elapsed_seconds': time.monotonic() - begin,
              'child_peak_rss_observation': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
              'child_memory_note': 'OS cumulative child peak observation; not simultaneous total or whole-interval physical cap',
              'legacy_m1a_acceptance_created': False, 'Studio_released': False, 'M1b_released': False,
              'new_native_executions': 0, 'raw_calls': 0, 'shipping_default': 'copied'}
    create(output / 'retained-numerical-requalification.json', result)
    if failure is not None:
        raise ValueError('retained attempt failed; preserved; no retry: ' + failure['error'])
    return {'verdict': 'PASS', 'counts': counts, 'result_sha256': digest(output / 'retained-numerical-requalification.json')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('admit', 'freeze', 'grade'))
    for name in ('archive', 'artifact', 'source', 'controller', 'inputs', 'input-manifest', 'grader', 'build-identity', 'receipt', 'output'):
        p.add_argument('--' + name, type=Path)
    a = p.parse_args()
    if a.command == 'admit':
        environment(); guard(); result = admission(arguments(a))
    elif a.command == 'freeze':
        result = freeze(a)
    else:
        result = grade(a)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
