#!/usr/bin/env python3
"""Receipt-bound full M1a continuation. No native imports or native launches.

The existing Rust parent owns every child/watchdog. This module admits its
create-only claims and validates the same bindings again during qualification.
Historical Studio observations never become current-binary observations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import select
import stat
import subprocess
import sys
import time

from copied_diagnostic import canonical, checked, create, sha, linkage, validate_originals
from report_checks import CONTRACT, confined, expected_population, admit_raw
import freeze_host

REPO = Path(__file__).resolve().parents[3]
EXP = 'experiments/packed-affine-adoption/'
BASE = '15c09d4377fcb95c35f7eb0aabf736b1d78e68c6'
BASE_TREE = '0883e91b6c2fef718d460668a38a17137a6fc883'
SCHEMA = 'pulsarmlx.m1a-continuation/1'
CAMPAIGN = 'f020-packed-affine-adoption-m1-v1'
AUTHORITY = {
    'M0_sha256': CONTRACT,
    'contract_sha256': 'eb96edd30be70ecf1b06ed3506ed964f7ffe24b7bf234b09664930f256155033',
    'prompt_commit': '9d8f1a3663b0ae40aff8ab42c2cd28a52f150052',
    'prompt_sha256': 'c7a99cf33d98ee9dfe0aa87d62c13b17e9446f3cddb1a060642ec09f6c44cf4d',
}
CI = 'CI_FRESH_ONCE'
STUDIO = 'STUDIO_RETAINED_OBSERVATION'
BRANCH = 'codex/rust-expert-streaming-m0-m1'
PINS = {'mlx': '68cf2fddd8de5edd8ab3d926391772b2e2cedad8',
        'mlx-c': '0726ca922fc902c4c61ef9c27d94132be418e945'}
PATCHES = {
    '1e3c24ffebfdfbeecca054c51637fc4381d98aab': '24831d5bc44b72a0fd027572a4e4eaf754ed9805ffed86185bb8dbdfb6284818',
    '782d4712862b247a094086419ce130fd82cf3c53': '4469b3ec2836efeadce98a192ae26f423cdbbd182edcd2126f4a6ef36891ce58',
    '89d3454ac3f46ff68668dd9f7817c6d47650e47c': '411749fd1908fdee783c3b378471603606852ce3a0ee0011ca5b66f47187b9d3',
    'fba4470b89073180056c9ea46c443051375f7399': '5102eafc68ea94cbe8cabb4acaa9905e17d1c92cb6a1b8c7f0f73dc863c09609',
}
FIXED_INPUTS = {'fixture_manifest_sha256': '513b8c800be7f1f491d0bfa08748123066e6ef9369cc907e0a2d8475e733e597',
                'portable_report_sha256': '26ae22fdf4d90bd7490e10e2abd96d9b16e295e6fd40e8fde7d91c03908e9d45',
                'reference_sha256': 'c27a9d51f7e2dee014749078ede961659a81ebe926bff644bfe62b9de058e191'}
MUTABLE = {EXP+p for p in ('tests/adoption_parent.rs', 'tools/freeze_host.py',
                         'tools/report_checks.py', 'tools/qualify_reports.py')}


def read(path):
    limit = 8*1024*1024
    with Path(path).open('rb') as stream:
        raw = stream.read(limit+1)
    if len(raw) > limit:
        raise ValueError('receipt size bound')
    return json.loads(raw)


def equal(actual, expected, reason):
    if canonical(actual) != canonical(expected):
        raise ValueError(reason)


def git(*args, root=REPO):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def source_inventory(commit, tree):
    equal([git('rev-parse', 'HEAD'), git('rev-parse', 'HEAD^{tree}')], [commit, tree], 'C identity')
    if git('status', '--porcelain=v1', '--untracked-files=all'):
        raise ValueError('source drift; preserve newer work')
    equal(git('rev-parse', BASE+'^{tree}'), BASE_TREE, 'base identity')
    subprocess.run(['git', '-C', str(REPO), 'merge-base', '--is-ancestor', BASE, commit], check=True)
    base = checked(REPO/EXP/'continuation-source-base-v1.json', 'a9b79462105ade201fb2f411e920854d3e6cea5c1b4e7e83760cda81c6b5fca6')
    if len(base) != 62 or len({r['path'] for r in base}) != 62:
        raise ValueError('62-row original source inventory')
    protected = []
    for r in base:
        old = subprocess.check_output(['git', '-C', str(REPO), 'show', BASE+':'+r['path']])
        equal([len(old), hashlib.sha256(old).hexdigest()], [r['bytes'], r['sha256']], 'base bytes')
        if r['path'] not in MUTABLE:
            equal(sha(confined(REPO, r['path'])), r['sha256'], 'protected source changed')
            protected.append(r)
    changed = git('diff', '--name-only', BASE, commit).splitlines()
    for path in changed:
        if not path.startswith(EXP):
            raise ValueError('outside continuation scope')
        exists = subprocess.run(['git', '-C', str(REPO), 'cat-file', '-e', BASE+':'+path], capture_output=True)
        if exists.returncode == 0 and path not in MUTABLE:
            raise ValueError('protected existing file changed')
    paths = {r['path'] for r in base} | set(git('ls-files', EXP).splitlines())
    rows = [{'path': p, 'bytes': confined(REPO, p).stat().st_size, 'sha256': sha(confined(REPO, p))}
            for p in sorted(paths)]
    return {'files': rows, 'changed': changed, 'protected': protected}


def host_facts(role):
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('required physical/native CI Apple host')
    def command(*args):
        return subprocess.check_output(args, text=True).strip()
    python_os = platform.mac_ver()[0]
    os_version = command('/usr/bin/sw_vers', '-productVersion')
    if python_os and python_os != os_version:
        raise ValueError('conflicting fresh OS observations')
    facts = {'system': platform.system(), 'architecture': platform.machine(),
             'machine': command('/usr/sbin/sysctl', '-n', 'machdep.cpu.brand_string'),
             'model': command('/usr/sbin/sysctl', '-n', 'hw.model'),
             'memory_bytes': int(command('/usr/sbin/sysctl', '-n', 'hw.memsize')),
             'page_bytes': int(command('/usr/sbin/sysctl', '-n', 'hw.pagesize')),
             'os': os_version, 'os_build': command('/usr/bin/sw_vers', '-buildVersion'),
             'python_os': python_os, 'os_source': 'fresh sw_vers; Python cross-check when available',
             'driver_identifier': None}
    if role == 'native-ci':
        equal(os.environ.get('GITHUB_ACTIONS'), 'true', 'native CI route')
    elif role == 'm1-ultra-studio':
        if os.environ.get('GITHUB_ACTIONS'):
            raise ValueError('physical Studio required')
        for key, expected in {'machine': 'Apple M1 Ultra', 'model': 'Mac13,2', 'page_bytes': 16384,
                              'memory_bytes': 137438953472, 'os': '26.0', 'os_build': '25A354'}.items():
            equal(facts[key], expected, 'retained Studio environment changed: '+key)
    else:
        raise ValueError('unsupported host role')
    return facts


RUNTIME_SHA256 = '36d3439033afa76443943a1a6967623cde063e435283ccf3b4e6a4e93a8755ca'
HARNESS_SHA256 = 'e0da9661808933b8ffea6f95b71ec5a9af707c9759940c7f59f5681a56a41d04'
INSPECTION_BYTES = 1024*1024


def inspect_image(flag, image):
    """Bounded, read-only otool capture; no library is loaded by this inspector."""
    if flag not in ('-L', '-l'):
        raise ValueError('unsupported inspection flag')
    argv = ['/usr/bin/otool', flag, str(image)]
    p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.monotonic()+15
    data = bytearray()
    try:
        while True:
            left = deadline-time.monotonic()
            if left <= 0 or not select.select([p.stdout], [], [], left)[0]:
                raise ValueError('otool inspection deadline')
            block = os.read(p.stdout.fileno(), min(65536, INSPECTION_BYTES+1-len(data)))
            if not block:
                break
            data.extend(block)
            if len(data) > INSPECTION_BYTES:
                raise ValueError('otool inspection output bound')
        if p.wait(timeout=max(0.001, deadline-time.monotonic())) != 0:
            raise ValueError('otool inspection failed')
        return bytes(data).decode('utf-8')
    finally:
        if p.poll() is None:
            p.kill()
        try:
            p.wait(timeout=5)
        finally:
            p.stdout.close()


def load_commands(text, image):
    """Parse one thin Mach-O display, preserving typed imports and own IDs."""
    lines = text.splitlines()
    if (len(text.encode()) > INSPECTION_BYTES or not lines or lines[0] != str(image)+':'
            or len(lines) > 16384 or any(len(x) > 4096 or '\x00' in x for x in lines)):
        raise ValueError('bounded single-image load commands')
    groups = []; current = None
    for line in lines[1:]:
        match = re.fullmatch(r'Load command (\d+)', line)
        if match:
            if int(match[1]) != len(groups) or len(groups) >= 512:
                raise ValueError('load command sequence/bound')
            current = []; groups.append(current)
        elif current is None:
            if line.strip():
                raise ValueError('unframed load command')
        else:
            current.append(line.strip())
    if not groups:
        raise ValueError('missing load commands')
    result = []
    imports = {'LC_LOAD_DYLIB', 'LC_LOAD_WEAK_DYLIB', 'LC_REEXPORT_DYLIB', 'LC_LOAD_UPWARD_DYLIB'}
    for number, fields in enumerate(groups):
        cmds = [x[4:] for x in fields if x.startswith('cmd ')]
        sizes = [x[8:] for x in fields if x.startswith('cmdsize ')]
        if len(cmds) != 1 or not re.fullmatch(r'LC_[A-Z0-9_]+', cmds[0]) or len(sizes) != 1 or not sizes[0].isdigit() or not 8 <= int(sizes[0]) <= 65536:
            raise ValueError('malformed load command header')
        cmd = cmds[0]; record = {'number': number, 'command': cmd}
        if cmd in imports or cmd == 'LC_ID_DYLIB' or cmd == 'LC_RPATH':
            key = 'path' if cmd == 'LC_RPATH' else 'name'
            values = [re.fullmatch(key+r' (.+) \(offset (\d+)\)', x) for x in fields if x.startswith(key+' ')]
            if len(values) != 1 or values[0] is None or not (12 if key == 'path' else 24) <= int(values[0][2]) < int(sizes[0]):
                raise ValueError('malformed dependency/rpath record')
            value = values[0][1]
            if any(ord(x) < 32 for x in value) or len(value.encode())+int(values[0][2])+1 > int(sizes[0]):
                raise ValueError('truncated dependency/rpath record')
            record.update(kind='rpath' if key == 'path' else 'own_id' if cmd == 'LC_ID_DYLIB' else 'import', value=value)
        elif any(x in cmd for x in ('DYLIB', 'DYLINKER', 'FVMLIB')) or cmd == 'LC_DYLD_ENVIRONMENT':
            raise ValueError('unsupported dependency/environment load command')
        else:
            continue  # Not a dependency command; complete raw bytes remain bound.
        result.append(record)
    if sum(x.get('kind') == 'own_id' for x in result) != 1:
        raise ValueError('one dylib own ID required')
    return result


def fixed_file(path):
    """Observe exactly this entry and its bounded symlink chain; never search."""
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('absolute fixed entry required')
    pending = list(path.parts[1:]); current = Path('/'); links = []; steps = 0
    while pending:
        steps += 1
        if steps > 1024 or len(links) > 32:
            raise ValueError('fixed-entry symlink traversal bound')
        part = pending.pop(0)
        if part in ('', '.'):
            continue
        if part == '..':
            current = current.parent; continue
        current /= part
        info = current.lstat()
        if stat.S_ISLNK(info.st_mode):
            if len(links) >= 32:
                raise ValueError('fixed-entry symlink traversal bound')
            target = os.readlink(current)
            links.append({'path': str(current), 'target': target})
            parts = Path(target).parts
            current = Path('/') if Path(target).is_absolute() else current.parent
            pending = list(parts[1:] if Path(target).is_absolute() else parts)+pending
        elif pending and not stat.S_ISDIR(info.st_mode):
            raise ValueError('fixed-entry non-directory component')
    info = current.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('fixed-entry regular file required')
    equal(str(path.resolve(strict=True)), str(current), 'fixed-entry canonical path')
    return {'lexical': str(path), 'canonical': str(current), 'symlinks': links,
            'bytes': info.st_size, 'mode': stat.S_IMODE(info.st_mode), 'device': info.st_dev,
            'inode': info.st_ino, 'mtime_ns': info.st_mtime_ns, 'sha256': sha(current)}


def retained_runtime(prefix, linked):
    """Fixed child-library-path policy; static evidence, never loaded-image proof."""
    if any(k.startswith('DYLD_') or k in ('LD_PRELOAD', 'LD_LIBRARY_PATH') for k in os.environ):
        raise ValueError('inspector loader overrides forbidden')
    equal(sha(REPO/'crates/mlx-native-affine/src/harness.rs'), HARNESS_SHA256, 'fixed child environment source')
    names = ('libmlx.dylib', 'libmlxc.dylib', 'libjaccl.dylib')
    files = {name: fixed_file(prefix/'lib'/name) for name in names}
    equal(files['libjaccl.dylib']['sha256'], RUNTIME_SHA256, 'retained runtime bytes')
    if len({r['canonical'] for r in files.values()}) != 3:
        raise ValueError('competing image identities')
    records = []; inspections = []; seen_runtime = False
    for name in names:
        image = prefix/'lib'/name
        text = inspect_image('-l', image); commands = load_commands(text, image)
        if name in linked:
            displayed = [x.strip().split(' (compatibility')[0] for x in linked[name]]
            equal(displayed, [x['value'] for x in commands if x['kind'] != 'rpath'], 'typed/linkage dependency mismatch')
        inspections.append({'image': str(image), 'method': 'otool -l', 'bytes': len(text.encode()),
                            'sha256': hashlib.sha256(text.encode()).hexdigest(), 'commands': commands})
        for command in commands:
            edge = {'image': str(image), **command}
            value = command['value']; kind = command['kind']
            if kind == 'rpath':
                edge['classification'] = 'recorded_unselected_rpath'
            elif kind == 'own_id':
                if Path(value).name != name:
                    raise ValueError('own install ID/image mismatch')
                edge['classification'] = 'own_id_not_import'
            elif value.startswith(('/usr/lib/', '/System/Library/')):
                if os.path.normpath(value) != value:
                    raise ValueError('noncanonical system dependency')
                if os.path.lexists(prefix/'lib'/Path(value).name):
                    raise ValueError('competing fixed-prefix system override')
                edge['classification'] = 'system_shared_cache_allowed'
            else:
                leaf = Path(value).name
                if leaf not in files:
                    raise ValueError('unexpected non-system dependency')
                target = files[leaf]
                if value != '@rpath/'+leaf and (not value.startswith('/') or os.path.normpath(value) not in (target['lexical'], target['canonical'])):
                    raise ValueError('unsupported dependency resolution context')
                edge.update(classification='retained_extra_runtime' if leaf == 'libjaccl.dylib' else 'pinned_MLX_image',
                            resolution='fixed_child_DYLD_LIBRARY_PATH_leaf_first_no_fallback',
                            lexical_candidate=target['lexical'], canonical_target=target['canonical'],
                            observed_sha256=target['sha256'])
                seen_runtime |= leaf == 'libjaccl.dylib' and name in linked
            records.append(edge)
    if not seen_runtime:
        raise ValueError('retained runtime import missing')
    equal({name: fixed_file(prefix/'lib'/name) for name in names}, files, 'static dependency inspection drift')
    return {'schema': 'pulsarmlx.retained-runtime-static/1', 'policy': 'fixed-prefix-child-library-path/1',
            'inspector_loader_overrides': 'absent', 'child_environment': {'inherited': 'cleared', 'DYLD_LIBRARY_PATH': str(prefix/'lib')},
            'harness_sha256': HARNESS_SHA256, 'files': files, 'edges': records, 'inspections': inspections,
            'expected_runtime_sha256': RUNTIME_SHA256, 'loaded_runtime_image_observed': False}


def native_state(prefix, receipt_path, role):
    if role == 'm1-ultra-studio' and any(k.startswith('DYLD_') or k in ('LD_PRELOAD', 'LD_LIBRARY_PATH') for k in os.environ):
        raise ValueError('inspector loader overrides forbidden')
    prefix = Path(prefix).resolve(strict=True)
    libraries = {name: sha(confined(prefix/'lib', name)) for name in ('libmlx.dylib', 'libmlxc.dylib', 'mlx.metallib')}
    receipt = read(receipt_path)
    pins = receipt.get('source_pins', {'mlx': receipt.get('mlx_commit'), 'mlx-c': receipt.get('mlx_c_commit')})
    equal(pins, PINS, 'native source pins')
    equal(len(receipt['patches']), 4, 'four patch records')
    equal({k.removesuffix('.patch').removeprefix('mlx-c-'): v for k, v in receipt['patches'].items()}, PATCHES, 'four native patches')
    linked = {}
    dependencies = {}
    linkage_inspections = []
    for name in ('libmlx.dylib', 'libmlxc.dylib'):
        text = (inspect_image('-L', prefix/'lib'/name) if role == 'm1-ultra-studio' else
                subprocess.check_output(['/usr/bin/otool', '-L', str(prefix/'lib'/name)], text=True))
        lines = text.splitlines()[1:]
        if role == 'm1-ultra-studio':
            equal(text.splitlines()[0], str(prefix/'lib'/name)+':', 'linkage inspection image')
            linkage_inspections.append({'image': str(prefix/'lib'/name), 'method': 'otool -L',
                                        'bytes': len(text.encode()), 'sha256': hashlib.sha256(text.encode()).hexdigest()})
        linked[name] = lines
        for line in lines:
            path = line.strip().split(' (compatibility')[0]
            if role != 'm1-ultra-studio' and path.startswith('/') and not path.startswith(('/usr/lib/', '/System/Library/')):
                actual = Path(path).resolve(strict=True)
                if not actual.is_relative_to(prefix):
                    dependencies[str(actual)] = sha(actual)
    if role == 'm1-ultra-studio':
        equal(sha(receipt_path), '7c2301eb59c037191cd296e3139a7ca4a93e61e27c5e8b05b1ae717888b16523', 'same retained installation')
        equal(libraries, {**{k: v['installed_sha256'] for k, v in receipt['libraries'].items()},
                          'mlx.metallib': receipt['metallib_sha256']}, 'installed native bytes')
        static = retained_runtime(prefix, linked)
        static['linkage_inspections'] = linkage_inspections
        dependencies = {static['files']['libjaccl.dylib']['canonical']: RUNTIME_SHA256}
        equal(receipt['extra_runtime_library_sha256'], RUNTIME_SHA256, 'pinned retained runtime')
        equal(sorted(dependencies.values()), [receipt['extra_runtime_library_sha256']], 'retained runtime dependency')
        metal = [line.strip() for lines in linked.values() for line in lines if 'Metal.framework/' in line]
        if not metal or any('current version 370.64.2)' not in line for line in metal):
            raise ValueError('Metal runtime identifier changed/unknown')
    result = {'libraries': libraries, 'dependencies': dependencies, 'linkage': linked,
              'receipt_sha256': sha(receipt_path), 'source_pins': pins, 'patches': PATCHES}
    if role == 'm1-ultra-studio':
        result['retained_runtime'] = static
    return result


def original_studio(paths):
    pins = read(REPO/EXP/'continuation-studio-originals-v1.json')
    equal(sorted(paths), sorted(pins), 'all actual original Studio files required')
    values = {}
    for name, pin in pins.items():
        path = Path(paths[name])
        with path.open('rb') as stream:
            raw = stream.read(pin['bytes']+1)
        equal([len(raw), hashlib.sha256(raw).hexdigest()], [pin['bytes'], pin['sha256']], 'original bytes missing/changed: '+name)
        values[name] = [json.loads(s) for s in raw.splitlines()] if name == 'raw_events' else json.loads(raw)
    return validate_studio_values(values, pins, paths)


def validate_studio_values(values, pins, paths):
    """Semantic validation after exact original-byte admission; also host-testable."""
    f = validate_originals(values)
    equal(values['raw_summary'], values['raw_report'], 'raw summary/report')
    outcome = values['raw_outcome']; raw = values['raw_report']
    equal(outcome['outcome'], 'EXIT_STATUS 0', 'retained termination')
    equal(outcome['binary_sha256'], f['binary_sha256'], 'retained binary')
    equal(outcome['config_sha256'], pins['raw_config']['sha256'], 'raw config/outcome')
    equal(raw['config_sha256'], outcome['config_sha256'], 'raw report/config')
    events = values['raw_events']
    equal([e['phase'] for e in events], ['provenance', 'before-call', 'after-return', 'cleanup'], 'raw call sequence')
    equal(events[0]['value'], raw['provenance'], 'raw events provenance')
    equal(events[1], {'allocation': 16384, 'control': 'P-RAW-LENGTH', 'phase': 'before-call', 'shape': [4095]}, 'raw geometry')
    equal(events[2], {'callbacks': 0, 'phase': 'after-return', 'status': 0}, 'raw return')
    equal(events[3], {'deallocation': 'process-exit-only', 'phase': 'cleanup', 'quarantine': True}, 'raw cleanup')
    d = values['diagnostic_receipt']; report = values['diagnostic_report']; check = values['diagnostic_check']
    equal([d['source_commit'], d['source_tree']], [BASE, BASE_TREE], 'diagnostic source')
    equal(d['source_manifest'], read(REPO/EXP/'continuation-source-base-v1.json'), 'original diagnostic inventory')
    equal(d['native_build_receipt_sha256'], pins['native_install']['sha256'], 'diagnostic installation')
    equal(d['native_libraries'], f['native_libraries'], 'crossed diagnostic stack')
    equal(d['raw_probe'], {'allowed': 1, 'used': 1, 'execution_authorized': False}, 'diagnostic allowance')
    equal(d['binary_sha256'], '6dfc6808490bbd864c593fb12fa96c3102edb6be3e9dda8dc4788c77351a532e', 'diagnostic binary')
    equal(d['rust_grader_sha256'], '1be15c08dc90b8f732301412b5e360d8cf5c273434e2691d94a3481c72a88329', 'diagnostic grader')
    for name in ('diagnostic_intent', 'diagnostic_outcome', 'diagnostic_check', 'diagnostic_check_intent'):
        equal(values[name]['receipt_sha256'], pins['diagnostic_receipt']['sha256'], 'diagnostic receipt link')
    equal(report['diagnostic_receipt_sha256'], pins['diagnostic_receipt']['sha256'], 'report receipt')
    equal(values['diagnostic_config']['diagnostic_receipt_sha256'], pins['diagnostic_receipt']['sha256'], 'config receipt')
    equal(values['diagnostic_outcome']['outcome'], 'EXIT_STATUS 0', 'diagnostic exit')
    for name in ('diagnostic_report', 'diagnostic_outcome'):
        equal(values[name]['config_sha256'], pins['diagnostic_config']['sha256'], 'diagnostic config binding')
    equal(check['report_sha256'], pins['diagnostic_report']['sha256'], 'diagnostic check/report')
    equal(check['rust_gates_sha256'], pins['diagnostic_rust_gates']['sha256'], 'diagnostic Rust gates')
    equal(check['G_QMM_RUST'], 'PASS', 'diagnostic checker')
    equal(check['native_acceptance'], False, 'diagnostic is not full M1a')
    for key in ('source_commit', 'source_tree', 'binary_sha256', 'native_libraries'):
        equal(report['provenance'][key], d[key], 'diagnostic provenance')
    for key, want in {'os': '26.0', 'os_build': '25A354', 'chip': 'Apple M1 Ultra', 'page_bytes': 16384}.items():
        equal(values['host001'][key], want, 'independent original host facts')
    h2 = values['host002']
    for key, want in {'cpu': 'Apple M1 Ultra', 'model': 'Mac13,2', 'page': '16384'}.items():
        equal([h2[key]['exit'], h2[key]['stdout'].strip()], [0, want], 'independent diagnostic host')
    if h2['os']['exit'] != 0 or '26.0' not in h2['os']['stdout'] or '25A354' not in h2['os']['stdout']:
        raise ValueError('independent Studio OS record')
    return {'evidence_kind': 'historical_host_native_stack', 'applies_to_current_binary': False,
            'source_commit': f['source_commit'], 'source_tree': f['source_tree'], 'binary_sha256': f['binary_sha256'],
            'native_libraries': f['native_libraries'], 'outcome': raw['outcome'], 'termination': outcome['outcome'],
            'originals': {k: {'path': str(Path(paths[k]).resolve(strict=True)), **v} for k, v in pins.items()}}


def ci_grant(path, commit, tree, inventory):
    g = read(path)
    e = os.environ
    for key, value in {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                       'GITHUB_REPOSITORY': 'MahdiHedhli/PulsarMLX', 'GITHUB_REF': 'refs/heads/'+BRANCH,
                       'GITHUB_RUN_ATTEMPT': '1', 'PULSAR_ADOPTION_PHASE': 'm1a'}.items():
        equal(e.get(key), value, 'CI grant route: '+key)
    event = read(e['GITHUB_EVENT_PATH'])
    equal(event.get('inputs'), {'mode': 'full'}, 'exact designated payload')
    equal(g['schema'], 'pulsarmlx.m1a-ci-continuation-grant/1', 'CI grant schema')
    equal(g['authority'], AUTHORITY, 'CI continuation authority')
    equal([g['candidate'], g['candidate_tree'], g['inventory_sha256']],
          [commit, tree, hashlib.sha256(canonical(inventory)).hexdigest()], 'C grant binding')
    equal(g['campaign_identity'], CAMPAIGN, 'stable campaign')
    equal(g['run_attempt'], 1, 'rerun refused')
    equal(str(g['run_id']), e.get('GITHUB_RUN_ID'), 'actual CI run')
    if not str(g['run_id']).isdigit() or g['run_id'] == 41481802750:
        raise ValueError('invalid current run')
    equal(g['controller_commit'], e.get('GITHUB_SHA'), 'actual H')
    controller = Path(e['GITHUB_WORKSPACE']).resolve(strict=True)
    equal(git('rev-parse', 'HEAD', root=controller), g['controller_commit'], 'H checkout')
    if git('status', '--porcelain=v1', '--untracked-files=all', root=controller):
        raise ValueError('H changed')
    equal(g['controller_tree'], git('rev-parse', 'HEAD^{tree}', root=controller), 'H tree')
    equal(g['raw_budget'], {'allowed': 1, 'used': 0, 'additional': 0}, 'original CI raw budget')
    equal(g['historical_run_ids'], [41481802750], 'predecessor ledger')
    equal(g['current_history_ids'], [41481802750, g['run_id']], 'complete reconciled history')
    equal(g['predecessor'], {'attempt': 1, 'job_id': 125402293053, 'runner_id': 0, 'steps': [], 'artifacts': 0,
                             'head': '015d748fe14ed555027ead7c0a2fb2a84a39fa35',
                             'tree': 'de7afb423e274a41e37fa06cc475b10c5b4ca345'}, 'predecessor zero execution')
    equal(sha(g['admission_evidence']), g['admission_sha256'], 'live admission capture')
    return {'evidence_kind': 'current_binary', 'applies_to_current_binary': True,
            'grant': str(Path(path).resolve(strict=True)), 'grant_sha256': sha(path),
            'controller_commit': g['controller_commit'], 'controller_tree': g['controller_tree'],
            'run_id': g['run_id'], 'run_attempt': 1}


def scope(r):
    for key, want in {'schema': SCHEMA, 'authority': AUTHORITY, 'phase': 'm1a', 'campaign_identity': CAMPAIGN,
                      'shipping_default': 'copied', 'M1b_released': False}.items():
        equal(r.get(key), want, 'continuation scope: '+key)
    policy = r['raw_policy']; role = r['host_role']
    if (role, policy) not in (('native-ci', CI), ('m1-ultra-studio', STUDIO)):
        raise ValueError('closed host/raw policy pair required')
    equal(r['raw_probe_budget'], {'allowed': 1, 'used': int(policy == STUDIO)}, 'raw budget')
    equal(r['raw_execution_authorized'], policy == CI, 'raw permission')
    p = r['raw_provenance']
    equal(p['applies_to_current_binary'], policy == CI, 'historical/current binary distinction')
    equal(p['evidence_kind'], 'current_binary' if policy == CI else 'historical_host_native_stack', 'raw provenance kind')
    for key, value in FIXED_INPUTS.items():
        equal(r[key], value, 'original input identity')


def revalidate(r):
    scope(r)
    if os.environ.get('PULSAR_ADOPTION_PHASE') != 'm1a':
        raise ValueError('explicit m1a phase required; timing forbidden')
    equal(r['source_root'], str(REPO), 'source location')
    equal(source_inventory(r['source_commit'], r['source_tree']), r['source_inventory'], 'source inventory changed')
    equal(host_facts(r['host_role']), r['host_facts'], 'fresh host changed')
    equal(native_state(r['native_prefix'], r['native_build_receipt'], r['host_role']), r['native_state'], 'native bindings changed')
    for key in ('binary', 'parent', 'rust_grader', 'python'):
        equal(sha(r[key]), r[key+'_sha256'], 'executable binding: '+key)
    equal(str(Path(sys.executable).resolve()), r['python'], 'actual interpreter')
    for key in ('parent', 'rust_grader', 'python'):
        equal(linkage(r[key], True), r['linkage'][key], 'host linkage')
    equal(linkage(r['binary'], False), r['linkage']['binary'], 'native child linkage')
    a = argparse.Namespace(**{k: Path(r[k]) for k in ('fixture_root', 'native_prefix', 'native_build_receipt', 'binary', 'parent', 'rust_grader')},
                           host_role=r['host_role'], source_commit=r['source_commit'], portable=Path(r['portable_report']),
                           reference=Path(r['reference']), native_ci_acceptance=None)
    original_input_admission(a)
    prepared = freeze_host.prepare(a)
    for key in ('contract_sha256', 'source_tree', 'native_libraries', 'fixture_manifest_sha256', 'portable_report_sha256',
                'reference_sha256', 'inherited_root', 'inherited_manifest_sha256', 'generator_hashes', 'dependency_manifest_sha256'):
        equal(prepared[key], r[key], 'frozen inputs changed: '+key)
    expected = expected_population(read(Path(r['fixture_root'])/'manifest.json'), read(Path(r['inherited_root'])/'manifest.json'))
    equal(r['population'], expected, 'exact ordinary population')
    equal([len(expected), sum(len(x[0]) for x in expected.values())], [52, 84], 'full M1a population')
    if r['raw_policy'] == STUDIO:
        provenance = original_studio({k: v['path'] for k, v in r['raw_provenance']['originals'].items()})
        equal(provenance['native_libraries'], r['native_libraries'], 'historical native stack')
    else:
        provenance = ci_grant(r['raw_provenance']['grant'], r['source_commit'], r['source_tree'], r['source_inventory']['files'])
    equal(provenance, r['raw_provenance'], 'raw provenance changed')
    return r


def stable_claim_path(r):
    # One stable predecessor/controller-owned location, independent of new C,
    # output directory, branch or schema. Renaming a campaign cannot refund use.
    anchor = r['raw_provenance']['grant'] if r['raw_policy'] == CI else r['native_build_receipt']
    return Path(anchor).resolve(strict=True).parent/'f020-m1a-continuation.claim.json'


def require_claim(r, campaign):
    equal(read(stable_claim_path(r)), {'campaign_identity': CAMPAIGN, 'campaign': str(campaign.resolve()),
                                      'receipt_sha256': sha(campaign/'freeze.json')}, 'stable consumed campaign claim')


def freeze(a):
    # Preparation is side-effect-free; the legacy 0/1 record is never written.
    if a.phase != 'm1a' or os.environ.get('PULSAR_ADOPTION_PHASE') != 'm1a':
        raise ValueError('m1a only')
    destination = a.campaign.resolve()
    if destination.is_relative_to(REPO) or any(destination.is_relative_to(p.resolve()) for p in (a.fixture_root, a.native_prefix)):
        raise ValueError('new campaign must be outside source, native prefix and immutable inputs')
    original_input_admission(a)
    r = freeze_host.prepare(a)
    inventory = source_inventory(r['source_commit'], r['source_tree'])
    role = r['host_role']; policy = a.raw_policy
    if (role, policy) not in (('native-ci', CI), ('m1-ultra-studio', STUDIO)):
        raise ValueError('host/policy mismatch')
    if policy == CI:
        if a.originals is not None or a.ci_grant is None:
            raise ValueError('CI requires its exact current grant only')
        provenance = ci_grant(a.ci_grant, r['source_commit'], r['source_tree'], inventory['files'])
    else:
        if a.originals is None or a.ci_grant is not None:
            raise ValueError('Studio requires original local evidence only')
        provenance = original_studio(read(a.originals))
    r.update(schema=SCHEMA, authority=AUTHORITY, phase='m1a', campaign_identity=CAMPAIGN,
             source_root=str(REPO), source_inventory=inventory, host_facts=host_facts(role),
             native_prefix=str(a.native_prefix.resolve(strict=True)), raw_policy=policy, raw_provenance=provenance,
             raw_probe_budget={'allowed': 1, 'used': int(policy == STUDIO)}, raw_execution_authorized=policy == CI,
             M1b_released=False, campaign=str(a.campaign.resolve()),
             population=expected_population(read(a.fixture_root/'manifest.json'), read(Path(r['inherited_root'])/'manifest.json')))
    r['host']['os'] = r['host_facts']['os']
    r['host']['os_build'] = r['host_facts']['os_build']
    r['native_state'] = native_state(a.native_prefix, a.native_build_receipt, role)
    for key, path in (('binary', a.binary), ('parent', a.parent), ('rust_grader', a.rust_grader), ('python', Path(sys.executable))):
        r[key] = str(path.resolve(strict=True)); r[key+'_sha256'] = sha(path)
    r['linkage'] = {key: linkage(r[key], key != 'binary') for key in ('binary', 'parent', 'rust_grader', 'python')}
    revalidate(r)
    if os.path.lexists(a.campaign):
        raise ValueError('occupied campaign; preserve attempt')
    create(stable_claim_path(r), {'campaign_identity': CAMPAIGN, 'campaign': str(a.campaign.resolve()),
                                 'receipt_sha256': hashlib.sha256(canonical(r)).hexdigest()})
    a.campaign.mkdir()
    create(a.campaign/'freeze.json', r)
    return {'receipt_sha256': sha(a.campaign/'freeze.json'), 'native_executions': 0}


def original_input_admission(a):
    # Bound reads and verify exact retained JSON bytes before the shared legacy
    # preparer parses them. No caller-supplied digest can widen this admission.
    for path, key in ((a.fixture_root/'manifest.json', 'fixture_manifest_sha256'),
                      (a.portable, 'portable_report_sha256'), (a.reference, 'reference_sha256')):
        checked(path, FIXED_INPUTS[key])


def binding(campaign):
    r = read(campaign/'freeze.json')
    return {'schema': SCHEMA, 'receipt_sha256': sha(campaign/'freeze.json'), 'authority': AUTHORITY,
            'campaign_identity': CAMPAIGN, 'raw_policy': r['raw_policy'], 'raw_provenance': r['raw_provenance'],
            'current_raw_children': int(r['raw_policy'] == CI), 'ordinary_children': 52, 'projections': 84,
            'M1b_released': False, 'shipping_default': 'copied'}


def admit(campaign, parent, binary):
    r = revalidate(read(campaign/'freeze.json'))
    require_claim(r, campaign)
    equal(str(campaign.resolve()), r['campaign'], 'campaign location')
    equal([str(parent.resolve()), str(binary.resolve())], [r['parent'], r['binary']], 'actual parent/compiled child')
    for name in ('continuation-attempt.json', 'm1a', 'raw-probe.intent.json', 'm1a-acceptance.json'):
        if os.path.lexists(campaign/name):
            raise ValueError('occupied/unknown campaign; no retry')
    create(campaign/'continuation-attempt.json', binding(campaign))
    return binding(campaign)


def before_child(campaign, label):
    r = revalidate(read(campaign/'freeze.json'))
    require_claim(r, campaign)
    equal(read(campaign/'continuation-attempt.json'), binding(campaign), 'attempt/receipt changed')
    root = campaign/'m1a'
    if label == 'raw-probe':
        if r['raw_policy'] != CI:
            raise ValueError('Studio current raw launch forbidden')
    elif label not in r['population']:
        raise ValueError('unknown ordinary child')
    # This is a consumed launch claim even when a later config write/spawn fails.
    create(root/(label+'.continuation-intent.json'), binding(campaign))
    return {'label': label, 'admitted': True}


def admit_raw_policy(campaign, r):
    equal(read(campaign/'continuation-attempt.json'), binding(campaign), 'campaign attempt binding')
    root = campaign/'m1a'
    if r['raw_policy'] == CI:
        equal(read(root/'raw-probe.continuation-intent.json'), binding(campaign), 'raw launch claim')
        equal(read(campaign/'raw-probe.intent.json'), {'binary_sha256': r['binary_sha256'], 'host_role': 'native-ci', 'attempt': 1}, 'raw intent')
        config = read(root/'raw-probe.config.json'); outcome = read(root/'raw-probe.outcome.json')
        equal(outcome['config_sha256'], sha(root/'raw-probe.config.json'), 'raw config')
        equal(outcome['binary_sha256'], r['binary_sha256'], 'raw outcome binary')
        equal(config['mode'], 'raw-length', 'raw mode')
        for key in ('source_commit', 'source_tree', 'binary_sha256', 'native_libraries'):
            equal(config[key], r[key], 'current raw identity')
        events = [json.loads(s) for s in (root/'raw-probe/events.jsonl').read_text().splitlines()]
        provenance = [e['value'] for e in events if e.get('phase') == 'provenance']
        if len(provenance) != 1:
            raise ValueError('raw current provenance absent')
        for key in ('source_commit', 'source_tree', 'binary_sha256', 'native_libraries'):
            equal(provenance[0][key], r[key], 'raw observed provenance')
        equal(provenance[0]['loaded_images_verified'], True, 'raw loaded images')
        admit_raw(root)
    else:
        if os.path.lexists(campaign/'raw-probe.intent.json') or any(root.glob('raw-probe*')):
            raise ValueError('historical raw cannot appear in current campaign')


def validate_reports(campaign, r, mechanism):
    revalidate(r)
    require_claim(r, campaign)
    equal(mechanism['continuation'], binding(campaign), 'mechanism continuation binding')
    admit_raw_policy(campaign, r)
    for label in r['population']:
        equal(read(campaign/'m1a'/(label+'.continuation-intent.json')), binding(campaign), 'ordinary launch claim')
        config = read(campaign/'m1a'/(label+'.config.json'))
        report = read(campaign/'m1a'/label/'run.json')
        equal(config['host'], r['host'], 'current host config')
        equal(report['frozen_host'], r['host'], 'crossed-host report')
        equal(report['source_binding'], {k: r[k] for k in ('source_commit', 'source_tree', 'dependency_manifest_sha256', 'generator_hashes')}, 'ordinary source/helper bindings')
        if report.get('diagnostic_only') is True:
            raise ValueError('diagnostic output cannot replace full ordinary evidence')


def main():
    p = argparse.ArgumentParser(); commands = p.add_subparsers(dest='command', required=True)
    f = commands.add_parser('freeze')
    f.add_argument('--host-role', required=True); f.add_argument('--source-commit', required=True)
    f.add_argument('--phase', choices=['m1a'], required=True); f.add_argument('--raw-policy', choices=[CI, STUDIO], required=True)
    for name in ('campaign', 'fixture-root', 'portable', 'reference', 'native-prefix', 'native-build-receipt', 'binary', 'parent', 'rust-grader'):
        f.add_argument('--'+name, type=Path, required=True)
    f.add_argument('--originals', type=Path); f.add_argument('--ci-grant', type=Path)
    f.set_defaults(native_ci_acceptance=None)
    for command in ('admit', 'before-child', 'seal'):
        c = commands.add_parser(command); c.add_argument('campaign', type=Path)
        if command == 'admit':
            c.add_argument('--parent', type=Path, required=True); c.add_argument('--binary', type=Path, required=True)
        if command == 'before-child':
            c.add_argument('--label', required=True)
    a = p.parse_args()
    if a.command == 'freeze':
        result = freeze(a)
    elif a.command == 'admit':
        result = admit(a.campaign, a.parent, a.binary)
    elif a.command == 'before-child':
        result = before_child(a.campaign, a.label)
    else:
        revalidate(read(a.campaign/'freeze.json')); result = binding(a.campaign)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
