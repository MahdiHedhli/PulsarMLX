"""Host-only integration controls. No native launch and no real output grading.

Test data copies structural report metadata, replaces EVERY numerical output
with controlled zero bytes, and mocks physical admission and CPU child execution.
Production has no synthetic-mode flag. Context/readiness mocks exist only here.
"""
import copy
from contextlib import ExitStack, redirect_stdout
import io
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import studio_bridge as b
import studio_qualify as s

TEST_ROOT = Path(os.environ['RUST012_TEST_EVIDENCE'])
C_ROOT = Path(os.environ['RUST012_C_SOURCE'])
Q_ROOT = Path(os.environ['RUST012_Q_SOURCE'])
INPUT = Path(os.environ['RUST012_REFERENCE_INPUTS'])
OLD = Path(os.environ['RUST012_RETAINED_ARTIFACT'])
ROOTS = {'C': C_ROOT, 'Q': Q_ROOT, 'R': s.ROOT}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b.canonical(value))


def ci_paths():
    return {'response': str(TEST_ROOT/'rust011__response.md'),
            'response_checksum': str(TEST_ROOT/'rust011__response.md.sha256'),
            'handoff': str(TEST_ROOT/'rust011__handoff.json'),
            'supplement': str(TEST_ROOT/'rust011__retained-numerical-requalification.json.gz')}


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.modules, cls.origins = b.load_modules(ROOTS)
        cls.manifest = b.read(INPUT/'fixtures/manifest.json')
        cls.inherited = b.read(C_ROOT/'fixtures/native-composition/manifest.json')
        cls.expected = cls.modules['report_checks'].expected_population(cls.manifest, cls.inherited)
        cls.saved = b.read(TEST_ROOT/'rust011-supplement.public.json')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='studio-bridge-test-', dir=TEST_ROOT)
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_actual_module_origins_and_no_bytecode(self):
        self.assertTrue(sys.dont_write_bytecode)
        for name, (role, path, digest) in b.PINS.items():
            self.assertEqual(Path(self.modules[name].__file__).resolve(), ROOTS[role]/path)
            self.assertEqual(b.sha(ROOTS[role]/path), digest)
        self.assertEqual(self.modules['m1a_continuation'].REPO, C_ROOT)
        self.assertEqual(self.modules['reference'].REPO, C_ROOT)

    def test_shadow_preloaded_and_wrong_root_refused(self):
        with patch.dict(sys.modules, {'reference': types.SimpleNamespace(__file__=str(s.ROOT/'reference.py'))}):
            with self.assertRaisesRegex(ValueError, 'preloaded/shadow'):
                b.load_modules(ROOTS)
        wrong = {**ROOTS, 'C': Q_ROOT}
        with self.assertRaisesRegex(ValueError, 'origin drift'):
            b.load_modules(wrong)

    def test_changed_helper_hash_refused(self):
        wrong = dict(b.PINS); row = list(wrong['retained_rational']); row[2] = '0'*64; wrong['retained_rational'] = row
        with patch.object(b, 'PINS', wrong), self.assertRaisesRegex(ValueError, 'helper identity'):
            b.load_modules(ROOTS)

    def test_source_identity_wrong_checkout_and_protected_modes(self):
        with self.assertRaisesRegex(ValueError, 'C checkout identity'):
            b.source_identity({**ROOTS, 'C': Q_ROOT, 'Q': C_ROOT}, {'commit': b.Q, 'tree': b.QT})
        for role, root, pin in [('C', C_ROOT, b.C), ('Q', Q_ROOT, b.Q)]:
            rows = b.inventory(root, pin)
            self.assertEqual(len(rows), 5085 if role == 'C' else 5090)

    def test_actual_c_source_inventory_under_installed_guard(self):
        import hashlib
        m = self.modules['m1a_continuation']
        inventory = m.source_inventory(b.C, b.CT)
        self.assertEqual(len(inventory['files']), 70)
        self.assertEqual(hashlib.sha256(m.canonical(inventory['files'])).hexdigest(),
                         '0fba859129320b062a909d0039f7d79af81d510676d18410376676081a6b60e6')

    def test_complete_actual_saved_ci_decisions_without_regrading(self):
        value = b.ci_prerequisite(ci_paths(), self.expected)
        self.assertEqual(value['counts'], b.COUNTS)
        self.assertFalse(value['original_local_verified'])
        self.assertEqual(value['ci_workflow_conclusion'], 'failure')
        self.assertEqual(value['unavailable_original_controls'], 124)
        self.assertEqual(value['managed_callbacks'], 26)

    def test_ci_tampering_missing_and_original_public_distinction(self):
        paths = ci_paths(); bad = self.root/'bad.gz'; bad.write_bytes(Path(paths['supplement']).read_bytes()+b'x')
        with self.assertRaises(ValueError):
            b.ci_prerequisite({**paths, 'supplement': str(bad)}, self.expected)
        with self.assertRaises(FileNotFoundError):
            b.ci_prerequisite({**paths, 'handoff': str(self.root/'missing')}, self.expected)
        with self.assertRaises(ValueError):
            b.ci_prerequisite({**paths, 'original_supplement': str(TEST_ROOT/'rust011-supplement.public.json')}, self.expected)

    def test_saved_gate_binding_and_deferral_refusals(self):
        rows = self.saved['reports']
        self.assertEqual(b.gate_counts(rows, self.expected), b.COUNTS)
        for mutate in (
            lambda r: r.pop(), lambda r: r.reverse(),
            lambda r: r[0]['exact_gates'][0]['gates']['G-QMM-EXACT'].update({'pass': False}),
            lambda r: r[0]['rust_cases'][0].update({'G-QMM-RUST': 'FAIL'}),
            lambda r: r[0]['exact_gates'][0].update({'id': 'crossed'}),
            lambda r: next(c for row in r for c in row['rust_cases'] if c['id'] in b.FULL).update({'rust': {}}),
        ):
            changed = copy.deepcopy(rows); mutate(changed)
            with self.assertRaises(ValueError):
                b.gate_counts(changed, self.expected)

    def test_frozen_reference_identity_and_census(self):
        raw = b.bounded(INPUT/'reference.json')
        _, census = self.modules['retained_rational'].frozen_view(raw, self.manifest)
        self.assertEqual(sum(v['converted'] for v in census['totals'].values()), 12288)
        self.assertEqual(sum(v['unchanged'] for v in census['totals'].values()), 37888)
        with self.assertRaisesRegex(ValueError, 'reference hash'):
            self.modules['retained_rational'].frozen_view(raw+b' ', self.manifest)
        changed = copy.deepcopy(self.manifest); changed['cases'][0]['M'] += 1
        with self.assertRaisesRegex(ValueError, 'geometry'):
            self.modules['retained_rational'].frozen_view(raw, changed)

    def test_actual_gate_rejects_controlled_bad_outputs(self):
        exact = {'k': 1, 'y_exact': ['0/1'], 'phi_exact': ['0/1']}
        case = {'id': 'synthetic', 'expected': {'families_0_31_2': [{'gamma_n': 1}]}}
        for value in (1.0, float('nan'), float('inf')):
            p = self.root/'output.f32'; p.write_bytes(struct.pack('<f', value))
            record = {'id': 'synthetic', 'output': {'file': p.name, 'dtype': 'F32', 'sha256': b.sha(p)}}
            gate = self.modules['exact_gates_v1'].decide_qmm(case, exact, None, record, self.root)
            self.assertFalse(gate['G-QMM-EXACT']['pass'])
        record['output']['sha256'] = '0'*64
        with self.assertRaises(ValueError):
            self.modules['exact_gates_v1'].decide_qmm(case, exact, None, record, self.root)
        record['output']['sha256'] = b.sha(p); exact['y_exact'] *= 2
        with self.assertRaises(ValueError):
            self.modules['exact_gates_v1'].decide_qmm(case, exact, None, record, self.root)

    def test_original_c_host_and_phase_refusals(self):
        m = self.modules['m1a_continuation']
        with self.assertRaisesRegex(ValueError, 'retained Studio environment changed'):
            m.host_facts(s.ROLE)
        r = copy.deepcopy(self.saved['admission']['native_provenance'])
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'explicit m1a'):
            m.revalidate(r)
        r['host_role'] = s.ROLE
        with self.assertRaisesRegex(ValueError, 'closed host/raw'):
            m.scope(r)

    def test_environment_no_production_macbook_fallback(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, 'explicit future'):
            s.environment()
        for key in ('MLX_PREFIX', 'GITHUB_ACTIONS', 'DYLD_INSERT_LIBRARIES', 'GIT_CONFIG_COUNT'):
            with patch.dict(os.environ, {'PULSAR_ADOPTION_PHASE': 'm1a', key: 'forbidden'}, clear=True), self.assertRaises(ValueError):
                s.environment()

    def test_authority_rust012_synthetic_and_wrong_hash_refused(self):
        a = {'schema': s.GRANT, 'purpose': 'STUDIO_FULL_M1A_ONCE', 'evidence_role': 'OPERATOR_AUTHORITY',
             'launch_authorized': True, 'synthetic': True}
        path = self.root/'authority.json'; write(path, a)
        (self.root/'authority.json.sha256').write_text(b.sha(path)+'  authority.json\n')
        with self.assertRaisesRegex(ValueError, 'synthetic'):
            s.authority(path, b.sha(path))
        with self.assertRaisesRegex(ValueError, 'authority bytes'):
            s.authority(path, '0'*64)
        a.update(synthetic=False, phase='m1a', host_role=s.ROLE, raw_policy=s.POLICY, contract_sha256=b.CONTRACT,
                 native_parent_allowance=1, numerical_allowance=1, new_raw_allowance=0, M1b_released=False, shipping_default='copied',
                 prompt={'commit': '30943cefe903b464b8b5ab57debfebc578bc4862', 'sha256': b.IMPLEMENTATION_PROMPT})
        write(path, a); (self.root/'authority.json.sha256').write_text(b.sha(path)+'  authority.json\n')
        with self.assertRaisesRegex(ValueError, 'Rust012 cannot'):
            s.authority(path, b.sha(path))

    def test_actual_allowlist_no_shell_native_network_or_arbitrary_git(self):
        g = b.Guard(ROOTS)
        for exe, argv in [('sh', ['sh', '-c', 'true']), ('curl', ['curl', 'https://example.invalid']),
                          ('git', ['git', '-C', str(C_ROOT), 'fetch']), ('git', ['git', '-c', 'x=y', 'status']),
                          ('/native/parent', ['/native/parent']), ('git', ['git', '-C', '/tmp', 'status', '--porcelain'])]:
            with self.assertRaises(ValueError):
                g.check('subprocess.Popen', (exe, argv, None, None))
        for event, args in [('socket.connect', ()), ('ctypes.dlopen', ()), ('os.system', ()), ('import', ('mlx.core',))]:
            with self.assertRaises(ValueError):
                g.check(event, args)
        for argv, cwd in [(['git', '-C', str(C_ROOT), 'rev-parse', 'HEAD'], None),
                          (['git', 'status', '--porcelain'], str(C_ROOT)),
                          (['/usr/sbin/sysctl', '-n', 'hw.model'], None), (['/usr/bin/sw_vers', '-buildVersion'], None)]:
            g.check('subprocess.Popen', (argv[0], tuple(argv), cwd, None))

    def test_installed_audit_hook_refuses_actual_shell_launch(self):
        with self.assertRaisesRegex(ValueError, 'unapproved executable'):
            subprocess.Popen(['/bin/sh', '-c', 'exit 0'])

    def test_original_install_custody_cannot_be_relocated(self):
        native = self.root/'installation/original.json'; write(native, {'synthetic': True})
        duplicate = self.root/'copied-installation/copied.json'; write(duplicate, {'synthetic': True})
        originals = {'native_install': str(native)}
        for key in ('freeze', 'diagnostic_receipt'):
            p = self.root/'originals'/(key+'.json'); write(p, {'native_build_receipt': str(native)})
            originals[key] = str(p)
        mapping = self.root/'original-map.json'; write(mapping, originals)
        pins = {k: {'bytes': Path(v).stat().st_size, 'sha256': b.sha(v)} for k, v in originals.items()}
        a = {'original_custody': originals, 'paths': {'native_install': str(native), 'originals': str(mapping),
             'fixture_root': str(self.root/'fixtures'), 'native_prefix': str(self.root/'native-prefix'),
             'state': str(self.root/'state'), 'campaign': str(self.root/'campaign'), 'output': str(self.root/'output')}}
        ctx = {'authority': a, 'roots': ROOTS}; read = b.read
        def selected(path):
            return pins if str(path).endswith('continuation-studio-originals-v1.json') else read(path)
        with patch.object(b, 'read', side_effect=selected):
            self.assertEqual(s.check_locations(ctx), originals)
            originals['native_install'] = str(duplicate); write(mapping, originals); a['paths']['native_install'] = str(duplicate)
            with self.assertRaisesRegex(ValueError, 'historical installation location'):
                s.check_locations(ctx)

    def test_claim_occupancy_precedes_readiness(self):
        ctx, _, ready = self.fixture(); write(s.claim_paths(ctx['authority'])[0], {'uncertain': True})
        with patch.object(s, 'readiness', return_value=ready) as call, self.assertRaisesRegex(ValueError, 'occupied/foreign'):
            s.prepare(ctx)
        call.assert_not_called()

    def test_tracked_modes_are_verified(self):
        import hashlib
        root = self.root/'source'; root.mkdir(); p = root/'example.py'; p.write_bytes(b'pass\n')
        digest = hashlib.sha1(b'blob 5\0pass\n').hexdigest()
        record = ('100755 blob '+digest+'\texample.py\0').encode()
        with patch.object(b.subprocess, 'check_output', return_value=record), self.assertRaisesRegex(ValueError, 'mode/type'):
            b.inventory(root, b.C)

    def test_readiness_interface_and_changed_native_stack(self):
        ctx, freeze, _ = self.fixture(); a = ctx['authority']; p = a['paths']; p['binary'] = str(self.root/'mock-native')
        for name in ('binary', 'parent'):
            Path(p[name]).write_bytes(b'SYNTHETIC NONEXECUTABLE')
        python = str(Path(sys.executable).resolve())
        a['executables'] = {k: {'path': p[k], 'sha256': b.sha(p[k])} for k in ('binary', 'parent', 'grader')}
        a['executables']['python'] = {'path': python, 'sha256': b.sha(python)}
        a['sources'] = {'R': {'commit': 'a'*40, 'tree': 'b'*40}}; a['ci_files'] = ci_paths()
        linkage = {k: ['SYNTHETIC linkage'] for k in a['executables']}
        build = self.root/'build.json'; write(build, {'schema': 'pulsarmlx.studio-c-build-identity/1', 'source_commit': b.C, 'source_tree': b.CT, 'executables': a['executables'], 'linkage': linkage})
        a['build_identity'] = {'path': str(build), 'sha256': b.sha(build)}
        ctx.update(source={'synthetic': True}, origins=self.origins)
        inventory = self.saved['admission']['native_provenance']['source_inventory']
        native = {'native': 'SYNTHETIC'}; raw = {'native_libraries': freeze['native_libraries']}
        m = self.modules['m1a_continuation']
        with ExitStack() as stack:
            stack.enter_context(patch.object(s, 'authority', return_value=a))
            stack.enter_context(patch.object(b, 'source_identity', return_value=ctx['source']))
            stack.enter_context(patch.object(s, 'check_locations', return_value={}))
            stack.enter_context(patch.object(self.modules['copied_diagnostic'], 'linkage', return_value=['SYNTHETIC linkage']))
            stack.enter_context(patch.object(m, 'host_facts', return_value={'physical': 'SYNTHETIC'}))
            native_check = stack.enter_context(patch.object(m, 'native_state', return_value=native))
            stack.enter_context(patch.object(self.modules['freeze_host'], 'prepare', return_value=freeze))
            stack.enter_context(patch.object(m, 'original_studio', return_value=raw))
            stack.enter_context(patch.object(m, 'source_inventory', return_value=inventory))
            result = s.readiness(ctx)
            self.assertEqual(result['ci_prerequisite']['counts'], b.COUNTS)
            self.assertEqual(result['normalization']['totals']['y_exact']['converted'], 8192)
            native_check.side_effect = ValueError('native bindings changed')
            with self.assertRaisesRegex(ValueError, 'native bindings changed'):
                s.readiness(ctx)
        self.assertFalse(Path(p['state']).exists())

    def test_grader_hash_and_exact_argv_allowlist(self):
        p = self.root/'mock-grader'; p.write_bytes(b'never executed')
        g = b.Guard(ROOTS); argv = [str(p), 'portable', 'inherited', 'report', 'result']
        g.child = {'argv': argv, 'sha256': b.sha(p)}
        g.check('subprocess.Popen', (str(p), argv, None, None))
        with self.assertRaises(ValueError):
            g.check('subprocess.Popen', (str(p), argv+['extra'], None, None))
        p.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'grader changed'):
            g.check('subprocess.Popen', (str(p), argv, None, None))

    def test_real_cpu_child_timeout_kills_and_waits_only_owned_child(self):
        proc = unittest.mock.Mock(pid=17); proc.wait.side_effect = [subprocess.TimeoutExpired(['mock'], 0.25), 9]; proc.poll.return_value = None
        with patch.object(self.modules['retained_qualify'].subprocess, 'Popen', return_value=proc) as launch:
            with self.assertRaises(subprocess.TimeoutExpired):
                self.modules['retained_qualify'].cpu_child({'sha256': 'test'}, ['mock'], self.root, 0.25)
        launch.assert_called_once(); proc.kill.assert_called_once(); self.assertEqual(proc.wait.call_count, 2)
        self.assertEqual(proc.wait.call_args_list[0].kwargs, {'timeout': 0.25})
        self.assertTrue(b.read(self.root/'rust-gates.outcome.json')['owned_child_killed_and_reaped'])

    def fixture(self):
        """Synthetic outputs only; original CI numerical files are never opened."""
        native = self.root/'installation/receipt.json'; write(native, {'evidence_role': 'SYNTHETIC_TEST_DATA'})
        grader = self.root/'mock-grader'; grader.write_bytes(b'NO EXECUTABLE; mocked boundary')
        p = {'state': str(self.root/'state'), 'campaign': str(self.root/'campaign'), 'output': str(self.root/'result'),
             'fixture_root': str(INPUT/'fixtures'), 'portable': str(INPUT/'portable.json'), 'reference': str(INPUT/'reference.json'),
             'native_install': str(native), 'parent': str(self.root/'mock-parent'), 'grader': str(grader)}
        authority = {'synthetic': True, 'paths': p, 'executables': {'grader': {'sha256': b.sha(grader)}, 'parent': {'sha256': 'mock-parent'}}}
        ctx = {'authority': authority, 'authority_path': str(self.root/'synthetic-authority'), 'authority_sha256': 'synthetic-test-only',
               'roots': ROOTS, 'modules': self.modules, 'guard': b.Guard(ROOTS)}
        freeze = copy.deepcopy(self.saved['admission']['native_provenance'])
        freeze.update(source_root=str(C_ROOT), host_role=s.ROLE, raw_policy=s.POLICY, raw_probe_budget={'allowed': 1, 'used': 1},
                      raw_execution_authorized=False, raw_provenance={'applies_to_current_binary': False, 'evidence_kind': 'historical_host_native_stack'},
                      campaign=p['campaign'], fixture_root=p['fixture_root'], portable_report=p['portable'], reference=p['reference'],
                      native_build_receipt=p['native_install'], parent=p['parent'], rust_grader=p['grader'], inherited_root=str(C_ROOT/'fixtures/native-composition'),
                      population=self.expected, evidence_role='SYNTHETIC_TEST_DATA')
        p['binary'] = freeze['binary']; p['native_prefix'] = freeze['native_prefix']
        ready = {k: freeze[k] for k in ('host_facts', 'native_state', 'raw_provenance')}
        ready['normalization'] = {'evidence_role': 'SYNTHETIC_TEST_DATA'}
        return ctx, freeze, ready

    def campaign(self, ctx, freeze):
        p = ctx['authority']['paths']; campaign = Path(p['campaign']); write(campaign/'freeze.json', freeze)
        write(s.claim_paths(ctx['authority'])[0], {'campaign_identity': self.modules['m1a_continuation'].CAMPAIGN,
                                                  'campaign': str(campaign), 'receipt_sha256': b.sha(campaign/'freeze.json')})

    def reports(self, ctx, freeze):
        root = Path(ctx['authority']['paths']['campaign'])/'m1a'; root.mkdir()
        binding = self.modules['m1a_continuation'].binding(root.parent)
        write(root.parent/'continuation-attempt.json', binding)
        mechanism = {'mechanism': 'PASS', 'M1b_released': False, 'continuation': binding, 'reports': []}
        for key in ('contract_sha256', 'source_commit', 'source_tree', 'binary_sha256', 'fixture_manifest_sha256', 'host_role'):
            mechanism[key] = freeze[key]
        write(root/'injected-controls.json', {'C-GEOMETRY': {'reached': True, 'native_calls': 0},
                                             'C-CALLBACK': {'reached': True, 'injected': True, 'native_fallback_claim': False}})
        view = {'fixture_manifest_sha256': freeze['fixture_manifest_sha256'], 'cases': {}}
        exact_by_id = {}; rust_by_id = {}
        for label, (ids, arm, kind) in self.expected.items():
            directory = root/label; directory.mkdir(); old = OLD/'campaign/m1a'
            run = b.read(old/label/'run.json'); config = b.read(old/(label+'.config.json')); outcome = b.read(old/(label+'.outcome.json'))
            events = [b.parse(line) for line in b.bounded(old/label/'events.jsonl').splitlines()]
            run['evidence_role'] = config['evidence_role'] = outcome['evidence_role'] = 'SYNTHETIC_TEST_DATA'
            config['fixture_root'] = freeze['fixture_root']; config['inherited_root'] = freeze['inherited_root']
            outputs = run['outputs'] if kind == 'group' else [run['output']]
            for i, out in enumerate(outputs):
                cid = ids[i]; shape = out['shape'] if kind == 'group' else [next(c for c in self.inherited['cases'] if c['id']==cid)['params'][k] for k in ('M_eff', 'N')]
                n = shape[0]*shape[1]; numerical = directory/out['file']; numerical.write_bytes(bytes(n*4)); out['sha256'] = b.sha(numerical)
                exact = {'k': 1, 'y_exact': ['0/1']*n, 'phi_exact': ['0/1']*n}
                rust = None if cid in b.FULL else {'y': ['0000000000000000']*n, 'phi': ['0000000000000000']*n}
                exact_by_id[cid] = exact; rust_by_id[cid] = rust
                if kind == 'group':
                    view['cases'][cid] = {'exact': exact, 'rust': rust, 'gamma_n': 1}
            operations = [e for e in events if e.get('phase') == 'operation']
            for e, out in zip(operations, outputs):
                e['output_sha256'] = out['sha256']
            write(root/(label+'.config.json'), config)
            run['config_sha256'] = outcome['config_sha256'] = b.sha(root/(label+'.config.json'))
            write(directory/'run.json', run); write(root/(label+'.outcome.json'), outcome)
            (directory/'events.jsonl').write_bytes(b''.join(b.canonical(e) for e in events))
            write(root/(label+'.continuation-intent.json'), binding)
            mechanism['reports'].append({'label': label, 'report': label+'/run.json'})
        write(root/'mechanism.json', mechanism)
        return view, exact_by_id, rust_by_id

    def run_sequence(self, mutate=None, fail_child=False, post_drift=False, repeat=False, output_race=False, report_drift=False):
        ctx, freeze, ready = self.fixture(); args = ['--authority', str(self.root/'synthetic-authority'), '--authority-sha256', 'synthetic-test-only', '--c-source', str(C_ROOT), '--q-source', str(Q_ROOT)]
        with ExitStack() as stack:
            stack.enter_context(patch.object(s, 'context', return_value=ctx))
            ready_mock = stack.enter_context(patch.object(s, 'readiness', return_value=ready))
            stack.enter_context(patch.object(self.modules['m1a_continuation'], 'revalidate', side_effect=lambda r: (self.modules['m1a_continuation'].scope(r), r)[1]))
            stack.enter_context(redirect_stdout(io.StringIO()))
            prepared = s.main(['prepare', *args]); self.assertFalse(s.claim_paths(ctx['authority'])[0].exists())
            self.campaign(ctx, freeze)
            bound = s.main(['bind', *args, '--ready-sha256', prepared['ready_sha256']])
            view, exact, rust = self.reports(ctx, freeze)
            stack.enter_context(patch.object(self.modules['retained_rational'], 'frozen_view', return_value=(view, ready['normalization'])))
            stack.enter_context(patch.object(self.modules['mlx_affine_qmm_reference_v1'], 'exact_case', side_effect=lambda c, root: exact[c['id']]))
            stack.enter_context(patch.object(self.modules['reference_budget'], 'start'))
            stack.enter_context(patch.object(self.modules['reference_budget'], 'check', return_value={'synthetic_memory_observation': True}))
            completion = self.root/'parent-completion.json'; stdout = self.root/'parent.stdout'; stdout.write_text('SYNTHETIC TEST, no parent executed\n')
            write(completion, {'schema': 'pulsarmlx.studio-parent-completion/1', 'exit_code': 0, 'reaped': True,
                               'bound_sha256': bound['bound_sha256'], 'receipt_sha256': b.sha(Path(freeze['campaign'])/'freeze.json'),
                               'parent_sha256': 'mock-parent', 'argv': [freeze['parent'], '--exact', 'required_native_m1a', '--test-threads=1', '--nocapture'],
                               'started_unix': 1, 'ended_unix': 2, 'stdout': {'path': str(stdout), 'sha256': b.sha(stdout)},
                               'stderr': {'path': str(stdout), 'sha256': b.sha(stdout)}})
            calls = []
            def child(grader, argv, directory, remaining):
                self.assertGreater(remaining, 0); self.assertLessEqual(remaining, 900)
                ctx['guard'].check('subprocess.Popen', (argv[0], argv, None, None))
                calls.append(argv)
                if fail_child:
                    raise subprocess.TimeoutExpired(argv, remaining)
                run = b.read(argv[3]); ids = [x['id'] for x in run['outputs']] if 'outputs' in run else [run['id']]
                cases = [{'id': cid, 'gate': 'selected exact original-input R1 required separately', 'rust': None} if cid in b.FULL else
                         {'id': cid, 'G-QMM-RUST': 'PASS', 'rust': rust[cid]} for cid in ids]
                write(Path(argv[4]), {'report_sha256': b.sha(argv[3]), 'cases': cases})
                if post_drift and len(calls) == 52:
                    ready_mock.side_effect = ValueError('post-pass changed host or authority')
                if report_drift and len(calls) == 52:
                    report = Path(freeze['campaign'])/'m1a/group-0-copied/run.json'
                    report.write_bytes(report.read_bytes()+b' ')
            stack.enter_context(patch.object(self.modules['retained_qualify'], 'cpu_child', side_effect=child))
            if mutate:
                mutate(ctx, freeze, completion)
            if output_race:
                real_create = b.create
                def race(path, value):
                    real_create(path, value)
                    if Path(path) == s.claim_paths(ctx['authority'])[1]:
                        Path(ctx['authority']['paths']['output']).mkdir()
                stack.enter_context(patch.object(b, 'create', side_effect=race))
            qualifier = ['qualify', *args, '--bound-sha256', bound['bound_sha256'], '--parent-completion', str(completion)]
            result = s.main(qualifier)
            if repeat:
                with self.assertRaisesRegex(ValueError, 'spent numerical'):
                    s.main(qualifier)
            return ctx, qualifier, calls, stack, result

    def test_full_mocked_production_entry_point_52_84_and_deferrals(self):
        ctx, _, calls, _, result = self.run_sequence(repeat=True)
        self.assertEqual(len(calls), 52); self.assertEqual(result['counts'], b.COUNTS)
        self.assertFalse((Path(ctx['authority']['paths']['campaign'])/'m1a-acceptance.json').exists())
        saved = b.read(Path(ctx['authority']['paths']['output'])/s.RESULT)
        self.assertEqual(saved['ci_workflow_conclusion'], 'failure'); self.assertFalse(saved['M1b_released'])
        self.assertTrue(s.claim_paths(ctx['authority'])[1].exists())

    def test_timeout_preserves_spent_claim_and_failure(self):
        with self.assertRaisesRegex(ValueError, 'claim spent'):
            self.run_sequence(fail_child=True)
        self.assertTrue((self.root/'installation'/s.NUMERICAL_CLAIM).exists())
        result = b.read(self.root/'result'/s.RESULT)
        self.assertEqual(result['verdict'], 'FAILED_NO_RETRY'); self.assertEqual(result['counts']['rust_invocations_attempted'], 1)

    def test_post_pass_drift_prevents_acceptance(self):
        with self.assertRaisesRegex(ValueError, 'post-pass changed'):
            self.run_sequence(post_drift=True)
        self.assertEqual(b.read(self.root/'result'/s.RESULT)['verdict'], 'FAILED_NO_RETRY')

    def test_post_pass_report_byte_drift_prevents_acceptance(self):
        with self.assertRaisesRegex(ValueError, 'campaign changed'):
            self.run_sequence(report_drift=True)
        self.assertEqual(b.read(self.root/'result'/s.RESULT)['verdict'], 'FAILED_NO_RETRY')

    def test_output_creation_race_never_writes_into_foreign_directory(self):
        with self.assertRaisesRegex(ValueError, 'claim spent'):
            self.run_sequence(output_race=True)
        self.assertEqual(list((self.root/'result').iterdir()), [])
        self.assertEqual(b.read(self.root/'state/qualification-failure.json')['verdict'], 'FAILED_NO_RETRY')

    def test_occupied_output_refused_before_numerical_claim(self):
        with self.assertRaisesRegex(ValueError, 'occupied output'):
            self.run_sequence(mutate=lambda ctx, f, p: Path(ctx['authority']['paths']['output']).mkdir())
        self.assertFalse((self.root/'installation'/s.NUMERICAL_CLAIM).exists())

    def test_prior_numerical_claim_refused(self):
        with self.assertRaisesRegex(ValueError, 'spent numerical'):
            self.run_sequence(mutate=lambda ctx, f, p: write(s.claim_paths(ctx['authority'])[1], {'unknown': True}))

    def test_parent_failure_refused_before_claim(self):
        def mutate(ctx, freeze, p):
            r = b.read(p); r['exit_code'] = 1; write(p, r)
        with self.assertRaisesRegex(ValueError, 'parent completion'):
            self.run_sequence(mutate=mutate)
        self.assertFalse((self.root/'installation'/s.NUMERICAL_CLAIM).exists())

    def test_native_claim_change_and_report_tampering_refused(self):
        def mutate(ctx, freeze, p):
            write(s.claim_paths(ctx['authority'])[0], {'unknown': True})
        with self.assertRaisesRegex(ValueError, 'stable consumed'):
            self.run_sequence(mutate=mutate)


if __name__ == '__main__':
    # Actual local commands carry no experiment/native/model environment.
    for key in ('PULSAR_ADOPTION_PHASE', 'MLX_PREFIX', 'MLX_C_PREFIX', 'PULSAR_REQUIRE_NATIVE_MLX', 'PULSARMLX_MODEL_GGUF'):
        if key in os.environ:
            raise RuntimeError('unsafe local test environment: '+key)
    safety = b.Guard(ROOTS)
    sys.addaudithook(safety.check)
    unittest.main(verbosity=2)
