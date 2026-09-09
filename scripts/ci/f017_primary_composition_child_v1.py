"""Primary-only child: reused stdlib bootstrap, real fences, fixed imports.

This new tooling entry is not a Sequence54 replay. No research code executes
before sealing. No NumPy, secondary dispatch, live authority or arbitrary argv.
"""
import sys
import os
import resource
import stat
import hashlib
import json
import ctypes
import socket
# Static-reviewed installed stdlib closure; no project imports in this prefix.
import argparse, dataclasses, errno, heapq, math, pathlib, random, re, struct
import tempfile, typing, importlib.util, importlib.abc, importlib.machinery
import __future__
import subprocess
import ast
# Exercise only the standard-library parser's fixed setup before freezing its
# module closure. Python versions may load color/locale helpers lazily here.
_source_free_parser = argparse.ArgumentParser()
_source_free_parser.add_argument('--check', action='store_true')
del _source_free_parser

LIMIT = 32768
GENERATION_SHA256 = 'bc8d4faa5dba71d205d5b271f4bfdc754e90fdafcc0682c5ae7b03275590e7c7'
PASSIVE_STARTUP_IMAGES = (
    '/System/Library/Frameworks/Accelerate.framework/Versions/A/Frameworks/vecLib.framework/Versions/A/libBLAS.dylib',
    '/System/Library/Frameworks/Accelerate.framework/Versions/A/Frameworks/vecLib.framework/Versions/A/libSparseBLAS.dylib',
)
WRITE_ONCE_PATH = 'scripts/research/f017_write_once_artifact_v1.py'
WRITE_ONCE_SHA256 = 'da1eeead2fceb475557456048bd8bda1f3bfdbde5c407d4ddc3c92b6ee83e768'

def encoded(value):
    raw = (json.dumps(value, sort_keys=True, separators=(',',':'))+'\n').encode()
    if len(raw) > LIMIT:
        raise ValueError('bounded record overflow before output')
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def read_control(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > LIMIT:
            raise ValueError('bounded regular control required')
        raw = os.read(fd, LIMIT + 1)
        if len(raw) != st.st_size:
            raise ValueError('control byte count')
    finally:
        os.close(fd)
    return raw


def module_closure(framework):
    rows = []
    for name, module in sorted(sys.modules.items()):
        if name == '__main__':
            continue
        spec = getattr(module, '__spec__', None)
        origin = getattr(spec, 'origin', None)
        if origin in ('built-in', 'frozen'):
            pass
        elif type(origin) is str and origin.startswith(framework + '/lib/python') and '/site-packages/' not in origin:
            origin = origin.replace(framework, '@PYTHON_FRAMEWORK@')
        else:
            raise ValueError('unlisted module origin: '+name)
        rows.append({'name': name, 'origin': origin})
    return rows


def own_fds():
    result = []
    for item in os.listdir('/dev/fd'):
        fd = int(item)
        try:
            st = os.fstat(fd)
        except OSError:
            continue
        result.append({'fd':fd, 'type':stat.S_IFMT(st.st_mode)})
    return sorted(result, key=lambda row:row['fd'])


def fd_guard(rows):
    if any(type(r['fd']) is not int or r['fd'] > 2 for r in rows):
        raise ValueError('unexpected inherited descriptor')
    if [r['fd'] for r in rows] != [0,1,2]:
        raise ValueError('standard descriptor census')


def bind_spi():
    image = ctypes.CDLL('/usr/lib/libsandbox.dylib', use_errno=True)
    seal = image.sandbox_init_with_parameters
    seal.argtypes = [ctypes.c_char_p, ctypes.c_uint64,
                     ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_char_p)]
    seal.restype = ctypes.c_int
    free = image.sandbox_free_error
    free.argtypes = [ctypes.c_void_p]
    free.restype = None
    class DlInfo(ctypes.Structure):
        _fields_ = [('dli_fname',ctypes.c_char_p),('dli_fbase',ctypes.c_void_p),
                    ('dli_sname',ctypes.c_char_p),('dli_saddr',ctypes.c_void_p)]
    dladdr = image.dladdr
    dladdr.argtypes = [ctypes.c_void_p,ctypes.POINTER(DlInfo)]
    dladdr.restype = ctypes.c_int
    def provenance(fn):
        info = DlInfo()
        if dladdr(ctypes.cast(fn,ctypes.c_void_p),ctypes.byref(info)) == 0 or not info.dli_fname:
            raise ValueError('system image provenance missing')
        path = info.dli_fname.decode('utf-8','strict')
        if not (path.startswith('/usr/lib/') or path.startswith('/System/Library/')):
            raise ValueError('non-system SPI image')
        return path
    prov = {'logical_image':'/usr/lib/libsandbox.dylib',
            'seal_image':provenance(seal), 'free_image':provenance(free)}
    return seal, free, prov


def public_read(path):
    fd = os.open(path,os.O_RDONLY | os.O_NOFOLLOW)
    try:
        return os.read(fd,1024)
    finally:
        os.close(fd)


def public_write(path, raw):
    fd = os.open(path,os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,0o600)
    try:
        if os.write(fd,raw) != len(raw):
            raise OSError('fixture short write')
        os.fsync(fd)
    finally:
        os.close(fd)


def fences(row):
    observed = {'read':None,'write':None,'network':None}
    for name, op in (('read','open'),('write','create')):
        try:
            fd = os.open(row[name+'_path'], os.O_RDONLY | os.O_NOFOLLOW if name == 'read' else
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except OSError as error:
            observed[name] = {'operation':op,'return':-1,'errno':error.errno}
            if error.errno not in (1,13):
                return observed,False
        else:
            os.close(fd) # An unexpected read-open never reads any contents.
            observed[name] = {'operation':op,'return':0,'errno':None}
            return observed,False
    try:
        sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    except OSError as error:
        observed['network'] = {'operation':'socket','return':-1,'errno':error.errno}
        return observed,False
    try:
        sock.settimeout(2)
        try:
            sock.connect(tuple(row['endpoint']))
        except OSError as error:
            observed['network'] = {'operation':'connect','return':-1,'errno':error.errno}
            return observed,error.errno in (1,13)
        observed['network'] = {'operation':'connect','return':0,'errno':None}
        return observed,False
    finally:
        sock.close()


def fixed_io(row):
    raw = public_read(row['allowed_read_path'])
    payload = bytes.fromhex(row['fixture_expected']['write_hex'])
    public_write(row['allowed_write_path'],payload)
    back = public_read(row['allowed_write_path'])
    return {'read_hex':raw.hex(),'write_hex':back.hex(),'integer':(2**48)+17,
            'json_hex':encoded({'integer':(2**65)+17,'tag':'S53_PUBLIC'}).hex()}


def startup_images(images, declared):
    # Code constants are authoritative; data cannot union/normalize/broaden.
    if type(declared) is not list or declared != list(PASSIVE_STARTUP_IMAGES):
        raise ValueError('STARTUP_IMAGE_POLICY_DATA')
    if (type(images) is not list or not 1 <= len(images) <= 512
            or any(type(p) is not str or not p.startswith('/') or len(p) > 4096 for p in images)
            or len(set(images)) != len(images)):
        raise ValueError('STARTUP_IMAGE_CENSUS')
    if any(p not in images for p in PASSIVE_STARTUP_IMAGES):
        raise ValueError('STARTUP_IMAGE_MISSING')
    if any('numpy' in p.lower() or ('blas' in p.lower() and p not in PASSIVE_STARTUP_IMAGES) for p in images):
        raise ValueError('FORBIDDEN_NUMERICAL_IMAGE')
    return dict(count=len(images), sha256=sha(encoded(images)),
                passive_system_startup_images=list(PASSIVE_STARTUP_IMAGES),
                system_internal_BLAS_routine_calls='NOT_MEASURED', signatures='NOT_MEASURED')

def same_images(images, baseline, expected_sha, declared):
    current = startup_images(images, declared)
    if type(baseline) is not list or not baseline:
        raise ValueError('STARTUP_BASELINE_MISSING')
    startup_images(baseline, declared)
    if sha(encoded(baseline)) != expected_sha or images != baseline:
        raise ValueError('STARTUP_BASELINE_STALE_OR_CHANGED')
    return current

def source_import_policy(relative, raw):
    tree = ast.parse(raw, filename=relative)
    for node in ast.walk(tree):
        names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
        for name in names:
            if any(word in name.lower() for word in ('numpy', 'blas', 'secondary', 'cffi')):
                raise ValueError('PROJECT_BACKEND_IMPORT')
            if name.split('.')[0] == 'ctypes' and (relative != WRITE_ONCE_PATH or sha(raw) != WRITE_ONCE_SHA256):
                raise ValueError('PROJECT_NEW_CTYPES_CAPABILITY')

def policy_data_controls(images):
    declared = list(PASSIVE_STARTUP_IMAGES); expected = sha(encoded(images))
    first = images.index(PASSIVE_STARTUP_IMAGES[0]); missing = images[:first] + images[first+1:]
    wrong = list(images); wrong[first] = '/fixture/libBLAS.dylib'
    reordered = list(images); reordered[0], reordered[1] = reordered[1], reordered[0]
    cases = (
        ('IMG_FOREIGN_BLAS', lambda: startup_images(images+['/fixture/libOpenBLAS.dylib'], declared)),
        ('IMG_SAME_BASENAME_WRONG_PATH', lambda: startup_images(wrong, declared)),
        ('IMG_MISSING_EXPECTED_STARTUP', lambda: startup_images(missing, declared)),
        ('IMG_POST_BASELINE_ADDITION', lambda: same_images(images+['/fixture/innocent.dylib'], images, expected, declared)),
        ('IMG_POST_BASELINE_REMOVAL', lambda: same_images(images, missing, sha(encoded(missing)), declared)),
        ('IMG_POST_BASELINE_REORDER', lambda: same_images(reordered, images, expected, declared)),
        ('SOURCE_NEW_BACKEND_CAPABILITY', lambda: source_import_policy('qualification/new-capability.py', b'import ctypes\n')),
        ('SOURCE_SECONDARY', lambda: source_import_policy('qualification/secondary.py', b'import f017_corrected_oracle_secondary_numerics_v3\n')),
        ('BASELINE_MISSING', lambda: same_images(images, None, expected, declared)),
        ('BASELINE_STALE_DIGEST', lambda: same_images(images, images, '0'*64, declared)),
        ('DATA_BROADENING', lambda: startup_images(images, declared+['/fixture/libBLAS.dylib'])),
    )
    # Fixed internal test operations, not caller-supplied callbacks or loads.
    result=[]
    for name, operation in cases:
        try: operation()
        except ValueError as error: result.append(dict(case=name, result='REFUSED', reason=str(error)))
        else: raise ValueError('POLICY_MUTATION_SURVIVED:'+name)
    same_images(images, images, expected, declared)
    return dict(scope='INERT_DATA_AND_AST_CONTROLS_ONLY', positive='PASS', refusals=result,
                numerical_library_loads_attempted=False)

def loaded_images():
    # Query dyld's current in-memory image list, not payload files or proc maps.
    lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
    count = lib._dyld_image_count
    count.argtypes = []; count.restype = ctypes.c_uint32
    name = lib._dyld_get_image_name
    name.argtypes = [ctypes.c_uint32]; name.restype = ctypes.c_char_p
    total = count()
    if total > 512:
        raise ValueError('DYLD_IMAGE_CENSUS_BOUND')
    result = []
    for i in range(total):
        value = name(i)
        if not value:
            raise ValueError('DYLD_IMAGE_NAME_MISSING')
        text = value.decode('utf-8', 'strict')
        if len(text) > 4096:
            raise ValueError('DYLD_IMAGE_NAME_BOUND')
        result.append(text)
    if count() != total:
        raise ValueError('DYLD_IMAGE_CENSUS_CHANGED')
    startup_images(result, list(PASSIVE_STARTUP_IMAGES))
    return result

def record(cat, phase, detail):
    raw = encoded(dict(phase=phase, scope='PRIMARY_STDLIB_ONLY',
                       nonce=cat['nonce'], profile_sha256=cat['profile_sha256'],
                       child_sha256=cat['child_sha256'], detail=detail))
    while raw:
        n = os.write(1, raw)
        if n <= 0:
            raise OSError('OUTPUT_SHORT_WRITE')
        raw = raw[n:]

def sources(cat, root):
    view = root + '/tooling/codeview'
    files = cat['files']; modules = cat['modules']
    if not files or len(files) > 80 or len(modules) > 64:
        raise ValueError('SOURCE_CENSUS_BOUND')
    for relative, expected in files.items():
        if not re.fullmatch(r'[A-Za-z0-9_./-]+', relative) or '..' in relative.split('/') or relative.startswith('/'):
            raise ValueError('SOURCE_PATH')
        path = view + '/' + relative
        if os.path.realpath(path) != path:
            raise ValueError('SOURCE_SYMLINK')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            a = os.fstat(fd)
            if not stat.S_ISREG(a.st_mode) or a.st_nlink != 1 or a.st_mode & 0o222 or a.st_size > 1048576:
                raise ValueError('SOURCE_IMMUTABILITY')
            digest = hashlib.sha256(); size = 0
            while True:
                part = os.read(fd, 32768)
                if not part: break
                size += len(part); digest.update(part)
                if size > 1048576: raise ValueError('SOURCE_SIZE')
            b = os.fstat(fd)
            if (a.st_dev,a.st_ino,a.st_size,a.st_mtime_ns) != (b.st_dev,b.st_ino,b.st_size,b.st_mtime_ns) or size != a.st_size or digest.hexdigest() != expected:
                raise ValueError('SOURCE_IDENTITY_MISMATCH')
            os.lseek(fd, 0, os.SEEK_SET)
            source_raw = os.read(fd, 1048577)
            if sha(source_raw) != expected or len(source_raw) != size:
                raise ValueError('SOURCE_AST_READ_IDENTITY')
            fixed_refusal = (cat['mode']=='forbidden-import'
                and relative=='qualification/primary_incidental_dependency.py'
                and source_raw==b'import numpy\n')
            if not fixed_refusal:
                source_import_policy(relative, source_raw)
        finally:
            os.close(fd)
    for name, relative in modules.items():
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name) or relative not in files or name in sys.modules:
            raise ValueError('IMPORT_CENSUS')
        if 'numpy' in name.lower() or 'secondary' in name.lower() or 'blas' in name.lower():
            raise ValueError('FORBIDDEN_DEPENDENCY')
    before = frozenset(sys.modules); requested = []
    class FixedImports(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            requested.append(fullname)
            if fullname in modules:
                return importlib.util.spec_from_file_location(fullname, view+'/'+modules[fullname])
            raise ImportError('UNDECLARED_POST_SEAL_IMPORT:'+fullname)
    sys.meta_path.insert(0, FixedImports())
    return view, before, requested

def import_census(cat, view, before, requested, baseline_images):
    result = []
    introduced = set(sys.modules) - before
    if introduced - set(cat['modules']):
        raise ValueError('UNDECLARED_IMPORTED_MODULE')
    for name in sorted(introduced):
        module = sys.modules[name]
        origin = module.__spec__.origin
        expected = view+'/'+cat['modules'][name]
        if origin != expected or os.path.realpath(origin) != expected:
            raise ValueError('IMPORTED_ORIGIN')
        result.append(dict(name=name, path=cat['modules'][name],
                           sha256=cat['files'][cat['modules'][name]]))
    if any('numpy' in n.lower() or 'blas' in n.lower() or 'secondary' in n.lower() for n in sys.modules):
        raise ValueError('FORBIDDEN_LOADED_MODULE')
    return dict(project_modules=result, requested_imports=requested,
                image_census=same_images(loaded_images(), baseline_images,
                    sha(encoded(baseline_images)), cat['passive_startup_images']))

def validate(cat, root):
    fields = {'schema','scope','root','root_identity','python','python_framework',
              'nonce','child_sha256','profile_sha256','module_closure_sha256',
              'api_provenance','row','mode','files','modules','fixture_generation_sha256',
              'startup_baseline_sha256','passive_startup_images'}
    if set(cat) != fields or cat['schema'] != 'pulsarmlx.primary-stdlib-doctor-catalogue/1' or cat['scope'] != 'PRIMARY_STDLIB_ONLY':
        raise ValueError('CATALOGUE_SCHEMA')
    if root != cat['root'] or os.path.realpath(root) != root:
        raise ValueError('ROOT_BINDING')
    s=os.stat(root, follow_symlinks=False)
    if not stat.S_ISDIR(s.st_mode) or (s.st_mode&0o777)!=0o700 or s.st_uid!=os.getuid() or cat['root_identity']!={'dev':s.st_dev,'inode':s.st_ino}:
        raise ValueError('ROOT_IDENTITY')
    if cat['python'] != os.path.realpath(sys.executable) or cat['python_framework'] != os.path.realpath(sys.base_prefix):
        raise ValueError('INTERPRETER_IDENTITY')
    if cat['fixture_generation_sha256'] != GENERATION_SHA256 or cat['passive_startup_images'] != list(PASSIVE_STARTUP_IMAGES):
        raise ValueError('FIXED_GENERATION_POLICY')
    if cat['mode'] not in ('basic-baseline','basic','wrapper-baseline','wrapper','faults','edges'):
        raise ValueError('FIXED_MODE')
    row=cat['row']
    if set(row)!={'read_path','write_path','allowed_read_path','allowed_write_path','endpoint','public_nonce','fixture_expected'}:
        raise ValueError('ROW_SCHEMA')
    for key in ('allowed_read_path','allowed_write_path'):
        if os.path.dirname(row[key]) != root+'/work' or os.path.realpath(os.path.dirname(row[key])) != root+'/work':
            raise ValueError('WORK_PATH')
    for key in ('read_path','write_path'):
        if os.path.dirname(row[key]) != os.path.dirname(root)+'/denied' or os.path.realpath(os.path.dirname(row[key])) != os.path.dirname(root)+'/denied':
            raise ValueError('DENIAL_OWNED_SIBLING')
    if row['endpoint'][0]!='127.0.0.1' or type(row['endpoint'][1])is not int or not 1024<=row['endpoint'][1]<=65535:
        raise ValueError('LOOPBACK_ENDPOINT')
    return row

def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    # The existing parent capture observes/limits this owned child's RSS.
    # No unsupported RSS setrlimit call or permission widening occurs here.
    if not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode or sys.flags.optimize:
        raise ValueError('ISOLATED_NO_SITE_ENTRY')
    if sys.argv[1:]==['--describe-source-free']:
        _,_,provenance=bind_spi(); images=loaded_images()
        print(json.dumps(dict(python=os.path.realpath(sys.executable),
            python_framework=os.path.realpath(sys.base_prefix),
            module_closure=module_closure(os.path.realpath(sys.base_prefix)),
            api_provenance=provenance,loaded_images=images,environment=dict(os.environ),
            python_framework_image_identity='UNKNOWN',system_internal_BLAS_routine_calls='NOT_MEASURED'),sort_keys=True));return 0
    if sys.argv[1:] != ['--run-fixed']:
        raise ValueError('FIXED_ENTRY')
    resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
    root=os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    cat=json.loads(read_control(root+'/tooling/catalogue.json'),object_pairs_hook=unique)
    row=validate(cat,root);profile=read_control(root+'/tooling/profile.sb')
    if sha(read_control(__file__))!=cat['child_sha256'] or sha(profile)!=cat['profile_sha256']:
        raise ValueError('CHILD_PROFILE_IDENTITY')
    if cat['mode']=='positive':
        a=public_read(row['read_path']);public_write(row['write_path'],bytes.fromhex(row['fixture_expected']['write_hex']))
        b=public_read(row['write_path'])
        with socket.socket()as sock:
            sock.settimeout(2);sock.connect(tuple(row['endpoint']));sock.sendall(row['public_nonce'].encode());ack=sock.recv(128)
        record(cat,'POSITIVE_COMPLETE',dict(read_hex=a.hex(),write_hex=b.hex(),ack_hex=ack.hex()));return 0
    seal,free,provenance=bind_spi();images=loaded_images()
    closure=module_closure(cat['python_framework'])
    if sha(encoded(closure))!=cat['module_closure_sha256'] or provenance!=cat['api_provenance']:
        raise ValueError('SOURCE_FREE_CLOSURE_MISMATCH')
    baseline_raw=read_control(root+'/tooling/startup-baseline.json')
    if sha(baseline_raw)!=cat['startup_baseline_sha256']:
        raise ValueError('STARTUP_BASELINE_IDENTITY')
    baseline=json.loads(baseline_raw,object_pairs_hook=unique)
    if (set(baseline)!={'images','python','child_sha256','generation_sha256','environment','module_closure_sha256'}
            or baseline['python']!=cat['python'] or baseline['child_sha256']!=cat['child_sha256']
            or baseline['generation_sha256']!=GENERATION_SHA256
            or baseline['environment']!=dict(os.environ)
            or baseline['module_closure_sha256']!=cat['module_closure_sha256']
            or any(k.startswith(('DYLD_','LD_')) for k in os.environ)):
        raise ValueError('STARTUP_BASELINE_BINDING')
    image_state=same_images(images,baseline['images'],sha(encoded(baseline['images'])),cat['passive_startup_images'])
    fds=own_fds();fd_guard(fds)
    record(cat,'PRE_SEAL',dict(stdlib_closure_sha256=sha(encoded(closure)),fds=fds,image_census=image_state,project_imports=[]))
    error=ctypes.c_char_p(None);params=(ctypes.c_char_p*1)(None)
    result=seal(profile,0,params,ctypes.byref(error));message=None
    if error:
        try:message=error.value.decode('utf-8','replace')
        finally:free(ctypes.cast(error,ctypes.c_void_p))
    if result!=0 or message is not None:
        record(cat,'SEAL_FAILED',dict(returncode=result,error=message));return 20
    record(cat,'SEAL_APPLIED',dict(returncode=0))
    observed,ok=fences(row)
    if not ok:record(cat,'FENCE_FAILED',observed);return 21
    try:
        pid=os.posix_spawn(cat['python'],[cat['python'],'-I','-S','-B',root+'/tooling/escape-control.py'],dict(PATH='/usr/bin:/bin'))
    except OSError as error:
        observed['exec']=dict(errno=error.errno,actual_target_start=False)
        if error.errno not in (1,13):record(cat,'FENCE_FAILED',observed);return 21
    else:
        try:os.kill(pid,9)
        except ProcessLookupError:pass
        _,status=os.waitpid(pid,0)
        observed['exec']=dict(actual_target_start=True,pid=pid,reaped=True,status=status)
        record(cat,'FENCE_FAILED',observed);return 21
    record(cat,'FENCE_PASSED',observed)
    detail=fixed_io(row)
    if cat['mode']=='policy-data':
        detail['policy_controls']=policy_data_controls(images)
        detail['image_census']=same_images(loaded_images(),images,sha(encoded(images)),cat['passive_startup_images'])
        record(cat,'FIXTURE_COMPLETE',detail);return 0
    view,before,requested=sources(cat,root)
    if cat['mode']=='forbidden-import':
        try:importlib.import_module('primary_incidental_dependency')
        except ImportError as error:
            if str(error)!='UNDECLARED_POST_SEAL_IMPORT:numpy':raise
            detail['expected_refusal']=str(error)
        else:raise ValueError('INCIDENTAL_DEPENDENCY_ACCEPTED')
    else:
        module=importlib.import_module('current_composition_cases')
        detail['case_result']=module.run(cat['mode'],root+'/work',view)
    detail['import_census']=import_census(cat,view,before,requested,images)
    record(cat,'FIXTURE_COMPLETE',detail)
    return 0

if __name__=='__main__':
    raise SystemExit(main())
