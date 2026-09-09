"""Explicit successor input roles; no historical guard import or replacement."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys

PREFIX = 'scripts/research/glm53_flash/router_caller/'
CODE_FILES = tuple(PREFIX + n for n in (
    'successor.py', 'successor_guard.py', 'successor_doctor.py',
    'successor_supervisor.py', 'successor_harness.py', 'successor_discrimination.py',
    'successor_discrimination_oracle.py', 'rc_archive.py',
    'rc_guard.py', 'runner.py', 'rc_source.py', 'rc_runtime.py', 'rc_oracle.py', 'rc_checks.py')) + (
    'scripts/research/tests/test_glm53_flash_router_caller_numeric.py',
    'scripts/research/glm53_flash/convolution_state/capsule.py',
    'scripts/research/glm53_flash/convolution_state/source.py',
    'scripts/research/glm53_flash/convolution_state/oracle.py',
    'scripts/research/glm53_flash/convolution_state/controls.py',
    'scripts/research/glm53_flash/convolution_state/provenance.json',
    'fixtures/research/glm53-flash-convolution-state-v1/fixtures.json',
    'scripts/research/glm53_flash/cache_lifecycle/capsule.py',
    'scripts/research/glm53_flash/cache_lifecycle/source.py',
    'scripts/research/glm53_flash/cache_lifecycle/controls.py',
    'scripts/research/glm53_flash/cache_lifecycle/provenance.json',
    'scripts/research/glm53_flash/cache_lifecycle/upstream-cache.txt',
    'fixtures/research/glm53-flash-cache-lifecycle-v1/fixtures.json')
CODE_FILES += (
    'scripts/research/glm53_flash/recurrent_ops/capsule.py',
    'scripts/research/glm53_flash/recurrent_ops/source.py',
    'scripts/research/glm53_flash/recurrent_ops/oracle.py',
    'scripts/research/glm53_flash/recurrent_ops/controls.py',
    'scripts/research/glm53_flash/recurrent_ops/provenance.json',
    'scripts/research/glm53_flash/recurrent_ops/upstream-gated-delta.txt',
    'scripts/research/glm53_flash/recurrent_ops/upstream-language.txt',
    'fixtures/research/glm53-flash-recurrent-ops-v1/fixtures.json',
)
FIXTURE_FILES = ('cases.json', 'controls.json', 'successor-discrimination-v1/fixtures.json')
UPSTREAM_FILES = ('config.json', 'capsules/Glm5NextMoEGate.py', 'capsules/MoEGate.py',
                  'capsules/group_expert_select.py', 'mlx-vlm/LICENSE',
                  'mlx-vlm/mlx_vlm/models/deepseek_v32/language.py', 'pipenetwork/LICENSE',
                  'pipenetwork/glm53_flash_mlx/glm5_next/language.py')
BODY_CAP = 16 * 1024**2
SYSTEM_TOOLS = ('/usr/bin/sandbox-exec', '/bin/ps')


class AdmissionError(ValueError):
    pass


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(path):
    p = Path(path)
    if not p.is_absolute() or p.resolve(strict=True) != p:
        raise AdmissionError('INPUT_ALIAS_OR_MISSING')
    if any(stat.S_ISLNK(x.lstat().st_mode) for x in (p, *p.parents)):
        raise AdmissionError('INPUT_ALIAS')
    return p


def relative(name):
    p = PurePosixPath(name)
    if (type(name) is not str or not name or p.is_absolute() or '..' in p.parts
            or str(p) != name or '\\' in name or '\x00' in name):
        raise AdmissionError('INPUT_ROLE_ESCAPE')
    return name


def confined(root, path):
    root = canonical(root)
    p = canonical(path)
    if not p.is_relative_to(root):
        raise AdmissionError('INPUT_ROLE_ESCAPE')
    return p


def read(path, cap=BODY_CAP):
    p = canonical(path)
    fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        a = os.fstat(fd)
        if not stat.S_ISREG(a.st_mode) or not 0 <= a.st_size <= cap:
            raise AdmissionError('INPUT_SIZE_OR_TYPE')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(cap + 1)
        b = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(raw) != a.st_size or identity(a) != identity(b):
            raise AdmissionError('INPUT_READ_DRIFT')
        return raw
    finally:
        os.close(fd)


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AdmissionError('INPUT_DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def parse(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(AdmissionError('INPUT_NONFINITE_JSON')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AdmissionError('INPUT_JSON') from exc


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def identity(path):
    p = canonical(path)
    s = p.stat()
    return {'dev': s.st_dev, 'ino': s.st_ino, 'path_sha256': sha(str(p).encode())}


def environment_check(root, manifest):
    root = canonical(root)
    expected = {relative(r['path']): r for r in manifest['files']}
    if len(expected) != len(manifest['files']) or len(expected) > 10000:
        raise AdmissionError('ENVIRONMENT_INVENTORY')
    # This census is restricted to the explicitly admitted tiny environment.
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual != set(expected):
        raise AdmissionError('ENVIRONMENT_INVENTORY')
    for name, row in expected.items():
        p = confined(root, root / name)
        h = hashlib.sha256()
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            a = os.fstat(fd)
            if not stat.S_ISREG(a.st_mode) or a.st_size != row['bytes'] or a.st_size > 512 * 1024**2:
                raise AdmissionError('ENVIRONMENT_SIZE')
            count = 0
            with os.fdopen(fd, 'rb', closefd=False) as f:
                while chunk := f.read(min(1024**2, row['bytes'] - count + 1)):
                    count += len(chunk)
                    if count > row['bytes']:
                        raise AdmissionError('ENVIRONMENT_GROWTH')
                    h.update(chunk)
            b = os.fstat(fd)
            if ((a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns, a.st_ctime_ns) !=
                    (b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns, b.st_ctime_ns)
                    or count != row['bytes'] or h.hexdigest() != row['sha256']):
                raise AdmissionError('ENVIRONMENT_DRIFT')
        finally:
            os.close(fd)
    return manifest


def input_rows(roots):
    rows = []
    roles = {'code': CODE_FILES, 'fixtures': FIXTURE_FILES, 'upstream': UPSTREAM_FILES,
             'environment_identity': ('environment-manifest.json', 'wheel-lock.json')}
    for role, names in roles.items():
        for name in names:
            raw = read(confined(roots[role], roots[role] / name))
            rows.append({'path': role + '/' + name, 'bytes': len(raw), 'sha256': sha(raw)})
    return sorted(rows, key=lambda row: row['path'])


def generation(rows):
    return sha(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode())


class Context:
    read = staticmethod(read)
    parse = staticmethod(parse)
    sha = staticmethod(sha)
    def __init__(self, roots, manifest, *, phase=None):
        self.roots = {key: canonical(value) for key, value in roots.items()}
        self.identities = {key: identity(value) for key, value in self.roots.items()}
        self.manifest = manifest
        self.phase = phase
        self.requests = []
        self.trace = False
        self.verified = False

    def resolve_input(self, row):
        role, name = row['path'].split('/', 1)
        relative(name)
        if role not in ('code', 'fixtures', 'upstream', 'environment_identity'):
            raise AdmissionError('INPUT_UNKNOWN_ROLE')
        return confined(self.roots[role], self.roots[role] / name)

    def read_verified(self, path):
        p = canonical(path)
        row = next((r for r in self.manifest['source_inputs'] if self.resolve_input(r) == p), None)
        if row is None:
            raise AdmissionError('UNLISTED_EXECUTABLE_OR_FIXTURE')
        raw = read(p, row['bytes'])
        if len(raw) != row['bytes'] or sha(raw) != row['sha256']:
            raise AdmissionError('INPUT_BOUNDARY_DRIFT')
        return raw

    def verify(self, *, environment=True):
        if any(identity(self.roots[k]) != v for k, v in self.identities.items()):
            raise AdmissionError('ROLE_IDENTITY_DRIFT')
        if self.manifest.get('schema') != 'flash-successor-inputs-v1':
            raise AdmissionError('INPUT_MANIFEST_SCHEMA')
        observed_tools = [{'path': p, 'bytes': len(raw), 'sha256': sha(raw)}
                          for p in SYSTEM_TOOLS for raw in [read(Path(p))]]
        if observed_tools != self.manifest['system_tools']:
            raise AdmissionError('SYSTEM_TOOL_IDENTITY_DRIFT')
        rows = input_rows(self.roots)
        if rows != self.manifest['source_inputs'] or generation(rows) != self.manifest['generation']:
            raise AdmissionError('INPUT_IDENTITY_DRIFT')
        m = parse(read(self.roots['environment_identity'] / 'environment-manifest.json', 1024**2))
        if sha(read(self.roots['environment_identity'] / 'wheel-lock.json')) != m['wheel_lock_sha256']:
            raise AdmissionError('ENVIRONMENT_LOCK_DRIFT')
        if environment:
            environment_check(self.roots['environment'], m)
        self.verified = True
        return m

    def verify_child_interpreter(self, phase):
        if (phase != self.phase or not sys.flags.isolated or not sys.dont_write_bytecode
                or Path(sys.prefix) != self.roots['environment'] or sys.prefix == sys.base_prefix
                or sha(read(Path(sys.executable))) != self.manifest['python_sha256']):
            raise AdmissionError('CHILD_INTERPRETER_IDENTITY')

    def verify_environment(self, phase):
        self.verify_child_interpreter(phase)
        return self.verify()

    def verify_origin(self, module, phase, manifest):
        self.verify_child_interpreter(phase)
        p = confined(self.roots['environment'], Path(module.__file__))
        rel = p.relative_to(self.roots['environment']).as_posix()
        row = next((r for r in manifest['files'] if r['path'] == rel), None)
        if row is None or sha(read(p)) != row['sha256']:
            raise AdmissionError('LIBRARY_ORIGIN_DRIFT')
        return {'module': module.__name__, 'role_path': rel, 'sha256': row['sha256']}

    def confined(self, root, path):
        if Path(root) != self.phase:
            raise AdmissionError('SOURCE_PHASE_ROLE')
        return confined(root, path)
