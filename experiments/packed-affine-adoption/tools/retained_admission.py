"""Exact Rust010 publication-chain admission. No live-host or numerical replay."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import zipfile

from report_checks import expected_population, admit_entries, admit_report, admit_raw, CONTRACT
from retained_rational import REFERENCE_SHA, FIXTURE_SHA

C = 'f61a8c19d6aad2265a12f417ddbe842024fe32f2'
C_TREE = '5f8a8c55f4e0067b10dcd6606fe05935e8e47659'
H = '8a21f17bdea7b9d04f7ac54b070fa0a4f12762a2'
H_TREE = 'f08812602debc2fce192e2035339844c6c284ef0'
RUN = 41933197121
ARCHIVE_SHA = 'ce6cb205f07c1e759adb39499457e6c21fd9285bce6ff1f341ff00b8b05b609f'
MANIFEST_SHA = '3bd3581767b34e010b10291c5a118fe0726582420b958d79bcad77fcf9f0ad19'
INVENTORY_SHA = '0fba859129320b062a909d0039f7d79af81d510676d18410376676081a6b60e6'
INPUT_MANIFEST_SHA = 'b9c8267f4b4d7fa5770b0fa23ef392ab30d55167c0934b42a0c86e17e160de1a'
INHERITED_SHA = '6f0e39e6d2c705603f3f897133d42c31837c53348aba0f4b0389dca18018fc14'
PORTABLE_SHA = '26ae22fdf4d90bd7490e10e2abd96d9b16e295e6fd40e8fde7d91c03908e9d45'
AUTHORITY = {'M0_sha256': CONTRACT,
             'contract_sha256': 'eb96edd30be70ecf1b06ed3506ed964f7ffe24b7bf234b09664930f256155033',
             'prompt_commit': '9d8f1a3663b0ae40aff8ab42c2cd28a52f150052',
             'prompt_sha256': 'c7a99cf33d98ee9dfe0aa87d62c13b17e9446f3cddb1a060642ec09f6c44cf4d'}
CAMPAIGN = 'f020-packed-affine-adoption-m1-v1'
SCHEMA = 'pulsarmlx.m1a-continuation/1'
LIMIT = 32 * 1024 * 1024


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def equal(actual, expected, reason):
    # JSON encodings also distinguish booleans from integers.
    require(json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True), reason)


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def bounded(path, limit=LIMIT):
    require(not Path(path).is_symlink(), 'symlink input')
    with Path(path).open('rb') as f:
        raw = f.read(limit + 1)
    require(len(raw) <= limit, 'input size bound')
    return raw


def pairs(rows):
    result = {}
    for k, v in rows:
        require(k not in result, 'duplicate JSON field')
        result[k] = v
    return result


def parse(raw):
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def read(path):
    return parse(bounded(path))


def relative(name):
    require(type(name) is str and bool(name) and '\\' not in name, 'relative path syntax')
    p = PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and str(p) == name and name != '.', 'relative path confinement')
    return p


def confined(root, name):
    p = Path(root) / relative(name)
    base = Path(root).resolve(strict=True)
    require(not p.is_symlink() and p.resolve(strict=True).is_relative_to(base), 'symlink/path escape')
    for parent in p.parents:
        if parent == Path(root):
            break
        require(not parent.is_symlink(), 'directory symlink')
    return p


class Paths:
    """Typed local resolution; original/publication receipt objects are never edited."""
    def __init__(self, source, inputs, artifact):
        self.aliases = {'<CAMPAIGN_ROOT>/source': Path(source),
                        '<CAMPAIGN_ROOT>/inputs': Path(inputs),
                        '<CAMPAIGN_ROOT>': Path(artifact)}

    def resolve(self, value):
        for alias, root in self.aliases.items():
            if value == alias:
                return root.resolve(strict=True)
            if value.startswith(alias + '/'):
                return confined(root, value[len(alias) + 1:])
        raise ValueError('unavailable or ambiguous path alias')


def check_members(infos):
    names = [i.filename for i in infos]
    require(len(names) == len(set(names)) and len(names) <= 588, 'archive duplicate/count')
    require(sum(i.file_size for i in infos) <= LIMIT, 'archive expanded bound')
    for i in infos:
        relative(i.filename)
        require(not i.is_dir() and stat.S_IFMT(i.external_attr >> 16) in (0, stat.S_IFREG), 'archive member type')
        require(not i.flag_bits & 1, 'encrypted archive')


def publication(archive, root):
    equal(Path(archive).stat().st_size, 586936, 'archive bytes')
    equal(digest(archive), ARCHIVE_SHA, 'archive identity')
    with zipfile.ZipFile(archive) as z:
        infos = z.infolist()
        check_members(infos)
        raw = z.read('public-view-manifest.json')
        equal(hashlib.sha256(raw).hexdigest(), MANIFEST_SHA, 'public manifest identity')
        manifest = parse(raw)
        rows = {r['path']: r for r in manifest['files']}
        require(len(rows) == len(manifest['files']) == 586, 'manifest duplicate/count')
        names = set(rows) | {'public-view-manifest.json', 'export-outcome.json'}
        equal(set_to_list(i.filename for i in infos), sorted(names), 'archive population')
        files = [p for p in Path(root).rglob('*') if not p.is_dir()]
        equal(sorted(str(p.relative_to(root)) for p in files), sorted(names), 'extracted population')
        for i in infos:
            data = z.read(i)
            local = bounded(confined(root, i.filename))
            require(local == data, 'extracted/public bytes changed: ' + i.filename)
            if i.filename in rows:
                row = rows[i.filename]
                equal(hashlib.sha256(data).hexdigest(), row['public_sha256'], 'public payload hash')
                equal(row['changed'], row['original_sha256'] != row['public_sha256'], 'original/public distinction')
        equal(sum(r['changed'] for r in rows.values()), 124, 'changed views population')
    return rows


def set_to_list(values):
    return sorted(set(values))


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args], text=True).strip()


def source_inputs(source, controller, inputs, input_manifest, inventory):
    equal(git(source, 'rev-parse', 'HEAD'), C, 'executed source checkout')
    equal(git(source, 'rev-parse', 'HEAD^{tree}'), C_TREE, 'executed source tree')
    equal(git(source, 'status', '--porcelain'), '', 'executed source dirty')
    equal(git(controller, 'rev-parse', 'HEAD'), H, 'exporter source checkout')
    equal(git(controller, 'rev-parse', 'HEAD^{tree}'), H_TREE, 'exporter source tree')
    equal(git(controller, 'status', '--porcelain'), '', 'exporter source dirty')
    equal(digest(Path(controller) / 'scripts/ci/packed_affine_m1a_v1.py'),
          '11213f770aadc7d41c2cbb5abbb6ab97dc994d65317ede758e466b74c114e83c', 'pinned exporter')
    inv_path = Path(controller) / 'scripts/ci/packed_affine_m1a_continuation_source_v1.json'
    equal(digest(inv_path), INVENTORY_SHA, 'inventory identity')
    equal(read(inv_path), inventory['files'], 'published source inventory')
    require(len(inventory['files']) == 70, 'source inventory count')
    # Q's imports must still be byte-identical to C. Q only adds host tools.
    checker = Path(__file__).resolve().parents[3]
    for row in inventory['files']:
        for root in (source, checker):
            p = confined(root, row['path'])
            equal([p.stat().st_size, digest(p)], [row['bytes'], row['sha256']], 'protected source bytes')
    equal(digest(input_manifest), INPUT_MANIFEST_SHA, 'original input inventory')
    rows = read(input_manifest)['files']
    require(len(rows) == 46 and sum(r['bytes'] for r in rows) == 88068103, 'input population')
    equal(sorted(str(p.relative_to(inputs)) for p in Path(inputs).rglob('*') if p.is_file()), sorted(r['path'] for r in rows), 'input file set')
    for row in rows:
        p = confined(inputs, row['path'])
        equal([p.stat().st_size, digest(p)], [row['bytes'], row['sha256']], 'original input bytes')
    # Verify every tracked inherited payload against immutable C Git objects.
    inherited = []
    for line in git(source, 'ls-tree', '-r', C, 'fixtures/native-composition').splitlines():
        meta, name = line.split('\t'); mode, kind, blob = meta.split()
        require(mode == '100644' and kind == 'blob', 'inherited Git object type')
        raw = bounded(confined(source, name))
        equal(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(), blob, 'inherited Git payload')
        inherited.append({'path': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'git_blob': blob})
    require(bool(inherited), 'inherited source unavailable')
    return rows, inherited


def original(rows, name):
    row = rows[name]
    require(row['changed'] is False and row['original_sha256'] == row['public_sha256'], 'required original unavailable: ' + name)
    return row['original_sha256']


def output_geometry(output, shape, name, size, explicit_shape):
    equal(output['file'], name, 'exact output path')
    equal(output['dtype'], 'F32', 'output dtype')
    if explicit_shape:
        equal(output['shape'], shape, 'output shape')
    require(len(shape) == 2 and all(type(n) is int and n > 0 for n in shape), 'positive output dimensions')
    equal(size, shape[0] * shape[1] * 4, 'projection byte length')


def binding(freeze, rows):
    return {'schema': SCHEMA, 'receipt_sha256': rows['campaign/freeze.json']['original_sha256'],
            'authority': AUTHORITY, 'campaign_identity': CAMPAIGN, 'raw_policy': 'CI_FRESH_ONCE',
            'raw_provenance': freeze['raw_provenance'], 'current_raw_children': 1,
            'ordinary_children': 52, 'projections': 84, 'M1b_released': False, 'shipping_default': 'copied'}


def control_views(root, rows, freeze, mechanism, expected, paths):
    f = freeze
    for key, want in {'schema': SCHEMA, 'authority': AUTHORITY, 'source_commit': C, 'source_tree': C_TREE,
                      'phase': 'm1a', 'host_role': 'native-ci', 'campaign_identity': CAMPAIGN,
                      'raw_policy': 'CI_FRESH_ONCE', 'raw_execution_authorized': True,
                      'raw_probe_budget': {'allowed': 1, 'used': 0}, 'M1b_released': False,
                      'shipping_default': 'copied', 'reference_sha256': REFERENCE_SHA,
                      'portable_report_sha256': PORTABLE_SHA, 'fixture_manifest_sha256': FIXTURE_SHA,
                      'inherited_manifest_sha256': INHERITED_SHA, 'contract_sha256': CONTRACT}.items():
        equal(f[key], want, 'freeze semantic: ' + key)
    equal(f['population'], expected, 'frozen population')
    for key, value in {'source_root': '<CAMPAIGN_ROOT>/source', 'fixture_root': '<CAMPAIGN_ROOT>/inputs/fixtures',
                       'inherited_root': '<CAMPAIGN_ROOT>/source/fixtures/native-composition',
                       'reference': '<CAMPAIGN_ROOT>/inputs/reference.json', 'portable_report': '<CAMPAIGN_ROOT>/inputs/portable.json',
                       'campaign': '<CAMPAIGN_ROOT>/campaign', 'native_build_receipt': '<CAMPAIGN_ROOT>/native-build-receipt.json'}.items():
        equal(f[key], value, 'typed source/input/receipt path'); paths.resolve(value)
    p = f['raw_provenance']
    equal(p, {'applies_to_current_binary': True, 'controller_commit': H, 'controller_tree': H_TREE,
              'evidence_kind': 'current_binary', 'grant': '<CAMPAIGN_ROOT>/continuation-grant.json',
              'grant_sha256': rows['continuation-grant.json']['original_sha256'], 'run_attempt': 1, 'run_id': RUN}, 'raw provenance')
    grant = read(root / 'continuation-grant.json')
    for key, value in {'schema': 'pulsarmlx.m1a-ci-continuation-grant/1', 'authority': AUTHORITY,
                       'candidate': C, 'candidate_tree': C_TREE, 'controller_commit': H, 'controller_tree': H_TREE,
                       'campaign_identity': CAMPAIGN, 'run_id': RUN, 'run_attempt': 1,
                       'inventory_sha256': INVENTORY_SHA, 'historical_run_ids': [41481802750],
                       'current_history_ids': [41481802750, RUN], 'raw_budget': {'allowed': 1, 'used': 0, 'additional': 0},
                       'admission_evidence': '<CAMPAIGN_ROOT>/admission-evidence.json',
                       'admission_sha256': rows['admission-evidence.json']['original_sha256'],
                       'predecessor': {'artifacts': 0, 'attempt': 1, 'head': '015d748fe14ed555027ead7c0a2fb2a84a39fa35',
                                       'job_id': 125402293053, 'runner_id': 0, 'steps': [],
                                       'tree': 'de7afb423e274a41e37fa06cc475b10c5b4ca345'}}.items():
        equal(grant[key], value, 'grant semantic: ' + key)
    b = binding(f, rows)
    equal(read(root / 'campaign/continuation-attempt.json'), b, 'parent attempt binding')
    equal(read(root / 'f020-m1a-continuation.claim.json'),
          {'campaign': f['campaign'], 'campaign_identity': CAMPAIGN, 'receipt_sha256': b['receipt_sha256']}, 'stable original claim')
    equal(mechanism['continuation'], b, 'mechanism continuation')
    for key in ('source_commit', 'source_tree', 'binary_sha256', 'contract_sha256', 'fixture_manifest_sha256', 'host_role'):
        equal(mechanism[key], f[key], 'mechanism semantic')
    equal([mechanism['mechanism'], mechanism['correctness'], mechanism['M1b_released']], ['PASS', 'PENDING_REFERENCE_GATES', False], 'mechanism is not numerical acceptance')
    for label in list(expected) + ['raw-probe']:
        equal(read(root / ('campaign/m1a/' + label + '.continuation-intent.json')), b, 'child claim')
    receipt = read(root / 'native-build-receipt.json')
    equal(original(rows, 'native-build-receipt.json'), f['native_build_receipt_sha256'], 'original native build receipt')
    equal(receipt['workflow_commit'], H, 'native build workflow'); equal(receipt['run_id'], str(RUN), 'native build run')
    ns = f['native_state']
    equal(ns['receipt_sha256'], f['native_build_receipt_sha256'], 'native receipt binding')
    equal(ns['libraries'], f['native_libraries'], 'native library views')
    equal(ns['source_pins'], receipt['source_pins'], 'native source pins')
    equal(ns['patches'], {k.removesuffix('.patch').removeprefix('mlx-c-'): v for k, v in receipt['patches'].items()}, 'native patches')
    equal(ns['source_pins'], {'mlx': f['mlx_commit'], 'mlx-c': f['mlx_c_commit']}, 'native pin views')
    equal(f['host_facts']['machine'], f['host']['machine'], 'native host views')
    for key in ('os', 'os_build'):
        equal(f['host_facts'][key], f['host'][key], 'native OS views')
    equal(f['host']['native_limits'], {'combined_logical_reservation': 100663296, 'live_working_bytes': 33554432,
                                      'mlx_cache_requested': 33554432, 'mlx_memory_requested': 33554432}, 'native bounds')
    return b


def report_semantics(f, expected, label, config, report, outcome, config_hash, manifest, portable, events):
    ids, arm, kind = expected[label]
    equal(config['arm'], arm, 'arm identity')
    equal(config.get('sequence') if kind == 'group' else [config.get('case_id')], ids, 'case/order identity')
    equal(config['mode'], 'diagnostic' if kind == 'group' else 'inherited', 'ordinary mode')
    equal(config['host'], f['host'], 'config host'); equal(report['frozen_host'], f['host'], 'report host')
    for key in ('source_commit', 'source_tree', 'binary_sha256', 'native_libraries', 'dependency_manifest_sha256', 'generator_hashes'):
        equal(config[key], f[key], 'config identity: ' + key)
    equal(report['source_binding'], {k: f[k] for k in ('source_commit', 'source_tree', 'dependency_manifest_sha256', 'generator_hashes')}, 'source/helper binding')
    require(report.get('diagnostic_only') is not True, 'copied diagnostic cannot replace full population')
    outputs = admit_report(f, expected, label, report, outcome, config_hash)
    equal(report['provenance']['TF32'], False, 'TF32 policy')
    equal([e['value'] for e in events if e.get('phase') == 'provenance'], [report['provenance']], 'event provenance')
    if kind == 'group':
        equal(config['fixture_root'], f['fixture_root'], 'fixture alias')
        equal(config['fixture_manifest_sha256'], FIXTURE_SHA, 'config fixture')
        equal(config['metadata_identities'], {c['id']: c['receipt']['metadata_snapshot_sha256'] for c in portable['cases']}, 'metadata identity census')
        cases = {c['id']: c for c in manifest['cases']}
        preflight = [e for e in events if e.get('phase') == 'original-preflight']
        equal([e['id'] for e in preflight], ids, 'original preflight order')
        by_portable = {c['id']: c for c in portable['cases']}
        for e in preflight:
            c = cases[e['id']]
            equal(e['component_hashes'], c['expected_hashes'], 'original plane hash')
            equal(e['input_sha256'], c['input_sha256'], 'original input hash')
            equal(e['bound_exponent'], by_portable[e['id']]['bound_exponent'], 'gamma selection')
        reads = [e for e in events if e.get('phase') == 'source-read-verified-before-native']
        equal([e['id'] for e in reads], ids, 'read order')
        for i, e in enumerate(reads):
            equal(e['receipt'], by_portable[e['id']]['receipt'], 'read receipt')
            equal([e['generation'], e['slot']], [i + 1, 0], 'whole slab generation')
        operations = [e for e in events if e.get('phase') == 'operation']
        equal([e['id'] for e in operations], ids, 'operation sequence')
        for i, (e, out) in enumerate(zip(operations, outputs, strict=True)):
            equal([e['iteration'], e['generation'], e['slot'], e['warmup'], e['output_sha256']], [i, i + 1, 0, False, out['sha256']], 'operation/output binding')
        copy_controls = [e for e in events if e.get('control') == 'C-COPY']
        equal(copy_controls, [{'control': 'C-COPY', 'pass': True, 'reached': True}], 'copy control')
        equal(report['adoption']['method'], 'managed-flat-parent' if arm == 'adopted' else 'copied', 'import method')
        equal(report['adoption']['pointer_identity'], arm == 'adopted', 'adopted pointer identity')
        equal(report['io']['read_policy'], 'buffered-exact', 'read policy')
        equal(report['io']['overread_bytes'], 0, 'read overrun')
        equal(report['io']['range_attempts'], 3 * len(ids), 'range calls')
        equal(report['io']['requested_bytes'], sum(e['receipt']['requested_bytes'] for e in reads), 'read byte count')
        equal(report['io']['physical_device_bytes'], None, 'unknown physical IO')
        mem = report['memory']
        for key, val in {'mlx_memory_limit_requested': 33554432, 'mlx_cache_limit_requested': 33554432,
                         'native_limit_calls_status': 0, 'combined_reservation': 100663296,
                         'deduplicated_physical_usage': None, 'wiring': 'unknown'}.items():
            equal(mem[key], val, 'memory predicate')
        require(0 < mem['live_working_bound'] <= 33554432, 'live working bound')
        require(mem['raw_mlx_active_cache_peak'][0] <= 33554432 and mem['raw_mlx_active_cache_peak'][2] <= 33554432, 'observed native memory bound')
        setups = [e for e in events if e.get('phase') == 'setup']
        require(len(setups) == 1, 'native setup evidence')
        setup = setups[0]
        equal(setup['adopted'], arm == 'adopted', 'setup arm')
        equal(setup['page'], f['host_facts']['page_bytes'], 'native page geometry')
        equal([setup['live_bound'], setup['rust_capacity']], [mem['live_working_bound'], mem['rust_capacity']], 'setup memory')
        registered = setup['registered_bytes'] if arm == 'adopted' else 0
        equal([report['adoption']['registered_bytes'], mem['adopted_capacity_constant_within_reset'], mem['adopted_overlap']], [registered] * 3, 'adoption allocation reporting')
        equal(mem['clear_events'], 2, 'native cache resets')
        equal(mem['reset_interval'], 'startup and post-copy-control', 'native peak interval')
        copies = report['copies']
        weight_bytes = sum(e['receipt']['plane']['ranges'][0]['len'] for e in reads)
        metadata_bytes = sum(sum(x['len'] for x in e['receipt']['plane']['ranges'][1:]) for e in reads)
        equal(copies, {'packed_import_bytes': 0 if arm == 'adopted' else weight_bytes,
                       'metadata_raw_bytes': metadata_bytes, 'metadata_widening_bytes': 2 * metadata_bytes,
                       'output_bytes': sum(cases[c]['M'] * cases[c]['H'] * 4 for c in ids),
                       'layout_materialization_bytes': None, 'unknown_materialization': True}, 'copy accounting')
        snapshot = report['bridge_diagnostic']
        for key, value in {'enabled': True, 'snapshot_status': 0, 'bridge_refusal': 0, 'failed_function': 0,
                           'failed_substage': 0, 'mlx_error_callbacks': 0, 'exception_category': 0,
                           'retirement_enter': 1, 'retirement_complete': 1, 'close_complete': 1,
                           'context_present': False, 'evidence_write_failed': False,
                           'qmm_graph_enter': len(ids), 'qmm_graph_return': len(ids),
                           'evaluation_attempts': len(ids), 'evaluation_completions': len(ids)}.items():
            equal(snapshot[key], value, 'bridge diagnostic/retirement')
        if len(ids) == 3:
            equal(ids[0], ids[2], 'ABA population')
            equal(outputs[0]['sha256'], outputs[2]['sha256'], 'ABA output identity')
            equal(outputs[0]['slab_sha256'], outputs[2]['slab_sha256'], 'ABA slab identity')
    else:
        equal(config['inherited_root'], f['inherited_root'], 'inherited alias')
        equal(report['original_population_unchanged'], True, 'inherited loader declaration')
        matches = [e for e in events if e.get('id') == ids[0]]
        require(len(matches) == 1, 'inherited original-loader evidence')
        equal(matches[0]['original_loader'], 'unchanged Source::open/compose/stage', 'inherited loader')
        require(matches[0]['memory'][0] <= 33554432 and matches[0]['memory'][2] <= 33554432, 'inherited native memory')
    return outputs


def admit(archive, root, source, controller, inputs, input_manifest):
    root, source, controller, inputs = map(Path, (root, source, controller, inputs))
    rows = publication(archive, root)
    f = read(root / 'campaign/freeze.json'); mechanism = read(root / 'campaign/m1a/mechanism.json')
    input_rows, inherited_rows = source_inputs(source, controller, inputs, input_manifest, f['source_inventory'])
    manifest = read(inputs / 'fixtures/manifest.json'); portable = read(inputs / 'portable.json')
    inherited = read(source / 'fixtures/native-composition/manifest.json')
    equal(digest(source / 'fixtures/native-composition/manifest.json'), INHERITED_SHA, 'inherited manifest')
    expected = expected_population(manifest, inherited)
    b = control_views(root, rows, f, mechanism, expected, Paths(source, inputs, root))
    entries = admit_entries(mechanism, expected)
    equal([e['label'] for e in entries], list(expected), 'original parent report order')
    equal(read(root / 'campaign/m1a/injected-controls.json'),
          {'C-GEOMETRY': {'reached': True, 'native_calls': 0}, 'C-CALLBACK': {'reached': True, 'injected': True, 'native_fallback_claim': False}}, 'injected controls')
    projections = []; paired = {}; reports = []
    cases = {c['id']: c for c in manifest['cases']}; inherited_cases = {c['id']: c for c in inherited['cases']}
    for entry in entries:
        label = entry['label']; prefix = 'campaign/m1a/'
        report_name = prefix + entry['report']; original(rows, report_name)
        report = read(root / report_name); config_name = prefix + label + '.config.json'
        cfg = read(root / config_name); outcome = read(root / (prefix + label + '.outcome.json'))
        events = [parse(line) for line in bounded(root / (prefix + label + '/events.jsonl')).splitlines()]
        outputs = report_semantics(f, expected, label, cfg, report, outcome, rows[config_name]['original_sha256'], manifest, portable, events)
        hashes = []
        for i, out in enumerate(outputs):
            kind = expected[label][2]; cid = expected[label][0][i]
            want_file = f'output-{i}.f32' if kind == 'group' else 'output.f32'
            if kind == 'group':
                shape = [cases[cid]['M'], cases[cid]['H']]
                equal([out['generation'], out['slot']], [i + 1, 0], 'output generation')
            else:
                p = inherited_cases[cid]['params']; shape = [p['M_eff'], p['N']]
                inherited_events = [e for e in events if e.get('id') == cid]
                equal(inherited_events[0]['source_identity'], inherited_cases[cid]['oracle']['identity'], 'inherited composition identity')
            name = prefix + label + '/' + want_file
            equal(original(rows, name), out['sha256'], 'original projection identity')
            output_geometry(out, shape, want_file, (root / name).stat().st_size, kind == 'group')
            hashes.append(out['sha256']); projections.append({'report': report_name, 'id': cid, 'arm': expected[label][1], 'path': name, 'shape': shape, 'sha256': out['sha256']})
        key = label.rsplit('-', 1)[0]
        if key in paired:
            equal(hashes, paired[key], 'copied/adopted pair identity')
        paired[key] = hashes
        reports.append({'label': label, 'path': report_name, 'original_sha256': rows[report_name]['original_sha256'],
                        'config': rows[config_name], 'output_count': len(outputs)})
    equal(len(projections), 84, 'complete projection count')
    equal(len(paired), 26, 'complete arm groups')
    # Current raw observation is re-admitted, never repeated.
    admit_raw(root / 'campaign/m1a')
    raw = read(root / 'campaign/m1a/raw-probe/run.json')
    cfgname = 'campaign/m1a/raw-probe.config.json'; original(rows, cfgname)
    cfg = read(root / cfgname); rawout = read(root / 'campaign/m1a/raw-probe.outcome.json')
    for n in ('run.json', 'events.jsonl'):
        original(rows, 'campaign/m1a/raw-probe/' + n)
    for key in ('source_commit', 'source_tree', 'binary_sha256', 'native_libraries'):
        equal(cfg[key], f[key], 'raw config identity'); equal(raw['provenance'][key], f[key], 'raw report identity')
    equal(cfg['mode'], 'raw-length', 'raw mode')
    equal([raw['config_sha256'], rawout['config_sha256']], [rows[cfgname]['original_sha256']] * 2, 'raw config hash')
    equal(rawout['binary_sha256'], f['binary_sha256'], 'raw binary')
    equal(rawout['outcome'], 'EXIT_STATUS 0', 'raw termination')
    equal([raw['outcome'], raw['qmm_calls'], raw['quarantine'], raw['callbacks']], ['outside-contract-acceptance', 0, True, 0], 'retained raw observation')
    events = [parse(line) for line in bounded(root / 'campaign/m1a/raw-probe/events.jsonl').splitlines()]
    equal(sum(e.get('phase') == 'after-return' for e in events), 1, 'raw return once')
    equal([e for e in events if e.get('phase') == 'cleanup'], [{'phase': 'cleanup', 'quarantine': True, 'deallocation': 'process-exit-only'}], 'raw quarantine boundary')
    equal([e['value'] for e in events if e.get('phase') == 'provenance'], [raw['provenance']], 'raw event identity')
    equal(read(root / 'campaign/raw-probe.intent.json'), {'attempt': 1, 'binary_sha256': f['binary_sha256'], 'host_role': 'native-ci'}, 'original raw intent')
    require(not (root / 'campaign/m1a-acceptance.json').exists(), 'legacy acceptance forbidden')
    equal(read(root / 'M1a.result.json')['exit_code'], 0, 'parent termination')
    equal(read(root / 'qualification.result.json')['exit_code'], 1, 'original qualifier failure')
    attempts = sorted(p for p in root.rglob('rust-gates.attempt.json'))
    equal(len(attempts), 17, 'preserved old Rust attempts')
    for path in attempts:
        attempt = read(path); old_report = path.parent / 'run.json'
        equal(attempt, {'grader_sha256': f['rust_grader_sha256'], 'report_sha256': digest(old_report)}, 'old Rust attempt binding')
    return {'schema': 'pulsarmlx.retained-publication-admission/1', 'verdict': 'PASS_WITH_DECLARED_PROVENANCE_LIMITS',
            'C': C, 'C_tree': C_TREE, 'H': H, 'H_tree': H_TREE, 'run': RUN, 'run_attempt': 1, 'historical_CI_conclusion': 'failure',
            'artifact_id': 13375695310, 'archive_sha256': ARCHIVE_SHA, 'public_manifest_sha256': MANIFEST_SHA,
            'manifest': list(rows.values()), 'reports': reports, 'projections': projections,
            'input_rows': input_rows, 'inherited_rows': inherited_rows, 'native_provenance': f,
            'unavailable_original_controls': [r for r in rows.values() if r['changed']],
            'native_executable_bytes_available': False, 'original_attempts': 17,
            'new_native_execution': False, 'Studio_released': False, 'M1b_released': False,
            'limits': ['published control views authenticate metadata, not unavailable original control bytes',
                       'native source and original report outcomes attest internal pointer/view/mutation guards; no native replay',
                       'native binary, runner host, native libraries and loaded-image provenance not newly inspected',
                       'native memory/physical IO/wiring unknowns retained; no physical-cap claim']}
