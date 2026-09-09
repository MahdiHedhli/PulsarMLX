"""Current tiny successor command. Bootstrap imports only standard library.

The caller supplies a materialized checkout and a separately hashed manifest.
No downloaded code, dependency installation or full model operation exists.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types


def bounded(path, cap=1024**2):
    p = Path(path)
    if not p.is_absolute() or p.resolve(strict=True) != p:
        raise ValueError('HARNESS_NOT_READY: bootstrap alias')
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > cap:
            raise ValueError('HARNESS_NOT_READY: bootstrap size/type')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(cap + 1)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after) or len(raw) != before.st_size:
            raise ValueError('HARNESS_NOT_READY: bootstrap drift')
        return raw
    finally:
        os.close(fd)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict(raw):
    def unique(pairs):
        obj = {}
        for k, v in pairs:
            if k in obj:
                raise ValueError('HARNESS_NOT_READY: duplicate JSON key')
            obj[k] = v
        return obj
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def producer_pass(stdout, stderr, stop, operation):
    """A failed or incomplete real capture never becomes an archive producer."""
    try:
        lines = stdout.decode('utf-8').splitlines()
        events = [strict(line) for line in lines if line.startswith('{')]
        results = [event for event in events if event.get('event') == 'result']
        expected_tests = {'case': 1, 'matrix': 4, 'discrimination': 4, 'convolution': 6, 'cache': 8}[operation]
        if len(results) != 1 or strict(lines[-1]) != results[0]:
            return False
        result = results[0]
        if operation == 'convolution' and result.get('test_ids') != [
                'test_classifier_wrong_type_and_message', 'test_interleaved_and_new_cache',
                'test_k1_source_diagnostic', 'test_mutants_normal_mutant_restored',
                'test_partition_composition', 'test_research_refusals_and_failure_order']:
            return False
        if operation == 'cache' and result.get('test_ids') != [
                'test_batch_lifecycle_composition', 'test_cache_bookkeeping_composition',
                'test_cache_construction_alias_and_errors', 'test_classifier',
                'test_interleaved_new_cache', 'test_mutations', 'test_partitions',
                'test_research_refusal_and_callee_failure']:
            return False
        return (stop['exit_code'] == 0 and stop['stop_confirmed'] and stop['capture_complete']
                and stop['direct_child_reaped'] and stop['process_group_absent'] and stop['reason'] is None
                and result['status'] == 'PASS' and type(result['tests_run']) is int and result['tests_run'] == expected_tests
                and all(type(result[k]) is int and result[k] == 0 for k in ('skips', 'failures', 'errors'))
                and all(stop['outputs'][name] == {'bytes': len(raw), 'sha256': sha(raw)}
                        for name, raw in [('stdout', stdout), ('stderr', stderr)]))
    except (ValueError, KeyError, TypeError, IndexError, UnicodeError):
        return False


def load(name, root, manifest=None):
    path = root / 'scripts/research/glm53_flash/router_caller' / (name + '.py')
    raw = bounded(path)
    if manifest is not None:
        row = next(r for r in manifest['source_inputs'] if r['path'] == 'code/' + path.relative_to(root).as_posix())
        if row['bytes'] != len(raw) or row['sha256'] != sha(raw):
            raise ValueError('HARNESS_NOT_READY: helper identity')
    namespace = {'__name__': 'flash_' + name, '__file__': str(path)}
    exec(compile(raw, 'verified-successor:' + name, 'exec'), namespace)
    return types.SimpleNamespace(**namespace)


def child(request_path):
    request = strict(bounded(request_path))
    roots = {}
    for role, binding in request['role_fds'].items():
        fd = binding['fd']
        s = os.fstat(fd)
        # Darwin F_GETPATH resolves only the explicitly inherited descriptor.
        raw = fcntl.fcntl(fd, 50, bytes(1024))
        path = Path(os.fsdecode(raw.split(b'\0', 1)[0]))
        if (not stat.S_ISDIR(s.st_mode) or (s.st_dev, s.st_ino) != (binding['dev'], binding['ino'])
                or sha(str(path).encode()) != binding['path_sha256']):
            raise ValueError('HARNESS_NOT_READY: inherited role identity')
        roots[role] = path
    code = roots['code']
    manifest = request['manifest']
    self_row = next(r for r in manifest['source_inputs'] if r['path'].endswith('/router_caller/successor.py'))
    if sha(bounded(Path(__file__))) != self_row['sha256']:
        raise ValueError('HARNESS_NOT_READY: entry drift')
    guard = load('successor_guard', code, manifest)
    context = guard.Context(roots, manifest, phase=roots['stage'])
    context.verify(environment=request['operation'] != 'archive-verify')
    if request['operation'] == 'archive-verify':
        archive = load('rc_archive', code, manifest)
        value = archive.verify_archive(roots['archive'], request['archive_manifest_sha256'])
        print(json.dumps({'event': 'archive_readback', 'status': 'PASS', **value}), flush=True)
        return 0
    doctor = load('successor_doctor', code, manifest)
    probe_work = roots['work'] / 'doctor-probe'
    probe_work.mkdir()
    denial = roots['denied'] / 'read-marker'
    mode = request.get('probe', 'capabilities')
    result = doctor.probe(mode, probe_work, denial)
    if result or request['operation'] == 'doctor':
        return result
    if mode != 'capabilities':
        raise ValueError('HARNESS_NOT_READY: numerical doctor mismatch')
    context.verify_child_interpreter(context.phase)
    for row in manifest['source_inputs']:
        if row['path'].startswith('upstream/'):
            p = context.phase / 'source' / row['path'].removeprefix('upstream/')
            if sha(guard.read(p, row['bytes'])) != row['sha256']:
                raise ValueError('HARNESS_NOT_READY: staged input drift')
    harness = load('successor_harness', code, manifest)
    return harness.run(context, request['operation'], request['backend'])


def public(args):
    for name in ('source', 'environment', 'fixtures', 'upstream', 'environment_identity', 'output'):
        spelling = getattr(args, name)
        if str(Path(spelling)) != spelling or not Path(spelling).is_absolute():
            raise ValueError('HARNESS_NOT_READY: noncanonical caller path spelling')
    code = Path(args.source)
    manifest = None
    if args.operation != 'manifest':
        raw = bounded(Path(args.manifest))
        if sha(raw) != args.manifest_sha:
            raise ValueError('HARNESS_NOT_READY: manifest identity')
        manifest = strict(raw)
        row = next(r for r in manifest['source_inputs'] if r['path'] == 'code/scripts/research/glm53_flash/router_caller/successor.py')
        if sha(bounded(Path(__file__))) != row['sha256']:
            raise ValueError('HARNESS_NOT_READY: entry identity')
    guard = load('successor_guard', code, manifest)
    roots = {k: guard.canonical(Path(getattr(args, k))) for k in ('environment', 'fixtures', 'upstream', 'environment_identity')}
    roots['code'] = guard.canonical(code)
    if roots['code'] / 'scripts/research/glm53_flash/router_caller/successor.py' != Path(__file__):
        raise ValueError('HARNESS_NOT_READY: source entry role')
    if args.operation == 'manifest':
        rows = guard.input_rows(roots)
        environment = guard.parse(guard.read(roots['environment_identity'] / 'environment-manifest.json', 1024**2))
        guard.environment_check(roots['environment'], environment)
        manifest = {'schema': 'flash-successor-inputs-v1', 'source_inputs': rows,
                    'generation': guard.generation(rows),
                    'python_sha256': sha(guard.read(roots['environment'] / 'bin/python')),
                    'system_tools': [{'path': p, 'bytes': len(raw), 'sha256': sha(raw)}
                                     for p in guard.SYSTEM_TOOLS for raw in [guard.read(Path(p))]],
                    'commit_binding': 'materialized source inputs; eventual commit recorded separately'}
        raw = guard.encoded(manifest)
        target = Path(args.output)
        guard.canonical(target.parent)
        with target.open('xb') as out:
            out.write(raw)
        print(json.dumps({'manifest_sha256': sha(raw), 'generation': manifest['generation']}))
        return 0
    context = guard.Context(roots, manifest)
    context.verify()
    run = Path(args.output)
    parent = guard.canonical(run.parent)
    if (parent / 'STOP_NUMERICAL.json').exists():
        raise ValueError('HARNESS_NOT_READY: unresolved stop latch')
    if run != parent / run.name or any(run.is_relative_to(p) or p.is_relative_to(run) for p in roots.values()):
        raise ValueError('HARNESS_NOT_READY: output role overlap')
    run.mkdir()
    stage = run / 'inputs'
    stage.mkdir()
    for row in manifest['source_inputs']:
        if row['path'].startswith('upstream/'):
            p = stage / 'source' / row['path'].removeprefix('upstream/')
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(guard.read(context.resolve_input(row), row['bytes']))
    denied = run / 'denied'
    denied.mkdir()
    (denied / 'read-marker').write_bytes(b'fabricated-denial-marker')
    roots.update(stage=stage, denied=denied, run=run)
    supervisor = load('successor_supervisor', code, manifest)
    ledger = []

    def spawn(name, operation, probe=None, archive_root=None, archive_sha=None):
        context.verify()
        d = run / name
        d.mkdir()
        work = d / 'work'
        work.mkdir()
        child_roots = {**roots, 'work': work}
        if archive_root is not None:
            child_roots['archive'] = archive_root
        fds = []
        try:
            bindings = {}
            for role, path in child_roots.items():
                fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                fds.append(fd)
                bindings[role] = {'fd': fd, **guard.identity(path)}
            request = {'schema': 'flash-successor-request-v1', 'operation': operation,
                       'probe': probe or 'capabilities', 'backend': args.backend,
                       'role_fds': bindings, 'manifest': manifest}
            if archive_sha is not None:
                request['archive_manifest_sha256'] = archive_sha
            rp = d / 'request.json'
            rp.write_bytes(guard.encoded(request))
            reads = [context.resolve_input(row) for row in manifest['source_inputs']]
            reads += [p for p in (stage / 'source').rglob('*') if p.is_file()]
            reads += [rp]
            control = probe == 'fork-cleanup-control'
            profile = supervisor.fence(work, roots['environment'], reads,
                                       read_dirs=([archive_root] if archive_root else []), fork_control=control)
            pf = d / 'fence.sb'
            pf.write_text(profile)
            argv = [str(roots['environment'] / 'bin/python'), '-I', '-B', str(Path(__file__)), '--child', str(rp)]
            prefix = {'schema': 'successor-prefix-v1', 'argv': argv, 'run': name,
                      'source_inputs': manifest['source_inputs'], 'ticket': {'input_digest': manifest['generation']},
                      'request_sha256': sha(guard.read(rp)), 'fence_sha256': sha(profile.encode()),
                      'role_identities': bindings, 'operation': operation, 'backend': args.backend,
                      'runtime_fork_policy': 'PERMITTED_CONTROL_REFUSES_ADMISSION' if control else 'OS_DENIED'}
            (d / 'prefix.json').write_bytes(guard.encoded(prefix))
            ledger.append({'name': name, 'started': True, 'controlled_extra_child_budget': int(control)})
            (run / 'children.json').write_bytes(guard.encoded(ledger))
            stopped = supervisor.capture(['/usr/bin/sandbox-exec', '-f', str(pf), *argv], d, work,
                                         seconds=args.child_seconds, pass_fds=tuple(fds),
                                         stop_latch=run.parent / 'STOP_NUMERICAL.json')
            ledger[-1].update(stop_confirmed=stopped['stop_confirmed'], exit_code=stopped['exit_code'])
            (run / 'children.json').write_bytes(guard.encoded(ledger))
            context.verify()
            return d, prefix, stopped
        finally:
            for fd in fds:
                os.close(fd)

    if args.operation == 'archive-verify':
        archive_root = guard.canonical(Path(args.archive))
        d, _, stop = spawn('archive-readback', 'archive-verify', archive_root=archive_root, archive_sha=args.archive_sha)
        if stop['exit_code'] != 0 or not stop['capture_complete']:
            return 1
        print(guard.read(d / 'stdout.txt').decode('utf-8'), end='')
        return 0
    doctor_records = []
    for probe, expected in [('capabilities', 0), ('native-exit', 23), ('native-signal', -15), ('fork-cleanup-control', 0)]:
        d, prefix, stop = spawn('doctor-' + probe, 'doctor', probe)
        out = guard.read(d / 'stdout.txt')
        err = guard.read(d / 'stderr.txt')
        if (stop['exit_code'] != expected or not stop['capture_complete']
                or b'successor-doctor-stdout' not in out or b'successor-doctor-stderr' not in err):
            raise ValueError('HARNESS_NOT_READY: doctor capture/stop')
        if probe in ('capabilities', 'fork-cleanup-control'):
            result = strict(out.splitlines()[-1])
            if probe == 'capabilities' and result.get('doctor') != 'PASS':
                raise ValueError('HARNESS_NOT_READY: capabilities')
            if probe == 'fork-cleanup-control':
                fork = result['fork']
                if fork['admitted'] or not fork['child_reaped'] or fork['child_exit_code'] != 97:
                    raise ValueError('HARNESS_NOT_READY: fork control')
                try:
                    os.kill(fork['child_pid'], 0)
                except ProcessLookupError:
                    pass
                else:
                    raise ValueError('HARNESS_NOT_READY: continuing fork child')
        doctor_records.append({'probe': probe, 'expected_exit': expected, 'stop': stop})
    (run / 'doctor.json').write_bytes(guard.encoded({'status': 'PASS', 'generation': manifest['generation'], 'records': doctor_records}))
    if args.operation == 'doctor':
        print(json.dumps({'doctor': 'PASS', 'direct_children': len(ledger), 'controlled_extra_children': 1}))
        return 0
    producer, prefix, stop = spawn('producer', args.operation)
    passed = producer_pass(guard.read(producer / 'stdout.txt'), guard.read(producer / 'stderr.txt'), stop, args.operation)
    archive = load('rc_archive', code, manifest)
    receipt = {'schema': 'successor-producer-v1', 'run': 'producer', 'status': 'PASS' if passed else 'FAIL',
               'input_manifest_sha256': manifest['generation'], 'outputs': stop['outputs'],
               'termination': stop, 'prefix_sha256': sha(guard.read(producer / 'prefix.json')),
               'request_sha256': prefix['request_sha256'], 'doctor_sha256': sha(guard.read(run / 'doctor.json')),
               'prefix_protected_sha256': archive.prefix_protected(prefix),
               'prefix_path_sha256': {str(i): sha(prefix['argv'][i].encode()) for i in (0, 3, 5)}}
    (producer / 'receipt.json').write_bytes(guard.encoded(receipt))
    (producer / 'checkpoint.json').write_bytes(guard.encoded({'generation': manifest['generation'], 'files': manifest['source_inputs']}))
    if not passed:
        print(json.dumps({'status': 'FAIL', 'archive': 'NOT_PACKED', 'stop_confirmed': stop['stop_confirmed']}))
        return 1
    packed = archive.pack_successor(context, producer, run / 'archive',
                                    redaction_roots=tuple((str(path), 'role:' + name.replace('_', '-')) for name, path in roots.items()))
    d, _, stop = spawn('archive-readback', 'archive-verify', archive_root=run / 'archive', archive_sha=packed['manifest_sha256'])
    if stop['exit_code'] != 0 or not stop['capture_complete']:
        raise ValueError('ARCHIVE_READBACK_FAILED')
    result = {'status': 'PASS', 'generation': manifest['generation'], 'archive': packed,
              'fresh_readback_stdout_sha256': stop['outputs']['stdout']['sha256'],
              'direct_children': len(ledger), 'controlled_extra_children': 1}
    (run / 'result.json').write_bytes(guard.encoded(result))
    print(json.dumps(result))
    return 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--child':
        return child(Path(sys.argv[2]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('manifest', 'doctor', 'case', 'matrix', 'discrimination', 'convolution', 'cache', 'archive-verify'))
    for name in ('source', 'environment', 'fixtures', 'upstream', 'environment-identity', 'output'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--manifest')
    parser.add_argument('--manifest-sha')
    parser.add_argument('--archive')
    parser.add_argument('--archive-sha')
    parser.add_argument('--backend', choices=('cpu', 'metal'), default='cpu')
    parser.add_argument('--child-seconds', type=float, default=180)
    return public(parser.parse_args())


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        # No raw caller path or arbitrary exception message is promoted to a
        # portable success receipt. The failed local attempt remains retained.
        print(json.dumps({'status': 'HARNESS_NOT_READY_OR_FAILED', 'exception_type': type(exc).__name__,
                          'project_or_numeric_success': False}), file=sys.stderr, flush=True)
        sys.exit(2)
