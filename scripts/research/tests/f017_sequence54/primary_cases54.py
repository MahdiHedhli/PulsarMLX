"""Fixed Sequence54 synthetic dispatch. Imported only after all three fences.

This file is qualification tooling, never a production authority or provider.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

GEOMETRY = dict(layers=1, hidden=4, vocab=9, dense_layers=1, experts=4,
    top_k=2, dense_ffn=6, expert_ffn=4, heads=1, q_rank=4, kv_rank=4,
    qk_nope=4, qk_rope=2, value_dim=4, rms_epsilon=1e-5,
    rope_base=8000000.0, route_scale=2.5)

def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()

def bank(path, raw):
    if len(raw) > 1048576:
        raise ValueError('synthetic fixture cap')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        if os.write(fd, raw) != len(raw):
            raise OSError('synthetic fixture short write')
        os.fsync(fd)
    finally:
        os.close(fd)

def ident(fd, ordinal):
    s = os.fstat(fd)
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1:
        raise ValueError('qualification descriptor ownership')
    return dict(device=s.st_dev, inode=s.st_ino, mode=s.st_mode, size=s.st_size,
        mtime_ns=s.st_mtime_ns, ctime_ns=s.st_ctime_ns, shard_ordinal=ordinal,
        role='GRAPH_PAYLOAD', lease_id='S54-LEASE-'+str(ordinal))

def run(case_id, work_dir, code_view):
    if case_id in ('BASIC_BASELINE','WRAPPER_BASELINE','BASIC_SUCCESSOR','WRAPPER_SUCCESSOR','FAULTS_SUCCESSOR'):
        import primary_suite54
        return primary_suite54.run(case_id, work_dir, code_view)
    if case_id != 'BASELINE_SMOKE':
        raise ValueError('unregistered fixed case')
    # The bootstrap has already verified provenance and inserted exactly this view.
    import f017_corrected_oracle_primary_target_source_v11 as target
    root = Path(work_dir)
    if root.resolve() != root or not root.is_dir():
        raise ValueError('fixed qualification root')
    area = root / 'BASELINE_SMOKE'
    area.mkdir(mode=0o700)
    payloads = [struct.pack('<4f', 1, 2, -3, 4), struct.pack('<f', 0.5), b'\0'*4, b'\0'*4, b'\0'*4]
    handles = []
    transcript = []
    original = os.pread
    try:
        for ordinal, raw in enumerate(payloads, 2):
            p = area / ('public-'+str(ordinal)+'.bin')
            bank(p, raw)
            handles.append(os.open(p, os.O_RDONLY | os.O_NOFOLLOW))
        identities = [ident(fd, ordinal) for ordinal, fd in enumerate(handles, 2)]
        records = [dict(name='v', format='F32', dims=[4], shard_ordinal=2,
                    byte_offset=0, byte_length=16, purpose='GRAPH'),
                   dict(name='p', format='F32', dims=[1], shard_ordinal=3,
                    byte_offset=0, byte_length=4, purpose='FORMAT_PROBE')]
        document = dict(schema='pulsarmlx.f017.synthetic-descriptor-catalog/9.0.0',
                        geometry=GEOMETRY, token=0, position=0, records=records)
        catalog = canonical(document)
        catalog_path = area/'catalog.json'
        bank(catalog_path, catalog)
        candidate = dict(tensor_catalog_path=str(catalog_path),
            tensor_catalog_sha256=hashlib.sha256(catalog).hexdigest(),
            shards=[dict(size_bytes=0)]+[dict(size_bytes=len(raw)) for raw in payloads])
        authority = {fd:ordinal for ordinal, fd in enumerate(handles, 2)}
        def observed(fd, size, offset):
            # Exact real-file call; independent transcript contains no producer counters.
            row = dict(shard=authority[fd], requested=size, offset=offset)
            transcript.append(row)
            value = original(fd, size, offset)
            row['returned'] = len(value)
            return value
        os.pread = observed
        source, geometry, token, position = target.source_from_inherited_descriptors(candidate, identities, handles)
        value = source.vector('v', 4)
        expected = [dict(shard=3, requested=4, offset=0, returned=4),
                    dict(shard=2, requested=16, offset=0, returned=16)]
        assert transcript == expected
        assert value == [1.0, 2.0, -3.0, 4.0]
        assert source.tensor_reads == 2 and source.path_reopen_count == 0
        return dict(result='PASS', case=case_id, actual_transcript=transcript,
                    decoded=value, factory_probe='PASS', descriptor_ownership='PASS',
                    expected_transcript=expected, target_import_after_fences=True,
                    instrumentation='NOT_STARTED', numerical_core='NOT_RUN')
    finally:
        os.pread = original
        for fd in handles:
            os.close(fd)
