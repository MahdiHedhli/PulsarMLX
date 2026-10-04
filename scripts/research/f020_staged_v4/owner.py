"""Live CPU/mock staged owner. No native backend, capability or ledger issuer."""
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import resource
import struct
import sys
import time

from . import numeric as N
from . import source as S
from .protocol import Stage

_CONSUMED = set()  # Process-local source/mock replay protection; never real authority.
ROOT = Path(__file__).resolve().parents[3]
DESIGN = ROOT/'specs/020-mlx-safetensors-affine/staged-checks-v4'


def bindings():
    """Current source/build/proof/profile identities, never caller declarations."""
    paths = sorted(Path(__file__).parent.glob('*.py'))
    paths += [ROOT/'scripts/research'/f for f in (
        'f020_selected_r1_v2.py', 'f020_selected_snapshot_v2.py', 'f020_expert_mlp_r1_v1.py')]
    checker = S.digest(tuple((str(p.relative_to(ROOT)), S.sha(p.read_bytes())) for p in paths))
    proof = S.sha((DESIGN/'approved-input-hashes.json').read_bytes())
    contract = S.sha((DESIGN/'contract-v4.json').read_bytes())
    binary = Path(sys.executable).resolve()
    base = Path(sys._base_executable).resolve()
    build = S.digest((str(binary), sys.version, sys.flags.optimize,
                      S.sha(binary.read_bytes()), S.sha(base.read_bytes())))
    return tuple(sorted({'checker': checker, 'source': checker, 'proof': proof,
                         'contract': contract, 'profile': 'A-CHECK-MAG', 'build': build,
                         'scope': 'CPU_PUBLIC_SYNTHETIC_UNQUALIFIED'}.items()))


def words(raw, n):
    N.require(type(raw) is bytes and len(raw) == n*4, 'immutable F32 buffer length')
    result = tuple(w[0] for w in struct.iter_unpack('<I', raw))
    return result, tuple(N.f32(w) for w in result)


def clamp_bits(raw, gate):
    bits, values = words(raw, 2048)
    result = []
    for word, v in zip(bits, values, strict=True):
        if v > 10:
            result.append(0x41200000)
        elif not gate and v < -10:
            result.append(0xc1200000)
        else:
            result.append(word)
    return tuple(result)


class Resources:
    def __init__(self, clock=time.monotonic, rss=None):
        self.clock = clock
        self.start = clock()
        self.rss = rss or self.system_rss
        self.peak = 0
        self.last_sample = self.start-1
        self.last_now = self.start
        self.working = 0

    @staticmethod
    def system_rss():
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        N.require(sys.platform in ('darwin', 'linux'), 'RSS units unknown')
        return int(value) if sys.platform == 'darwin' else int(value)*1024

    def reserve(self, size):
        N.require(type(size) is int and 0 <= size <= 512*1024*1024, 'working data cap')
        self.working = size

    def check(self, force=False):
        now = self.clock()
        N.require(type(now) in (int, float) and now == now and self.last_now <= now < self.start+900,
                  'deadline or monotonic clock')
        self.last_now = now
        if force or now-self.last_sample >= .1:
            value = self.rss()
            N.require(type(value) is int and 0 <= value <= 256*1024*1024, 'reference RSS cap')
            self.peak = max(self.peak, value)
            self.last_sample = now


class Owner:
    """Trusted serial mock owner; no API accepts externally minted receipts."""
    def __init__(self, original, attempt, resources=None):
        N.require(type(original) is S.Original, 'original type')
        N.require(type(attempt) is str and 1 <= len(attempt) <= 128, 'attempt identity')
        self.original = original
        self._original_digest = original.source_digest
        self.attempt = attempt
        self._claim_attempt = attempt
        self.resources = resources or Resources()
        self.identity = bindings()
        self.state = 'UNUSED'
        self.receipts = ()
        self._transcript = S.digest(())
        self.buffers = ()
        self.buffer_digests = ()
        self.certificate = None
        self.certificate_digest = None
        self.cache_stats = {}
        self._running = False
        self._cleaned = False

    def _record(self, state, outcome='progress'):
        predecessors = {'CLAIMED': 'UNUSED', 'PRE_ADMITTED': 'CLAIMED',
                        'GU_CHECKED': 'PRE_ADMITTED', 'H_CHECKED': 'GU_CHECKED',
                        'DOWN_CHECKED': 'H_CHECKED'}
        if state != 'TERMINAL':
            N.require(state in predecessors and self.state == predecessors[state],
                      'illegal state transition')
        previous = S.sha(self.receipts[-1]) if self.receipts else '0'*64
        record = {'state': state, 'outcome': outcome, 'identity': self.identity,
                  'attempt': self.attempt, 'previous': previous,
                  'original': self.original.source_digest, 'reference': self.certificate_digest,
                  'E': self.certificate.e_digest if self.certificate else None,
                  'buffers': self.buffer_digests, 'real_native_qualified': False}
        raw = json.dumps(record, sort_keys=True, separators=(',', ':')).encode()
        self.receipts += (raw,)
        self._transcript = S.digest(self.receipts)
        self.state = state

    def _integrity(self):
        N.require(self.state != 'TERMINAL', 'terminal attempt')
        N.require(self.attempt == self._claim_attempt, 'attempt identity changed')
        N.require(self.original.source_digest == self._original_digest, 'original identity changed')
        N.require(bindings() == self.identity, 'source/build/checker/proof/profile changed')
        N.require(S.digest(self.receipts) == self._transcript, 'receipt chain changed')
        self.original.verify()
        N.require(tuple(S.sha(v) for v in self.buffers) == self.buffer_digests, 'checked buffer changed')
        if self.certificate is not None:
            N.require(self.certificate.identity == self.identity and self.certificate.original_digest == self._original_digest,
                      'certificate source identity')
            N.require(S.digest(self.certificate) == self.certificate_digest, 'certificate/E identity changed')
        self.resources.check(force=True)

    def _keep(self, *buffers):
        N.require(all(type(b) is bytes for b in buffers), 'mutable backend buffer')
        self.buffers += buffers
        self.buffer_digests += tuple(S.sha(b) for b in buffers)

    def _stage(self, result, expected_inputs, family, sizes, phase):
        N.require(self.state == phase, 'callback state changed')
        N.require(type(result) is Stage and type(result.buffers) is tuple, 'stage report type')
        N.require(type(result.family) is tuple and all(type(x) is int for x in result.family), 'family type')
        N.require(result.input_digests == expected_inputs and result.family == family, 'stage input/family')
        N.require(len(result.buffers) == len(sizes), 'stage output count')
        for raw, size in zip(result.buffers, sizes, strict=True):
            words(raw, size)
        r = result.resources
        N.require(type(r) is tuple and len(r) == 3 and all(type(x) is int and x >= 0 for x in r), 'resource sample type')
        N.require(r[0] <= 64*1024*1024 and r[1] <= 64*1024*1024 and r[2] <= 1024*1024*1024,
                  'backend resource cap')
        self._integrity()

    def run(self, backend):
        if self._running:
            self.state = 'TERMINAL'  # Outer finally records the one terminal receipt.
            raise N.Refusal('reentry')
        N.require(self.state == 'UNUSED', 'replay')
        # Never trust a backend's declaration as proof of native compliance.
        N.require(getattr(backend, 'execution_scope', None) == 'CPU_PUBLIC_SYNTHETIC', 'backend scope')
        key = self.attempt
        N.require(key not in _CONSUMED, 'duplicate attempt')
        N.require(len(_CONSUMED) < 4096, 'bounded process attempt registry')
        _CONSUMED.add(key)
        self._running = True
        self._record('CLAIMED')
        error = None
        try:
            # Fixed reservation covers source, exact arrays, <=32 row caches and
            # stage buffers. Actual Python overhead independently hits RSS gate.
            self.resources.reserve(64*1024*1024)
            self._integrity()
            self.certificate, self.cache_stats = S.references(self.original, self.identity, self.resources.check)
            self.certificate_digest = S.digest(self.certificate)
            self._record('PRE_ADMITTED')
            self._integrity()
            result = backend.gate_up(self.original)
            self._stage(result, (S.sha(self.original.x),), (273, 273), (2048, 2048), 'PRE_ADMITTED')
            graw, uraw = result.buffers
            g, u = words(graw, 2048)[1], words(uraw, 2048)[1]
            N.check_gu(g, u, self.certificate.lanes)
            self._keep(graw, uraw)
            self._record('GU_CHECKED')
            self._integrity()
            result = backend.activation(graw, uraw)
            self._stage(result, (S.sha(graw), S.sha(uraw)), (2048,), (2048,), 'GU_CHECKED')
            N.require(type(result.clamp_gate) is type(result.clamp_up) is tuple and
                      all(type(v) is int for v in result.clamp_gate+result.clamp_up), 'clamp words type')
            N.require(result.clamp_gate == clamp_bits(graw, True) and result.clamp_up == clamp_bits(uraw, False),
                      'semantic clamp bits')
            hraw = result.buffers[0]
            h = words(hraw, 2048)[1]
            cache = {}
            local = []
            for gv, uv in zip(g, u, strict=True):
                self.resources.check()
                key = (gv, uv)
                if key not in cache:
                    if len(cache) == 32:
                        cache.clear()
                    cache[key] = N.activation(gv, uv)
                local.append(cache[key])
            N.check_hidden(h, tuple(local), self.certificate.lanes)
            N.domain(h)
            # Explicit original down metadata + actual hidden admission and
            # local affine occur before down dispatch. No candidate-fed ideal.
            local, rounding, stats = S.local_down(self.original, hraw, self.resources.check)
            self.cache_stats.update(stats)
            self._keep(hraw)
            self._record('H_CHECKED')
            self._integrity()
            result = backend.down(hraw, self.original)
            self._stage(result, (S.sha(hraw),), (145,), (4096,), 'H_CHECKED')
            N.require(self.buffers[2] is hraw, 'actual checked hidden object')
            yraw = result.buffers[0]
            y = words(yraw, 4096)[1]
            N.check_down(y, local, rounding, self.certificate.y, self.certificate.propagation)
            N.check_down(y, local, rounding, self.certificate.y, self.certificate.old_propagation)
            self._keep(yraw)
            self._record('DOWN_CHECKED')
        except Exception as exc:
            error = exc
        finally:
            if not self._cleaned:
                self._cleaned = True
                try:
                    result = backend.cleanup()
                    N.require(type(result) is tuple and all(type(v) is int for v in result)
                              and result == (0, 0, 0), 'cleanup census')
                    if error is None:
                        self._integrity()
                except Exception as exc:
                    error = exc
            self._record('TERMINAL', 'mock-checked' if error is None else 'refused: '+str(error))
            self._running = False
        if error is not None:
            raise N.Refusal(str(error)) from error
        return self.receipts[-1]
