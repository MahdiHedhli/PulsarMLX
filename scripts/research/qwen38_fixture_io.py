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
from qwen38_verified_files import VerifiedFiles


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
                 observe: Callable[[], Observation], *, verified_files: VerifiedFiles | None = None):
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
        if verified_files is not None and (verified_files.root != root or
                                           verified_files.file_sizes != file_sizes):
            raise PagerProtocolError("verified fixture files do not match store")
        self.root = root
        self.file_sizes = dict(file_sizes)
        self.pager = pager
        self.observe_sample = observe
        self.verified_files = verified_files
        self.fds: dict[str, int] = {}
        self.file_identity: dict[str, tuple[int, ...]] = {}
        self.buffers: dict[PageKey, bytearray] = {}
        self.borrows: dict[int, PageBorrow] = {}
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
                if verified_files is not None:
                    verified_files.check(name)
                    continue
                fd = os.open(root / name, os.O_RDONLY | os.O_CLOEXEC |
                             os.O_NOFOLLOW | os.O_NONBLOCK)
                self.fds[name] = fd
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_size != expected_size:
                    raise PagerProtocolError("fixture file type or size mismatch")
                self.file_identity[name] = self._identity(info)
        except BaseException as exc:
            try:
                self.close()
            except BaseException as cleanup_error:
                if hasattr(exc, "add_note"):
                    exc.add_note(f"fixture initialization cleanup also failed: {cleanup_error}")
            raise

    @staticmethod
    def _identity(info: os.stat_result) -> tuple[int, ...]:
        return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)

    def _verify_file(self, name: str) -> None:
        if self.verified_files is not None:
            self.verified_files.check(name)
            return
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
            try:
                self.pager.stop("host buffer accounting mismatch")
            finally:
                for key in list(self.buffers):
                    if key not in self.pager.resident:
                        del self.buffers[key]

    def accounting(self) -> dict[str, int]:
        self._reconcile()
        return {"retained_host_buffer_bytes": sum(map(len, self.buffers.values())),
                **self.pager.accounting()}

    def _observe(self) -> None:
        try:
            sample = self.observe_sample()
        except Exception:
            try:
                self.pager.stop("memory observation failed")
            finally:
                self._reconcile()
        try:
            self.pager.observe(sample)
        finally:
            self._reconcile()

    def _read_exact(self, spec: PageSpec, buffer: bytearray) -> None:
        cursor = 0
        seen = set()
        for span in spec.spans:
            if (span.tensor in seen or span.filename not in self.file_sizes or
                    type(span.offset) is not int or type(span.length) is not int or
                    span.offset < 0 or span.length <= 0 or
                    span.offset + span.length > self.file_sizes[span.filename]):
                raise PagerProtocolError("page span outside admitted fixture")
            seen.add(span.tensor)
            self._verify_file(span.filename)
            target = memoryview(buffer)[cursor:cursor + span.length]
            if self.verified_files is not None:
                self.verified_files.readinto(span.filename, target, span.offset)
                self._verify_file(span.filename)
                cursor += span.length
                continue
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
        borrow = PageBorrow(lease_id, segments)
        self.borrows[lease_id] = borrow
        return borrow

    def _verify_borrow(self, borrow: PageBorrow) -> None:
        if self.borrows.get(borrow.lease_id) is not borrow:
            raise PagerProtocolError("unknown fixture borrow")

    def gpu_done(self, borrow: PageBorrow) -> None:
        self._verify_borrow(borrow)
        self.pager.mark_gpu_done(borrow.lease_id)

    def release(self, borrow: PageBorrow) -> None:
        self._verify_borrow(borrow)
        lease = self.pager.leases.get(borrow.lease_id)
        if lease is None or not lease.gpu_done:
            raise PagerProtocolError("release before GPU completion")
        # If an extension refuses to release an exported view, keep the page
        # pinned. Derived views may still outlive these parent views.
        for view in borrow.segments.values():
            view.release()
        self.pager.release(borrow.lease_id)
        del self.borrows[borrow.lease_id]
        borrow.segments.clear()
        self._reconcile()

    def _close_fds(self) -> None:
        first_error = None
        for fd in self.fds.values():
            try:
                os.close(fd)
            except OSError as exc:
                first_error = first_error or exc
        self.fds.clear()
        if first_error is not None:
            raise first_error

    def _abort(self) -> None:
        self.closed = True
        first_error = None
        try:
            self.pager.stop("fixture context exited with unfinished work")
        except PagerStop:
            pass
        except BaseException as exc:
            first_error = exc
        try:
            self._reconcile()
        except BaseException as exc:
            first_error = first_error or exc
        try:
            self._close_fds()
        except BaseException as exc:
            first_error = first_error or exc
        if first_error is not None:
            raise first_error

    def close(self) -> None:
        if self.closed:
            return
        if self.pager.pending or self.pager.leases:
            raise PagerProtocolError("cannot close with in-flight I/O or GPU lease")
        self.closed = True
        first_error = None
        try:
            self.pager.stop("fixture store closed")
        except PagerStop:
            pass
        except BaseException as exc:
            first_error = exc
        self.buffers.clear()
        try:
            self._close_fds()
        except BaseException as exc:
            first_error = first_error or exc
        if first_error is not None:
            raise first_error

    def __enter__(self) -> FixturePageStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        if _exc[0] is None:
            try:
                self.close()
            except PagerProtocolError:
                self._abort()
                raise
            return
        # Preserve the original exception while dropping file descriptors.
        # A borrowed page remains pinned until its GPU lease is acknowledged.
        try:
            self.close()
        except BaseException:
            try:
                self._abort()
            except BaseException as cleanup_error:
                # The exception already propagating from the context wins.
                if isinstance(_exc[1], BaseException) and hasattr(_exc[1], "add_note"):
                    _exc[1].add_note(f"fixture cleanup also failed: {cleanup_error}")
