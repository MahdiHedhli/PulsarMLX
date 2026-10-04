"""Fixture-only actual preadv I/O for the synthetic Qwen page scheduler.

This adapter refuses directories without a synthetic marker. It holds exact
page bytearrays and never imports MLX, checkpoint Python, or model weights.
It is not a qualified production allocator or GPU residency implementation.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from qwen38_bounded_pager import BoundedPager, Observation, PagerProtocolError, PagerStop
from qwen38_page_catalog import PageKey, PageSpec


MARKER = ".qwen38-synthetic-fixture"
MARKER_CONTENT = "qwen38-synthetic-fixture-v1\n"
MAX_FIXTURE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class PageBorrow:
    lease_id: int
    segments: dict[str, memoryview]


class FixturePageStore:
    """Bind synthetic page tickets to exact synchronous file reads and buffers."""

    def __init__(self, root: Path, file_sizes: dict[str, int], pager: BoundedPager,
                 observe: Callable[[], Observation]):
        if root.is_symlink():
            raise PagerProtocolError("symlinked fixture root refused")
        root = root.resolve(strict=True)
        marker = root / MARKER
        if marker.is_symlink() or not marker.is_file() or marker.read_text() != MARKER_CONTENT:
            raise PagerProtocolError("synthetic fixture marker required")
        if not file_sizes or not callable(observe):
            raise PagerProtocolError("fixture files and observation callback required")
        if pager.resident or pager.pending or pager.leases or pager.closed:
            raise PagerProtocolError("fixture store requires an empty open pager")
        self.root = root
        self.file_sizes = dict(file_sizes)
        self.pager = pager
        self.observe_sample = observe
        self.fds: dict[str, int] = {}
        self.file_identity: dict[str, tuple[int, ...]] = {}
        self.buffers: dict[PageKey, bytearray] = {}
        self.closed = False
        total_fixture_bytes = 0
        try:
            for name, expected_size in file_sizes.items():
                if (Path(name).name != name or type(expected_size) is not int or expected_size <= 0
                        or expected_size > MAX_FIXTURE_BYTES or (root / name).is_symlink()):
                    raise PagerProtocolError("invalid fixture file identity")
                total_fixture_bytes += expected_size
                if total_fixture_bytes > MAX_FIXTURE_BYTES:
                    raise PagerProtocolError("synthetic fixture exceeds size cap")
                fd = os.open(root / name, os.O_RDONLY | os.O_CLOEXEC |
                             os.O_NOFOLLOW | os.O_NONBLOCK)
                self.fds[name] = fd
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_size != expected_size:
                    raise PagerProtocolError("fixture file type or size mismatch")
                self.file_identity[name] = self._identity(info)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _identity(info: os.stat_result) -> tuple[int, ...]:
        return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)

    def _verify_file(self, name: str) -> None:
        try:
            opened = os.fstat(self.fds[name])
            current = os.stat(self.root / name, follow_symlinks=False)
        except OSError as exc:
            raise PagerProtocolError("fixture file changed during use") from exc
        expected = self.file_identity[name]
        if self._identity(opened) != expected or self._identity(current) != expected:
            raise PagerProtocolError("fixture file changed during use")

    def _reconcile(self) -> None:
        for key in list(self.buffers):
            if key not in self.pager.resident:
                del self.buffers[key]
        if sum(len(buffer) for buffer in self.buffers.values()) != self.pager.resident_bytes:
            self.pager.stop("host buffer accounting mismatch")

    def accounting(self) -> dict[str, int]:
        self._reconcile()
        return {"retained_host_buffer_bytes": sum(map(len, self.buffers.values())),
                **self.pager.accounting()}

    def _observe(self) -> None:
        try:
            sample = self.observe_sample()
        except Exception:
            self._reconcile()
            self.pager.stop("memory observation failed")
        try:
            self.pager.observe(sample)
        finally:
            self._reconcile()

    def _read_exact(self, spec: PageSpec, buffer: bytearray) -> None:
        cursor = 0
        seen = set()
        for span in spec.spans:
            if (span.tensor in seen or span.filename not in self.fds or
                    type(span.offset) is not int or type(span.length) is not int or
                    span.offset < 0 or span.length <= 0 or
                    span.offset + span.length > self.file_sizes[span.filename]):
                raise PagerProtocolError("page span outside admitted fixture")
            seen.add(span.tensor)
            self._verify_file(span.filename)
            target = memoryview(buffer)[cursor:cursor + span.length]
            done = 0
            while done < span.length:
                count = os.preadv(self.fds[span.filename], [target[done:]], span.offset + done)
                if count <= 0 or count > span.length - done:
                    raise PagerProtocolError("short or invalid page read")
                done += count
            self._verify_file(span.filename)
            cursor += span.length
        if cursor != len(buffer):
            raise PagerProtocolError("page buffer length mismatch")

    def pump_one(self) -> PageKey | None:
        """Read one admitted ticket; failures stop the pager and drain its reservation."""
        if self.closed:
            raise PagerProtocolError("fixture store closed")
        self._observe()
        try:
            ticket = self.pager.next_io()
        finally:
            self._reconcile()  # evicted host buffers must go before allocation.
        if ticket is None:
            return None
        try:
            buffer = bytearray(ticket.spec.size_bytes)
            self._read_exact(ticket.spec, buffer)
            self._observe()
            self.pager.complete_io(ticket)
        except BaseException:
            if ticket.spec.key in self.pager.pending:
                try:
                    self.pager.fail_io(ticket)
                except PagerStop:
                    pass
            self._reconcile()
            raise
        if ticket.spec.key in self.pager.resident:
            self.buffers[ticket.spec.key] = buffer
        self._reconcile()
        return ticket.spec.key

    def borrow(self, key: PageKey) -> PageBorrow:
        if self.closed or key not in self.buffers:
            raise PagerProtocolError("page has no retained host buffer")
        lease_id = self.pager.acquire(key)
        spec = self.pager.resident[key]
        cursor = 0
        segments = {}
        for span in spec.spans:
            segments[span.tensor] = memoryview(self.buffers[key])[cursor:cursor + span.length].toreadonly()
            cursor += span.length
        return PageBorrow(lease_id, segments)

    def gpu_done(self, borrow: PageBorrow) -> None:
        self.pager.mark_gpu_done(borrow.lease_id)

    def release(self, borrow: PageBorrow) -> None:
        self.pager.release(borrow.lease_id)
        for view in borrow.segments.values():
            view.release()
        borrow.segments.clear()
        self._reconcile()

    def close(self) -> None:
        if self.closed:
            return
        if self.pager.pending or self.pager.leases:
            raise PagerProtocolError("cannot close with in-flight I/O or GPU lease")
        self.closed = True
        try:
            self.pager.stop("fixture store closed")
        except PagerStop:
            pass
        self.buffers.clear()
        for fd in self.fds.values():
            os.close(fd)
        self.fds.clear()

    def __enter__(self) -> FixturePageStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
