"""Source-free, bounded process capture. No project or numeric imports."""
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import time

CAPTURE_CAP = 16 * 1024**2


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def fence(work, environment, read_files=(), read_dirs=(), *, fork_control=False):
    """The separate fork control is never a numerical admission profile."""
    lines = ['(version 1)', '(allow default)', '(deny network*)',
             '(deny file-read*)', '(deny file-write*)', '(allow file-read-metadata)']
    if not fork_control:
        lines.append('(deny process-fork)')
    for p in ['/System', '/usr/lib', '/usr/share',
              '/opt/homebrew/Cellar/python@3.14', '/opt/homebrew/opt/python@3.14',
              '/opt/homebrew/lib', '/private/var/db/dyld', str(environment), str(work),
              *map(str, read_dirs)]:
        lines.append('(allow file-read* (subpath ' + json.dumps(p) + '))')
    for p in ['/', '/dev/null', '/dev/random', '/dev/urandom',
              '/private/etc/localtime', '/usr/bin/sandbox-exec', '/bin/ps', *map(str, read_files)]:
        lines.append('(allow file-read* (literal ' + json.dumps(p) + '))')
    lines.extend(['(allow file-write* (subpath ' + json.dumps(str(work)) + '))',
                  '(allow file-write* (literal "/dev/null"))'])
    return '\n'.join(lines) + '\n'


def group_exists(pid):
    try:
        os.killpg(pid, 0)
        return True
    except ProcessLookupError:
        return False


def capture(argv, run, work, *, seconds=180, capture_cap=CAPTURE_CAP, pass_fds=(), stop_latch=None):
    """Own and reap the exact process group; incomplete capture cannot pass."""
    if not 0 < seconds <= 180 or not 0 < capture_cap <= CAPTURE_CAP:
        raise ValueError('invalid child limit')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    for name in ('tmp', 'cache'):
        (work / name).mkdir(exist_ok=True)
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'USER', 'LOGNAME', 'SHELL') if k in os.environ}
    env.update(TMPDIR=str(work / 'tmp') + '/', XDG_CACHE_HOME=str(work / 'cache'),
               PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
               PYTHONHASHSEED='0', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    start = time.monotonic()
    reason = None
    total = 0
    monitor_children = 0
    peak = 0
    next_rss = start
    streams = {name: (run / (name + '.txt')).open('xb') for name in ('stdout', 'stderr')}
    proc = None
    failure = None
    cleanup_errors = []
    group_absent = proc is None
    old_term = signal.getsignal(signal.SIGTERM)
    def interrupted(signum, frame):
        raise InterruptedError('supervisor termination requested')
    signal.signal(signal.SIGTERM, interrupted)
    try:
        proc = subprocess.Popen(argv, cwd=work, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, start_new_session=True, pass_fds=pass_fds)
        (run / 'started.json').write_text(json.dumps({'pid': proc.pid, 'process_group': proc.pid,
                                                     'started_monotonic': time.monotonic()}) + '\n')
        with selectors.DefaultSelector() as selector:
            for name in streams:
                pipe = getattr(proc, name)
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, name)
            while selector.get_map() or proc.poll() is None:
                now = time.monotonic()
                if now - start > seconds:
                    reason = 'DEADLINE'
                if proc.poll() is None and now >= next_rss:
                    monitor_children += 1
                    sampled = subprocess.run(['/bin/ps', '-o', 'rss=', '-p', str(proc.pid)],
                                             capture_output=True, timeout=2, check=False)
                    if sampled.stdout.strip().isdigit():
                        peak = max(peak, int(sampled.stdout.strip()) * 1024)
                    elif proc.poll() is None:
                        reason = 'RSS_SAMPLE_UNAVAILABLE'
                    next_rss = now + .25
                    if peak > 1024**3:
                        reason = 'DIRECT_RSS_LIMIT'
                if reason:
                    break
                for key, _ in selector.select(.05):
                    chunk = os.read(key.fileobj.fileno(), min(65536, capture_cap - total + 1))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    available = capture_cap - total
                    streams[key.data].write(chunk[:available])
                    total += min(len(chunk), available)
                    if len(chunk) > available:
                        reason = 'CAPTURE_LIMIT'
                        break
                if reason:
                    break
    except BaseException as exc:
        reason = 'SUPERVISOR_FAILURE'
        failure = type(exc).__name__
    finally:
        if proc is not None:
            # Also clean descendants on a natural direct-child exit.
            try:
                if group_exists(proc.pid):
                    os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError as exc:
                cleanup_errors.append({'operation': 'group_signal', 'errno': exc.errno})
                try:
                    proc.kill()
                except OSError as direct:
                    cleanup_errors.append({'operation': 'direct_signal', 'errno': direct.errno})
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                reason = 'STOP_UNCONFIRMED'
            for pipe in (proc.stdout, proc.stderr):
                pipe.close()
            try:
                group_absent = not group_exists(proc.pid)
            except OSError as exc:
                group_absent = False
                cleanup_errors.append({'operation': 'group_observation', 'errno': exc.errno})
        for stream in streams.values():
            stream.close()
        signal.signal(signal.SIGTERM, old_term)
    stopped = proc is None or (proc.poll() is not None and group_absent)
    if cleanup_errors:
        reason = 'STOP_UNCONFIRMED' if not stopped else 'CLEANUP_ERROR'
    record = {'schema': 'successor-stop-v1', 'pid': proc.pid if proc else None, 'exit_code': proc.returncode if proc else None,
              'reason': reason, 'failure_type': failure, 'child_started': proc is not None,
              'stop_confirmed': stopped, 'direct_child_reaped': proc is not None and proc.poll() is not None,
              'process_group_absent': group_absent, 'capture_complete': reason is None,
              'cleanup_errors': cleanup_errors,
              'elapsed_seconds': time.monotonic() - start, 'capture_cap_bytes': capture_cap,
              'peak_direct_rss_bytes': peak, 'rss_monitor_children': monitor_children,
              'outputs': {n: {'bytes': (run / (n + '.txt')).stat().st_size,
                              'sha256': digest(run / (n + '.txt'))} for n in streams}}
    (run / 'stop.json').write_text(json.dumps(record, indent=2) + '\n')
    if not stopped:
        if stop_latch is not None:
            Path(stop_latch).write_text(json.dumps({'status': 'STOP_UNCONFIRMED', 'pid': proc.pid}) + '\n')
        raise RuntimeError('HARNESS_NOT_READY: unknown stop; no subsequent child permitted')
    if failure is not None:
        raise RuntimeError('HARNESS_NOT_READY: supervised failure after cleanup')
    return record
