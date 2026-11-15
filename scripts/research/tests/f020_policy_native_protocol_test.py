"""Fabricated custody records for admission ordering, with no native entrypoint."""
import copy
import subprocess
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f020_policy_native_supervise as run
import f020_policy_native_custody as custody
import f020_policy_native_check as check


class StudioBoundary(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        def name(k):
            p = self.root / k / k
            p.parent.mkdir()
            return p
        self.config = {k:str(name(k)) for k in run.PATHS if k != "repo"}
        self.config.update(repo=str(run.ROOT), commit="a"*40,tree="b"*40,input_sha256="c"*64,run="d"*64)
        for k in run.PATHS:
            if k not in ("repo","output","private_description"):
                Path(self.config[k]).write_bytes(b"fabricated nonexecutable witness")
        self.cfg = self.root/"config.json"
        self.cfg.write_bytes(run.canonical(self.config))
        self.ident = dict(commit=self.config["commit"],tree=self.config["tree"],run=self.config["run"],
                          input_sha256=self.config["input_sha256"],page_size=16384,host={"page":"16384"},
                          binary_sha256="e"*64,build_sha256="f"*64,seal="simulated-seal",
                          verifier_modules={"simulated":"1"*64},fixture_bindings={"simulated":"2"*64})
        raw, self.grant = run.envelope(self.config,self.ident)
        self.desc = Path(self.config["private_description"])
        self.desc.write_bytes(raw);self.desc.chmod(0o600)
        self.spec = dict(commit="a"*40,path="fabricated",sha256="e"*64)
        self.claims = []
        self.inspect = Mock(side_effect=lambda c:copy.deepcopy(self.ident))
        self.authority = Mock(side_effect=lambda s:copy.deepcopy(self.grant))
        self.forbidden = []
        # Real external effects raise before a child, library or payload can be accessed.
        for module,name in [(run.prior,"wait_child"),(custody,"_run_build"),(custody.prior,"installed"),
                            (run.prior,"fixture_identity"),(run.prior,"exclusive")]:
            spy = Mock(side_effect=AssertionError("unexpected external effect: "+name))
            hook = patch.object(module,name,spy);hook.start();self.addCleanup(hook.stop);self.forbidden.append(spy)
    def start(self):
        return run.start_campaign(self.cfg,self.spec,self.inspect,self.authority,
                                  lambda path,record:self.claims.append((path,record)))
    def check_untouched(self):
        self.assertEqual(self.claims,[])
        self.assertTrue(all(spy.call_count==0 for spy in self.forbidden))
        self.assertFalse(Path(self.config["output"]).exists())

    def test_original_compiler_record_survives_linkage_validation(self):
        import hashlib
        from contextlib import ExitStack

        release = self.root / "fabricated-target" / "release"
        release.mkdir(parents=True)
        binary = release / custody.BIN
        binary.write_bytes(b"fabricated, never executed")
        binary.chmod(0o700)
        prefix = self.root / "fabricated-prefix"
        prefix.mkdir()
        paths = dict(binary=binary, prefix=prefix, cargo_log=self.root / "compiler.jsonl",
                     artifact=self.root / "selected.jsonl")
        package = custody.ROOT / "crates/mlx-expert-mlp"
        row = dict(reason="compiler-artifact", package_id="path+" + package.as_uri() + "#0.1.0",
                   target=dict(name=custody.BIN, kind=["bin"], src_path=str(package / "src/bin" / (custody.BIN + ".rs"))),
                   executable=str(binary), profile=dict(test=False, opt_level="3"),
                   fresh=False, features=[custody.FEATURE])
        # Noncanonical but valid JSONL bytes distinguish original artifact custody from re-encoding.
        selected = b"  " + json.dumps(row).encode("utf-8") + b" \t\n"
        other = b'{"reason":"compiler-artifact","target":{"name":"another-package"}}\n'
        finished = b'{"reason":"build-finished","success":true}\n'
        good = other + selected + finished
        expected_sha = hashlib.sha256(selected).hexdigest()
        log_sha = hashlib.sha256(good).hexdigest()
        libraries = {name: dict(lexical=str(prefix / "lib" / name), canonical=str(prefix / "lib" / name))
                     for name in ("libmlx.dylib", "libmlxc.dylib")}
        imports = ["\t@rpath/" + name + " (compatibility version 1.0.0, current version 1.0.0)"
                   for name in libraries]
        admission = dict(self.ident, prefix=str(prefix), accounting_abi_stamp="fabricated ABI", headers={},
                         cargo_configs={}, native=dict(install_sha256="a"*64, static_inspection=dict(files=libraries)))
        tools = {name: dict(path=str(self.root / "fabricated-tools" / name)) for name in ("cargo", "rustc")}
        with ExitStack() as stack:
            linkage = stack.enter_context(patch.object(custody.prior, "links", return_value=imports))
            stack.enter_context(patch.object(custody.prior, "contains_marker", return_value=True))
            stack.enter_context(patch.object(custody.prior.old, "hashed", return_value="b"*64))
            toolchain = stack.enter_context(patch.object(custody, "_toolchain", return_value=tools))
            paths["cargo_log"].write_bytes(good)
            self.assertEqual(custody._artifact(paths), (selected, log_sha))
            original, build = custody._built(paths, admission, toolchain())
            self.assertEqual(original, selected)
            self.assertEqual(build["artifact_sha256"], expected_sha)
            self.assertEqual(build["cargo_log_sha256"], log_sha)
            self.assertEqual(build["linkage"], imports)

            for label, bad in (("duplicate artifact", other + selected + selected + finished),
                               ("missing build-finished", other + selected)):
                with self.subTest(label=label):
                    paths["cargo_log"].write_bytes(bad)
                    with self.assertRaisesRegex(ValueError, "successful unique Cargo artifact"):
                        custody._built(paths, admission, toolchain())
            paths["cargo_log"].write_bytes(good)
            linkage.return_value = imports + ["\t@rpath/libunbound.dylib (compatibility version 1.0.0)"]
            with self.assertRaisesRegex(ValueError, "pinned physical binary import"):
                custody._built(paths, admission, toolchain())
        self.assertFalse(paths["artifact"].exists())
        self.check_untouched()

    def test_valid_mock_boundary_consumes_only_injected_intent(self):
        _cfg,ident,path,claim=self.start()
        self.assertEqual(ident,self.ident)
        self.assertEqual(self.claims,[(path,claim)])
        self.assertFalse(path.exists())
        self.assertTrue(all(spy.call_count==0 for spy in self.forbidden))

    def test_crossed_identity_and_budget_refused_before_inspection(self):
        for key,wrong in (("source","c"*40),("tree","d"*40),("input_sha256","e"*64),
                          ("run","b"*64),("arms",list(reversed(run.ARMS))),
                          ("budget",dict(run.BUDGET,children=9))):
            with self.subTest(key=key):
                old=self.grant[key];self.grant[key]=wrong
                with self.assertRaises(ValueError):self.start()
                self.grant[key]=old
                self.inspect.assert_not_called();self.check_untouched()

    def test_drift_in_measured_custody_refused_before_claim(self):
        for key,value in (("binary_sha256","3"*64),("build_sha256","2"*64),
                          ("seal","inherited-wrong-seal"),("verifier_modules",{"foreign":"a"*64}),
                          ("fixture_bindings",{"crossed":"b"*64}),("page_size",4096),("page_size",8192)):
            with self.subTest(key=key,value=value):
                old=self.ident[key];self.ident[key]=value
                with self.assertRaises(ValueError):self.start()
                self.ident[key]=old;self.check_untouched()

    def test_private_description_byte_change_or_policy_drift_refused(self):
        original=self.desc.read_bytes()
        self.desc.write_bytes(original+b" ")
        with self.assertRaises(ValueError):self.start()
        self.desc.write_bytes(original)
        self.desc.chmod(0o644)
        with self.assertRaises(ValueError):self.start()
        self.check_untouched()

    def test_actual_build_entry_on_macbook_refuses_before_launcher(self):
        # Simulate the host observation, even if this test later executes on another machine.
        foreign=dict(custody.prior.HOST,model="simulated-MacBook")
        cfg = dict(self.config,binary=str(self.root/"fresh-target/release"/custody.BIN))
        with patch.object(custody.prior,"host_facts",return_value=foreign) as observed:
            with self.assertRaisesRegex(ValueError,"^physical Studio model$"):custody.capture_build(cfg)
            observed.assert_called_once()
        self.check_untouched()

    def test_bootstrap_module_mismatch_cannot_import_project(self):
        import f020_policy_native_bootstrap as bootstrap
        fake=self.root/"modules";fake.mkdir()
        (fake/"f020_marker.py").write_text("raise AssertionError('project module executed')")
        # Exercise the real pre-import guard with the actual isolated interpreter flags.
        wrapper = ("import runpy,sys;from pathlib import Path;"
                   "b=runpy.run_path(sys.argv[1]);"
                   "b['verified_modules'](Path(sys.argv[2]),[['f020_marker','0'*64]])")
        result=subprocess.run([sys.executable,"-I","-S","-B","-c",wrapper,bootstrap.__file__,str(fake)],
                              env={"PATH":"/usr/bin:/bin:/usr/sbin:/sbin","HOME":str(self.root)},
                              capture_output=True,timeout=15)
        self.assertNotEqual(result.returncode,0)
        self.assertIn(b"ValueError",result.stderr)
        self.assertNotIn(b"project module executed",result.stderr)

    def test_closed_grant_and_canonical_token_boundaries(self):
        self.assertEqual(check.strict(b'{"bytes":0,"unknown":null}',26),{"bytes":0,"unknown":None})
        for bad in (b'{"x":0,"x":0}',b'{"x":-0}',b'{"x":1.0}',b'{"x":1e0}',b'{"x":NaN}',
                    b'{"x":18446744073709551616}',b'{"x":-9223372036854775809}'):
            with self.subTest(bad=bad),self.assertRaises(ValueError):check.strict(bad)
        data=b'{"x":1}'
        self.assertEqual(check.strict(data,len(data)),{"x":1})
        with self.assertRaises(ValueError):check.strict(data,len(data)-1)
        for value in ("../grant.json","Prompts/RUST-ENGINE/Mac-Studio-M1-Ultra/x__prompt.md"):
            with patch.object(run.prior,"fetch",side_effect=AssertionError("premature fetch")):
                with self.assertRaises(ValueError):run.operator(dict(self.spec,path=value))
        self.check_untouched()

    def test_preexisting_claim_blocks_all_effects(self):
        _,claim=run.configuration(self.config)
        claim.write_bytes(b"spent")
        with self.assertRaises(ValueError):self.start()
        self.assertEqual(claim.read_bytes(),b"spent");self.inspect.assert_not_called();self.check_untouched()

    def test_no_implicit_or_crossed_ordinal(self):
        for n in (-1,8,False,1.0):
            with self.assertRaises(ValueError):run.arm_dir(self.root,n)
        for n,(p,m,v) in enumerate(run.ARMS):
            row=run.intent_for(self.cfg,self.spec,self.ident,"0"*64,23,n)
            self.assertEqual([row[k] for k in ("ordinal","profile","arm","policy")],[n,p,m,v])
            self.assertTrue(run.arm_dir(self.root,n).name.endswith("-".join((p,m,v))))


# Additional independent checker controls
"""Fabricated wire controls for the policy qualification checker. These do not run a native producer."""
import copy
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import f020_policy_native_check as policy_check


class PolicyWireControls(unittest.TestCase):
    def test_strict_protocol_integers_and_byte_limits(self):
        valid = b'{"u":18446744073709551615,"s":-9223372036854775808,"p":null}'
        self.assertIsNone(policy_check.strict(valid, len(valid))['p'])
        for raw in (b'{"x":{"q":0,"q":0}}', b'-0', b'1e0', b'2.5', b'NaN', b'Infinity',
                    b'18446744073709551616', b'-9223372036854775809', b'"\xff"', valid[:-1]):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                policy_check.strict(raw)
        with self.assertRaises(ValueError):
            policy_check.strict(valid, len(valid) - 1)
        for page in (4096, 16384):
            self.assertEqual(policy_check.supported_page(page), page)
        for page in (True, 8192, '16384', None):
            with self.assertRaises(ValueError):
                policy_check.supported_page(page)

    def test_fabricated_setup_failure_preserves_opened_and_released_slot(self):
        # Three distinct fake shards allow one successful setter followed by a refused setter.
        page = 4096
        stamps = [[i + 1] * 32 for i in range(3)]
        fixture = dict(stamps=stamps, lengths=[2 * page] * 3, mapping=[0, 1, 2],
                       binding=[7] * 32, components=[dict(bytes=page)] * 3)
        ticket = dict(invocation=1, wave=0, bank=0, generation=1, expert=0, binding=[6] * 32)
        slots = []
        for i in range(2):
            slots.append(dict(open_attempted=True, fresh_owned=True, original_stamp=stamps[i], fresh_stamp=stamps[i],
                              matched=True, configured=i == 0, setter=dict(command='F_NOCACHE', number=48, argument=1,
                              returned=0 if i == 0 else -1, errno=None if i == 0 else 4)))
        slots.append(None)
        setup = dict(policy='NoCacheRequested', role='gate', binding=fixture['binding'], original_stamps=stamps,
                     lengths=fixture['lengths'], alignment=page, page_size=page, map=[0, 1, None], slots=slots,
                     live=0, released=2, kernel_close_observed=None, minimum_reservation=2 * page - 1 + 131072,
                     policy_control=65536)
        row = dict(**ticket, owner=1, epoch=1, role='gate', verified=False, primary_phase='POLICY',
                   outcome=dict(kind='setup_failure', setup=setup))
        def check(observed):
            return policy_check.check_setup_failure(observed, ticket, 0, fixture, 'NoCacheRequested', page, 0,
                                                    observed_slots=slots)
        self.assertEqual(check(row), dict(owned=2, released=2, setters=2, kernel_close_observed=None))
        for field, value in (('released', 1), ('live', False), ('kernel_close_observed', True),
                             ('slots', [slots[0], None, None])):
            changed = copy.deepcopy(row)
            changed['outcome']['setup'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                check(changed)
        crossed = copy.deepcopy(row)
        crossed['generation'] += 1
        with self.assertRaises(ValueError):
            check(crossed)

    def test_failure_marker_and_indeterminate_partial_read(self):
        phases = ['verified_child', 'initial_guard', 'abi']
        failure = dict(status='failed', completed_phases=phases, ffi_counts=[2, 1],
                       reason='fabricated unwind', unobserved_effects='unknown')
        policy_check.check_unknown_progress(failure, completed_phases=phases, ffi_counts=[2, 1])
        for field, value in (('unobserved_effects', 0), ('ffi_counts', [2, True]), ('partial_bytes', 0)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                policy_check.check_unknown_progress(dict(failure, **{field:value}), completed_phases=phases, ffi_counts=[2, 1])
        routes = [dict(route='buffered-requested-aligned-window', begin=i * 4096, bytes=4096, delta=16,
                       logical_begin=i * 4096 + 16, logical_bytes=64) for i in range(3)]
        # Only the transfer Progress fields are consumed by this focused validator.
        receipt = dict.fromkeys(policy_check.TRANSFER.split())
        receipt.update(schema='pulsarmlx.fixed-descriptor-transfer/1', components=routes, published=False,
                       logical_attempts=2, logical_requested=128, attempted=2, requested=8192, completed=4096,
                       logical_delivered=64, copies=1, copied=64, candidate_overread=3 * 4032,
                       attempted_overread=2 * 4032, completed_overread=4032, edge_attempts=0, coalescing_overread=0,
                       effects=[dict(attempted=True, returned_bytes=4096, copied=64),
                                dict(attempted=True, returned_bytes=None, copied=0),
                                dict(attempted=False, returned_bytes=None, copied=0)])
        self.assertEqual(policy_check.check_transfer_progress(receipt, routes), dict(known_bytes=4096, unknown_components=1))
        changed = copy.deepcopy(receipt)
        changed['effects'][1]['returned_bytes'] = 0
        with self.assertRaises(ValueError):
            policy_check.check_transfer_progress(changed, routes)
        with self.assertRaises(ValueError):
            policy_check.check_transfer_progress(dict(receipt, completed=8192), routes)

    def test_pure_hit_and_replay_witnesses(self):
        args = ([], {}, 'default', 'BufferedRequested', 4096, 0, 1)
        self.assertEqual(policy_check.policy_journal(b'[]', *args), (set(), [], 0))
        with self.assertRaises(ValueError):
            policy_check.policy_journal(b'[]', [{'phase':'submit'}], *args[1:])
        digest = policy_check.sha(b'[]')
        snapshot = dict(dispatches=1, records=1, weighted=1)
        replay = dict(same_commit=True, lost_delivery=True, position=1, input_reads=1, counts=[7, 12],
                      snapshot=snapshot, guard_count=4, policy_sha256=digest)
        policy_check.check_replay(replay, snapshot, [7, 12], digest)
        for key, value in (('input_reads', 2), ('policy_sha256', None), ('counts', [8,12]), ('same_commit', 1)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                policy_check.check_replay(dict(replay, **{key:value}), snapshot, [7, 12], digest)

    @unittest.skipUnless(os.environ.get('RUST027_HOST_CAPTURES'), 'requires current Rust027 CPU adapter export')
    def test_actual_host_capture_rejects_crossed_schema_and_perturbed_evidence(self):
        root = Path(os.environ['RUST027_HOST_CAPTURES']) / 'default-Serial-BufferedRequested'
        fixed = policy_check.fixed
        matrix, golden, recipes = fixed.frozen_inputs()
        source = policy_check.strict(policy_check.ref.bounded(fixed.ROOT / 'fixtures/weighted-expert-mlp/routes.json', 1 << 20))
        args = (root, 'default', 'Serial', 'BufferedRequested', os.sysconf('SC_PAGE_SIZE'), matrix, golden, recipes['default'])
        kwargs = dict(patterns=source['patterns']['default'])
        original = policy_check.ref.bounded
        success = policy_check.check_files(*args, **kwargs)
        self.assertEqual(success['schema'], 'staged-policy-host-adapter/1')
        # The full host record never passes the native report grammar.
        with self.assertRaisesRegex(ValueError, 'closed keys'):
            policy_check.check_files(*args, native=(None, None, None))
        def wrong_count(raw):
            report = policy_check.strict(raw)
            report['standing'] += 1
            return fixed.compact(report)
        def extra_field(raw):
            report = policy_check.strict(raw)
            report['policy_observed'] = True
            return fixed.compact(report)
        def missing_field(raw):
            report = policy_check.strict(raw)
            del report['policy_journals']
            return fixed.compact(report)
        negatives = [('weighted-0.f32', lambda raw: bytes([raw[0] ^ 1]) + raw[1:], 'synthetic weighted lanes'),
                     ('weighted-0.f32', lambda raw: raw[:-1], '128 binary32 lanes'),
                     ('report.json', wrong_count, 'standing reservation'), ('report.json', extra_field, 'closed keys'),
                     ('report.json', missing_field, 'closed keys')]
        for name, change, reason in negatives:
            def read_changed(path, cap):
                data = original(path, cap)
                return change(data) if path == root / name else data
            with self.subTest(name=name, reason=reason), patch.object(policy_check.ref, 'bounded', read_changed):
                with self.assertRaisesRegex(ValueError, reason):
                    policy_check.check_files(*args, **kwargs)

if __name__=="__main__":
    unittest.main()
