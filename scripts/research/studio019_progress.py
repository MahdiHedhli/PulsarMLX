"""Owner metadata liveness only; no numerical reads, certification or fsync claim.

The frozen structural census is checked against studio017_ref_grade.layout(REAL)
by the synthetic controls. Two unchanged, complete-sized metadata observations
are a conservative progress signal, not proof that Sink.sync_all has returned.
No golden data or reference module is imported into the production owner.
"""
import os
from pathlib import Path
import socket
import stat
import threading
import time


def expected_sizes():
    result = {'00.input.embedding.f32': 4096*4}
    for i in range(45):
        counts = {'attention.output':4096, 'ffn.output':4096, 'layer.streams':16384,
                  'state.offset':1, 'mhc.attn':24, 'mhc.ffn':24}
        counts.update({'mla.latent':512, 'mla.indexer':257} if i%4 == 3 else
                      {'kda.recurrent_state':64*128*128, 'kda.qkv_beta':3*64*128+64,
                       'kda.decay':64*128, 'kda.conv_state':9*64*128})
        if i >= 3: counts.update({'moe.corrected':288, 'moe.routed':4096, 'moe.shared':4096})
        result.update({f'{i:02}.{name}.f32':count*4 for name,count in counts.items()})
    result.update({'45.final.norm.f32':4096*4, 'logits.f32':154880*4})
    return result


def identity(st):
    return st.st_dev, st.st_ino, getattr(st, 'st_birthtime_ns', getattr(st, 'st_birthtime', None))


def metadata(st):
    return identity(st), st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_mode, st.st_uid, st.st_nlink


class Witnesses:
    def __init__(self, out, sizes=None):
        self.out = Path(out)
        self.sizes = expected_sizes() if sizes is None else dict(sizes)
        self.directory = self.out.lstat()
        if not stat.S_ISDIR(self.directory.st_mode) or self.directory.st_uid != os.getuid():
            raise RuntimeError('progress output directory identity')
        if any(self.out.iterdir()): raise RuntimeError('progress output must start empty')
        self.first = {}; self.previous = {}; self.credited = {}; self.refused = set()

    def observe(self):
        now = self.out.lstat()
        if identity(now) != identity(self.directory) or not stat.S_ISDIR(now.st_mode):
            raise RuntimeError('progress directory replaced')
        new = []
        for name, size in self.sizes.items():
            try: st = (self.out/name).lstat()
            except FileNotFoundError:
                if name in self.first: self.refused.add(name)
                if name in self.credited: raise RuntimeError('completed progress witness removed')
                continue
            ident = identity(st); stamp = metadata(st)
            original = self.first.setdefault(name, ident)
            valid = (ident == original and stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid()
                     and stat.S_IMODE(st.st_mode) == 0o600 and st.st_nlink == 1)
            if not valid: self.refused.add(name)
            if name in self.credited:
                if stamp != self.credited[name]: raise RuntimeError('completed progress witness changed')
                continue
            if name in self.refused: continue
            if st.st_size != size:
                self.previous.pop(name, None)
                continue
            if self.previous.get(name) == stamp:
                self.credited[name] = stamp; new.append(name)
            self.previous[name] = stamp
        return new


class ProgressDeadline:
    """Short lock protects deadlines/latch only; independent thread aborts guardian EOF."""
    def __init__(self, total_deadline, seconds=300, clock=time.monotonic, abort=lambda:None):
        self.total = total_deadline; self.seconds = seconds; self.clock = clock; self.abort = abort
        self.condition = threading.Condition(threading.RLock())
        self.progress = None; self.cancelled = False; self.reason = None
        self.stopped = False; self.thread = None

    def _deadline(self):
        return min(self.total, self.progress) if self.progress is not None else self.total

    def _check(self, now=None):
        if now is None: now = self.clock()
        if not self.cancelled and now >= self._deadline():
            self.cancelled = True; self.reason = 'total/progress deadline expired'
        return not self.cancelled

    def check(self):
        with self.condition: good = self._check()
        if not good:
            self.abort()
            raise TimeoutError(self.reason)

    def cancel(self, reason='owned stage cancelled'):
        with self.condition:
            self.cancelled = True
            if self.reason is None: self.reason = reason
            self.condition.notify_all()
        self.abort()

    def remaining(self):
        self.check()
        with self.condition:
            now = self.clock()
            good = self._check(now)
            remaining = max(0.000001, self._deadline()-now)
        if not good:
            self.abort(); raise TimeoutError(self.reason)
        return remaining

    def release(self):
        with self.condition:
            if self.progress is not None: raise RuntimeError('progress already released')
            now = self.clock()
            if not self._check(now): raise TimeoutError(self.reason)
            self.progress = now+self.seconds
            if self.cancelled: raise TimeoutError(self.reason)
            self.thread = threading.Thread(target=self._watch, name='studio019-progress', daemon=True)
            self.thread.start()

    def observe(self, witnesses):
        self.check()
        new = witnesses.observe()  # potentially slow metadata work is outside deadline lock
        with self.condition:
            now = self.clock()
            good = self._check(now)
            if good and new:
                self.progress = now+self.seconds
                self.condition.notify_all()
            good = good and not self.cancelled
        if not good:
            self.abort(); raise TimeoutError(self.reason)
        return new

    def _watch(self):
        with self.condition:
            while not self.stopped and self._check():
                self.condition.wait(max(0, self._deadline()-self.clock()))
            cancelled = self.cancelled
        if cancelled: self.abort()

    def stop(self):
        with self.condition:
            self._check(); self.stopped = True; self.condition.notify_all()
        if self.thread is not None: self.thread.join()
        self.check()


def abort_channel(channel):
    try: channel.shutdown(socket.SHUT_WR)
    except OSError: pass
