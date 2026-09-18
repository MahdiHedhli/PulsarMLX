"""Offline (stdlib) checks of repack_v2's fail-safe behaviour (graph 32): a valid copy is byte-for-byte equal per tensor and
validated; truncated headers and payloads, short reads, missing parts, dtype/shape vs length mismatches, overlapping
intervals, interrupted writes, existing destinations and aliases each terminate with an explicit error and leave no
newly published valid-looking file. A watchdog kills the process if the old hang recurs.

The safetensors files are built here with a stdlib writer independent of the runtime's parser."""
import faulthandler
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/research/glm53_flash/dogfood'))
import repack_v2  # noqa: E402

faulthandler.dump_traceback_later(60, exit=True)   # the pre-graph-32 copy loop hung forever on a truncated source


def tensor_bytes(seed, n):
    return bytes((seed * 131 + i * 7) % 256 for i in range(n))


def write_st(path, tensors, metadata=None, order=None, header_pad=True):
    """tensors: {name: (dtype, shape, data bytes)}; data laid out in `order` (default: dict order)."""
    order = order or list(tensors)
    header = {}
    off = 0
    for n in order:
        dtype, shape, data = tensors[n]
        header[n] = {'dtype': dtype, 'shape': shape, 'data_offsets': [off, off + len(data)]}
        off += len(data)
    doc = {}
    if metadata is not None:
        doc['__metadata__'] = metadata
    doc.update(header)
    hdr = json.dumps(doc, separators=(',', ':')).encode()
    if header_pad:
        hdr += b' ' * ((8 - len(hdr) % 8) % 8)
    with open(path, 'wb') as fh:
        fh.write(struct.pack('<Q', len(hdr))); fh.write(hdr)
        for n in order:
            fh.write(tensors[n][2])
    return header


def read_st(path):
    """Independent reader: {name: (dtype, shape, bytes)} plus metadata."""
    with open(path, 'rb') as fh:
        n = struct.unpack('<Q', fh.read(8))[0]; header = json.loads(fh.read(n)); base = 8 + n
        out = {}
        for name, e in header.items():
            if name == '__metadata__':
                continue
            a, b = e['data_offsets']; fh.seek(base + a); out[name] = (e['dtype'], e['shape'], fh.read(b - a))
    return out, header.get('__metadata__')


def expert_tensors(E, hidden=8, inter=16, bits=4, group=8):
    """A hash-ordered layer file's tensors: every expert's nine parts with realistic shapes; U32 words, F32 scales/biases."""
    per_word = 32 // bits
    t = {}
    seed = 0
    for j in range(E):
        for p in ('gate_proj', 'up_proj', 'down_proj'):
            out, inp = (inter, hidden) if p != 'down_proj' else (hidden, inter)
            t[f'e{j}.{p}.weight'] = ('U32', [out, inp // per_word], tensor_bytes(seed, out * (inp // per_word) * 4)); seed += 1
            t[f'e{j}.{p}.scales'] = ('F32', [out, inp // group], tensor_bytes(seed, out * (inp // group) * 4)); seed += 1
            t[f'e{j}.{p}.biases'] = ('F32', [out, inp // group], tensor_bytes(seed, out * (inp // group) * 4)); seed += 1
    return t


def scattered_order(names):
    """A deterministic non-expert-contiguous order (what an unordered-map writer produces)."""
    return sorted(names, key=lambda n: (hash(n) % 7, n))


class RepackV2FailSafe(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix='repack-v2-', dir=os.environ.get('TMPDIR')))
        self.tensors = expert_tensors(4)
        self.src = self.dir / 'src.safetensors'; self.dst = self.dir / 'dst.safetensors'
        write_st(self.src, self.tensors, metadata={'format': 'mlx'}, order=scattered_order(list(self.tensors)))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def assert_no_dst(self):
        self.assertFalse(self.dst.exists(), 'a destination was published'); self.assertFalse(Path(str(self.dst) + repack_v2.PARTIAL).exists(), 'a .partial was left')

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_valid_copy_is_byte_identical_and_contiguous(self):
        self.assertFalse(repack_v2.check_contiguous(str(self.src)))
        experts, nbytes = repack_v2.write_contiguous(str(self.src), str(self.dst), chunk=100)   # small chunk: many reads per tensor
        self.assertEqual(experts, [0, 1, 2, 3]); self.assertEqual(nbytes, sum(len(d) for _, _, d in self.tensors.values()))
        got, meta = read_st(self.dst)
        self.assertEqual(got, self.tensors); self.assertEqual(meta['layout'], repack_v2.LAYOUT); self.assertEqual(meta['format'], 'mlx')
        self.assertTrue(repack_v2.check_contiguous(str(self.dst)))
        raw = self.dst.read_bytes(); header = json.loads(raw[8:8 + struct.unpack('<Q', raw[:8])[0]])
        names = [k for k in header if k != '__metadata__']
        self.assertEqual(names, [f'e{j}.{p}.{k}' for j in range(4) for p in ('gate_proj', 'up_proj', 'down_proj') for k in ('weight', 'scales', 'biases')])
        starts = [header[n]['data_offsets'][0] for n in names]
        self.assertEqual(starts, sorted(starts))

    def test_truncated_header_rejected(self):
        raw = self.src.read_bytes()
        (self.dir / 'bad.safetensors').write_bytes(raw[:200])       # header longer than the file
        with self.assertRaisesRegex(repack_v2.RepackError, 'HEADER_TRUNCATED'):
            repack_v2.write_contiguous(str(self.dir / 'bad.safetensors'), str(self.dst))
        (self.dir / 'tiny.safetensors').write_bytes(raw[:4])
        with self.assertRaisesRegex(repack_v2.RepackError, 'HEADER_TRUNCATED'):
            repack_v2.write_contiguous(str(self.dir / 'tiny.safetensors'), str(self.dst))
        self.assert_no_dst()

    def test_truncated_payload_rejected_before_copy(self):
        raw = self.src.read_bytes()
        (self.dir / 'trunc.safetensors').write_bytes(raw[:-100])
        calls = []
        with self.assertRaisesRegex(repack_v2.RepackError, 'FILE_LENGTH_MISMATCH'):
            repack_v2.write_contiguous(str(self.dir / 'trunc.safetensors'), str(self.dst), fault_hook=lambda *a: calls.append(a))
        self.assertEqual(calls, [], 'copy started on a truncated source'); self.assert_no_dst()
        (self.dir / 'long.safetensors').write_bytes(raw + b'xx')    # trailing bytes are a mismatch too
        with self.assertRaisesRegex(repack_v2.RepackError, 'FILE_LENGTH_MISMATCH'):
            repack_v2.write_contiguous(str(self.dir / 'long.safetensors'), str(self.dst))

    def test_short_read_terminates(self):
        """The source passes validation, then shrinks before the copy (the old loop spun forever here)."""
        def shrink(stage, *a):
            if stage == 'before-copy':
                os.truncate(self.src, os.path.getsize(self.src) - 500)
        with self.assertRaisesRegex(repack_v2.RepackError, 'SHORT_READ_EOF'):
            repack_v2.write_contiguous(str(self.src), str(self.dst), chunk=64, fault_hook=shrink)
        self.assert_no_dst()

    def test_missing_part_rejected(self):
        t = dict(self.tensors); del t['e2.up_proj.scales']
        write_st(self.dir / 'missing.safetensors', t, order=scattered_order(list(t)))
        with self.assertRaisesRegex(repack_v2.RepackError, 'INVENTORY_MISMATCH'):
            repack_v2.write_contiguous(str(self.dir / 'missing.safetensors'), str(self.dst))
        t = dict(self.tensors); t['stray'] = ('F32', [2], b'\0' * 8)
        write_st(self.dir / 'stray.safetensors', t)
        with self.assertRaisesRegex(repack_v2.RepackError, 'UNEXPECTED_TENSORS'):
            repack_v2.write_contiguous(str(self.dir / 'stray.safetensors'), str(self.dst))
        self.assert_no_dst()

    def test_length_dtype_shape_mismatch_rejected(self):
        t = dict(self.tensors); dtype, shape, data = t['e0.gate_proj.weight']; t['e0.gate_proj.weight'] = ('U32', [shape[0], shape[1] + 1], data)
        write_st(self.dir / 'shape.safetensors', t)
        with self.assertRaisesRegex(repack_v2.RepackError, 'LENGTH_MISMATCH'):
            repack_v2.validate_file(str(self.dir / 'shape.safetensors'))
        t = dict(self.tensors); t['e0.gate_proj.weight'] = ('U16', shape, data)      # itemsize halves, bytes do not
        write_st(self.dir / 'dtype.safetensors', t)
        with self.assertRaisesRegex(repack_v2.RepackError, 'LENGTH_MISMATCH'):
            repack_v2.validate_file(str(self.dir / 'dtype.safetensors'))
        t = dict(self.tensors); t['e0.gate_proj.weight'] = ('Q4', shape, data)
        write_st(self.dir / 'unknown.safetensors', t)
        with self.assertRaisesRegex(repack_v2.RepackError, 'DTYPE_UNKNOWN'):
            repack_v2.validate_file(str(self.dir / 'unknown.safetensors'))

    def test_overlapping_or_gapped_intervals_rejected(self):
        raw = self.src.read_bytes(); n = struct.unpack('<Q', raw[:8])[0]; header = json.loads(raw[8:8 + n])
        name = next(k for k in header if k != '__metadata__' and header[k]['data_offsets'][0] > 0)
        bad = json.loads(json.dumps(header)); bad[name]['data_offsets'][0] -= 4      # overlaps its predecessor; length now mismatches too
        bad[name]['shape'] = [bad[name]['data_offsets'][1] - bad[name]['data_offsets'][0]]; bad[name]['dtype'] = 'U8'
        hdr = json.dumps(bad, separators=(',', ':')).encode(); hdr += b' ' * ((8 - len(hdr) % 8) % 8)
        (self.dir / 'overlap.safetensors').write_bytes(struct.pack('<Q', len(hdr)) + hdr + raw[8 + n:])
        with self.assertRaisesRegex(repack_v2.RepackError, 'INTERVALS_NOT_TILING'):
            repack_v2.validate_file(str(self.dir / 'overlap.safetensors'))

    def test_interrupted_write_leaves_nothing_published(self):
        def crash(stage, *a):
            if stage == 'copied' and a[0] == 5:
                raise KeyboardInterrupt('simulated interruption')
        with self.assertRaises(KeyboardInterrupt):
            repack_v2.write_contiguous(str(self.src), str(self.dst), fault_hook=crash)
        self.assert_no_dst()
        repack_v2.write_contiguous(str(self.src), str(self.dst))              # a rerun completes
        self.assertTrue(repack_v2.check_contiguous(str(self.dst)))

    def test_truncated_destination_fails_check(self):
        repack_v2.write_contiguous(str(self.src), str(self.dst))
        raw = self.dst.read_bytes(); self.dst.write_bytes(raw[:-1])
        self.assertFalse(repack_v2.check_contiguous(str(self.dst)))         # the pre-graph-32 check passed this
        self.dst.write_bytes(raw + b'\0')
        self.assertFalse(repack_v2.check_contiguous(str(self.dst)))
        self.dst.write_bytes(raw)
        self.assertTrue(repack_v2.check_contiguous(str(self.dst)))

    def test_existing_destination_and_aliases_refused(self):
        self.dst.write_bytes(b'not a repack')
        with self.assertRaisesRegex(repack_v2.RepackError, 'DST_EXISTS'):
            repack_v2.write_contiguous(str(self.src), str(self.dst))
        self.assertEqual(self.dst.read_bytes(), b'not a repack')
        with self.assertRaisesRegex(repack_v2.RepackError, 'ALIAS'):
            repack_v2.write_contiguous(str(self.src), str(self.src))
        link = self.dir / 'link.safetensors'; os.symlink(self.src, link)
        with self.assertRaisesRegex(repack_v2.RepackError, 'ALIAS'):
            repack_v2.write_contiguous(str(self.src), str(link))
        self.assertEqual(read_st(self.src)[0], self.tensors, 'the source was modified')

    def test_main_resume_and_partial_handling(self):
        srcdir = self.dir / 'srcdir'; dstdir = self.dir / 'dstdir'
        (srcdir / 'experts').mkdir(parents=True)
        for lid in (0, 1):
            write_st(srcdir / 'experts' / f'layer_{lid:04d}.safetensors', self.tensors, metadata={'format': 'mlx'}, order=scattered_order(list(self.tensors)))
        (srcdir / 'offload_index.json').write_text(json.dumps({'layers': [0, 1], 'num_experts': 4}))
        (srcdir / 'config.json').write_text('{}')
        with self.assertRaisesRegex(SystemExit, 'ALIAS'):
            repack_v2.main(['--src', str(srcdir), '--dst', str(srcdir)])
        repack_v2.main(['--src', str(srcdir), '--dst', str(dstdir)])
        idx = json.loads((dstdir / 'offload_index.json').read_text()); self.assertEqual(idx['layout'], repack_v2.LAYOUT)
        self.assertTrue(all(repack_v2.check_contiguous(str(dstdir / 'experts' / f'layer_{lid:04d}.safetensors')) for lid in (0, 1)))
        with self.assertRaisesRegex(SystemExit, 'DST_EXISTS'):                 # a second run without --resume
            repack_v2.main(['--src', str(srcdir), '--dst', str(dstdir)])
        # damage layer 1, leave a stale .partial for layer 0, drop the index: --resume keeps 0, rewrites 1, restores the index
        l1 = dstdir / 'experts' / 'layer_0001.safetensors'; raw = l1.read_bytes(); l1.write_bytes(raw[:-10])
        (dstdir / 'experts' / ('layer_0000.safetensors' + repack_v2.PARTIAL)).write_bytes(b'junk'); (dstdir / 'offload_index.json').unlink()
        with self.assertRaisesRegex(SystemExit, 'PARTIAL_PRESENT'):
            repack_v2.main(['--src', str(srcdir), '--dst', str(dstdir)])
        repack_v2.main(['--src', str(srcdir), '--dst', str(dstdir), '--resume'])
        self.assertEqual(l1.read_bytes(), raw); self.assertFalse((dstdir / 'experts' / ('layer_0000.safetensors' + repack_v2.PARTIAL)).exists())
        self.assertEqual(json.loads((dstdir / 'offload_index.json').read_text())['layout'], repack_v2.LAYOUT)
        self.assertEqual(sorted(os.listdir(dstdir / 'experts')), ['layer_0000.safetensors', 'layer_0001.safetensors'])


if __name__ == '__main__':
    unittest.main()
