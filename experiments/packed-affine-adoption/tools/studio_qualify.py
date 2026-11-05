#!/usr/bin/env python3
"""Future original-byte Studio prepare/bind/qualify; no native launcher.

Production requires a separately pinned later operator-authority file. Rust012,
Rust013 and its recovery amendment are implementation authority only. Tests
substitute synthetic external physical/execution boundaries.
"""
import argparse
import hashlib
import os
from pathlib import Path
import signal
import sys
import time
import traceback

import studio_bridge as b

ROOT = Path(__file__).resolve().parents[3]
ROLE = 'm1-ultra-studio'
POLICY = 'STUDIO_RETAINED_OBSERVATION'
SCHEMA = 'pulsarmlx.studio-qualification-bridge/1'
GRANT = 'pulsarmlx.studio-m1a-operator-authority/1'
RESULT = 'studio-live-m1a-acceptance.json'
NATIVE_CLAIM = 'f020-m1a-continuation.claim.json'
NUMERICAL_CLAIM = 'f020-studio-m1a-numerical.claim.json'
PATH_KEYS = ('state', 'campaign', 'output', 'fixture_root', 'portable', 'reference',
             'native_prefix', 'native_install', 'binary', 'parent', 'grader', 'originals')


def environment():
    b.equal(os.environ.get('PULSAR_ADOPTION_PHASE'), 'm1a', 'explicit future m1a phase required')
    bad = ('MLX_PREFIX', 'MLX_C_PREFIX', 'PULSAR_REQUIRE_NATIVE_MLX', 'PULSARMLX_MODEL_GGUF',
           'PULSAR_ADOPTION_HOST_ROLE', 'PULSAR_ADOPTION_CAMPAIGN', 'GITHUB_ACTIONS',
           'PYTHONPATH', 'PYTHONHOME', 'DYLD_LIBRARY_PATH', 'DYLD_INSERT_LIBRARIES', 'LD_PRELOAD')
    b.require(not any(k in os.environ for k in bad) and not any(k.startswith('GIT_') for k in os.environ), 'unsafe inherited environment')


def location(value, exists=True):
    p = Path(value)
    b.require(p.is_absolute() and str(p) == value and p.resolve(strict=exists) == p, 'actual canonical path required')
    return p


def authority(path, expected_hash):
    raw = b.bounded(path)
    b.equal(hashlib.sha256(raw).hexdigest(), expected_hash, 'operator authority bytes')
    side = b.bounded(str(path)+'.sha256', 512).decode().split()
    b.equal(side, [expected_hash, Path(path).name], 'operator authority sidecar')
    a = b.parse(raw)
    for k, v in {'schema': GRANT, 'purpose': 'STUDIO_FULL_M1A_ONCE', 'evidence_role': 'OPERATOR_AUTHORITY',
                 'launch_authorized': True, 'synthetic': False, 'phase': 'm1a', 'host_role': ROLE,
                 'raw_policy': POLICY, 'contract_sha256': b.CONTRACT,
                 'correction_contract_sha256': b.CORRECTION, 'source_profile_sha256': b.PROFILE_SHA256,
                 'native_parent_allowance': 1, 'numerical_allowance': 1, 'new_raw_allowance': 0,
                 'M1b_released': False, 'shipping_default': 'copied'}.items():
        b.equal(a.get(k), v, 'later Studio authority: '+k)
    prompt = a['prompt']
    b.require(prompt['commit'] not in b.FORBIDDEN_PROMPTS and prompt['sha256'] not in b.FORBIDDEN_PROMPTS.values(), 'Rust012/Rust013/Studio003 cannot authorize corrected Studio')
    b.require(len(prompt['commit']) == 40 and all(c in '0123456789abcdef' for c in prompt['commit']), 'prompt commit identity')
    prompt_bytes = b.bounded(prompt['path'])
    b.equal(hashlib.sha256(prompt_bytes).hexdigest(), prompt['sha256'], 'later prompt bytes')
    b.equal(b.bounded(prompt['path']+'.sha256', 512).decode().split(), [prompt['sha256'], Path(prompt['path']).name], 'later prompt sidecar')
    b.exact_file(a['contract_path'], (15561, b.CONTRACT))
    b.exact_file(a['correction_contract_path'], (20370, b.CORRECTION))
    b.equal(b.bounded(a['correction_contract_path']+'.sha256', 512).decode().split(),
            [b.CORRECTION, Path(a['correction_contract_path']).name], 'correction contract sidecar')
    b.source_profile()
    b.equal(a['historical_sources'], {'C': {'commit': b.CI_C, 'tree': b.CI_CT},
                                     'R': {'commit': b.ORIGINAL_R, 'tree': b.ORIGINAL_RT}}, 'historical authority source identities')
    b.equal(a['sources']['C'], {'commit': b.C, 'tree': b.CT}, 'authority C')
    b.equal(a['sources']['Q'], {'commit': b.Q, 'tree': b.QT}, 'authority Q')
    b.require(a['sources']['R']['commit'] not in (b.C, b.Q), 'distinct committed orchestration R')
    b.equal(sorted(a['paths']), sorted(PATH_KEYS), 'closed path roles')
    for k, v in a['paths'].items():
        location(v, k not in ('state', 'campaign', 'output'))
    b.require(a['paths']['state'] != a['paths']['campaign'] != a['paths']['output'] and a['paths']['state'] != a['paths']['output'], 'distinct owned state roots')
    return a


def context(args):
    environment()
    a = authority(args.authority, args.authority_sha256)
    roots = {'C': location(str(args.c_source)), 'Q': location(str(args.q_source)), 'R': ROOT}
    b.equal(a['roots'], {k: str(v) for k, v in roots.items()}, 'authority source locations')
    guard = b.Guard(roots)
    sys.addaudithook(guard.check)
    source = b.source_identity(roots, a['sources']['R'])
    modules, origins = b.load_modules(roots)
    return {'authority': a, 'authority_path': str(args.authority.resolve()), 'authority_sha256': args.authority_sha256,
            'roots': roots, 'source': source, 'modules': modules, 'origins': origins, 'guard': guard}


def expected_population(ctx):
    a = ctx['authority']; modules = ctx['modules']
    return modules['report_checks'].expected_population(b.read(Path(a['paths']['fixture_root'])/'manifest.json'),
                                                       b.read(ctx['roots']['C']/'fixtures/native-composition/manifest.json'))


def correction_binding(ctx):
    return {'contract_sha256': b.CORRECTION, 'source_profile_sha256': b.PROFILE_SHA256,
            'historical_C': {'commit': b.CI_C, 'tree': b.CI_CT},
            'current_C2': {'commit': b.C, 'tree': b.CT}, 'current_R2': ctx['authority']['sources']['R'],
            'source_delta': ctx['source']['source_delta'], 'C2_experimental_CI_acceptance': False}


def claim_paths(a):
    anchor = location(a['paths']['native_install'])
    return anchor.parent/NATIVE_CLAIM, anchor.parent/NUMERICAL_CLAIM


def check_locations(ctx):
    a = ctx['authority']; paths = a['paths']; originals = b.read(paths['originals'])
    b.equal(originals, a['original_custody'], 'original Studio custody map')
    b.equal(originals['native_install'], paths['native_install'], 'original installation anchor')
    pins = b.read(ctx['roots']['C']/b.EXP/'continuation-studio-originals-v1.json')
    b.equal(sorted(originals), sorted(pins), 'complete original custody')
    for name, pin in pins.items():
        location(originals[name]); b.exact_file(originals[name], (pin['bytes'], pin['sha256']))
    # Historical immutable bytes independently bind the original location. Merely
    # copying the install receipt and editing the authority cannot refund a claim.
    for key in ('freeze', 'diagnostic_receipt'):
        b.equal(b.read(originals[key])['native_build_receipt'], paths['native_install'], 'historical installation location')
    protected = [*ctx['roots'].values(), Path(paths['fixture_root']), Path(paths['native_prefix']),
                 *(Path(v).parent for v in originals.values())]
    state, campaign, output = (Path(paths[k]) for k in ('state', 'campaign', 'output'))
    for dest in (state, campaign, output):
        for root in protected:
            b.require(not dest.is_relative_to(root) and not root.is_relative_to(dest), 'state overlaps protected inputs')
    for left, right in ((state, campaign), (state, output), (campaign, output)):
        b.require(not left.is_relative_to(right) and not right.is_relative_to(left), 'nested output/campaign/state')
    return originals


def readiness(ctx):
    a = ctx['authority']; p = a['paths']; m = ctx['modules']; live = m['m1a_continuation']
    b.equal(authority(Path(ctx['authority_path']), ctx['authority_sha256']), a, 'authority drift')
    b.equal(b.source_identity(ctx['roots'], a['sources']['R']), ctx['source'], 'source drift')
    _, origins = b.load_modules(ctx['roots']); b.equal(origins, ctx['origins'], 'helper origin drift')
    originals = check_locations(ctx)
    guard = ctx['guard']
    for name in ('binary', 'parent', 'grader'):
        guard.link_paths.add(p[name])
    python = str(Path(sys.executable).resolve()); guard.link_paths.add(python)
    for lib in ('libmlx.dylib', 'libmlxc.dylib', 'libjaccl.dylib'):
        image = str(Path(p['native_prefix'])/'lib'/lib)
        guard.link_paths.add(image); guard.load_paths.add(image)
    executable = {name: {'path': p[name], 'sha256': b.sha(p[name])} for name in ('binary', 'parent', 'grader')}
    executable['python'] = {'path': python, 'sha256': b.sha(python)}
    b.equal(executable, a['executables'], 'fresh executable/build pins')
    # Build receipts are supplied by the future tracked build/verification and
    # sealed by its operator authority, separately from the retained installation.
    build = b.read(a['build_identity']['path'])
    b.equal(b.sha(a['build_identity']['path']), a['build_identity']['sha256'], 'C build receipt')
    b.equal(build['schema'], 'pulsarmlx.studio-c-build-identity/1', 'C build receipt schema')
    b.equal([build['source_commit'], build['source_tree']], [b.C, b.CT], 'native/grader build C')
    b.equal(build['executables'], executable, 'build executable identities')
    linkage = {name: m['copied_diagnostic'].linkage(row['path'], name != 'binary') for name, row in executable.items()}
    b.equal(linkage, build['linkage'], 'build/current linkage')
    facts = live.host_facts(ROLE)
    native = live.native_state(Path(p['native_prefix']), Path(p['native_install']), ROLE)
    args = argparse.Namespace(host_role=ROLE, source_commit=b.C, native_ci_acceptance=None,
                              fixture_root=Path(p['fixture_root']), portable=Path(p['portable']), reference=Path(p['reference']),
                              native_prefix=Path(p['native_prefix']), native_build_receipt=Path(p['native_install']),
                              binary=Path(p['binary']), parent=Path(p['parent']), rust_grader=Path(p['grader']))
    live.original_input_admission(args)
    prepared = m['freeze_host'].prepare(args)
    raw = live.original_studio(originals)
    b.equal(raw['native_libraries'], prepared['native_libraries'], 'retained current native stack')
    inventory = live.source_inventory(b.C, b.CT)
    profile = b.source_profile()
    b.equal(inventory['files'], profile['C2_experiment_inventory'], '72-row corrected native source inventory')
    b.equal(hashlib.sha256(live.canonical(inventory['files'])).hexdigest(), profile['C2_experiment_inventory_sha256'], 'corrected inventory digest')
    expected = expected_population(ctx)
    _, census = m['retained_rational'].frozen_view(b.bounded(p['reference']), b.read(Path(p['fixture_root'])/'manifest.json'))
    ci = b.ci_prerequisite(a['ci_files'], expected)
    return {'source': ctx['source'], 'origins': origins, 'executables': executable, 'linkage': linkage,
            'host_facts': facts, 'native_state': native, 'native_preparation': prepared, 'raw_provenance': raw,
            'normalization': census, 'ci_prerequisite': ci, 'originals': originals,
            'build_identity': a['build_identity'], 'population': expected, 'correction': correction_binding(ctx)}


def outer(ctx, ready):
    return {'schema': SCHEMA, 'authority_path': ctx['authority_path'], 'authority_sha256': ctx['authority_sha256'],
            'authority': ctx['authority'], 'readiness': ready, 'contract_sha256': b.CONTRACT,
            'correction': correction_binding(ctx),
            'native_claim': str(claim_paths(ctx['authority'])[0]), 'numerical_claim': str(claim_paths(ctx['authority'])[1]),
            'M1b_released': False, 'shipping_default': 'copied'}


def prepare(ctx):
    a = ctx['authority']; paths = a['paths']
    for p in [*(Path(paths[k]) for k in ('state', 'campaign', 'output')), *claim_paths(a)]:
        b.require(not os.path.lexists(p), 'occupied/foreign/uncertain claim or state')
    ready = readiness(ctx)
    # Repeat absence checks after read-only preparation; C remains claim owner.
    for p in [*(Path(paths[k]) for k in ('state', 'campaign', 'output')), *claim_paths(a)]:
        b.require(not os.path.lexists(p), 'claim appeared during preparation')
    state = Path(paths['state']); state.mkdir()
    path = state/'ready.json'; b.create(path, outer(ctx, ready))
    return {'ready_sha256': b.sha(path), 'native_claim_consumed': False, 'numerical_claim_consumed': False}


def checked_ready(ctx, digest):
    path = Path(ctx['authority']['paths']['state'])/'ready.json'
    b.equal(b.sha(path), digest, 'prepared seal bytes')
    ready = b.read(path)
    b.equal(ready, outer(ctx, readiness(ctx)), 'post-prepare source/host/input/authority drift')
    return ready


def live_receipt(ctx, ready):
    p = ctx['authority']['paths']; campaign = Path(p['campaign']); m = ctx['modules']['m1a_continuation']
    r = m.revalidate(b.read(campaign/'freeze.json')); m.require_claim(r, campaign)
    b.equal([r['source_commit'], r['source_tree'], r['source_root'], r['host_role'], r['raw_policy']],
            [b.C, b.CT, str(ctx['roots']['C']), ROLE, POLICY], 'live C Studio identity')
    for rk, pk in [('fixture_root', 'fixture_root'), ('portable_report', 'portable'), ('reference', 'reference'),
                   ('native_prefix', 'native_prefix'), ('native_build_receipt', 'native_install'), ('binary', 'binary'),
                   ('parent', 'parent'), ('rust_grader', 'grader'), ('campaign', 'campaign')]:
        b.equal(r[rk], p[pk], 'live receipt path: '+rk)
    for k in ('host_facts', 'native_state', 'raw_provenance'):
        b.equal(r[k], ready['readiness'][k], 'live receipt readiness: '+k)
    b.equal(str(m.stable_claim_path(r)), ready['native_claim'], 'native claim original anchor')
    return r


def bind(ctx, ready_hash):
    a = ctx['authority']; state = Path(a['paths']['state']); campaign = Path(a['paths']['campaign'])
    b.require(not os.path.lexists(state/'bound.json') and not os.path.lexists(claim_paths(a)[1]), 'occupied bridge/qualification')
    ready = checked_ready(ctx, ready_hash); r = live_receipt(ctx, ready)
    for name in ('continuation-attempt.json', 'm1a', 'raw-probe.intent.json', 'm1a-acceptance.json'):
        b.require(not os.path.lexists(campaign/name), 'parent already started before bridge binding')
    bound = {'schema': SCHEMA, 'ready_sha256': ready_hash, 'authority_sha256': ctx['authority_sha256'],
             'correction': correction_binding(ctx),
             'receipt_sha256': b.sha(campaign/'freeze.json'), 'native_claim_sha256': b.sha(ready['native_claim']),
             'native_claim': ready['native_claim'], 'numerical_claim': ready['numerical_claim'], 'receipt': r}
    b.create(state/'bound.json', bound)
    return {'bound_sha256': b.sha(state/'bound.json'), 'native_parent_started': False}


def tree_snapshot(root):
    rows = {}
    for p in sorted(root.rglob('*')):
        b.require(not p.is_symlink(), 'evidence symlink refused')
        if p.is_file():
            rows[str(p.relative_to(root))] = {'bytes': p.stat().st_size, 'sha256': b.sha(p)}
        else:
            b.require(p.is_dir(), 'nonregular campaign evidence')
    return rows


def current_reports(ctx, freeze):
    m = ctx['modules']; p = ctx['authority']['paths']; campaign = Path(p['campaign']); root = campaign/'m1a'
    f, mechanism, entries = m['report_checks'].check_campaign(campaign)
    b.equal(f, freeze, 'campaign freeze binding')
    expected = expected_population(ctx)
    b.equal([e['label'] for e in entries], list(expected), 'exact report order')
    manifest = b.read(Path(p['fixture_root'])/'manifest.json'); portable = b.read(p['portable'])
    cases = {c['id']: c for c in manifest['cases']}
    inherited = {c['id']: c for c in b.read(Path(f['inherited_root'])/'manifest.json')['cases'] if c['expected']['outcome'] == 'accept'}
    b.equal(sorted(p.name for p in root.iterdir() if p.is_dir()), sorted(expected), 'extra/missing ordinary report directories')
    b.equal(sorted(p.name for p in root.glob('*.config.json')), sorted(label+'.config.json' for label in expected), 'extra/missing original configs')
    outputs = []
    for entry in entries:
        label = entry['label']; ids, arm, kind = expected[label]; report_path = root/entry['report']
        run = b.read(report_path); config = root/(label+'.config.json'); outcome = root/(label+'.outcome.json')
        events = [b.parse(line) for line in b.bounded(report_path.parent/'events.jsonl').splitlines()]
        current = m['retained_admission'].report_semantics(f, expected, label, b.read(config), run, b.read(outcome), b.sha(config), manifest, portable, events)
        for i, out in enumerate(current):
            c = cases[ids[i]] if kind == 'group' else inherited[ids[i]]
            shape = [c['M'], c['H']] if kind == 'group' else [c['params']['M_eff'], c['params']['N']]
            if kind == 'group':
                b.equal([out['generation'], out['slot']], [i+1, 0], 'output generation/slot')
            else:
                matching = [e for e in events if e.get('id') == ids[i]]
                b.equal(matching[0]['source_identity'], c['oracle']['identity'], 'inherited composition identity')
            filename = 'output-'+str(i)+'.f32' if kind == 'group' else 'output.f32'
            path = m['report_checks'].confined(report_path.parent, filename)
            m['retained_admission'].output_geometry(out, shape, filename, path.stat().st_size, kind == 'group')
            b.equal(b.sha(path), out['sha256'], 'fresh original output bytes')
            outputs.append({'report': entry['report'], 'id': ids[i], 'arm': arm, 'path': str(path), 'sha256': out['sha256'], 'shape': shape})
        b.equal(sorted(x.name for x in report_path.parent.glob('*.f32')), sorted(x['file'] for x in current), 'extra/missing projection files')
    b.equal(len(outputs), 84, '84 original current outputs')
    return mechanism, entries, outputs


def parent_completion(ctx, bound_hash, bound, path):
    x = b.read(path); p = ctx['authority']['paths']
    expected = {'schema': 'pulsarmlx.studio-parent-completion/1', 'exit_code': 0, 'reaped': True,
                'bound_sha256': bound_hash, 'receipt_sha256': bound['receipt_sha256'],
                'parent_sha256': ctx['authority']['executables']['parent']['sha256'],
                'argv': [p['parent'], '--exact', 'required_native_m1a', '--test-threads=1', '--nocapture']}
    for k, v in expected.items():
        b.equal(x.get(k), v, 'observed parent completion: '+k)
    b.require(type(x['started_unix']) in (int, float) and type(x['ended_unix']) in (int, float) and 0 < x['started_unix'] <= x['ended_unix'], 'parent observation interval')
    for name in ('stdout', 'stderr'):
        b.equal(b.sha(x[name]['path']), x[name]['sha256'], 'parent capture identity')
    return {'path': str(path.resolve()), 'sha256': b.sha(path), 'record': x}


def qualify(ctx, bound_hash, completion_path):
    a = ctx['authority']; p = a['paths']; state = Path(p['state']); campaign = Path(p['campaign'])
    bound_path = state/'bound.json'; b.equal(b.sha(bound_path), bound_hash, 'bound seal bytes')
    bound = b.read(bound_path); ready = checked_ready(ctx, bound['ready_sha256'])
    freeze = live_receipt(ctx, ready)
    b.equal(bound['receipt'], freeze, 'post-bind receipt drift')
    b.equal(bound['authority_sha256'], ctx['authority_sha256'], 'bound authority')
    b.equal(bound['correction'], correction_binding(ctx), 'bound correction/source proof')
    b.equal(b.sha(campaign/'freeze.json'), bound['receipt_sha256'], 'bound original receipt hash')
    b.equal(b.sha(ready['native_claim']), bound['native_claim_sha256'], 'bound stable native claim')
    completion = parent_completion(ctx, bound_hash, bound, completion_path)
    m = ctx['modules']; mechanism, entries, outputs = current_reports(ctx, freeze)
    before = tree_snapshot(campaign)
    b.require(not any('rust-gates' in name or 'acceptance.json' in name for name in before), 'prior/unknown numerical work in original campaign')
    claim = claim_paths(a)[1]; output = Path(p['output'])
    b.require(not os.path.lexists(claim) and not os.path.lexists(output), 'spent numerical claim or occupied output')
    intent = {'schema': SCHEMA, 'bound_sha256': bound_hash, 'authority_sha256': ctx['authority_sha256'],
              'native_claim_sha256': bound['native_claim_sha256'], 'campaign': p['campaign'], 'output': p['output'],
              'attempt': 1, 'allowance_consumed': True, 'started_unix': time.time()}
    b.create(claim, intent)  # stable namespace; every subsequent failure stays spent
    intent_hash = b.sha(claim); rows = []; count = 0; failure = None; label = None; envelope = None; output_owned = False
    started = time.monotonic(); deadline = started+900
    try:
        output.mkdir()
        output_owned = True
        m['reference_budget'].start()
        signal.setitimer(signal.ITIMER_REAL, max(0.001, deadline-time.monotonic()))
        view, census = m['retained_rational'].frozen_view(b.bounded(p['reference']), b.read(Path(p['fixture_root'])/'manifest.json'))
        b.equal(census, ready['readiness']['normalization'], 'frozen rational semantics')
        inherited = Path(freeze['inherited_root'])
        cases = {c['id']: c for c in b.read(inherited/'manifest.json')['cases'] if c['expected']['outcome'] == 'accept'}
        grader = {'path': p['grader'], 'sha256': a['executables']['grader']['sha256']}
        for entry in entries:
            envelope = m['reference_budget'].check(); label = entry['label']
            report = campaign/'m1a'/entry['report']; run = b.read(report); directory = output/label; directory.mkdir()
            result_path = directory/'rust-gates.json'
            argv = [grader['path'], p['portable'], str(inherited), str(report), str(result_path)]
            b.equal(b.sha(grader['path']), grader['sha256'], 'grader hash before invocation')
            count += 1; ctx['guard'].child = {'argv': argv, 'sha256': grader['sha256']}
            try:
                m['retained_qualify'].cpu_child(grader, argv, directory, deadline-time.monotonic())
            finally:
                ctx['guard'].child = None
            rust = b.read(result_path)
            b.equal(rust['report_sha256'], b.sha(report), 'Rust current report binding')
            if run.get('population') == 'inherited_slice2c_changed_import':
                b.equal([c['id'] for c in rust['cases']], [run['id']], 'inherited Rust binding')
                c = cases[run['id']]; exact = m['mlx_affine_qmm_reference_v1'].exact_case(c, inherited)
                gates = [{'id': run['id'], 'gates': m['exact_gates_v1'].decide_qmm(c, exact, rust['cases'][0]['rust'], run, report.parent)}]
            else:
                gates = m['retained_rational'].grade_compatible(view, report)
            row = {'label': label, 'report_sha256': b.sha(report), 'rust_gates_sha256': b.sha(result_path),
                   'rust_cases': rust['cases'], 'exact_gates': gates}
            b.create(directory/'exact-gates.json', gates); rows.append(row)
            for g in gates:
                b.require(all(v is None or v['pass'] is True for v in g['gates'].values()), 'numerical failure')
        counts = b.gate_counts(rows, expected_population(ctx))
        b.equal(count, 52, '52 actual grader invocations')
        b.equal(checked_ready(ctx, bound['ready_sha256']), ready, 'post-pass readiness drift')
        b.equal(live_receipt(ctx, ready), freeze, 'post-pass live admission')
        b.equal(current_reports(ctx, freeze), (mechanism, entries, outputs), 'post-pass current reports drift')
        b.equal(tree_snapshot(campaign), before, 'original campaign changed during grading')
        b.equal(b.sha(bound_path), bound_hash, 'post-pass bound seal drift')
        b.equal(b.sha(claim), intent_hash, 'owned numerical intent changed')
        b.equal(b.read(claim), intent, 'owned numerical intent fields changed')
        b.equal(parent_completion(ctx, bound_hash, bound, completion_path), completion, 'parent evidence drift')
        b.require(time.monotonic() <= deadline, 'whole-pass deadline exceeded')
        envelope = m['reference_budget'].check()
    except BaseException as e:
        failure = {'type': type(e).__name__, 'message': str(e), 'label': label, 'traceback': traceback.format_exc(),
                   'case': getattr(e, 'case', None), 'gates': getattr(e, 'gates', None)}
        counts = {'rust_invocations_attempted': count, 'completed_reports': len(rows)}
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        ctx['guard'].child = None
    result = {'schema': 'pulsarmlx.studio-live-m1a-acceptance/1', 'verdict': 'PASS' if failure is None else 'FAILED_NO_RETRY',
              'correction': correction_binding(ctx), 'combined_cross_host_decision': 'PENDING',
              'failure': failure, 'authority': a, 'readiness': ready, 'bound_sha256': bound_hash, 'native_receipt': freeze,
              'native_claim_sha256': bound['native_claim_sha256'], 'numerical_intent_sha256': intent_hash,
              'parent_completion': completion, 'mechanism': mechanism, 'outputs': outputs, 'reports': rows, 'counts': counts,
              'elapsed_seconds': time.monotonic()-started, 'reference_envelope': envelope,
              'memory_limit_interpretation': 'Observed reference-working-data budget; not an OS-enforced combined physical cap',
              'ci_prerequisite_kind': 'RETAINED_C_MECHANISM_PLUS_Q_NUMERICS', 'ci_workflow_conclusion': 'failure',
              'current_raw_children': 0, 'native_launches_by_R': 0, 'legacy_acceptance_created': False,
              'M1b_released': False, 'M2_M4_started': False, 'shipping_default': 'copied'}
    destination = output/RESULT if output_owned else state/'qualification-failure.json'
    b.create(destination, result)
    if failure:
        raise ValueError('numerical claim spent; failure preserved: '+failure['message'])
    return {'verdict': 'PASS', 'counts': counts, 'result_sha256': b.sha(destination), 'M1b_released': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prepare', 'bind', 'qualify'))
    parser.add_argument('--authority', type=Path, required=True)
    parser.add_argument('--authority-sha256', required=True)
    parser.add_argument('--c-source', type=Path, required=True)
    parser.add_argument('--q-source', type=Path, required=True)
    parser.add_argument('--ready-sha256'); parser.add_argument('--bound-sha256')
    parser.add_argument('--parent-completion', type=Path)
    args = parser.parse_args(argv)
    b.require(args.stage != 'bind' or args.ready_sha256 is not None, 'bind requires ready seal hash')
    b.require(args.stage != 'qualify' or (args.bound_sha256 is not None and args.parent_completion is not None), 'qualify requires bound seal and parent outcome')
    ctx = context(args)
    if args.stage == 'prepare':
        result = prepare(ctx)
    elif args.stage == 'bind':
        result = bind(ctx, args.ready_sha256)
    else:
        result = qualify(ctx, args.bound_sha256, args.parent_completion)
    print(b.canonical(result).decode(), end='')
    return result


if __name__ == '__main__':
    main()
