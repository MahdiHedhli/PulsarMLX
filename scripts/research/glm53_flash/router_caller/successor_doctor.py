"""Source-free capability probes for the bounded successor entrypoint.

Only the capabilities operation imports the previously admitted libraries.
The controlled fork operation is separate from the restricted runtime fence.
"""
import errno
import json
import os
from pathlib import Path
import resource
import signal
import stat
import sys
import tempfile
import time


def fork_probe():
    """A permitted fork always fails admission, after exact-child cleanup."""
    try:
        child = os.fork()
    except OSError as exc:
        if exc.errno not in (errno.EPERM, errno.EACCES):
            raise
        return {'admitted': True, 'denied': True, 'errno': exc.errno, 'extra_children': 0}
    if child == 0:
        os._exit(97)
    deadline = time.monotonic() + 1.0
    killed = False
    while True:
        got, status = os.waitpid(child, os.WNOHANG)
        if got == child:
            break
        if time.monotonic() >= deadline:
            os.kill(child, signal.SIGKILL)
            killed = True
            got, status = os.waitpid(child, 0)
            break
        time.sleep(.01)
    if got != child:
        raise RuntimeError('HARNESS_NOT_READY: exact fork child was not reaped')
    return {'admitted': False, 'denied': False, 'extra_children': 1,
            'child_pid': child, 'child_reaped': True, 'killed': killed,
            'child_exit_code': os.waitstatus_to_exitcode(status)}


def probe(mode, work, denied):
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    print('successor-doctor-stdout', flush=True)
    print('successor-doctor-stderr', file=sys.stderr, flush=True)
    if mode == 'native-exit':
        return 23
    if mode == 'native-signal':
        os.kill(os.getpid(), signal.SIGTERM)
        raise AssertionError('signal did not terminate child')
    if mode == 'fork-cleanup-control':
        parent = os.getpid()
        result = fork_probe()
        if os.getpid() != parent:
            (work / 'unexpected-continuing-child').write_text('FAILED')
            os._exit(98)
        assert result['admitted'] is False and result['child_reaped'] is True
        assert result['child_exit_code'] == 97 and not result['killed']
        assert not (work / 'unexpected-continuing-child').exists()
        print(json.dumps({'doctor_control': 'PASS', 'fork': result,
                          'admission': 'HARNESS_NOT_READY_EXPECTED_FOR_PERMITTED_FORK'}), flush=True)
        return 0
    if mode != 'capabilities':
        raise ValueError('unknown source-free doctor operation')
    import socket
    checks = {}
    for name, operation in [
        ('read', lambda: denied.read_bytes()),
        ('write', lambda: denied.with_name('forbidden-write').write_bytes(b'forbidden')),
        ('network', lambda: socket.create_connection(('127.0.0.1', 9), timeout=1)),
    ]:
        try:
            operation()
        except OSError as exc:
            if exc.errno not in (errno.EPERM, errno.EACCES):
                raise
            checks[name] = {'denied': True, 'errno': exc.errno}
        else:
            raise RuntimeError('HARNESS_NOT_READY: required ' + name + ' denial absent')
    checks['fork'] = fork_probe()
    if not checks['fork']['admitted']:
        print(json.dumps({'doctor': 'HARNESS_NOT_READY', 'checks': checks}), flush=True)
        return 2
    canonical = work / 'canonical-parent'
    canonical.mkdir()
    alias = work / 'alias-parent'
    alias.symlink_to(canonical, target_is_directory=True)
    for name, parent in [('canonical', canonical), ('alias', alias)]:
        with tempfile.TemporaryDirectory(prefix='doctor-', dir=parent.resolve(strict=True)) as tmp:
            root = Path(tmp)
            assert root.is_dir() and root.resolve(strict=True) == root
            assert all(not stat.S_ISLNK(p.lstat().st_mode) for p in (root, *root.parents))
            marker = root / 'answer'
            marker.write_bytes(b'known-answer-42')
            assert marker.read_bytes() == b'known-answer-42'
        checks[name] = {'canonical_allocation': True, 'read_write': True}
    import numpy as np
    import jinja2
    import markupsafe
    import mlx.core as mx
    import mlx.nn as nn
    mx.set_memory_limit(512 * 1024**2)
    mx.set_cache_limit(16 * 1024**2)
    assert np.array([2, 3]).sum() == 5
    assert jinja2.Template('{{ a }}').render(a=7) == '7'
    for name, device in [('cpu', mx.cpu), ('metal', mx.gpu)]:
        with mx.stream(device):
            a = mx.array([2.0, 3.0])
            b = mx.compile(lambda x: x + x)(a)
            mx.eval(b)
            assert b.tolist() == [4.0, 6.0]
        checks[name] = {'compiled_addition': [4.0, 6.0]}
    print(json.dumps({'doctor': 'PASS', 'checks': checks, 'python': sys.version,
                      'numpy': np.__version__, 'mlx': mx.__version__,
                      'project_imports': 0, 'core_limit': resource.getrlimit(resource.RLIMIT_CORE)}), flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(probe(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])))
