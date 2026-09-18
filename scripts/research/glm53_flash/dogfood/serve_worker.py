"""InferenceWorker: one thread owns the model; HTTP handlers only enqueue and await (graph 30).

The first server ran generation inside the async handler: the non-streaming branch consumed the generator on the
event loop and a threading lock was held across the streaming generator's yields, so an active stream (which needs
the event loop to send its chunks) plus a concurrent non-streaming request (which blocks the event loop waiting for
the lock) deadlocked, and /health starved with them. Here:

  * one daemon thread runs jobs strictly one at a time (model ownership by construction, no lock);
  * submit() takes a zero-argument callable that returns the generator; the queue holds at most `max_queue` jobs
    (running + waiting) and submit raises QueueFull beyond that: the caller answers 503 and never blocks;
  * every item the generator yields is handed to the consumer through `job.deliver`, which the HTTP layer binds to
    loop.call_soon_threadsafe(asyncio.Queue.put_nowait) so the handler awaits natively; the stdlib default is a
    queue.Queue for synchronous consumers and tests;
  * job.cancel() sets a flag the worker checks between yields, then the generator is closed (GeneratorExit) and the
    model is free within one token; a job cancelled before it starts is skipped without running its generator;
  * an exception inside a generator is delivered to that job as ('error', exc) and the worker continues with the
    next job, so a failing request never takes the server down or wedges the queue.

Stdlib only (no mlx, no fastapi): the same module and its tests run in CI.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Optional


class QueueFull(RuntimeError):
    """More than `max_queue` jobs are pending (running + waiting)."""


class Job:
    def __init__(self, job_id: int, make_generator: Callable[[], object], deliver: Optional[Callable[[tuple], None]]):
        self.id = job_id
        self.make_generator = make_generator
        self._sync = None
        if deliver is None:
            self._sync = queue.Queue()
            deliver = self._sync.put
        self.deliver = deliver
        self.cancelled = threading.Event()
        self.started = threading.Event()
        self.finished = threading.Event()
        self.outcome = None            # 'done' | 'error' | 'cancelled' | 'skipped'
        self.submitted_at = time.time(); self.started_at = None
        self.items = 0

    def cancel(self) -> None:
        self.cancelled.set()

    # synchronous consumption (tests, scripts): iterate items until the terminal marker
    def results(self, timeout: Optional[float] = None):
        if self._sync is None:
            raise RuntimeError("JOB_HAS_ASYNC_DELIVERY")
        while True:
            kind, payload = self._sync.get(timeout=timeout)
            if kind == "item":
                yield payload
            elif kind == "error":
                raise payload
            else:                      # 'done' | 'cancelled' | 'skipped'
                return



class InferenceWorker:
    def __init__(self, max_queue: int = 4, name: str = "inference"):
        if int(max_queue) < 1:
            raise ValueError("MAX_QUEUE_MIN_1")
        self.max_queue = int(max_queue)
        self._q: "queue.Queue[Optional[Job]]" = queue.Queue()
        self._lock = threading.Lock()
        self._pending = 0              # running + waiting
        self._next_id = 0
        self.busy = False
        self.current: Optional[Job] = None
        self.completed = self.failed = self.cancelled = self.skipped = self.rejected = 0
        self._stop = False
        self._thread = threading.Thread(target=self._loop, name=name, daemon=True)
        self._thread.start()

    # --- submission -------------------------------------------------------------------------------
    def submit(self, make_generator: Callable[[], object], deliver: Optional[Callable[[tuple], None]] = None) -> Job:
        """Enqueue; raises QueueFull when max_queue jobs are already pending. Never blocks."""
        with self._lock:
            if self._pending >= self.max_queue:
                self.rejected += 1
                raise QueueFull(f"QUEUE_FULL pending={self._pending} max={self.max_queue}")
            self._pending += 1
            self._next_id += 1
            job = Job(self._next_id, make_generator, deliver)
        self._q.put(job)
        return job

    @property
    def pending(self) -> int:
        with self._lock:
            return self._pending

    @property
    def queued(self) -> int:
        with self._lock:
            return self._pending - (1 if self.busy else 0)

    def stats(self) -> dict:
        with self._lock:
            return {"max_queue": self.max_queue, "pending": self._pending, "busy": self.busy, "completed": self.completed, "failed": self.failed,
                    "cancelled": self.cancelled, "skipped": self.skipped, "rejected": self.rejected, "current_job": self.current.id if self.current else None}

    def close(self, timeout: Optional[float] = 5.0) -> None:
        self._stop = True
        self._q.put(None)
        self._thread.join(timeout)

    # --- the one thread that touches the model ----------------------------------------------------
    def _loop(self) -> None:
        while not self._stop:
            job = self._q.get()
            if job is None:
                break
            with self._lock:
                self.busy = True; self.current = job
            try:
                self._run(job)
            finally:
                with self._lock:
                    self._pending -= 1; self.busy = False; self.current = None
                job.finished.set()

    def _run(self, job: Job) -> None:
        if job.cancelled.is_set():
            job.outcome = "skipped"; self._bump("skipped"); job.deliver(("skipped", None))
            return
        job.started.set(); job.started_at = time.time()
        gen = None
        try:
            gen = job.make_generator()
            for item in gen:
                if job.cancelled.is_set():
                    break
                job.items += 1
                job.deliver(("item", item))
        except BaseException as exc:          # the job gets the failure; the worker survives
            job.outcome = "error"; self._bump("failed"); job.deliver(("error", exc))
            return
        finally:
            close = getattr(gen, "close", None)
            if close is not None:
                try:
                    close()                    # GeneratorExit inside the generation: the model is released here
                except BaseException:
                    pass
        if job.cancelled.is_set():
            job.outcome = "cancelled"; self._bump("cancelled"); job.deliver(("cancelled", None))
        else:
            job.outcome = "done"; self._bump("completed"); job.deliver(("done", None))

    def _bump(self, counter: str) -> None:
        with self._lock:
            setattr(self, counter, getattr(self, counter) + 1)
