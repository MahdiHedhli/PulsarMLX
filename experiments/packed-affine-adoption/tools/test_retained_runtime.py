"""SYNTHETIC host fixtures; no actual Studio library/receipt or native launch.

Only external inspection and unavailable original-byte identities are doubled.
The actual native_state, parser, classification and comparison run unchanged.
"""
import ast
from contextlib import ExitStack
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import m1a_continuation as m
PRODUCTION_INSPECT = m.inspect_image


class SyntheticRuntime:
    """Reusable, explicitly synthetic external boundary for bridge controls."""
    def __init__(self, root):
        self.prefix = root/'synthetic-prefix'; (self.prefix/'lib').mkdir(parents=True)
        self.receipt = root/'synthetic-install.json'
        self.real_sha = m.sha
        for name in ('libmlx.dylib', 'libmlxc.dylib', 'mlx.metallib', 'libjaccl.dylib'):
            (self.prefix/'lib'/name).write_bytes(('SYNTHETIC:'+name).encode())
        libraries = {n: self.real_sha(self.prefix/'lib'/n) for n in ('libmlx.dylib','libmlxc.dylib')}
        self.receipt.write_bytes(m.canonical({'evidence_role':'SYNTHETIC_TEST_DATA', 'source_pins':m.PINS,
            'patches':m.PATCHES, 'libraries':{k:{'installed_sha256':v} for k,v in libraries.items()},
            'metallib_sha256':self.real_sha(self.prefix/'lib/mlx.metallib'), 'extra_runtime_library_sha256':m.RUNTIME_SHA256}))
        self.imports = {'libmlx.dylib':['@rpath/libjaccl.dylib', '/System/Library/Frameworks/Metal.framework/Versions/A/Metal'],
                        'libmlxc.dylib':['@rpath/libmlx.dylib'], 'libjaccl.dylib':['/usr/lib/libSystem.B.dylib']}
        self.rpaths = {'libmlx.dylib':['@loader_path/../lib'], 'libmlxc.dylib':[], 'libjaccl.dylib':[]}
        self.inspections = []

    def sha(self, path):
        p=Path(path)
        if p == self.receipt:
            return '7c2301eb59c037191cd296e3139a7ca4a93e61e27c5e8b05b1ae717888b16523'
        if p.read_bytes() == b'SYNTHETIC:libjaccl.dylib':
            return m.RUNTIME_SHA256
        return self.real_sha(p)

    def inspect(self, flag, image):
        image=Path(image); name=image.name; self.inspections.append((flag,str(image)))
        values=['@rpath/'+name,*self.imports[name]]
        if flag == '-L':
            return str(image)+':\n'+''.join('\t'+v+' (compatibility version 1.0.0, current version '+('370.64.2' if 'Metal.framework/' in v else '1.0.0')+')\n' for v in values)
        commands=[('LC_ID_DYLIB',values[0]),*[('LC_LOAD_DYLIB',v) for v in values[1:]],*[('LC_RPATH',v) for v in self.rpaths[name]]]
        out=str(image)+':\n'
        for i,(cmd,value) in enumerate(commands):
            offset=12 if cmd=='LC_RPATH' else 24
            size=(offset+len(value.encode())+1+7)//8*8
            out+=f'Load command {i}\n      cmd {cmd}\n  cmdsize {size}\n     '+('path' if cmd=='LC_RPATH' else 'name')+f' {value} (offset {offset})\n'
        return out

    def patches(self):
        stack=ExitStack(); stack.enter_context(patch.object(m,'sha',side_effect=self.sha))
        stack.enter_context(patch.object(m,'inspect_image',side_effect=self.inspect))
        return stack


class RetainedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='synthetic-runtime-',dir=os.environ.get('RUST013_TEST_ROOT'))
        self.addCleanup(self.temp.cleanup); self.root=Path(self.temp.name).resolve(); self.f=SyntheticRuntime(self.root)
        self.stack=self.f.patches(); self.addCleanup(self.stack.close)

    def state(self):return m.native_state(self.f.prefix,self.f.receipt,'m1-ultra-studio')

    def test_original_refusal_then_production_tokenized_inside_prefix_acceptance(self):
        old=Path(os.environ['RUST013_ORIGINAL_C_SOURCE'])/m.EXP/'tools/m1a_continuation.py'
        node=next(n for n in ast.parse(old.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='native_state')
        scope=dict(m.__dict__); exec(compile(ast.Module(body=[node],type_ignores=[]),str(old),'exec'),scope)
        with patch.object(m.subprocess,'check_output',side_effect=lambda a,**k:self.f.inspect('-L',a[2])):
            with self.assertRaisesRegex(ValueError,'retained runtime dependency') as failure:
                scope['native_state'](self.f.prefix,self.f.receipt,'m1-ultra-studio')
        print('Preserved original synthetic refusal:',str(failure.exception))
        state=self.state(); record=state['retained_runtime']; runtime=record['files']['libjaccl.dylib']
        self.assertEqual(runtime['canonical'],str(self.f.prefix/'lib/libjaccl.dylib'))
        self.assertEqual(list(state['dependencies'].values()),[m.RUNTIME_SHA256])
        self.assertFalse(record['loaded_runtime_image_observed'])
        self.assertEqual(record['child_environment']['DYLD_LIBRARY_PATH'],str(self.f.prefix/'lib'))
        self.assertEqual(len(record['inspections']),3)

    def test_own_ids_system_edges_and_duplicate_alias_imports(self):
        self.f.imports['libmlxc.dylib'] += [str(self.f.prefix/'lib/libjaccl.dylib'),'@rpath/libjaccl.dylib']
        x=self.state(); self.assertEqual(len(x['dependencies']),1)
        kinds=[e['classification'] for e in x['retained_runtime']['edges']]
        self.assertEqual(kinds.count('own_id_not_import'),3); self.assertEqual(kinds.count('retained_extra_runtime'),3)
        self.assertIn('system_shared_cache_allowed',kinds)

    def test_external_fixed_symlink_and_dotdot_target(self):
        p=self.f.prefix/'lib/libjaccl.dylib'; p.unlink(); target=self.root/'external'; target.mkdir(); (target/'inner').mkdir()
        actual=target/'runtime'; actual.write_bytes(b'SYNTHETIC:libjaccl.dylib'); p.symlink_to('../../external/inner/../runtime')
        record=self.state()['retained_runtime']['files']['libjaccl.dylib']
        self.assertEqual(record['canonical'],str(actual)); self.assertEqual(len(record['symlinks']),1)

    def test_wrong_missing_dangling_and_nonregular_runtime_refuse(self):
        p=self.f.prefix/'lib/libjaccl.dylib'; p.write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'retained runtime bytes'):self.state()
        p.unlink()
        with self.assertRaises(FileNotFoundError):self.state()
        p.symlink_to('absent')
        with self.assertRaises(FileNotFoundError):self.state()
        p.unlink(); p.mkdir()
        with self.assertRaisesRegex(ValueError,'regular file'):self.state()

    def test_unexpected_and_unsupported_dependency_contexts(self):
        for value in ['@rpath/other.dylib','@loader_path/libjaccl.dylib','@executable_path/libjaccl.dylib','/foreign/libjaccl.dylib','@rpath/sub/libjaccl.dylib']:
            self.f.imports['libmlx.dylib'][0]=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.state()

    def test_system_override_and_missing_import_refuse(self):
        (self.f.prefix/'lib/Metal').write_bytes(b'competing')
        with self.assertRaisesRegex(ValueError,'competing'):self.state()
        (self.f.prefix/'lib/Metal').unlink(); self.f.imports['libmlx.dylib'].pop(0)
        with self.assertRaisesRegex(ValueError,'import missing'):self.state()

    def test_system_prefix_cannot_hide_parent_traversal(self):
        for value in ['/usr/lib/../../private/libevil.dylib',
                      '/System/Library/../../private/libevil.dylib',
                      '/usr/lib/../lib/libSystem.B.dylib']:
            self.f.imports['libjaccl.dylib']=[value]
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'noncanonical system dependency'):
                self.state()

    def test_runtime_self_import_does_not_establish_an_MLX_dependency(self):
        self.f.imports['libmlx.dylib'].pop(0)
        self.f.imports['libjaccl.dylib'].append('@rpath/libjaccl.dylib')
        with self.assertRaisesRegex(ValueError,'import missing'):
            self.state()

    def test_loader_override_refuses_before_any_inspection(self):
        with patch.dict(os.environ,{'DYLD_FALLBACK_LIBRARY_PATH':'/foreign'}),self.assertRaisesRegex(ValueError,'overrides'):
            self.state()
        self.assertEqual(self.f.inspections,[])

    def test_parser_malformed_truncated_and_unsupported_commands(self):
        image=self.f.prefix/'lib/libmlx.dylib'; text=self.f.inspect('-l',image)
        for bad in [text.replace('Load command 1','Load command 9'),text.replace('cmdsize 48','cmdsize 8'),text.replace('LC_LOAD_DYLIB','LC_LAZY_LOAD_DYLIB'),text+'Load command 3\n cmd LC_DYLD_ENVIRONMENT\n cmdsize 24\n',text.replace(' (offset 24)',' (offset 9999)'),text+'x'*(m.INSPECTION_BYTES+1)]:
            with self.subTest(prefix=bad[:30]),self.assertRaises(ValueError):m.load_commands(bad,image)

    def test_relevant_inspection_and_file_drift_changes_record(self):
        first=self.state(); self.f.rpaths['libmlx.dylib'].append('/unselected/rpath')
        self.assertNotEqual(first,self.state())
        p=self.f.prefix/'lib/libjaccl.dylib'; old=p.with_suffix('.saved'); p.rename(old); p.symlink_to(old.name)
        self.assertNotEqual(first,self.state())

    def test_typed_and_displayed_edges_must_agree(self):
        inspect=self.f.inspect
        def crossed(flag,image):
            text=inspect(flag,image)
            return text.replace('@rpath/libjaccl.dylib','@rpath/libother.dylib') if flag=='-L' else text
        with patch.object(m,'inspect_image',side_effect=crossed),self.assertRaisesRegex(ValueError,'typed/linkage'):self.state()

    def test_runtime_changed_during_inspection_refused(self):
        inspect=self.f.inspect
        def changed(flag,image):
            text=inspect(flag,image)
            if flag=='-l' and Path(image).name=='libjaccl.dylib':(self.f.prefix/'lib/libjaccl.dylib').write_bytes(b'changed')
            return text
        with patch.object(m,'inspect_image',side_effect=changed),self.assertRaisesRegex(ValueError,'inspection drift'):self.state()

    def test_actual_inspector_bounds_and_owned_cleanup(self):
        for oversized in (False,True):
            p=Mock(); p.stdout.fileno.return_value=17; p.poll.return_value=None
            ready=([p.stdout],[],[]) if oversized else ([],[],[])
            with patch.object(m.subprocess,'Popen',return_value=p) as launch,patch.object(m.select,'select',return_value=ready),patch.object(m.os,'read',return_value=b'x'*(m.INSPECTION_BYTES+1)):
                with self.assertRaisesRegex(ValueError,'output bound' if oversized else 'deadline'):
                    PRODUCTION_INSPECT('-l',self.f.prefix/'lib/libjaccl.dylib')
            p.kill.assert_called_once(); p.wait.assert_called_once_with(timeout=5); p.stdout.close.assert_called_once()
            self.assertEqual(launch.call_args.args[0],['/usr/bin/otool','-l',str(self.f.prefix/'lib/libjaccl.dylib')])

    def test_inspector_unconfirmed_reap_refuses_and_closes_capture(self):
        p=Mock(); p.poll.return_value=None
        p.wait.side_effect=m.subprocess.TimeoutExpired('SYNTHETIC inspection',5)
        with patch.object(m.subprocess,'Popen',return_value=p),patch.object(m.select,'select',return_value=([],[],[])):
            with self.assertRaises(m.subprocess.TimeoutExpired):
                PRODUCTION_INSPECT('-l',self.f.prefix/'lib/libjaccl.dylib')
        p.wait.assert_called_once_with(timeout=5);p.stdout.close.assert_called_once()


if __name__=='__main__':unittest.main(verbosity=2)
