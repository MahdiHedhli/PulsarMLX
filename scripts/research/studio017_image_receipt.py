"""Verify the reaped child's two loader observations against independently pinned images."""
import ctypes
import os

from studio017_guard import hexid, need, opened, parse, sha

LINE_LIMIT = 256 << 10


def check_host_cache(expected_uuid, observed_size, names):
    """Check both observations against the owner's OS cache, including libraries this process did not load."""
    dyld = ctypes.CDLL(None)
    uuid = (ctypes.c_ubyte * 16)()
    uuid_query = dyld._dyld_get_shared_cache_uuid
    uuid_query.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
    uuid_query.restype = ctypes.c_bool
    size = ctypes.c_size_t()
    cache_range = dyld._dyld_get_shared_cache_range
    cache_range.argtypes = [ctypes.POINTER(ctypes.c_size_t)]
    cache_range.restype = ctypes.c_void_p
    need(uuid_query(uuid) and bytes(uuid).hex() == expected_uuid and
         cache_range(ctypes.byref(size)) and size.value == observed_size, 'owner Darwin cache identity')
    contains = dyld._dyld_shared_cache_contains_path
    contains.argtypes = [ctypes.c_char_p]
    contains.restype = ctypes.c_bool
    need(all(contains(os.fsencode(name)) for name in names), 'observed path outside owner Darwin cache')


def checked_observations(stdout, expected_inode, policy, operation, pid):
    """Read the owner's exact capture. Darwin's shared-cache membership can grow between samples."""
    hexid(operation, 32)
    need(type(pid) is int and pid > 1, 'invalid original native PID')
    with opened(stdout, 2 * LINE_LIMIT) as (fd, st):
        need([st.st_dev, st.st_ino] == expected_inode and st.st_uid == os.geteuid()
             and st.st_nlink == 1 and not st.st_mode & 0o077, 'replaced or nonprivate native stdout')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            raw = stream.read(2 * LINE_LIMIT + 1)
        need(len(raw) == st.st_size, 'short native stdout')

    parts = raw.split(b'\n')
    need(len(parts) == 3 and parts[-1] == b'', 'expected two complete native image observations')
    observations = {}
    for phase, line in zip(('before', 'after'), parts):
        need(0 < len(line) + 1 <= LINE_LIMIT, 'native image observation exceeds limit')
        record = parse(line)
        need(isinstance(record, dict) and set(record) == {'schema', 'phase', 'pid', 'operation', 'census'}
             and record['schema'] == 'studio017-native-image-observation/1' and record['phase'] == phase
             and record['operation'] == operation and type(record['pid']) is int and record['pid'] == pid,
             'wrong native image observation, phase or process')
        census = record['census']
        need(isinstance(census, dict) and set(census) == {'schema', 'noncache_images', 'shared_cache_uuid',
             'shared_cache_bytes', 'shared_cache_images'} and census['schema'] == 'studio017-native-images/1',
             'native image census schema')
        need(census['shared_cache_uuid'] == policy['platform_cache_uuid'] and
             type(census['shared_cache_bytes']) is int and 0 < census['shared_cache_bytes'] < 64 << 30
             and census['noncache_images'] == policy['noncache_images'], 'native image bindings disagree')
        shared = census['shared_cache_images']
        need(isinstance(shared, list) and 0 < len(shared) < 4096 - len(policy['noncache_images'])
             and all(type(n) is str and n.startswith('/') and len(n) <= 4096 and '\x00' not in n for n in shared)
             and shared == sorted(set(shared)) and not set(shared).intersection(policy['noncache_images']),
             'invalid shared-cache image list')
        observations[phase] = census
    need(observations['before']['shared_cache_bytes'] == observations['after']['shared_cache_bytes'],
         'Darwin shared cache size changed')
    names = set(observations['before']['shared_cache_images']) | set(observations['after']['shared_cache_images'])
    check_host_cache(policy['platform_cache_uuid'], observations['before']['shared_cache_bytes'], names)
    return dict(stdout_sha256=sha(raw), stdout_bytes=len(raw), observations=observations)
