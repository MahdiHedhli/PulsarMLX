"""Primary-only API observations, not execution or result authority.

The fixed append-only format prioritizes small synthetic qualification, not
production overhead. An intent is not a known API call. Only a durable return
or error resolves it; interrupted suffixes and persistence failures are unknown.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

from f017_descriptor_lease_manager_v10 import validate_descriptors

__all__: tuple[str, ...] = ()
LIMIT = 32768
VOCABULARY_SHA256 = "9974e6531377b16398fc65d433e923789c757b21c3223d2454bd83bf0297ff43"
DIRECTORY = "primary-read-observations"
RECEIPT = "observation-receipt.json"
TERMINAL = "observation-terminal.json"
FIELDS = ("attempts", "requested_bytes", "successful_returns", "error_returns",
          "short_returns", "zero_returns", "returned_bytes")
PURPOSES = ("FORMAT_PROBE", "NUMERICAL_PAYLOAD")
BINDINGS = ("role", "package_attempt_id", "consumer_event_id",
            "producer_measurement_sha256", "vocabulary_sha256",
            "measurement_implementation_sha256", "descriptor_set_sha256")


def _canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _encode_record(value):
    raw = _canonical(value)
    if len(raw) > LIMIT:
        raise ValueError("MEASUREMENT_SERIALIZATION_OVERFLOW")
    return raw


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _implementation_sha():
    parent = Path(__file__).resolve().parent
    names = ("f017_primary_read_observation_v1.py",
             "f017_corrected_oracle_primary_target_source_v10.py",
             "f017_corrected_oracle_primary_target_source_v11.py",
             "f017_corrected_oracle_primary_wrapper_v11.py")
    return _sha(_canonical({name: _sha((parent / name).read_bytes()) for name in names}))


def _rows():
    return [{"shard_ordinal": shard, "purpose": purpose, **dict.fromkeys(FIELDS, 0)}
            for shard in range(2, 7) for purpose in PURPOSES]


def _copy_rows(rows):
    return [dict(row) for row in rows]


def _exact(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(_exact(left[key], right[key]) for key in left)
    if type(left) is list:
        return len(left) == len(right) and all(_exact(a, b) for a, b in zip(left, right, strict=True))
    return left == right


def _parse(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("DUPLICATE_OBSERVATION_KEY")
            value[key] = item
        return value
    def constant(_value):
        raise ValueError("NONFINITE_OBSERVATION")
    if len(raw) > LIMIT:
        raise ValueError("MEASUREMENT_RECORD_BOUND")
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    if _canonical(value) != raw:
        raise ValueError("NONCANONICAL_OBSERVATION")
    return value


def _read_record(directory_fd, leaf):
    fd = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                or before.st_uid != os.getuid() or before.st_size > LIMIT):
            raise ValueError("OBSERVATION_FILE_IDENTITY")
        raw = os.read(fd, LIMIT + 1)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or len(raw) != before.st_size:
            raise ValueError("OBSERVATION_READBACK_IDENTITY")
        return raw
    finally:
        os.close(fd)


def _bank_record(directory_fd, leaf, value):
    """Actual fixed measurement writer; fault tests may replace OS operations."""
    raw = _encode_record(value)  # Size refusal precedes exclusive creation.
    fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    try:
        offset = 0
        while offset < len(raw):
            count = os.write(fd, raw[offset:])
            if count <= 0:
                raise OSError("MEASUREMENT_SHORT_WRITE")
            offset += count
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory_fd)
    if _read_record(directory_fd, leaf) != raw:
        raise ValueError("MEASUREMENT_READBACK_MISMATCH")
    return _sha(raw)


def _missing(failure="OBSERVATION_OWNER_ABSENT_OR_INVALID"):
    return {"schema": "pulsarmlx.f017.primary-read-observation-attachment/1.0.0",
            "role": "PRIMARY", "package_attempt_id": None, "consumer_event_id": None,
            "producer_measurement_sha256": None, "vocabulary_sha256": VOCABULARY_SHA256,
            "measurement_implementation_sha256": None, "descriptor_set_sha256": None,
            "completeness": "INCOMPLETE", "measurement_failure": failure,
            "last_durable_boundary": None, "unknown_suffix": True,
            "totals": None, "validated_prefix_counters": [],
            "receipt_sha256": None, "terminal_sha256": None}


class _PrimaryObservation:
    def __init__(self, candidate, identities, directory, authority):
        self.binding = {}; self.identities = []; self.directory_fd = None
        self.counters = _rows(); self.pending = None; self.entered = False
        self.sequence = 0; self.last = None; self.last_record = None
        self.failure = None; self.finished = False; self.stage = "FACTORY"
        self.receipt_sha = None; self.terminal_sha = None
        self.source = None; self.records = {}; self.catalog_identity = None
        try:
            validate_descriptors(identities)
            for key in ("package_attempt_id", "consumer_event_id"):
                value = authority[key]
                if type(value) is not str or re.fullmatch(r"[A-Z0-9][A-Z0-9-]{0,127}", value) is None:
                    raise ValueError("OBSERVATION_ATTEMPT_IDENTITY")
            if (candidate.get("package_attempt_id") != authority["package_attempt_id"]
                    or candidate.get("primary_event_id") != authority["consumer_event_id"]):
                raise ValueError("OBSERVATION_EXECUTOR_CONTEXT_MISMATCH")
            measured = authority["producer_measurement_sha256"]
            if type(measured) is not str or re.fullmatch(r"[0-9a-f]{64}", measured) is None:
                raise ValueError("OBSERVATION_MEASUREMENT_IDENTITY")
            catalog_path = candidate["tensor_catalog_path"]
            catalog_sha = candidate["tensor_catalog_sha256"]
            if (type(catalog_path) is not str or not Path(catalog_path).is_absolute()
                    or type(catalog_sha) is not str or re.fullmatch(r"[0-9a-f]{64}", catalog_sha) is None):
                raise ValueError("OBSERVATION_CATALOG_IDENTITY")
            self.catalog_identity = (catalog_path, catalog_sha)
            self.identities = [dict(item) for item in identities]
            self.binding = {"role": "PRIMARY", "package_attempt_id": authority["package_attempt_id"],
                "consumer_event_id": authority["consumer_event_id"],
                "producer_measurement_sha256": measured, "vocabulary_sha256": VOCABULARY_SHA256,
                "measurement_implementation_sha256": _implementation_sha(),
                "descriptor_set_sha256": _sha(_canonical(self.identities))}
            if not isinstance(directory, Path) or not directory.is_absolute():
                raise ValueError("OBSERVATION_EXECUTOR_DIRECTORY")
            directory.mkdir(parents=True, exist_ok=True)
            if directory.resolve(strict=True) != directory or directory.is_symlink():
                raise ValueError("OBSERVATION_DIRECTORY_ALIAS")
            parent_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.mkdir(DIRECTORY, 0o700, dir_fd=parent_fd)
                os.fsync(parent_fd)
                self.directory_fd = os.open(DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                            dir_fd=parent_fd)
            finally:
                os.close(parent_fd)
            self._persist("OWNER_STARTED")
        except Exception as exc:
            self._fail("OWNER_INITIALIZATION_FAILED:" + type(exc).__name__)

    def _fail(self, reason):
        if self.failure is None:
            self.failure = reason

    def _persist(self, boundary):
        if self.failure is not None or self.directory_fd is None or self.finished:
            return
        try:
            record = {"schema": "pulsarmlx.f017.primary-read-observation-record/1.0.0",
                      **self.binding, "sequence": self.sequence + 1,
                      "previous_sha256": None if self.last is None else self.last["sha256"],
                      "boundary": boundary, "counters": _copy_rows(self.counters),
                      "pending": None if self.pending is None else dict(self.pending)}
            digest = _bank_record(self.directory_fd, f"record-{self.sequence + 1:08d}.json", record)
            self.sequence += 1
            self.last = {"sequence": self.sequence, "sha256": digest, "boundary": boundary}
            self.last_record = record
        except Exception as exc:
            self._fail("OBSERVATION_PERSISTENCE_FAILED:" + type(exc).__name__)

    def bind(self, source, candidate, identities):
        try:
            if (candidate.get("package_attempt_id") != self.binding["package_attempt_id"]
                    or candidate.get("primary_event_id") != self.binding["consumer_event_id"]
                    or identities != self.identities or self.source is not None
                    or (candidate.get("tensor_catalog_path"), candidate.get("tensor_catalog_sha256")) != self.catalog_identity):
                raise ValueError("OBSERVATION_SOURCE_CONTEXT")
            self.source = source
            self.records = {name: (record, _sha(_canonical(record)), record["shard_ordinal"],
                                  "FORMAT_PROBE" if record["purpose"] == "FORMAT_PROBE" else "NUMERICAL_PAYLOAD")
                            for name, record in source.records.items()}
        except Exception as exc:
            self._fail("OBSERVATION_SOURCE_BINDING_FAILED:" + type(exc).__name__)

    def intent(self, source, record, identity, requested):
        if self.failure is not None or self.finished:
            return None
        try:
            known, digest, ordinal, purpose = self.records[record["name"]]
            if (source is not self.source or record is not known or _sha(_canonical(record)) != digest
                    or identity != self.identities[ordinal - 2] or self.pending is not None
                    or type(requested) is not int or requested < 0):
                raise ValueError("OBSERVATION_READ_ATTRIBUTION")
            self.pending = {"shard_ordinal": ordinal, "purpose": purpose, "requested_bytes": requested}
            self._persist("READ_INTENT")
            return self.sequence if self.failure is None else None
        except Exception as exc:
            self._fail("OBSERVATION_ATTRIBUTION_FAILED:" + type(exc).__name__)
            return None

    def enter(self, ticket):
        if ticket is None or self.failure is not None:
            return
        try:
            if ticket != self.sequence or self.pending is None or self.entered:
                raise ValueError("OBSERVATION_CALL_TICKET")
            row = self.counters[(self.pending["shard_ordinal"] - 2) * 2 + PURPOSES.index(self.pending["purpose"])]
            row["attempts"] += 1; row["requested_bytes"] += self.pending["requested_bytes"]
            self.entered = True  # Memory-only until a known return/error.
        except Exception as exc:
            self._fail("OBSERVATION_CALL_ENTRY_FAILED:" + type(exc).__name__)

    def complete(self, ticket, returned=None):
        if ticket is None or self.failure is not None:
            return
        try:
            if ticket != self.sequence or self.pending is None or not self.entered:
                raise ValueError("OBSERVATION_RETURN_TICKET")
            row = self.counters[(self.pending["shard_ordinal"] - 2) * 2 + PURPOSES.index(self.pending["purpose"])]
            if returned is None:
                row["error_returns"] += 1; boundary = "READ_ERROR"
            else:
                if type(returned) is not int or not 0 <= returned <= self.pending["requested_bytes"]:
                    raise ValueError("OBSERVATION_RETURN_LENGTH")
                row["successful_returns"] += 1; row["returned_bytes"] += returned
                row["short_returns"] += int(returned < self.pending["requested_bytes"])
                row["zero_returns"] += int(returned == 0); boundary = "READ_RETURN"
            self.pending = None; self.entered = False
            self._persist(boundary)
        except Exception as exc:
            self._fail("OBSERVATION_RETURN_FAILED:" + type(exc).__name__)

    def phase(self, stage):
        self.stage = stage
        self._persist("PHASE_" + stage)

    def attachment(self):
        result = _missing(self.failure)
        result.update(self.binding)
        result["last_durable_boundary"] = None if self.last is None else dict(self.last)
        result["validated_prefix_counters"] = [] if self.last_record is None else _copy_rows(self.last_record["counters"])
        complete = (self.finished and self.failure is None and self.pending is None
                    and self.receipt_sha is not None and self.terminal_sha is not None)
        result.update(completeness="COMPLETE" if complete else "INCOMPLETE", unknown_suffix=not complete,
                      totals=_copy_rows(self.counters) if complete else None,
                      receipt_sha256=self.receipt_sha, terminal_sha256=self.terminal_sha)
        return result

    def finish(self, outcome, stage):
        if self.finished:
            return self.attachment()
        try:
            if outcome not in {"RETURNED", "RAISED"} or stage not in {"FACTORY", "CORE", "BANK", "COMPLETE"}:
                self._fail("OBSERVATION_FINAL_OUTCOME_OR_STAGE")
            if self.source is not None and getattr(self.source, "_observation_owner", None) is not self:
                self._fail("OBSERVATION_SOURCE_OWNER_LOST_OR_REPLACED")
            if self.pending is not None:
                self._fail("OBSERVATION_PENDING_CALL_OR_RETURN_UNKNOWN")
            self._persist("OWNER_FINISHED")
            complete = self.failure is None and self.pending is None and self.last is not None
            receipt = {"schema": "pulsarmlx.f017.primary-read-observation-receipt/1.0.0", **self.binding,
                "numerical_outcome": outcome, "diagnostic_stage": stage,
                "completeness": "COMPLETE" if complete else "INCOMPLETE", "unknown_suffix": not complete,
                "measurement_failure": self.failure, "last_durable_boundary": self.last,
                "totals": _copy_rows(self.counters) if complete else None,
                "validated_prefix_counters": [] if self.last_record is None else _copy_rows(self.last_record["counters"])}
            if self.directory_fd is not None:
                self.receipt_sha = _bank_record(self.directory_fd, RECEIPT, receipt)
                terminal = {"schema": "pulsarmlx.f017.primary-read-observation-terminal/1.0.0",
                            **self.binding, "receipt_sha256": self.receipt_sha,
                            "last_durable_boundary": self.last, "completeness": receipt["completeness"]}
                self.terminal_sha = _bank_record(self.directory_fd, TERMINAL, terminal)
        except Exception as exc:
            self._fail("OBSERVATION_CLOSURE_FAILED:" + type(exc).__name__)
        finally:
            self.finished = True
            if self.directory_fd is not None:
                try:
                    os.close(self.directory_fd)
                except OSError:
                    self._fail("OBSERVATION_DIRECTORY_CLOSE_FAILED")
                self.directory_fd = None
        return self.attachment()


def _start_primary_observation(candidate, identities, directory, authority):
    return _PrimaryObservation(candidate, identities, directory, authority)


def _bind_primary_observation(owner, source, candidate, identities):
    if type(owner) is _PrimaryObservation:
        owner.bind(source, candidate, identities)
        return owner
    return None


def _finish_primary_observation(owner, outcome, stage):
    return owner.finish(outcome, stage) if type(owner) is _PrimaryObservation else _missing()


def _primary_observation_stage(owner):
    if type(owner) is _PrimaryObservation and owner.stage in {"FACTORY", "CORE", "BANK", "COMPLETE"}:
        return owner.stage
    return "FACTORY"


def _primary_observation_attachment(owner):
    return owner.attachment() if type(owner) is _PrimaryObservation else _missing()


def _phase_primary_observation(source, stage):
    owner = getattr(source, "_observation_owner", None)
    if type(owner) is _PrimaryObservation:
        owner.phase(stage)


def _read_intent(owner, source, record, identity, requested):
    return owner.intent(source, record, identity, requested) if type(owner) is _PrimaryObservation else None


def _read_enter(owner, ticket):
    if type(owner) is _PrimaryObservation:
        owner.enter(ticket)


def _read_return(owner, ticket, returned):
    if type(owner) is _PrimaryObservation:
        owner.complete(ticket, returned)


def _read_error(owner, ticket):
    if type(owner) is _PrimaryObservation:
        owner.complete(ticket)


def _validate_rows(rows):
    if type(rows) is not list or len(rows) != 10:
        raise ValueError("OBSERVATION_COUNTER_CENSUS")
    for got, expected in zip(rows, _rows(), strict=True):
        if (type(got) is not dict or set(got) != set(expected)
                or got["shard_ordinal"] != expected["shard_ordinal"] or got["purpose"] != expected["purpose"]
                or any(type(got[key]) is not int or got[key] < 0 for key in FIELDS)
                or type(got["shard_ordinal"]) is not int
                or got["attempts"] != got["successful_returns"] + got["error_returns"]
                or got["short_returns"] > got["successful_returns"]
                or got["zero_returns"] > got["successful_returns"]
                or got["returned_bytes"] > got["requested_bytes"]):
            raise ValueError("OBSERVATION_COUNTER_VALUE")


def _transition(previous, record):
    _validate_rows(record["counters"])
    before = _rows() if previous is None else _copy_rows(previous["counters"])
    pending = None if previous is None else previous["pending"]
    boundary = record["boundary"]
    if previous is None:
        if boundary != "OWNER_STARTED" or record["pending"] is not None or record["counters"] != before:
            raise ValueError("OBSERVATION_INITIAL_RECORD")
        return
    if previous["boundary"] == "OWNER_FINISHED":
        raise ValueError("OBSERVATION_AFTER_FINISH")
    if boundary == "READ_INTENT":
        item = record["pending"]
        if (pending is not None or type(item) is not dict
                or set(item) != {"shard_ordinal", "purpose", "requested_bytes"}
                or type(item["shard_ordinal"]) is not int or item["shard_ordinal"] not in range(2, 7)
                or item["purpose"] not in PURPOSES or type(item["requested_bytes"]) is not int
                or item["requested_bytes"] < 0 or record["counters"] != before):
            raise ValueError("OBSERVATION_INTENT_TRANSITION")
    elif boundary in {"READ_RETURN", "READ_ERROR"}:
        if pending is None or record["pending"] is not None:
            raise ValueError("OBSERVATION_COMPLETION_WITHOUT_INTENT")
        index = (pending["shard_ordinal"] - 2) * 2 + PURPOSES.index(pending["purpose"])
        row = before[index]; observed = record["counters"][index]
        row["attempts"] += 1; row["requested_bytes"] += pending["requested_bytes"]
        if boundary == "READ_ERROR":
            row["error_returns"] += 1
        else:
            returned = observed["returned_bytes"] - row["returned_bytes"]
            if not 0 <= returned <= pending["requested_bytes"]:
                raise ValueError("OBSERVATION_RETURN_DELTA")
            row["successful_returns"] += 1; row["returned_bytes"] += returned
            row["short_returns"] += int(returned < pending["requested_bytes"])
            row["zero_returns"] += int(returned == 0)
        if record["counters"] != before:
            raise ValueError("OBSERVATION_COUNTER_TRANSITION")
    elif boundary in {"PHASE_CORE", "PHASE_CORE_COMPLETE", "PHASE_BANK", "OWNER_FINISHED"}:
        if record["counters"] != before or record["pending"] != pending:
            raise ValueError("OBSERVATION_PHASE_TRANSITION")
    else:
        raise ValueError("OBSERVATION_BOUNDARY")


def _read_closure(directory_fd, binding):
    receipt_raw = _read_record(directory_fd, RECEIPT); receipt = _parse(receipt_raw)
    terminal_raw = _read_record(directory_fd, TERMINAL); terminal = _parse(terminal_raw)
    receipt_keys = {"schema", *BINDINGS, "numerical_outcome", "diagnostic_stage", "completeness",
                    "unknown_suffix", "measurement_failure", "last_durable_boundary", "totals", "validated_prefix_counters"}
    terminal_keys = {"schema", *BINDINGS, "receipt_sha256", "last_durable_boundary", "completeness"}
    if (type(receipt) is not dict or set(receipt) != receipt_keys
            or type(terminal) is not dict or set(terminal) != terminal_keys
            or receipt["schema"] != "pulsarmlx.f017.primary-read-observation-receipt/1.0.0"
            or terminal["schema"] != "pulsarmlx.f017.primary-read-observation-terminal/1.0.0"
            or any(not _exact(receipt[key], binding[key]) or not _exact(terminal[key], binding[key]) for key in BINDINGS)
            or not _exact(receipt["last_durable_boundary"], terminal["last_durable_boundary"])
            or terminal["receipt_sha256"] != _sha(receipt_raw)
            or terminal["completeness"] != receipt["completeness"]
            or receipt["numerical_outcome"] not in {"RETURNED", "RAISED"}
            or receipt["diagnostic_stage"] not in {"FACTORY", "CORE", "BANK", "COMPLETE"}):
        raise ValueError("OBSERVATION_RECEIPT_TERMINAL_BINDING")
    if receipt["completeness"] == "COMPLETE":
        if receipt["unknown_suffix"] is not False or receipt["measurement_failure"] is not None:
            raise ValueError("OBSERVATION_FALSE_COMPLETE")
    elif (receipt["completeness"] != "INCOMPLETE" or receipt["unknown_suffix"] is not True
          or receipt["totals"] is not None or type(receipt["measurement_failure"]) is not str
          or not receipt["measurement_failure"]):
        raise ValueError("OBSERVATION_INCOMPLETE_TOTALS")
    return receipt, _sha(receipt_raw), _sha(terminal_raw)


def _read_primary_observation(directory, expected):
    """Validate a writer-confirmed prefix, not the physically present last file.

    A closure may anchor an earlier prefix than a fully written failed suffix.
    Without usable closure, a valid successor confirms its predecessor only:
    the writer cannot advance previous_sha256 before that predecessor's bank
    succeeds. The unconfirmed tail is never promoted to a durable boundary.

    COMPLETE here validates the closure bytes, not an unobservable final
    terminal fsync/readback outcome. Durability qualification also requires
    the original live owner attachment to be COMPLETE with identical binding,
    receipt, terminal, and prefix. Readback must not upgrade an INCOMPLETE owner.
    """
    result = _missing("OBSERVATION_CLOSURE_UNAVAILABLE")
    fd = None; last = None; previous = None; sequence = 1
    confirmed_last = None; confirmed_record = None; anchored_record = None
    closure = None; closure_error = None; scan_error = None
    try:
        expected_keys = {"package_attempt_id", "consumer_event_id", "producer_measurement_sha256", "descriptor_set_sha256"}
        if (type(expected) is not dict or set(expected) != expected_keys
                or any(type(expected[key]) is not str for key in expected_keys)):
            raise ValueError("OBSERVATION_EXPECTED_CONTEXT_CENSUS")
        for key in ("producer_measurement_sha256", "descriptor_set_sha256"):
            if re.fullmatch(r"[0-9a-f]{64}", expected[key]) is None:
                raise ValueError("OBSERVATION_DIGEST")
        binding = {**expected, "role": "PRIMARY", "vocabulary_sha256": VOCABULARY_SHA256,
                   "measurement_implementation_sha256": _implementation_sha()}
        fd = os.open(Path(directory) / DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            closure = _read_closure(fd, binding)
        except Exception as exc:
            closure_error = exc
        while True:
            try:
                raw = _read_record(fd, f"record-{sequence:08d}.json")
                record = _parse(raw)
                keys = {"schema", *BINDINGS, "sequence", "previous_sha256", "boundary", "counters", "pending"}
                if (type(record) is not dict or set(record) != keys
                        or record["schema"] != "pulsarmlx.f017.primary-read-observation-record/1.0.0"
                        or type(record["sequence"]) is not int or record["sequence"] != sequence
                        or record["previous_sha256"] != (None if last is None else last["sha256"])):
                    raise ValueError("OBSERVATION_RECORD_CHAIN")
                if any(not _exact(record[key], binding[key]) for key in BINDINGS):
                    raise ValueError("OBSERVATION_EXPECTED_BINDING")
                _transition(previous, record)
                confirmed_last, confirmed_record = last, previous
                previous = record
                last = {"sequence": sequence, "sha256": _sha(raw), "boundary": record["boundary"]}
                if closure is not None and _exact(closure[0]["last_durable_boundary"], last):
                    anchored_record = record
                result.update(binding)
                sequence += 1
            except FileNotFoundError:
                break
            except Exception as exc:
                scan_error = exc
                break
        if confirmed_record is not None:
            result["last_durable_boundary"] = dict(confirmed_last)
            result["validated_prefix_counters"] = _copy_rows(confirmed_record["counters"])
        if closure is None:
            raise closure_error
        receipt, receipt_sha, terminal_sha = closure
        anchor = receipt["last_durable_boundary"]
        if anchor is None:
            if receipt["completeness"] != "INCOMPLETE" or not _exact(receipt["validated_prefix_counters"], []):
                raise ValueError("OBSERVATION_PREFIX_ABSENT")
            prefix = []
        else:
            if anchored_record is None or not _exact(receipt["validated_prefix_counters"], anchored_record["counters"]):
                raise ValueError("OBSERVATION_RECEIPT_PREFIX_ANCHOR")
            prefix = _copy_rows(anchored_record["counters"])
        complete = receipt["completeness"] == "COMPLETE"
        if complete and (anchored_record is None or anchored_record["boundary"] != "OWNER_FINISHED"
                         or anchored_record["pending"] is not None or not _exact(anchor, last)
                         or not _exact(receipt["totals"], prefix)):
            raise ValueError("OBSERVATION_FALSE_COMPLETE")
        # Select the exact closure anchor before rejecting a torn/orphan suffix.
        # This may intentionally retreat from the raw scan's apparent frontier.
        result.update(binding, last_durable_boundary=None if anchor is None else dict(anchor),
                      validated_prefix_counters=prefix, receipt_sha256=receipt_sha,
                      terminal_sha256=terminal_sha)
        if scan_error is not None:
            raise scan_error
        expected_leaves = {f"record-{index:08d}.json" for index in range(1, sequence)} | {RECEIPT, TERMINAL}
        if set(os.listdir(fd)) != expected_leaves:
            raise ValueError("OBSERVATION_LEAF_CENSUS_OR_ORPHAN")
        result.update(completeness=receipt["completeness"], unknown_suffix=not complete,
                      measurement_failure=receipt["measurement_failure"],
                      totals=_copy_rows(prefix) if complete else None)
    except Exception as exc:
        result.update(completeness="INCOMPLETE", unknown_suffix=True, totals=None,
                      measurement_failure="OBSERVATION_READBACK_FAILED:" + type(exc).__name__)
    finally:
        if fd is not None:
            os.close(fd)
    return result
