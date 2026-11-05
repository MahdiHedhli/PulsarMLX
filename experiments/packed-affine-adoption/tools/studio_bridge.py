"""Explicit source loading, process confinement and saved CI prerequisite checks.

No physical-host admission or numerical execution occurs at import time.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import zlib

C = 'f61a8c19d6aad2265a12f417ddbe842024fe32f2'
CT = '5f8a8c55f4e0067b10dcd6606fe05935e8e47659'
Q = '14ac1c7e1ffaf8c25b160bcca7cdbe9abf57cd41'
QT = 'b611e3dd7f40947b8409ca574d5f6ccdcd67ee02'
H = '8a21f17bdea7b9d04f7ac54b070fa0a4f12762a2'
HT = 'f08812602debc2fce192e2035339844c6c284ef0'
CONTRACT = '7d28d6a427606dd622d3e00d362757365b51990972be8a4e7ee17131d5297d2d'
IMPLEMENTATION_PROMPT = '9aea22c7b7008ac34d90eeca0f8a4c196e6f08f619e067cbc083b056a72b2295'
EXP = 'experiments/packed-affine-adoption/'
COUNTS = {'rust_invocations': 52, 'exact_projections': 84, 'rust_checks': 76, 'rust_deferrals': 8, 'self_checks': 76}
FULL = {'full-positive-A-gate', 'full-positive-A-up', 'full-positive-B-gate', 'full-positive-B-up'}
CI_FILES = {
    'response': (5399, '8a340ea7a26c78f3af6199491d54f92cb4254a663567edddfd48468ddd544ab3'),
    'handoff': (390256, 'b186213e14188a3b6d42166b52acd97ee2ca7e4c6cdb2e8df0ad6f0cd4b02076'),
    'supplement': (799510, 'ccf08f1e7c18e34566c3b80d7347d1c1f99497b48c36038234c61dfb89eb8c1f'),
}
PUBLIC = (6425177, 'c79d6a12493adcffc72df0b450b2a0140c10425854e44f4bd720230e39c21273')
ORIGINAL = (6425327, '1507dac4e9a861ff32d0b5c1c0c0b41bea4ed58e8afc432a4b5540f9a5b80d3c')
PINS = {
    'report_checks': ('C', EXP+'tools/report_checks.py', 'e73a515555d639b29c49bf7559a2a9a6e88b6ff54bf0203b822ab4113b597624'),
    'freeze_host': ('C', EXP+'tools/freeze_host.py', 'ca5146fb46ab3e4328ae0754ea3b21a0cee15011fe6c51f2f2c00c96518a0e25'),
    'copied_diagnostic': ('C', EXP+'tools/copied_diagnostic.py', '14ed17730621e475b4851aa3513367b08ee8226609efcc95f88af84d4647320e'),
    'm1a_continuation': ('C', EXP+'tools/m1a_continuation.py', '3ccf57039df11f88851e4b96897e66feb399b76788274dc73ae997ccdd93c9fe'),
    'reference_budget': ('C', EXP+'tools/reference_budget.py', 'cedbbe26c8f813aa165d567354fb9628e870a6a66f7504dec5aedb6c398543a6'),
    'f020_expert_mlp_r1_v1': ('C', 'scripts/research/f020_expert_mlp_r1_v1.py', '3aad179cda4d4fe054d4a4b52fd3ef4911956559ac2cdad131b435bb03d81f01'),
    'f020_selected_r1_v2': ('C', 'scripts/research/f020_selected_r1_v2.py', '1d7276286f400ae2026c32b996c1269b9947abad95f60e33f255f89f1541a913'),
    'mlx_affine_qmm_reference_v1': ('C', 'scripts/research/mlx_affine_qmm_reference_v1.py', 'b9ef145e2bdce533aa733b70866d39364e2e61ee4642746b650e705f8a40ef15'),
    'exact_gates_v1': ('C', 'crates/mlx-native-affine/acceptance/exact_gates_v1.py', '23b6c46e1d2e986d5027c0eea9d902c88a54f623a07d6ab42264fc410f23e887'),
    'reference': ('C', EXP+'tools/reference.py', '6292af372218bfa1969736f393ac829fce65accde3e139b8f67cd2a0fcd90983'),
    'retained_rational': ('Q', EXP+'tools/retained_rational.py', '5bca96ddef887773ef77fc4d47965af0763c877f4a2c94f9902022056a6a947c'),
    'retained_admission': ('Q', EXP+'tools/retained_admission.py', '38d036885817177c024b3d00f1a97a4b0f9340f5fceb9b613a9ce3d6339e1e7f'),
    'retained_qualify': ('Q', EXP+'tools/retained_qualify.py', 'f14d54ece7e33da1d8144736d190e51d369e02e036332127af1f7be0a30eb98e'),
}
_loaded = {}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()


def equal(a, b, message):
    require(canonical(a) == canonical(b), message)


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def bounded(path, limit=8*1024*1024):
    with Path(path).open('rb') as f:
        raw = f.read(limit+1)
    require(len(raw) <= limit, 'bounded input exceeded: '+str(path))
    return raw


def parse(raw):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            require(k not in result, 'duplicate JSON key')
            result[k] = v
        return result
    def nonfinite(_):
        raise ValueError('nonfinite JSON token')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)


def read(path):
    return parse(bounded(path))


def create(path, value):
    with Path(path).open('xb') as f:
        f.write(canonical(value)); f.flush(); os.fsync(f.fileno())


def exact_file(path, identity):
    raw = bounded(path, identity[0])
    equal([len(raw), hashlib.sha256(raw).hexdigest()], list(identity), 'exact file identity: '+str(path))
    return raw


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], timeout=45).decode().strip()


def inventory(root, commit):
    raw = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-rz', '--full-tree', commit], timeout=45)
    result = {}
    for entry in raw.split(b'\0'):
        if not entry:
            continue
        meta, name = entry.split(b'\t', 1); mode, kind, blob = meta.decode().split()
        require(kind == 'blob' and mode in ('100644', '100755', '120000'), 'unsupported tracked type')
        name = name.decode(); path = root/name; info = path.lstat()
        if mode == '120000':
            require(stat.S_ISLNK(info.st_mode), 'tracked symlink type changed')
            data = os.readlink(path).encode()
        else:
            require(stat.S_ISREG(info.st_mode) and bool(info.st_mode & 0o111) == (mode == '100755'), 'tracked file mode/type changed')
            data = path.read_bytes()
        equal(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest(), blob, 'tracked source bytes changed: '+name)
        result[name] = {'mode': mode, 'blob': blob, 'sha256': hashlib.sha256(data).hexdigest()}
    return result


def source_identity(roots, r_pin):
    require(len(set(roots.values())) == 3, 'separate C/Q/R roots required')
    records = {}; inventories = {}
    for role, pin in {'C': {'commit': C, 'tree': CT}, 'Q': {'commit': Q, 'tree': QT}, 'R': r_pin}.items():
        root = roots[role]
        equal([git(root, 'rev-parse', 'HEAD'), git(root, 'rev-parse', 'HEAD^{tree}')], [pin['commit'], pin['tree']], role+' checkout identity')
        equal(git(root, 'status', '--porcelain=v1', '--untracked-files=all'), '', role+' source drift')
        inventories[role] = inventory(root, pin['commit'])
        records[role] = {**pin, 'root': str(root)}
    equal(len(inventories['C']), 5085, 'C tracked population')
    equal(len(inventories['Q']), 5090, 'Q tracked population')
    for parent, child in [('C', 'Q'), ('Q', 'R')]:
        for name, row in inventories[parent].items():
            equal(inventories[child].get(name), row, 'protected source changed: '+name)
    equal(git(roots['R'], 'merge-base', Q, r_pin['commit']), Q, 'R must descend from Q')
    delta = {p: v for p, v in inventories['R'].items() if p not in inventories['Q']}
    require(delta and all(p.startswith(EXP) and (p.endswith('.py') or p.endswith('.md')) for p in delta), 'R additive host scope')
    require(Path(__file__).resolve() == roots['R']/EXP/'tools/studio_bridge.py', 'R actual module origin')
    return {'roles': records, 'delta': delta, 'protected_C_files': 5085, 'protected_Q_files': 5}


def load_modules(roots):
    sys.dont_write_bytecode = True
    # Explicitly load dependencies in topological order. Never search R or cwd
    # for a C/Q module, and never adopt an already loaded foreign module.
    for name, (role, relative, digest) in PINS.items():
        path = roots[role]/relative
        require(path.resolve(strict=True) == path and sha(path) == digest, 'helper identity: '+name)
        if name in sys.modules:
            require(_loaded.get(name) is sys.modules[name], 'preloaded/shadow module: '+name)
        else:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except BaseException:
                sys.modules.pop(name, None)
                raise
            _loaded[name] = module
    origins = {}
    for name, (role, relative, digest) in PINS.items():
        module = sys.modules[name]; path = roots[role]/relative
        require(Path(module.__file__).resolve() == path and sha(path) == digest, 'module origin drift: '+name)
        origins[name] = {'role': role, 'path': str(path), 'sha256': digest}
    for name in ('m1a_continuation', 'copied_diagnostic', 'freeze_host', 'reference'):
        equal(str(sys.modules[name].REPO), str(roots['C']), 'derived C REPO: '+name)
    return {n: sys.modules[n] for n in PINS}, origins


class Guard:
    """Read-only C introspection plus one exact CPU argv per admitted launch."""
    def __init__(self, roots):
        self.roots = set(map(str, roots.values()))
        self.git = str(Path(shutil.which('git')).resolve(strict=True))
        self.git_hash = sha(self.git)
        self.link_paths = set()
        self.child = None

    def check(self, event, args):
        if event.startswith(('ctypes.dlopen', 'socket.')) or event in ('os.system', 'os.posix_spawn', 'os.exec', 'os.spawn'):
            raise ValueError('native load/network/alternate launch forbidden')
        if event == 'import' and str(args[0]).split('.')[0] in ('mlx', 'torch', 'tensorflow'):
            raise ValueError('MLX/model import forbidden')
        if event != 'subprocess.Popen':
            return
        exe, argv, cwd, env = args
        require(isinstance(argv, (list, tuple)) and all(isinstance(a, str) for a in argv), 'shell/argv forbidden')
        argv = list(argv)
        require(env is None, 'child environment substitution forbidden')
        if self.child is not None and list(argv) == self.child['argv'] and exe == argv[0]:
            equal(sha(exe), self.child['sha256'], 'grader changed before spawn')
            return
        if exe == '/usr/bin/otool':
            require(len(argv) == 3 and argv[:2] == ['/usr/bin/otool', '-L'] and str(Path(argv[2]).resolve()) in self.link_paths, 'otool inspection target')
            return
        if exe == '/usr/sbin/sysctl':
            require(argv[:2] == ['/usr/sbin/sysctl', '-n'] and len(argv) == 3 and argv[2] in ('machdep.cpu.brand_string', 'hw.model', 'hw.memsize', 'hw.pagesize'), 'sysctl read-only allowlist')
            return
        if exe == '/usr/bin/sw_vers':
            require(len(argv) == 2 and argv[1] in ('-productVersion', '-buildVersion'), 'OS observation allowlist')
            return
        require(exe == 'git' and sha(self.git) == self.git_hash and str(Path(shutil.which('git')).resolve()) == self.git, 'unapproved executable')
        tail = list(argv[1:]); root = str(Path(cwd).resolve()) if cwd else None
        if tail[:1] == ['-C']:
            require(len(tail) >= 3, 'git root required'); root = str(Path(tail[1]).resolve()); tail = tail[2:]
        require(root in self.roots, 'git outside admitted source')
        require(bool(tail), 'git command required')
        command, rest = tail[0], tail[1:]
        fixed = {'status': [('--porcelain',), ('--porcelain=v1', '--untracked-files=all')],
                 'rev-parse': [('HEAD',), ('HEAD^{tree}',)]}
        if command in fixed and tuple(rest) in fixed[command]:
            return
        revision = r'[0-9a-f]{40}(?:\^\{tree\})?'
        if command == 'rev-parse' and len(rest) == 1 and re.fullmatch(revision, rest[0]):
            return
        if command == 'ls-tree' and len(rest) == 3 and rest[:2] == ['-rz', '--full-tree'] and re.fullmatch(r'[0-9a-f]{40}', rest[2]):
            return
        if command == 'merge-base' and len(rest) in (2, 3):
            if rest[:1] == ['--is-ancestor']:
                rest = rest[1:]
            if len(rest) == 2 and all(re.fullmatch(r'[0-9a-f]{40}', v) for v in rest):
                return
        if command == 'diff' and len(rest) == 3 and rest[0] == '--name-only' and all(re.fullmatch(r'[0-9a-f]{40}', v) for v in rest[1:]):
            return
        if command == 'ls-files' and rest == [EXP]:
            return
        if command == 'cat-file' and rest[:1] == ['-e']:
            rest = rest[1:]; command = 'show'
        if command == 'show' and len(rest) == 1 and re.fullmatch(r'[0-9a-f]{40}:[A-Za-z0-9_./-]+', rest[0]) and '..' not in rest[0].split(':', 1)[1].split('/'):
            return
        raise ValueError('git command outside read-only allowlist')


def gate_counts(rows, expected):
    equal([r['label'] for r in rows], list(expected), '52 report order/coverage')
    counts = dict.fromkeys(COUNTS, 0)
    for row in rows:
        ids = expected[row['label']][0]
        equal([g['id'] for g in row['exact_gates']], ids, 'exact case sequence')
        equal([g['id'] for g in row['rust_cases']], ids, 'Rust case sequence')
        counts['rust_invocations'] += 1
        for exact, rust in zip(row['exact_gates'], row['rust_cases'], strict=True):
            g = exact['gates']; full = exact['id'] in FULL
            equal(sorted(g), ['G-QMM-EXACT', 'G-R1-SELF-QMM'], 'required mathematical gates')
            equal(g['G-QMM-EXACT']['pass'], True, 'exact gate failed')
            counts['exact_projections'] += 1
            if full:
                equal(rust, {'id': exact['id'], 'gate': 'selected exact original-input R1 required separately', 'rust': None}, 'full-K Rust deferral')
                equal(g['G-R1-SELF-QMM'], None, 'full-K self deferral')
                counts['rust_deferrals'] += 1
            else:
                equal(rust['G-QMM-RUST'], 'PASS', 'Rust gate failed')
                require(rust['rust'] is not None, 'missing Rust reference')
                equal(g['G-R1-SELF-QMM']['pass'], True, 'self gate failed')
                counts['rust_checks'] += 1; counts['self_checks'] += 1
    equal(counts, COUNTS, 'complete numerical counts')
    return counts


def ci_prerequisite(paths, expected):
    raw = {k: exact_file(paths[k], pin) for k, pin in CI_FILES.items()}
    sidecar = bounded(paths['response_checksum'], 512).decode().split()
    require(len(sidecar) == 2 and sidecar[0] == CI_FILES['response'][1], 'response checksum')
    z = zlib.decompressobj(31); decoded = z.decompress(raw['supplement'], PUBLIC[0]+1)
    require(z.eof and not z.unused_data and not z.unconsumed_tail, 'bounded single gzip stream')
    equal([len(decoded), hashlib.sha256(decoded).hexdigest()], list(PUBLIC), 'decoded publication identity')
    result = parse(decoded); handoff = parse(raw['handoff'])
    equal(result['schema'], 'pulsarmlx.retained-numerical-requalification/1', 'CI supplement schema')
    equal(result['verdict'], 'PASS', 'completed CI numerical prerequisite')
    equal(result['failure'], None, 'CI result failure')
    for key, value in {'legacy_m1a_acceptance_created': False, 'Studio_released': False, 'M1b_released': False,
                       'new_native_executions': 0, 'raw_calls': 0, 'shipping_default': 'copied'}.items():
        equal(result[key], value, 'CI prerequisite release boundary: '+key)
    equal([result['Q']['commit'], result['Q']['tree']], [Q, QT], 'CI rational source')
    equal(result['native_execution'], {'C': C, 'C_tree': CT, 'H': H, 'H_tree': HT, 'run': 41933197121, 'attempt': 1, 'CI_conclusion': 'failure'}, 'original CI execution')
    counts = gate_counts(result['reports'], expected)
    equal(result['counts'], {k: v for k, v in counts.items() if k != 'self_checks'}, 'declared CI counts')
    summaries = []
    for row in result['reports']:
        summaries.append({k: row[k] for k in ('label', 'report_sha256', 'rust_gates_sha256', 'exact_gates')} | {
            'rust_gates': [{'id': c['id'], 'G-QMM-RUST': c.get('G-QMM-RUST'),
                            'deferral': c.get('gate'), 'rust_reference_present': c['rust'] is not None}
                           for c in row['rust_cases']]})
    equal(handoff['result']['gates'], summaries, 'handoff/supplement gate binding')
    admission = result['admission']; manifests = {r['path']: r for r in admission['manifest']}
    equal(len(manifests), 586, 'CI manifest population')
    equal(len(admission['unavailable_original_controls']), 124, 'publication control distinction')
    equal(admission['original_attempts'], 17, 'historical attempts')
    equal(admission['native_executable_bytes_available'], False, 'unavailable native bytes')
    equal(admission['historical_CI_conclusion'], 'failure', 'historical CI failure preserved')
    equal([admission['C'], admission['C_tree'], admission['H'], admission['H_tree'], admission['run'], admission['run_attempt']], [C, CT, H, HT, 41933197121, 1], 'admission source/run bindings')
    equal([admission['artifact_id'], admission['archive_sha256'], admission['public_manifest_sha256']], [13375695310, 'ce6cb205f07c1e759adb39499457e6c21fd9285bce6ff1f341ff00b8b05b609f', '3bd3581767b34e010b10291c5a118fe0726582420b958d79bcad77fcf9f0ad19'], 'artifact chain')
    equal([r['label'] for r in admission['reports']], list(expected), 'admitted report order')
    for gate, report in zip(result['reports'], admission['reports'], strict=True):
        row = manifests[report['path']]
        equal([row['changed'], row['original_sha256'], row['public_sha256']], [False, gate['report_sha256'], gate['report_sha256']], 'original report binding')
    projection_ids = []
    for row in admission['projections']:
        manifest = manifests[row['path']]
        equal([manifest['changed'], manifest['original_sha256'], manifest['public_sha256']], [False, row['sha256'], row['sha256']], 'original output binding')
        projection_ids.append((row['report'], row['id'], row['arm']))
    equal(projection_ids, [('campaign/m1a/'+label+'/run.json', cid, arm) for label, (ids, arm, _) in expected.items() for cid in ids], '84 exact projection bindings')
    original_verified = False
    if paths.get('original_supplement'):
        original = parse(exact_file(paths['original_supplement'], ORIGINAL))
        equal(original['reports'], result['reports'], 'original/public numerical decisions')
        original_verified = True
    return {'ci_prerequisite_kind': 'RETAINED_C_MECHANISM_PLUS_Q_NUMERICS', 'ci_workflow_conclusion': 'failure',
            'publication_commit': 'bc38ce3d7d5aa140f82b8da097689ffa232fae0f', 'file_identities': CI_FILES,
            'decoded_publication': PUBLIC, 'original_identity': ORIGINAL, 'original_local_verified': original_verified,
            'native_execution': result['native_execution'], 'artifact_id': admission['artifact_id'],
            'archive_sha256': admission['archive_sha256'], 'public_manifest_sha256': admission['public_manifest_sha256'],
            'counts': counts, 'original_attempts': 17, 'original_reports': 52, 'original_projections': 84,
            'managed_callbacks': 26, 'unavailable_original_controls': 124,
            'native_executable_bytes_available': False, 'limits': admission['limits'],
            'legacy_acceptance_created': False, 'Studio_released': False, 'M1b_released': False}
