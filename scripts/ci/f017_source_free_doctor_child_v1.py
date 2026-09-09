"""Fixed source-free doctor child, derived from the accepted self-sealing prefix.

No project numerical import or arbitrary dispatch exists. NumPy is the one
installed third-party dependency, imported only after actual denial fences.
This does not inventory all Mach capabilities or qualify native compilation.
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
import sysconfig
DEPENDENCY_ROOT = os.path.realpath(sysconfig.get_path('purelib'))
DEPENDENCY_PACKAGE = os.path.dirname(os.path.realpath(DEPENDENCY_ROOT+'/numpy/__init__.py'))
# Exercise only the standard-library parser's fixed setup before freezing its
# module closure. Python versions may load color/locale helpers lazily here.
_source_free_parser = argparse.ArgumentParser()
_source_free_parser.add_argument('--check', action='store_true')
del _source_free_parser

LIMIT = 32768
ROW_PATTERN = re.compile(r'S54-(B(?:0[1-9]|[1-9][0-9]))-(POSITIVE|BASELINE|SUCCESSOR|POSITIVE-FRESH|FRESH)\Z')
MODE_MAP = {'POSITIVE':'positive','BASELINE':'baseline','SUCCESSOR':'successor','POSITIVE-FRESH':'positive','FRESH':'fresh'}
CASE_IDS = frozenset(('CI_SCOPE_TESTS','INTEGRATION','HISTORICAL_DRIFT_CONTROL','ACTIVE_CENSUS_CONTROL','BASELINE_SMOKE','BASIC_BASELINE','WRAPPER_BASELINE','BASIC_SUCCESSOR','WRAPPER_SUCCESSOR','FAULTS_SUCCESSOR'))
VIEW_IDS = frozenset(('baseline','successor','baseline-b02','baseline-b03','successor-b04','successor-b05','successor-b06','successor-b07','successor-b08','successor-b09'))
CAT_KEYS = frozenset(('schema','sequence','root','root_identity','python',
    'python_framework','bootstrap_sha256','profile_sha256','module_closure_sha256',
    'api_provenance','rows','code_manifests','dispatch_sha256','dependency_root','dependency_package'))
ROW_KEYS = frozenset(('mode','nonce','read_path','write_path','allowed_read_path',
    'allowed_write_path','endpoint','public_nonce','fixture_expected','fixture_identity','case_id','view'))

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

def validate_catalogue(cat, root, row_id):
    if set(cat) != CAT_KEYS or cat['schema'] != 'pulsarmlx.f017.source-free-doctor-catalogue/1' or type(cat['sequence']) is not int or cat['sequence'] != 54:
        raise ValueError('catalogue schema')
    if cat['root'] != root or os.path.realpath(root) != root or '@' in root:
        raise ValueError('root binding')
    s = os.stat(root, follow_symlinks=False)
    if not stat.S_ISDIR(s.st_mode) or (s.st_mode & 0o777) != 0o700 or s.st_uid != os.getuid():
        raise ValueError('owner-only root')
    if cat['root_identity'] != {'dev':str(s.st_dev),'inode':str(s.st_ino)}:
        raise ValueError('stale root')
    if cat['python'] != os.path.realpath(sys.executable) or row_id not in cat['rows'] or ROW_PATTERN.fullmatch(row_id) is None:
        raise ValueError('closed executable or row')
    row = cat['rows'][row_id]
    if set(row) != ROW_KEYS or row['mode'] not in ('positive','baseline','successor','fresh'):
        raise ValueError('row schema')
    if row['mode'] != MODE_MAP[ROW_PATTERN.fullmatch(row_id)[2]]:
        raise ValueError('fixed row mode')
    if row['endpoint'][0] != '127.0.0.1' or type(row['endpoint'][1]) is not int or not 1024 <= row['endpoint'][1] <= 65535:
        raise ValueError('own loopback endpoint')
    for key in ('allowed_read_path','allowed_write_path'):
        p = row[key]
        if os.path.dirname(p) != root+'/work' or os.path.realpath(os.path.dirname(p)) != root+'/work':
            raise ValueError('work path escape')
    for key in ('read_path','write_path'):
        p = row[key]
        if not p.startswith('/') or '@' in p or '/..' in p or os.path.realpath(os.path.dirname(p)) != os.path.dirname(p):
            raise ValueError('denial path escape')
        if p.startswith(root+'/'):
            raise ValueError('denial fixture overlaps graph')
    if row['mode'] == 'positive':
        if row['case_id'] is not None or row['view'] is not None:
            raise ValueError('positive control cannot dispatch source')
    elif row['case_id'] != 'SOURCE_FREE_DOCTOR' or row['view'] is not None:
        raise ValueError('fixed source dispatch selector')
    if cat['dependency_root'] != os.path.realpath(sysconfig.get_path('purelib')):
        raise ValueError('fixed installed dependency root')
    if cat['dependency_package'] != DEPENDENCY_PACKAGE:
        raise ValueError('fixed resolved dependency package')
    return row

def emit(row_id, row, cat, phase, ordinal, detail):
    raw = encoded({'phase':phase,'row':row_id,'nonce':row['nonce'],'ordinal':ordinal,
        'profile_sha256':cat['profile_sha256'],'bootstrap_sha256':cat['bootstrap_sha256'],
        'detail':detail})
    view = memoryview(raw)
    while view:
        n = os.write(1,view)
        if n <= 0:
            raise OSError('short output')
        view = view[n:]

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

def positive(row_id,row,cat):
    raw = public_read(row['read_path'])
    public_write(row['write_path'], bytes.fromhex(row['fixture_expected']['write_hex']))
    reread = public_read(row['write_path'])
    os.unlink(row['write_path'])
    sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    sock.settimeout(2)
    try:
        sock.connect(tuple(row['endpoint']))
        nonce = row['public_nonce'].encode()
        sock.sendall(nonce)
        ack = sock.recv(128)
    finally:
        sock.close()
    emit(row_id,row,cat,'POSITIVE_COMPLETE',1,{'read_hex':raw.hex(),
        'write_hex':reread.hex(),'ack_hex':ack.hex()})

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



def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    if sys.flags.optimize != 0:
        raise ValueError('qualification requires optimization disabled')
    if sys.argv[1:] == ['--describe-source-free']:
        _, _, provenance = bind_spi()
        print(json.dumps({'python':os.path.realpath(sys.executable), 'python_framework':os.path.realpath(sys.base_prefix), 'module_closure':module_closure(os.path.realpath(sys.base_prefix)), 'api_provenance':provenance, 'dependency_root':DEPENDENCY_ROOT, 'dependency_package':DEPENDENCY_PACKAGE}, sort_keys=True))
        return 0
    # Sequence54 separately bounds synthetic files; stream/measurement records
    # remain 32768 bytes in their independent serializers and parent capture.
    resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
    if len(sys.argv) != 2 or ROW_PATTERN.fullmatch(sys.argv[1]) is None or not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode:
        raise ValueError('fixed isolated argv required')
    root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    cat = json.loads(read_control(root+'/tooling/catalogue54-'+ROW_PATTERN.fullmatch(sys.argv[1])[1]+'.json'),object_pairs_hook=unique)
    row_id = sys.argv[1]
    row = validate_catalogue(cat,root,row_id)
    raw_profile = read_control(root+'/tooling/baseline.sb')
    if sha(read_control(__file__)) != cat['bootstrap_sha256'] or sha(raw_profile) != cat['profile_sha256']:
        raise ValueError('bootstrap or profile hash')
    if row['mode'] == 'positive':
        positive(row_id,row,cat)
        return
    seal,free,prov = bind_spi()
    modules = module_closure(cat['python_framework'])
    if sha(encoded(modules)) != cat['module_closure_sha256'] or prov != cat['api_provenance']:
        raise ValueError('module closure or system SPI provenance')
    fds = own_fds()
    try:
        fd_guard(fds)
    except ValueError:
        for record in fds:
            if record['fd'] > 2:
                os.close(record['fd'])
        raise
    params = (ctypes.c_char_p * 1)(None)
    error = ctypes.c_char_p(None)
    emit(row_id,row,cat,'PRE_SEAL',1,{'module_closure_sha256':cat['module_closure_sha256'],
        'fd_numbers':[r['fd'] for r in fds],'unexpected_fds':[],'api_provenance':prov,
        'preseal_fixture_operations':0})
    result = seal(raw_profile,0,params,ctypes.byref(error))
    message = None
    if error:
        try:
            message = error.value.decode('utf-8','replace')
        finally:
            free(ctypes.cast(error,ctypes.c_void_p))
    if result != 0 or message is not None:
        emit(row_id,row,cat,'SEAL_FAILED',2,{'api_return':result,'error':message})
        return 20
    emit(row_id,row,cat,'SEAL_APPLIED',2,{'api_return':result,'error':message})
    observed,ok = fences(row)
    if not ok:
        emit(row_id,row,cat,'FENCE_FAILED',3,observed)
        return 21
    emit(row_id,row,cat,'FENCE_PASSED',3,observed)
    detail = fixed_io(row)
    # Resolve the one package directly: do not enumerate/read the surrounding
    # site-packages directory or admit arbitrary package names through sys.path.
    entry = cat['dependency_package']+'/__init__.py'
    spec = importlib.util.spec_from_file_location('numpy', entry,
        submodule_search_locations=[cat['dependency_package']])
    if spec is None or spec.loader is None:
        raise ValueError('fixed dependency entry')
    np = importlib.util.module_from_spec(spec)
    sys.modules['numpy'] = np
    spec.loader.exec_module(np)
    if (np.asarray([1.0,2.0], dtype=np.float64)+1.0).tolist() != [2.0,3.0]:
        raise ValueError('fixed dependency arithmetic')
    origin = os.path.realpath(np.__file__)
    if not origin.startswith(cat['dependency_package']+'/'):
        raise ValueError('dependency origin')
    detail.update(numpy_version=np.__version__, numpy_origin=origin, numpy_entry_sha256=sha(read_control(origin)), project_modules_imported=0)
    detail['loaded_numpy_modules'] = sorted(name for name in sys.modules if name=='numpy' or name.startswith('numpy.'))
    emit(row_id,row,cat,'FIXTURE_COMPLETE',4,detail)
    return 0

if __name__ == '__main__':
    sys.exit(main())
