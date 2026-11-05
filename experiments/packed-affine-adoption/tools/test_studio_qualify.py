"""Host-only integration controls. No native launch and no real output grading.

Test data copies structural report metadata, replaces EVERY numerical output
with controlled zero bytes, and mocks physical admission and CPU child execution.
Production has no synthetic-mode flag. Context/readiness mocks exist only here.
"""
import copy
from contextlib import ExitStack, redirect_stdout
import io
import importlib.util
import hashlib
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
        cls.current_inventory = cls.modules['m1a_continuation'].source_inventory(b.C, b.CT)

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
        with self.assertRaisesRegex(ValueError, 'helper identity|origin drift'):
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
            self.assertEqual(len(rows), 5087 if role == 'C' else 5090)

    def test_actual_c_source_inventory_under_installed_guard(self):
        import hashlib
        m = self.modules['m1a_continuation']
        inventory = m.source_inventory(b.C, b.CT)
        self.assertEqual(len(inventory['files']), 72)
        self.assertEqual(hashlib.sha256(m.canonical(inventory['files'])).hexdigest(),
                         b.source_profile()['C2_experiment_inventory_sha256'])

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
                 correction_contract_sha256=b.CORRECTION, source_profile_sha256=b.PROFILE_SHA256,
                 native_parent_allowance=1, numerical_allowance=1, new_raw_allowance=0, M1b_released=False, shipping_default='copied',
                 prompt={'commit': '30943cefe903b464b8b5ab57debfebc578bc4862', 'sha256': b.IMPLEMENTATION_PROMPT})
        write(path, a); (self.root/'authority.json.sha256').write_text(b.sha(path)+'  authority.json\n')
        with self.assertRaisesRegex(ValueError, 'cannot authorize corrected Studio'):
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
        ctx.update(source={'source_delta': {'synthetic': True}}, origins=self.origins)
        inventory = self.current_inventory
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
            old_build = b.read(build); old_build.update(source_commit=b.CI_C, source_tree=b.CI_CT)
            write(build, old_build); a['build_identity']['sha256'] = b.sha(build)
            with self.assertRaisesRegex(ValueError, 'native/grader build C'):
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
        authority['sources'] = {'C': {'commit': b.C, 'tree': b.CT}, 'Q': {'commit': b.Q, 'tree': b.QT},
                                'R': {'commit': 'a'*40, 'tree': 'b'*40}}
        ctx = {'authority': authority, 'authority_path': str(self.root/'synthetic-authority'), 'authority_sha256': 'synthetic-test-only',
               'roots': ROOTS, 'modules': self.modules, 'guard': b.Guard(ROOTS),
               'source': {'source_delta': {'synthetic': True}}, 'origins': self.origins}
        freeze = copy.deepcopy(self.saved['admission']['native_provenance'])
        freeze.update(source_root=str(C_ROOT), source_commit=b.C, source_tree=b.CT,
                      source_inventory=copy.deepcopy(self.current_inventory), host_role=s.ROLE, raw_policy=s.POLICY, raw_probe_budget={'allowed': 1, 'used': 1},
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
        root = Path(ctx['authority']['paths']['campaign'])/'m1a'; root.mkdir(exist_ok=True)
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
            for key in ('source_commit', 'source_tree', 'binary_sha256', 'native_libraries', 'dependency_manifest_sha256', 'generator_hashes'):
                config[key] = freeze[key]
            config['host'] = run['frozen_host'] = freeze['host']
            run['source_binding'] = {k: freeze[k] for k in ('source_commit', 'source_tree', 'dependency_manifest_sha256', 'generator_hashes')}
            for key in ('source_commit', 'source_tree', 'binary_sha256', 'native_libraries'):
                run['provenance'][key] = freeze[key]
            outcome['binary_sha256'] = freeze['binary_sha256']
            for event in events:
                if event.get('phase') == 'provenance': event['value'] = run['provenance']
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
            intent = root/(label+'.continuation-intent.json')
            if intent.exists(): self.assertEqual(b.read(intent), binding)
            else: write(intent, binding)
            mechanism['reports'].append({'label': label, 'report': label+'/run.json'})
        write(root/'mechanism.json', mechanism)
        return view, exact_by_id, rust_by_id

    def run_sequence(self, mutate=None, fail_child=False, post_drift=False, repeat=False, output_race=False, report_drift=False, runtime=False, runtime_drift=None):
        ctx, freeze, ready = self.fixture(); args = ['--authority', str(self.root/'synthetic-authority'), '--authority-sha256', 'synthetic-test-only', '--c-source', str(C_ROOT), '--q-source', str(Q_ROOT)]
        with ExitStack() as stack:
            stack.enter_context(patch.object(s, 'context', return_value=ctx))
            m = self.modules['m1a_continuation']
            if runtime:
                fixture = self.runtime_fixture(stack, ctx, freeze)
                if runtime_drift == 'prepare':
                    (fixture.prefix/'lib/libjaccl.dylib').write_bytes(b'wrong runtime')
            else:
                ready_mock = stack.enter_context(patch.object(s, 'readiness', return_value=ready))
                stack.enter_context(patch.object(m, 'revalidate', side_effect=lambda r: (m.scope(r), r)[1]))
            stack.enter_context(redirect_stdout(io.StringIO()))
            prepared = s.main(['prepare', *args]); self.assertFalse(s.claim_paths(ctx['authority'])[0].exists())
            if runtime:
                ready = b.read(Path(ctx['authority']['paths']['state'])/'ready.json')['readiness']
                observed = {'prepare': len(fixture.inspections)}
                p = ctx['authority']['paths']
                argv = ['freeze', '--host-role', s.ROLE, '--source-commit', b.C,
                        '--phase', 'm1a', '--raw-policy', s.POLICY]
                for flag, key in [('campaign','campaign'), ('fixture-root','fixture_root'), ('portable','portable'),
                                  ('reference','reference'), ('native-prefix','native_prefix'),
                                  ('native-build-receipt','native_install'), ('binary','binary'),
                                  ('parent','parent'), ('rust-grader','grader'), ('originals','originals')]:
                    argv += ['--'+flag, p[key]]
                if runtime_drift == 'freeze':
                    (fixture.prefix/'lib/libjaccl.dylib').write_bytes(b'wrong runtime')
                with patch.object(sys, 'argv', ['m1a_continuation.py', *argv]): m.main()
                freeze = b.read(Path(p['campaign'])/'freeze.json')
                self.assertEqual(ready['native_state'], freeze['native_state'])
                observed['freeze/revalidate'] = len(fixture.inspections)
            else:
                self.campaign(ctx, freeze)
            bound = s.main(['bind', *args, '--ready-sha256', prepared['ready_sha256']])
            if runtime:
                observed['bind'] = len(fixture.inspections)
                campaign = Path(freeze['campaign'])
                m.admit(campaign, Path(freeze['parent']), Path(freeze['binary']))
                (campaign/'m1a').mkdir()
                if runtime_drift == 'before-child':
                    fixture.imports['libmlx.dylib'].append('@rpath/unexpected.dylib')
                m.before_child(campaign, next(iter(self.expected)))
                observed['before-child'] = len(fixture.inspections)
            view, exact, rust = self.reports(ctx, freeze)
            if runtime:
                with patch.object(sys, 'argv', ['m1a_continuation.py', 'seal', freeze['campaign']]): m.main()
                observed['seal'] = len(fixture.inspections)
                if runtime_drift == 'precommit':
                    fixture.rpaths['libmlx.dylib'].append('/synthetic/changed/rpath')
            stack.enter_context(patch.object(self.modules['retained_rational'], 'frozen_view', return_value=(view, ready['normalization'])))
            stack.enter_context(patch.object(self.modules['mlx_affine_qmm_reference_v1'], 'exact_case', side_effect=lambda c, root: exact[c['id']]))
            stack.enter_context(patch.object(self.modules['reference_budget'], 'start'))
            stack.enter_context(patch.object(self.modules['reference_budget'], 'check', return_value={'synthetic_memory_observation': True}))
            completion = self.root/'parent-completion.json'; stdout = self.root/'parent.stdout'; stdout.write_text('SYNTHETIC TEST, no parent executed\n')
            write(completion, {'schema': 'pulsarmlx.studio-parent-completion/1', 'exit_code': 0, 'reaped': True,
                               'bound_sha256': bound['bound_sha256'], 'receipt_sha256': b.sha(Path(freeze['campaign'])/'freeze.json'),
                               'parent_sha256': ctx['authority']['executables']['parent']['sha256'], 'argv': [freeze['parent'], '--exact', 'required_native_m1a', '--test-threads=1', '--nocapture'],
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
                if runtime_drift == 'postcommit' and len(calls) == 52:
                    fixture.rpaths['libmlx.dylib'].append('/synthetic/changed/rpath')
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
            if runtime:
                observed['qualify/final'] = len(fixture.inspections)
                self.assertTrue(all(x < y for x, y in zip(observed.values(), list(observed.values())[1:])))
                saved = b.read(Path(ctx['authority']['paths']['output'])/s.RESULT)
                self.assertEqual(saved['native_receipt']['native_state'], ready['native_state'])
                self.assertEqual(saved['readiness']['readiness']['native_state'], ready['native_state'])
                self.assertEqual(saved['correction'], s.correction_binding(ctx))
                self.assertEqual(saved['combined_cross_host_decision'], 'PENDING')
                self.assertFalse(saved['correction']['C2_experimental_CI_acceptance'])
                ctx['synthetic_validator_coverage'] = observed
            if repeat:
                with self.assertRaisesRegex(ValueError, 'spent numerical'):
                    s.main(qualifier)
            return ctx, qualifier, calls, stack, result

    def runtime_fixture(self, stack, ctx, freeze):
        """Only unavailable physical custody, inspection and build boundaries."""
        spec = importlib.util.spec_from_file_location('synthetic_retained_runtime_fixture', C_ROOT/b.EXP/'tools/test_retained_runtime.py')
        helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
        f = helper.SyntheticRuntime(self.root); stack.enter_context(f.patches())
        m = self.modules['m1a_continuation']; a = ctx['authority']; p = a['paths']
        p.update(native_prefix=str(f.prefix), native_install=str(f.receipt), binary=str(self.root/'mock-native'), originals=str(self.root/'originals.json'))
        write(Path(p['originals']), {'SYNTHETIC_TEST_DATA': str(f.receipt)})
        for key in ('binary', 'parent'):
            Path(p[key]).write_bytes(b'SYNTHETIC NONEXECUTABLE '+key.encode())
        python = str(Path(sys.executable).resolve())
        a['executables'] = {k: {'path': p[k], 'sha256': b.sha(p[k])} for k in ('binary', 'parent', 'grader')}
        a['executables']['python'] = {'path': python, 'sha256': b.sha(python)}
        linkage = {k: ['SYNTHETIC linkage'] for k in a['executables']}
        build = self.root/'build.json'
        write(build, {'schema': 'pulsarmlx.studio-c-build-identity/1', 'source_commit': b.C, 'source_tree': b.CT, 'executables': a['executables'], 'linkage': linkage})
        a.update(build_identity={'path': str(build), 'sha256': b.sha(build)}, ci_files=ci_paths())
        state = m.native_state(f.prefix, f.receipt, s.ROLE)
        raw = {'applies_to_current_binary': False, 'evidence_kind': 'historical_host_native_stack',
               'native_libraries': state['libraries'], 'originals': {'synthetic': {'path': str(f.receipt)}}}
        freeze.update(native_prefix=str(f.prefix), native_build_receipt=str(f.receipt), native_libraries=state['libraries'], native_state=state, raw_provenance=raw)
        for key, role in [('binary','binary'), ('parent','parent'), ('rust_grader','grader'), ('python','python')]:
            freeze[key] = a['executables'][role]['path']; freeze[key+'_sha256'] = a['executables'][role]['sha256']
        freeze['linkage'] = {k: ['SYNTHETIC linkage'] for k in ('binary','parent','rust_grader','python')}
        stack.enter_context(patch.dict(os.environ, {'PULSAR_ADOPTION_PHASE': 'm1a'}))
        stack.enter_context(patch.object(m, 'host_facts', return_value=freeze['host_facts']))
        stack.enter_context(patch.object(m, 'original_studio', return_value=raw))
        stack.enter_context(patch.object(m, 'linkage', return_value=['SYNTHETIC linkage']))
        stack.enter_context(patch.object(self.modules['copied_diagnostic'], 'linkage', return_value=['SYNTHETIC linkage']))
        stack.enter_context(patch.object(self.modules['freeze_host'], 'prepare', side_effect=lambda _: copy.deepcopy(freeze)))
        stack.enter_context(patch.object(s, 'authority', return_value=a))
        stack.enter_context(patch.object(s, 'check_locations', return_value={'SYNTHETIC_TEST_DATA': str(f.receipt)}))
        stack.enter_context(patch.object(b, 'source_identity', return_value=ctx['source']))
        # No native_state/revalidate/readiness/source_inventory replacement.
        return f

    def test_real_runtime_prepare_freeze_bind_before_child_seal_qualify(self):
        ctx, _, calls, _, result = self.run_sequence(runtime=True, repeat=True)
        self.assertEqual(len(calls), 52); self.assertEqual(result['counts'], b.COUNTS)
        print('SYNTHETIC actual-validator inspection counts:', ctx['synthetic_validator_coverage'])
        self.assertTrue(all(p.exists() for p in s.claim_paths(ctx['authority'])))
        self.assertFalse((Path(ctx['authority']['paths']['campaign'])/'m1a-acceptance.json').exists())

    def test_real_runtime_refusal_precedes_ready_and_claims(self):
        with self.assertRaisesRegex(ValueError, 'retained runtime bytes'):
            self.run_sequence(runtime=True, runtime_drift='prepare')
        self.assertFalse((self.root/'state').exists()); self.assertFalse((self.root/'campaign').exists())
        self.assertFalse((self.root/s.NATIVE_CLAIM).exists()); self.assertFalse((self.root/s.NUMERICAL_CLAIM).exists())

    def test_real_runtime_freeze_refusal_precedes_native_claim(self):
        with self.assertRaisesRegex(ValueError, 'retained runtime bytes'):
            self.run_sequence(runtime=True, runtime_drift='freeze')
        self.assertTrue((self.root/'state/ready.json').exists())
        self.assertFalse((self.root/'campaign').exists())
        self.assertFalse((self.root/s.NATIVE_CLAIM).exists()); self.assertFalse((self.root/s.NUMERICAL_CLAIM).exists())

    def test_real_runtime_before_child_refusal_preserves_native_claim_no_child_intent(self):
        with self.assertRaisesRegex(ValueError, 'unexpected non-system dependency'):
            self.run_sequence(runtime=True, runtime_drift='before-child')
        self.assertTrue((self.root/s.NATIVE_CLAIM).exists())
        self.assertEqual(list((self.root/'campaign/m1a').iterdir()), [])
        self.assertFalse((self.root/s.NUMERICAL_CLAIM).exists())

    def test_real_runtime_prequalification_drift_does_not_spend_numerical_claim(self):
        with self.assertRaisesRegex(ValueError, 'post-prepare.*drift'):
            self.run_sequence(runtime=True, runtime_drift='precommit')
        self.assertTrue((self.root/s.NATIVE_CLAIM).exists())
        self.assertFalse((self.root/s.NUMERICAL_CLAIM).exists())

    def test_real_runtime_final_drift_preserves_spent_claim_and_refuses_acceptance(self):
        with self.assertRaisesRegex(ValueError, 'claim spent'):
            self.run_sequence(runtime=True, runtime_drift='postcommit')
        self.assertTrue((self.root/s.NUMERICAL_CLAIM).exists())
        self.assertEqual(b.read(self.root/'result'/s.RESULT)['verdict'], 'FAILED_NO_RETRY')

    def authority_fixture(self):
        # Parser-only fixture. This is never passed to context or physical work.
        prompt=self.root/'future-synthetic-prompt.md'; prompt.write_text('SYNTHETIC future-authority parser control only\n')
        (self.root/'future-synthetic-prompt.md.sha256').write_text(b.sha(prompt)+'  '+prompt.name+'\n')
        contract=self.root/'correction.md'; contract.write_bytes((TEST_ROOT.parent/'rust-013/contract.md').read_bytes())
        Path(str(contract)+'.sha256').write_text(b.CORRECTION+'  '+contract.name+'\n')
        paths={}
        for key in s.PATH_KEYS:
            target=self.root/('path-'+key)
            if key not in ('state','campaign','output'): target.write_bytes(b'SYNTHETIC parser-only path')
            paths[key]=str(target)
        a={'schema':s.GRANT, 'purpose':'STUDIO_FULL_M1A_ONCE', 'evidence_role':'OPERATOR_AUTHORITY',
           'launch_authorized':True, 'synthetic':False, 'phase':'m1a','host_role':s.ROLE,'raw_policy':s.POLICY,
           'contract_sha256':b.CONTRACT,'correction_contract_sha256':b.CORRECTION,'source_profile_sha256':b.PROFILE_SHA256,
           'native_parent_allowance':1,'numerical_allowance':1,'new_raw_allowance':0,'M1b_released':False,'shipping_default':'copied',
           'prompt':{'commit':'f'*40,'sha256':b.sha(prompt),'path':str(prompt)},
           'contract_path':str(TEST_ROOT/'contract.md'),'correction_contract_path':str(contract),
           'historical_sources':{'C':{'commit':b.CI_C,'tree':b.CI_CT},'R':{'commit':b.ORIGINAL_R,'tree':b.ORIGINAL_RT}},
           'sources':{'C':{'commit':b.C,'tree':b.CT},'Q':{'commit':b.Q,'tree':b.QT},'R':{'commit':'a'*40,'tree':'b'*40}},'paths':paths}
        return a

    def parse_authority(self,a):
        path=self.root/'parser-only-authority.json'; write(path,a)
        Path(str(path)+'.sha256').write_text(b.sha(path)+'  '+path.name+'\n')
        return s.authority(path,b.sha(path))

    def test_correction_authority_positive_and_exact_negative_bindings(self):
        a=self.authority_fixture(); self.assertEqual(self.parse_authority(a),a)
        for key in ('correction_contract_sha256','source_profile_sha256','contract_sha256'):
            with self.subTest(field=key),self.assertRaises(ValueError): self.parse_authority({**a,key:'0'*64})
        changed=copy.deepcopy(a); changed['sources']['C']=a['historical_sources']['C']
        with self.assertRaisesRegex(ValueError,'authority C'):self.parse_authority(changed)
        changed=copy.deepcopy(a); changed['historical_sources']['C']=a['sources']['C']
        with self.assertRaisesRegex(ValueError,'historical authority'):self.parse_authority(changed)
        contract=Path(a['correction_contract_path']); contract.write_bytes(contract.read_bytes()+b' ')
        with self.assertRaises(ValueError):self.parse_authority(a)

    def test_all_implementation_and_old_studio_authorities_refused(self):
        a=self.authority_fixture()
        for commit,digest in b.FORBIDDEN_PROMPTS.items():
            for key,value in [('commit',commit),('sha256',digest)]:
                changed=copy.deepcopy(a); changed['prompt'][key]=value
                with self.subTest(commit=commit,field=key),self.assertRaisesRegex(ValueError,'cannot authorize corrected Studio'):
                    self.parse_authority(changed)
        side=Path(a['correction_contract_path']+'.sha256'); side.write_text('0'*64+'  correction.md\n')
        with self.assertRaisesRegex(ValueError,'correction contract sidecar'):self.parse_authority(a)

    def test_exact_inspection_allowlist(self):
        g = b.Guard(ROOTS)
        paths = {str(self.root/'native/lib'/n) for n in ('libmlx.dylib','libmlxc.dylib','libjaccl.dylib')}
        g.link_paths.update(paths); g.load_paths.update(paths)
        for name in paths:
            for flag in ('-l','-L'):
                argv = ['/usr/bin/otool', flag, name]
                g.check('subprocess.Popen', (argv[0], argv, None, None))
        for argv in [['/usr/bin/otool','-l',str(self.root/'foreign')],
                     ['/usr/bin/otool','-l',next(iter(paths)), '-v'],
                     ['/usr/bin/otool','-h',next(iter(paths))],
                     ['/usr/bin/otool','-l',str(self.root/'native/lib/../lib/libmlx.dylib')]]:
            with self.assertRaisesRegex(ValueError, 'otool inspection target'):
                g.check('subprocess.Popen', (argv[0], argv, None, None))

    def test_current_profile_and_fixed_delta_proof_adversarial(self):
        profile = b.source_profile(); q = b.inventory(Q_ROOT,b.Q); c2 = b.inventory(C_ROOT,b.C)
        old_c = b.original_inventory(C_ROOT,b.CI_C,q); old_r = b.original_inventory(s.ROOT,b.ORIGINAL_R,q)
        r2 = copy.deepcopy(old_r)
        # Explicit prospective candidate rows; production checks clean Git identity
        # after commit. This does not call inventory(current root, historical R).
        for name in b.R_PATHS:
            data=(s.ROOT/name).read_bytes(); r2[name]={'mode':'100644', 'blob':hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest(), 'sha256':hashlib.sha256(data).hexdigest(), 'bytes':len(data)}
        proof=b.source_delta(old_c,c2,q,old_r,r2,profile)
        self.assertEqual(proof['protected_C_files'],5084); self.assertEqual(proof['protected_Q_files'],5090)
        protected=next(n for n in old_c if n not in b.C_PATHS)
        def changed(rows, name, key, value):
            result=copy.deepcopy(rows); result[name][key]=value; return result
        for bad in [changed(c2,protected,'sha256','0'*64), changed(c2,next(iter(b.C_PATHS)),'mode','100755')]:
            with self.assertRaises(ValueError): b.source_delta(old_c,bad,q,old_r,r2,profile)
        renamed=copy.deepcopy(c2); renamed['renamed']=renamed.pop(protected)
        with self.assertRaisesRegex(ValueError,'deletion/rename'): b.source_delta(old_c,renamed,q,old_r,r2,profile)
        for bad in [changed(r2,protected,'sha256','0'*64), changed(r2,b.EXP+'tools/studio_bridge.py','mode','100755')]:
            with self.assertRaises(ValueError): b.source_delta(old_c,c2,q,old_r,bad,profile)
        missing=copy.deepcopy(r2); del missing[protected]
        with self.assertRaises(ValueError): b.source_delta(old_c,c2,q,old_r,missing,profile)
        crossed=copy.deepcopy(profile); crossed['C2_changes'][b.EXP+'tools/m1a_continuation.py']['after']['sha256']='0'*64
        with self.assertRaises(ValueError): b.source_delta(old_c,c2,q,old_r,r2,crossed)
        fake=self.root/'fake/tools/studio_bridge.py'; fake.parent.mkdir(parents=True)
        write(fake.parent.parent/'runtime-correction-source-v1.json', {**profile,'C2':profile['C']})
        with patch.object(b,'__file__',str(fake)), self.assertRaises(ValueError): b.source_profile()

    def test_historical_ci_cannot_be_rewritten_as_current_c2(self):
        parse=b.parse
        def crossed(raw):
            value=parse(raw)
            if isinstance(value,dict) and value.get('schema')=='pulsarmlx.retained-numerical-requalification/1':
                value['native_execution'].update(C=b.C,C_tree=b.CT)
            return value
        with patch.object(b,'parse',side_effect=crossed), self.assertRaisesRegex(ValueError,'original CI execution'):
            b.ci_prerequisite(ci_paths(),self.expected)

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
