"""Finite real secondary descriptor/owner/readback cases, with byte-only fakes.

No numerical backend is replaced. No decode, graph, model or native operation
is executed. All descriptors are tiny files created inside the sealed work root.
"""
import hashlib
import json
import os
from pathlib import Path

import f017_secondary_descriptor_source_v1 as source_module
import f017_secondary_read_observation_v1 as observation
from f017_secondary_read_observation_prefix_v1 import open_secondary_descriptor_prefix
from secondary_oracle_v1 import derive, require_complete, require_incomplete, validate_requests


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


class Fixture:
    def __init__(self, root, name):
        self.root = Path(root) / name
        self.root.mkdir(mode=0o700)
        self.descriptors = []
        self.identities = []
        self.payloads = {}
        self.shards = {}
        self.transcript = []
        records = []
        for ordinal in (2, 3, 4, 5, 6):
            payload = bytes((index + ordinal) % 251 for index in range(256))
            path = self.root / ("shard-" + str(ordinal) + ".bin")
            path.write_bytes(payload)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            self.descriptors.append(fd)
            self.payloads[fd] = payload
            self.shards[fd] = ordinal
            st = os.fstat(fd)
            self.identities.append({"device": st.st_dev, "inode": st.st_ino,
                "mode": st.st_mode, "size": st.st_size, "mtime_ns": st.st_mtime_ns,
                "ctime_ns": st.st_ctime_ns, "shard_ordinal": ordinal,
                "role": "GRAPH_PAYLOAD", "lease_id": "SECONDARY-LEASE-" + str(ordinal)})
            for purpose, offset, prefix in (("GRAPH", 0, "graph"), ("FORMAT_PROBE", 128, "probe")):
                records.append({"name": prefix + str(ordinal), "format": "F32", "dims": [4, 4],
                    "shard_ordinal": ordinal, "byte_offset": offset, "byte_length": 64, "purpose": purpose})
        raw = canonical({"schema": "pulsarmlx.f017.synthetic-descriptor-catalog/9.0.0",
                         "records": records, "geometry": {}, "token": 9703, "position": 0})
        catalog = self.root / "catalog.json"
        catalog.write_bytes(raw)
        self.candidate = {"package_attempt_id": "SECONDARY-PACKAGE-" + name.upper(),
            "secondary_event_id": "SECONDARY-EVENT-" + name.upper(),
            "tensor_catalog_path": str(catalog), "tensor_catalog_sha256": hashlib.sha256(raw).hexdigest(),
            "shards": [{"size_bytes": 0}] + [{"size_bytes": 256} for _ in range(5)]}
        self.authority = {"package_attempt_id": self.candidate["package_attempt_id"],
            "consumer_event_id": self.candidate["secondary_event_id"],
            "producer_measurement_sha256": hashlib.sha256(b"FINITE-SECONDARY-DESCRIPTOR-GENERATION-1").hexdigest()}
        self.directory = self.root / "result"
        self.prefix = None
        self.mode = "success"
        self.original_pread = os.pread

    def open(self):
        self.prefix = open_secondary_descriptor_prefix(self.candidate, self.identities,
            self.descriptors, self.directory, self.authority)
        return self.prefix

    def backend(self, fd, size, offset):
        # The fake returns only bytes/errors and records independently delegated
        # requests. It never reads the producer or supplies expected totals.
        event = {"shard_ordinal": self.shards[fd], "requested_bytes": size,
            "offset": offset, "purpose": "FORMAT_PROBE" if offset >= 128 else "NUMERICAL_PAYLOAD"}
        if self.mode == "error":
            event.update(outcome="ERROR", error_type="OSError", error_message="SECONDARY_BYTE_BACKEND_ERROR")
            self.transcript.append(event)
            raise OSError("SECONDARY_BYTE_BACKEND_ERROR")
        payload = (self.original_pread(fd, size, offset) if self.mode == "real-pread"
                   else self.payloads[fd][offset:offset + size])
        if self.mode == "short":
            payload = payload[:max(0, len(payload) - 1)]
        if self.mode == "zero":
            payload = b""
        event.update(outcome="RETURN", returned_hex=payload.hex())
        self.transcript.append(event)
        return payload

    def read(self, name="graph2", rows=1, columns=4, row_start=0):
        store = self.prefix.store
        original = source_module.os.pread
        source_module.os.pread = self.backend
        try:
            return store.read_encoded(store.records[name], None, rows, columns, row_start)
        finally:
            source_module.os.pread = original

    def finish(self, outcome="RETURNED"):
        return self.prefix.finish(outcome, "COMPLETE")

    def back(self, **changes):
        expected = {key: self.prefix.owner.binding[key] for key in (
            "package_attempt_id", "consumer_event_id", "producer_measurement_sha256", "descriptor_set_sha256")}
        expected.update(changes)
        return observation._read_secondary_observation(self.directory, expected)

    def cleanup(self):
        if self.prefix is not None and not self.prefix.owner.finished:
            self.prefix.finish_while_raising()
        for fd in self.descriptors:
            if fd is not None:
                os.close(fd)


def run(case_id, work, view):
    if case_id != "INTEGRATION":
        raise ValueError("FIXED_SECONDARY_CASE")
    results = []

    def record(name, fixture, attachment, expected, detail=None):
        validate_requests(fixture.transcript)
        if expected == "COMPLETE":
            require_complete(attachment, fixture.transcript)
        else:
            require_incomplete(attachment)
        results.append({"case": name, "result": "PASS", "expected": expected,
            "transcript": fixture.transcript, "independent_rows": derive(fixture.transcript),
            "attachment": attachment, "detail": detail})
        # Every qualified row survives a later case failure. Never infer the
        # missing suffix from the number of rows in this durable prefix.
        with (Path(work) / ("case-%03d.json" % len(results))).open("xb") as output:
            output.write(canonical(results[-1]))
            output.flush()
            os.fsync(output.fileno())

    for mode in ("success", "error", "short", "zero", "zero-request"):
        f = Fixture(work, mode)
        try:
            f.open()
            f.mode = mode
            error = None
            try:
                raw = f.read(rows=0 if mode == "zero-request" else 1)
                if mode not in ("success", "zero-request"):
                    raise AssertionError("EXPECTED_ORIGINAL_READ_FAILURE")
                if raw.hex() != f.transcript[-1]["returned_hex"]:
                    raise AssertionError("EXACT_DELEGATED_BYTES")
            except (OSError, ValueError) as exc:
                error = str(exc)
                expected_error = "SECONDARY_BYTE_BACKEND_ERROR" if mode == "error" else "secondary descriptor short read"
                if mode not in ("error", "short", "zero") or error != expected_error:
                    raise
            record(mode, f, f.finish("RAISED" if error else "RETURNED"), "COMPLETE", {"original_error": error})
        finally:
            f.cleanup()

    f = Fixture(work, "shard-purpose-isolation")
    try:
        f.open()
        for ordinal in (2, 3, 4, 5, 6):
            f.read("graph" + str(ordinal), row_start=ordinal - 2 if ordinal < 6 else 0)
            f.read("probe" + str(ordinal))
        record("shard-purpose-isolation", f, f.finish(), "COMPLETE")
    finally:
        f.cleanup()

    for mode in ("bounds", "identity", "closed-descriptor"):
        f = Fixture(work, mode)
        try:
            f.open()
            if mode == "identity":
                f.prefix.store.handles[2][0]["size"] = 255
            if mode == "closed-descriptor":
                os.close(f.descriptors[0])
                f.descriptors[0] = None
            try:
                f.read(row_start=16 if mode == "bounds" else 0)
                raise AssertionError("PRE_IO_REFUSAL_MISSING")
            except (ValueError, OSError) as exc:
                error = str(exc)
            if f.transcript:
                raise AssertionError("PRE_IO_REFUSAL_DELEGATED")
            # Identity was modified in-place deliberately; ownership remains
            # bound, but descriptor attribution fails before any pread.
            record(mode, f, f.finish("RAISED"), "COMPLETE", {"original_error": error})
        finally:
            f.cleanup()

    for mode in ("drop-return", "double-return", "wrong-shard", "owner-detach", "unknown-owner"):
        for control in (False, True):
            name = mode + ("-restored" if control else "-mutant")
            f = Fixture(work, name)
            old_return = source_module._read_return
            old_intent = source_module._read_intent
            try:
                f.open()
                if not control:
                    if mode == "drop-return":
                        source_module._read_return = lambda owner, ticket, returned: None
                    elif mode == "double-return":
                        def double(owner, ticket, returned):
                            old_return(owner, ticket, returned)
                            old_return(owner, ticket, returned)
                        source_module._read_return = double
                    elif mode == "wrong-shard":
                        def wrong(owner, source, tensor, identity, size):
                            return old_intent(owner, source, tensor, {**identity, "shard_ordinal": 3}, size)
                        source_module._read_intent = wrong
                    else:
                        f.prefix.store._observation_owner = None if mode == "owner-detach" else object()
                raw = f.read()
                if raw.hex() != f.transcript[-1]["returned_hex"]:
                    raise AssertionError("MUTANT_CHANGED_BYTE_OUTCOME")
                attachment = f.finish()
                intended = {"drop-return": "OBSERVATION_PENDING_CALL_OR_RETURN_UNKNOWN",
                    "double-return": "OBSERVATION_RETURN_FAILED:ValueError",
                    "wrong-shard": "OBSERVATION_ATTRIBUTION_FAILED:ValueError",
                    "owner-detach": "OBSERVATION_FACTORY_OWNER_LOST_OR_REPLACED",
                    "unknown-owner": "OBSERVATION_FACTORY_OWNER_LOST_OR_REPLACED"}[mode]
                if not control and f.prefix.owner.failure != intended:
                    raise AssertionError("MUTANT_NOT_DETECTED_AT_INTENDED_OWNER_EDGE")
                record(name, f, attachment, "COMPLETE" if control else "INCOMPLETE",
                       {"owner_failure": f.prefix.owner.failure, "intended_failure": None if control else intended})
            finally:
                source_module._read_return = old_return
                source_module._read_intent = old_intent
                f.cleanup()

    f = Fixture(work, "never-bound")
    try:
        owner = observation._start_secondary_observation()
        observation._initialize_secondary_observation(owner, f.candidate, f.identities, f.directory, f.authority)
        attachment = observation._finish_secondary_observation(owner, "RAISED", "FACTORY")
        record("never-bound", f, attachment, "INCOMPLETE", {"owner_failure": owner.failure})
        if owner.failure != "OBSERVATION_SOURCE_NEVER_BOUND":
            raise AssertionError("NEVER_BOUND_INTENDED_REFUSAL")
    finally:
        f.cleanup()

    for mode in ("short-write", "fsync-error", "overflow"):
        for control in (False, True):
            f = Fixture(work, mode + ("-restored" if control else "-mutant"))
            old_write = observation.os.write
            old_sync = observation.os.fsync
            old_encode = observation._encode_record
            try:
                f.open()
                if not control:
                    if mode == "short-write":
                        observation.os.write = lambda fd, raw: 0 if fd > 2 else old_write(fd, raw)
                    elif mode == "fsync-error":
                        def fail_sync(fd):
                            if fd == f.prefix.owner.directory_fd:
                                raise OSError("SYNTHETIC_DIRECTORY_FSYNC")
                            return old_sync(fd)
                        observation.os.fsync = fail_sync
                    else:
                        observation._encode_record = lambda value: old_encode({**value, "oversize": "x" * 32768})
                raw = f.read()
                observation.os.write = old_write
                observation.os.fsync = old_sync
                observation._encode_record = old_encode
                record(mode + ("-restored" if control else "-mutant"), f, f.finish(),
                       "COMPLETE" if control else "INCOMPLETE",
                       {"writer_failure": f.prefix.owner.failure, "returned_bytes_unchanged": raw.hex() == f.transcript[-1]["returned_hex"]})
                if not control and "OBSERVATION_PERSISTENCE_FAILED" not in f.prefix.owner.failure:
                    raise AssertionError("PERSISTENCE_MUTANT_WRONG_EDGE")
            finally:
                observation.os.write = old_write
                observation.os.fsync = old_sync
                observation._encode_record = old_encode
                f.cleanup()

    for mode in ("cross-attempt", "missing-prefix", "counter-transition"):
        f = Fixture(work, mode)
        try:
            f.open()
            f.read()
            good = f.finish()
            require_complete(good, f.transcript)
            changed_path = None
            original = None
            if mode == "cross-attempt":
                bad = f.back(consumer_event_id="ANOTHER-SECONDARY-EVENT")
            else:
                changed_path = f.directory / observation.DIRECTORY / "record-00000004.json"
                original = changed_path.read_bytes()
                if mode == "missing-prefix":
                    changed_path.unlink()
                else:
                    document = json.loads(original)
                    # Keep the wrong row internally consistent, so the causal
                    # transition checker (not a malformed-row check) rejects it.
                    for key, delta in (("attempts", 1), ("successful_returns", 1),
                                       ("requested_bytes", 16), ("returned_bytes", 16)):
                        document["counters"][1][key] += delta
                    previous = json.loads((changed_path.parent / "record-00000003.json").read_bytes())
                    try:
                        observation._transition(previous, document)
                        raise AssertionError("CAUSAL_COUNTER_TRANSITION_NOT_REJECTED")
                    except ValueError as error:
                        if str(error) != "OBSERVATION_COUNTER_TRANSITION":
                            raise AssertionError("COUNTER_MUTANT_REJECTED_AT_WRONG_EDGE") from error
                    changed_path.write_bytes(canonical(document))
                bad = f.back()
            record(mode + "-mutant", f, bad, "INCOMPLETE",
                   {"reader_failure": bad["measurement_failure"],
                    "direct_transition_failure": "OBSERVATION_COUNTER_TRANSITION" if mode == "counter-transition" else None})
            if changed_path is not None:
                changed_path.write_bytes(original)
            restored = f.back()
            record(mode + "-restored", f, restored, "COMPLETE")
        finally:
            f.cleanup()

    f = Fixture(work, "repeated-finish")
    try:
        f.open()
        f.read()
        first = f.finish()
        before = sorted(p.name for p in (f.directory / observation.DIRECTORY).iterdir())
        second = f.finish()
        if first != second or before != sorted(p.name for p in (f.directory / observation.DIRECTORY).iterdir()):
            raise AssertionError("REPEATED_FINISH_CHANGED_CUSTODY")
        record("repeated-finish", f, second, "COMPLETE")
    finally:
        f.cleanup()

    a = Fixture(work, "attempt-isolation-a")
    b = Fixture(work, "attempt-isolation-b")
    try:
        a.open()
        b.open()
        a.read("graph2")
        b.read("probe6")
        a.read("graph3")
        record("attempt-isolation-a", a, a.finish(), "COMPLETE")
        record("attempt-isolation-b", b, b.finish(), "COMPLETE")
        if a.prefix.owner.binding == b.prefix.owner.binding:
            raise AssertionError("ATTEMPT_BINDINGS_NOT_DISTINCT")
    finally:
        a.cleanup()
        b.cleanup()

    for control in (False, True):
        f = Fixture(work, "record-substitution" + ("-restored" if control else "-mutant"))
        try:
            f.open()
            if not control:
                f.prefix.store.records["graph2"]["name"] = "graph3"
            f.read()
            attachment = f.finish()
            if not control and f.prefix.owner.failure != "OBSERVATION_ATTRIBUTION_FAILED:ValueError":
                raise AssertionError("RECORD_MUTANT_REJECTED_AT_WRONG_EDGE")
            record("record-substitution" + ("-restored" if control else "-mutant"),
                   f, attachment, "COMPLETE" if control else "INCOMPLETE",
                   {"owner_failure": f.prefix.owner.failure})
        finally:
            f.cleanup()

    f = Fixture(work, "real-synthetic-pread-vs-direct-baseline")
    try:
        f.open()
        baseline = []
        for ordinal in (2, 3, 4, 5, 6):
            descriptor = f.descriptors[ordinal - 2]
            for purpose, offset in (("NUMERICAL_PAYLOAD", 0), ("FORMAT_PROBE", 128)):
                raw = f.original_pread(descriptor, 16, offset)
                baseline.append({"shard_ordinal": ordinal, "requested_bytes": 16,
                    "offset": offset, "purpose": purpose, "outcome": "RETURN", "returned_hex": raw.hex()})
        f.mode = "real-pread"
        returned = []
        for ordinal in (2, 3, 4, 5, 6):
            returned.append(f.read("graph" + str(ordinal)).hex())
            returned.append(f.read("probe" + str(ordinal)).hex())
        if baseline != f.transcript or returned != [item["returned_hex"] for item in baseline]:
            raise AssertionError("REAL_PREAD_BASELINE_BYTES_ORDER_OR_REQUEST_MISMATCH")
        record("real-synthetic-pread-vs-direct-baseline", f, f.finish(), "COMPLETE",
               {"direct_baseline_transcript": baseline, "actual_pread_calls": len(baseline) + len(f.transcript),
                "storage_faults_or_physical_bytes": "NOT_MEASURABLE",
                "baseline_scope": "DIRECT_POSITIONAL_READ_ONLY_NOT_NUMPY_OR_NUMERICAL_GRAPH"})
    finally:
        f.cleanup()

    report = {"schema": "pulsarmlx.secondary-descriptor-cases/1", "result": "PASS", "cases": results,
        "scope": "STDLIB_SECONDARY_DESCRIPTOR_TO_PREFIX_ONLY", "numerical_decode": "NOT_RUN_NOT_QUALIFIED",
        "full_wrapper_numerical_composition": "NOT_QUALIFIED", "native_full_forward_P1": "NOT_QUALIFIED"}
    raw = canonical(report)
    if len(raw) > 1048576:
        raise ValueError("FINITE_CASE_REPORT_BOUND")
    (Path(work) / "secondary-cases.json").write_bytes(raw)
    return {"result": "PASS", "case_count": len(results), "report": "secondary-cases.json",
        "report_bytes": len(raw), "report_sha256": hashlib.sha256(raw).hexdigest(),
        "scope": report["scope"], "numerical_decode": report["numerical_decode"]}
